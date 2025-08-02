# 必要なライブラリをインポート
from dotenv import load_dotenv
import os, asyncio, boto3, json, uuid
import streamlit as st

# .envファイルから環境変数をロード
load_dotenv(override=True)

# タイトルを描画
st.title("Strands on AgentCore")
st.write("何でも聞いてね！")

# チャットボックスを描画
if prompt := st.chat_input("メッセージを入力してね"):

    # ユーザーのプロンプトを表示
    with st.chat_message("user"):
        st.markdown(prompt)

    # エージェントの回答を表示
    with st.chat_message("assistant"):

        # AgentCoreランタイムを呼び出し
        with st.spinner("考え中…"):
            agentcore = boto3.client('bedrock-agentcore')
            response = agentcore.invoke_agent_runtime(
                agentRuntimeArn=os.getenv("AGENT_RUNTIME_ARN"),
                payload=json.dumps({"prompt": prompt})
            )

        # 結果のテキストを取り出して表示
        response_body = response["response"].read()
        response_data = json.loads(response_body.decode('utf-8'))
        st.write(response_data["result"]["content"][0]["text"])