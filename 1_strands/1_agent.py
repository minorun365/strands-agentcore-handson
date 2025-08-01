# 必要なライブラリをインポート
from dotenv import load_dotenv
from strands import Agent

# .envファイルから環境変数を読み込む
load_dotenv()

# エージェントを作成して起動
agent = Agent("us.anthropic.claude-3-7-sonnet-20250219-v1:0")
agent("KAGってどんな会社？")