import asyncio, os
from strands import Agent, tool
from strands.tools.mcp import MCPClient
from mcp import stdio_client, StdioServerParameters
from mcp.client.streamable_http import streamablehttp_client
from bedrock_agentcore.runtime import BedrockAgentCoreApp

app = BedrockAgentCoreApp()
states = {"kb": {"client": None, "queue": None}, "api": {"client": None, "queue": None}}

async def send_event(queue, message, stage, tool_name=None):
    if queue:
        progress = {"message": message, "stage": stage}
        if tool_name: progress["tool_name"] = tool_name
        await queue.put({"event": {"subAgentProgress": progress}})

async def merge_streams(stream, queue):
    main = asyncio.create_task(anext(stream, None))
    sub = asyncio.create_task(queue.get())
    waiting = {main, sub}
    
    while waiting:
        ready, waiting = await asyncio.wait(waiting, return_when=asyncio.FIRST_COMPLETED)
        for chunk in ready:
            if chunk == main:
                if (event := chunk.result()) is not None:
                    yield event
                    waiting.add(main := asyncio.create_task(anext(stream, None)))
                else: main = None
            elif chunk == sub:
                try:
                    yield chunk.result()
                    waiting.add(sub := asyncio.create_task(queue.get()))
                except: sub = None
        if main is None and queue.empty(): break

async def extract_stream(queue, agent, event, state):
    if isinstance(event, str):
        state["text"] += event
        if queue: await queue.put({"event": {"contentBlockDelta": {"delta": {"text": event}}}})
    elif isinstance(event, dict) and "event" in event:
        event_data = event["event"]
        if "contentBlockStart" in event_data:
            if tool_use := event_data.get("contentBlockStart", {}).get("start", {}).get("toolUse"):
                await send_event(queue, f"「{agent}」がツール「{tool_use.get('name', 'unknown')}」を実行中", "tool_use", tool_use.get("name"))
        if delta := event_data.get("contentBlockDelta", {}).get("delta", {}).get("text"):
            state["text"] += delta
        if queue: await queue.put(event)

async def invoke_agent(agent, query, mcp, create_agent, queue):
    state = {"text": ""}
    await send_event(queue, f"サブエージェント「{agent}」が呼び出されました", "start")
    try:
        with mcp:
            async for event in create_agent().stream_async(query):
                await extract_stream(queue, agent, event, state)
        await send_event(queue, f"「{agent}」が対応を完了しました", "complete")
        return state["text"]
    except: return f"{agent}エージェントの処理に失敗しました"

def setup_mcp(key, queue, client_fn):
    states[key]["queue"] = queue
    if queue and not states[key]["client"]:
        try: states[key]["client"] = MCPClient(client_fn)
        except: states[key]["client"] = None

@tool
async def aws_kb_agent(query):
    """AWSナレッジエージェント"""
    if not states["kb"]["client"]: return "AWSナレッジMCPクライアントが利用不可です"
    return await invoke_agent("AWSナレッジ", query, states["kb"]["client"],
        lambda: Agent(model="us.anthropic.claude-3-7-sonnet-20250219-v1:0", tools=states["kb"]["client"].list_tools_sync()),
        states["kb"]["queue"])

@tool  
async def aws_api_agent(query):
    """AWS APIエージェント"""
    if not states["api"]["client"]: return "AWS API MCPクライアントが利用不可です"
    return await invoke_agent("AWS API", query, states["api"]["client"],
        lambda: Agent(model="us.anthropic.claude-3-7-sonnet-20250219-v1:0", tools=states["api"]["client"].list_tools_sync()),
        states["api"]["queue"])

@app.entrypoint
async def invoke(payload):
    prompt = payload.get("input", {}).get("prompt", "")
    queue = asyncio.Queue()
    
    setup_mcp("kb", queue, lambda: streamablehttp_client("https://knowledge-mcp.global.api.aws"))
    env = os.environ.copy()
    env["READ_OPERATIONS_ONLY"] = "true"
    setup_mcp("api", queue, lambda: stdio_client(StdioServerParameters(command="python", args=["-m", "awslabs.aws_api_mcp_server.server"], env=env)))
    
    try:
        orchestrator = Agent(
            model="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
            tools=[aws_kb_agent, aws_api_agent],
            system_prompt="""2つのサブエージェントを使えます。
1. AWSナレッジエージェント: AWSドキュメント等から情報を検索
2. AWS APIエージェント: AWSアカウントをAPI操作
API操作を行う前に、必ずAWSナレッジで情報収集してください。""")
        
        async for event in merge_streams(orchestrator.stream_async(prompt), queue):
            yield event
    finally:
        setup_mcp("kb", None, None)
        setup_mcp("api", None, None)

if __name__ == "__main__":
    app.run()