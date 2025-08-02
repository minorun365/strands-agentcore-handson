import os, asyncio, boto3, json, uuid
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.title("Strands on AgentCore")
st.write("何でも聞いてね！")

if arn := st.text_input("👇 AgentCoreランタイムのARNを入力", key="arn"):
    os.environ['AGENT_RUNTIME_ARN'] = arn

agent_core = boto3.client('bedrock-agentcore')

if prompt := st.chat_input("メッセージを入力してね"):
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("考え中…"):
            response = agent_core.invoke_agent_runtime(
                agentRuntimeArn=os.getenv("AGENT_RUNTIME_ARN"),
                payload=json.dumps({"prompt": prompt}),
                qualifier="DEFAULT"
            )
            response_body = response["response"].read()
            response_data = json.loads(response_body.decode('utf-8'))
        
        st.write(response_data["result"]["content"][0]["text"])