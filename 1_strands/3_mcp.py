# 必要なライブラリをインポート
from dotenv import load_dotenv
from strands import Agent
from strands.tools.mcp import MCPClient
from mcp import stdio_client, StdioServerParameters

# .envファイルから環境変数を読み込む
load_dotenv()

# MCPクライアントを作成
mcp = MCPClient(lambda: stdio_client(
    StdioServerParameters(
        command="uvx", 
        args=["strands-agents-mcp-server"]
    )
))

# エージェントを呼び出し
with mcp:
    # エージェントを作成
    agent = Agent(
        model="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
        tools=mcp.list_tools_sync()
    )
    agent("StrandsでA2Aサーバーの最小サンプルコードを書いて！")
