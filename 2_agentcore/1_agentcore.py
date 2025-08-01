# 必要なライブラリをインポート
from dotenv import load_dotenv
from strands import Agent
from bedrock_agentcore.runtime import BedrockAgentCoreApp # 追加

# .envファイルから環境変数を読み込む
load_dotenv()

# Strandsでエージェントを作成
agent = Agent("us.anthropic.claude-3-7-sonnet-20250219-v1:0")

# ---------- 以下、追加コード--------------

# AgentCoreのサーバーを作成
app = BedrockAgentCoreApp()

# エージェント呼び出し関数を、AgentCoreの開始点に設定
@app.entrypoint
def invoke_agent(payload, context):

    # リクエストのペイロード（中身）からプロンプトを取得
    prompt = payload.get("prompt")
    
    # エージェントを呼び出してレスポンスを返却
    return {"result": agent(prompt).message}

# AgentCoreサーバーを起動
app.run()