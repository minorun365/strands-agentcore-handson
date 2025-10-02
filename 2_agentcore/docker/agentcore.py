# 必要なライブラリをインポート
from strands import Agent
from strands.tools.mcp.mcp_client import MCPClient
from mcp.client.streamable_http import streamablehttp_client
from bedrock_agentcore.runtime import BedrockAgentCoreApp

# AgentCoreのサーバーを作成
app = BedrockAgentCoreApp()

# エージェント呼び出し関数を、AgentCoreの開始点に設定（ストリーミング対応）
@app.entrypoint
async def invoke_agent(payload, context):

    # ペイロードからプロンプトとAPIキーを取得
    prompt = payload.get("prompt")
    tavily_api_key = payload.get("tavily_api_key")

    # MCPクライアントを作成（リクエストごとにAPIキーを使用）
    mcp = MCPClient(lambda: streamablehttp_client(
        f"https://mcp.tavily.com/mcp/?tavilyApiKey={tavily_api_key}"
    ))

    # MCPクライアントを起動してエージェントを作成・実行
    with mcp:
        agent = Agent(
            model="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
            tools=mcp.list_tools_sync()
        )

        # エージェントをストリーミングで呼び出してイベントをyieldで返却
        stream = agent.stream_async(prompt)
        async for event in stream:
            yield event

# AgentCoreサーバーを起動
app.run()