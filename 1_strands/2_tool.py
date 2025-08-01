# 必要なライブラリをインポート
from dotenv import load_dotenv
from strands import Agent, tool

# .envファイルから環境変数を読み込む
load_dotenv()

# 文字カウント関数をツールとして定義
@tool
def counter(word: str, letter: str):
    return word.lower().count(letter.lower())

# エージェントを作成
agent = Agent(
    model="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    tools=[counter]
)

# エージェントを呼び出し
agent("Strandsの中にSはいくつある？")