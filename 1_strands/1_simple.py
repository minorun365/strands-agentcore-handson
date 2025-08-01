# 必要なライブラリをインポート
from strands import Agent
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()

# エージェントを作成して起動
agent = Agent("us.anthropic.claude-3-7-sonnet-20250219-v1:0")
agent("Strandsってどういう意味？")