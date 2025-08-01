import os, asyncio, boto3, json, uuid
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.title("エージェント構築の家庭教師")
st.write("StrandsやAgentCoreのことは何でも聞いてね！")

if arn := st.text_input("👇 AgentCoreランタイムのARNを入力", key="arn"):
    os.environ['AGENT_RUNTIME_ARN'] = arn

if 'messages' not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

agent_core = boto3.client('bedrock-agentcore')

def update_status(container, state, message, stage="processing"):
    if state["current_status"]:
        state["current_status"][0].status(state["current_status"][1], state="complete")
    with container:
        new_status = st.empty()
        new_status.status(message, state="complete" if stage == "complete" else "running")
    state["containers"].append((new_status, message))
    state["current_status"] = (new_status, message)
    state["current_text"] = None

def handle_stream(data, container, state):
    if not isinstance(data, dict):
        return
    
    event = data.get("event", {})
    if progress := event.get("subAgentProgress"):
        update_status(container, state, progress.get("message"), progress.get("stage"))
    elif delta := event.get("contentBlockDelta", {}).get("delta", {}).get("text"):
        if state["current_text"] is None:
            if state["containers"] and "思考中" in state["containers"][0][1]:
                state["containers"][0][0].status("思考中", state="complete")
            if state["current_status"]:
                state["current_status"][0].status(state["current_status"][1], state="complete")
            with container:
                state["current_text"] = st.empty()
        state["final_response"] += delta
        state["current_text"].markdown(state["final_response"])
    elif error := data.get("error"):
        st.error(f"AgentCoreエラー: {error}")
        state["final_response"] = f"エラー: {error}"

async def invoke_agent(prompt, container):
    state = {"containers": [], "current_status": None, "current_text": None, "final_response": ""}
    session_id = f"session_{uuid.uuid4()}"
    
    with container:
        thinking = st.empty()
        thinking.status("思考中", state="running")
    state["containers"].append((thinking, "思考中"))
    
    try:
        response = agent_core.invoke_agent_runtime(
            agentRuntimeArn=os.getenv("AGENT_RUNTIME_ARN"),
            runtimeSessionId=session_id,
            payload=json.dumps({"input": {"prompt": prompt, "session_id": session_id}}).encode(),
            qualifier="DEFAULT"
        )
        
        for line in response["response"].iter_lines():
            if line and (decoded := line.decode("utf-8")).startswith("data: "):
                try:
                    handle_stream(json.loads(decoded[6:]), container, state)
                except json.JSONDecodeError:
                    pass
        
        for status, msg in state["containers"]:
            status.status(msg, state="complete")
        return state["final_response"]
    except Exception as e:
        st.error(f"エラーが発生しました: {e}")
        return ""

if prompt := st.chat_input("メッセージを入力してね"):
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    with st.chat_message("assistant"):
        if response := asyncio.run(invoke_agent(prompt, st.container())):
            st.session_state.messages.append({"role": "assistant", "content": response})