# 必要なライブラリをインポート
import requests

# ローカルサーバーにリクエストを実施
response = requests.post(
    url="http://localhost:8080/invocations",
    headers={"Content-Type": "application/json"},
    json={"prompt": "JAWS-UGって何？"}
)

# レスポンスを画面に表示
print(response.json())