import os
import asyncio
from strands import Agent, tool
from strands.tools.mcp import MCPClient
from mcp import stdio_client, StdioServerParameters
from mcp.client.streamable_http import streamablehttp_client
from bedrock_agentcore.runtime import BedrockAgentCoreApp

# =============================================================================
# サブエージェントのストリーミング処理
# =============================================================================

async def send_event(queue, message, stage, tool_name=None):
    """サブエージェントのステータスを送信"""
    if not queue:
        return
    
    progress = {"message": message, "stage": stage}
    if tool_name:
        progress["tool_name"] = tool_name
    await queue.put({"event": {"subAgentProgress": progress}})

async def merge_streams(stream, queue):
    """親子エージェントのストリームを統合"""
    create_task = asyncio.create_task
    main = create_task(anext(stream, None))
    sub = create_task(queue.get())
    waiting = {main, sub}
    
    # チャンクの到着を待機
    while waiting:
        ready_chunks, waiting = await asyncio.wait(
            waiting, return_when=asyncio.FIRST_COMPLETED
        )
        for ready_chunk in ready_chunks:
            # 監督者エージェントのチャンクを処理
            if ready_chunk == main:
                event = ready_chunk.result()
                if event is not None:
                    yield event
                    main = create_task(anext(stream, None))
                    waiting.add(main)
                else:
                    main = None
            
            # サブエージェントのチャンクを処理
            elif ready_chunk == sub:
                try:
                    sub_event = ready_chunk.result()
                    yield sub_event
                    sub = create_task(queue.get())
                    waiting.add(sub)
                except Exception:
                    sub = None
        
        if main is None and queue.empty():
            break

# =============================================================================
# サブエージェントの呼び出し
# =============================================================================

async def _extract(queue, agent, event, state):
    """ストリーミングから内容を抽出"""
    if isinstance(event, str):
        state["text"] += event
        if queue:
            delta = {"delta": {"text": event}}
            await queue.put(
                {"event": {"contentBlockDelta": delta}}
            )
    elif isinstance(event, dict) and "event" in event:
        event_data = event["event"]
        
        # ツール使用を検出
        if "contentBlockStart" in event_data:
            block = event_data["contentBlockStart"]
            start_data = block.get("start", {})
            if "toolUse" in start_data:
                tool_use = start_data["toolUse"]
                tool = tool_use.get("name", "unknown")
                await send_event(queue, 
                    f"「{agent}」がツール「{tool}」を実行中", 
                    "tool_use", tool
                )
        
        # テキスト増分を処理
        if "contentBlockDelta" in event_data:
            block = event_data["contentBlockDelta"]
            delta = block.get("delta", {})
            if "text" in delta:
                state["text"] += delta["text"]
        
        if queue:
            await queue.put(event)

async def invoke_agent(agent, query, mcp, create_agent, queue):
    """サブエージェントを呼び出し"""
    state = {"text": ""}
    await send_event(
        queue, f"サブエージェント「{agent}」が呼び出されました", "start"
    )
    
    try:
        # MCPクライアントを起動しながら、エージェントを呼び出し
        with mcp:
            agent_obj = create_agent()
            async for event in agent_obj.stream_async(query):
                await _extract(queue, agent, event, state)
        
        await send_event(
            queue, f"「{agent}」が対応を完了しました", "complete"
        )
        return state["text"]
    
    except Exception:
        return f"{agent}エージェントの処理に失敗しました"

# =============================================================================
# サブエージェント1: AWSマスター
# =============================================================================

class AwsMasterState:
    def __init__(self):
        self.client = None
        self.queue = None

_aws_state = AwsMasterState()

def setup_aws_master(queue):
    """新規キューを受け取り、MCPクライアントを準備"""
    _aws_state.queue = queue
    if queue and not _aws_state.client:
        try:
            _aws_state.client = MCPClient(
                lambda: streamablehttp_client(
                    "https://knowledge-mcp.global.api.aws"
                )
            )
        except Exception:
            _aws_state.client = None

def _create_aws_agent():
    """AWS知識参照エージェントを作成"""
    if not _aws_state.client:
        return None
    return Agent(
        model="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
        tools=_aws_state.client.list_tools_sync()
    )

@tool
async def aws_master(query):
    """AWSマスターエージェント"""
    if not _aws_state.client:
        return "MCPクライアントが利用不可です"
    return await invoke_agent(
        "AWSマスター", query, _aws_state.client,
        _create_aws_agent, _aws_state.queue
    )

# =============================================================================
# サブエージェント2: APIマスター
# =============================================================================

class ApiMasterState:
    def __init__(self):
        self.client = None
        self.queue = None

_api_state = ApiMasterState()

def setup_api_master(queue):
    """新規キューを受け取り、MCPクライアントを準備"""
    _api_state.queue = queue
    if queue and not _api_state.client:
        try:
            _api_state.client = MCPClient(
                lambda: stdio_client(StdioServerParameters(
                    command="uvx", args=["awslabs.aws-api-mcp-server"],
                    env=os.environ.copy()
                ))
            )
        except Exception:
            _api_state.client = None

def _create_api_agent():
    """API操作エージェントを作成"""
    if not _api_state.client:
        return None
    return Agent(
        model="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
        tools=_api_state.client.list_tools_sync()
    )

@tool
async def api_master(query):
    """APIマスターエージェント"""
    if not _api_state.client:
        return "MCPクライアントが利用不可です"
    return await invoke_agent(
        "APIマスター", query, _api_state.client,
        _create_api_agent, _api_state.queue
    )

# =============================================================================
# メイン処理
# =============================================================================

def _create_orchestrator():
    """監督者エージェントを作成"""
    return Agent(
        model="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
        tools=[aws_master, api_master],
        system_prompt="""2体のサブエージェントを使って日本語で応対して。
1. AWSマスター：AWSドキュメントなどを参照できます。
2. APIマスター：AWSアカウントをAPIで操作できます。
語尾は「〜だQ。」にしてください。"""
    )

# アプリケーションを初期化
app = BedrockAgentCoreApp()
orchestrator = _create_orchestrator()

@app.entrypoint
async def invoke(payload):
    """呼び出し処理の開始地点"""
    prompt = payload.get("input", {}).get("prompt", "")
    
    # サブエージェント用のキューを初期化
    queue = asyncio.Queue()
    setup_aws_master(queue)
    setup_api_master(queue)
    
    try:
        # 監督者エージェントを呼び出し、ストリームを統合
        stream = orchestrator.stream_async(prompt)
        async for event in merge_streams(stream, queue):
            yield event
            
    finally:
        # キューをクリーンアップ
        setup_aws_master(None)
        setup_api_master(None)

# AgentCoreランタイムを起動
if __name__ == "__main__":
    app.run()