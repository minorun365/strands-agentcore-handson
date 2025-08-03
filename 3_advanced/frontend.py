from dotenv import load_dotenv
import os, json, uuid, asyncio, boto3
import streamlit as st

load_dotenv(override=True)

# =============================================================================
# ストリーミング処理
# =============================================================================

def create_state():
    """新しい状態を作成"""
    return {
        "containers": [],
        "current_status": None,
        "current_text": None,
        "final_response": ""
    }

def think(container, state):
    """思考開始を表示"""
    with container:
        thinking_status = st.empty()
        thinking_status.status("思考中", state="running")
    state["containers"].append((thinking_status, "思考中"))

def change_status(event, container, state):
    """サブエージェントのステータスを更新"""
    progress_info = event["subAgentProgress"]
    message = progress_info.get("message")
    stage = progress_info.get("stage", "processing")
    
    # 前のステータスを完了状態に
    if state["current_status"]:
        status, old_message = state["current_status"]
        status.status(old_message, state="complete")
    
    # 新しいステータス表示
    with container:
        new_status_box = st.empty()
        if stage == "complete":
            display_state = "complete"
        else:
            display_state = "running"
        new_status_box.status(message, state=display_state)
    
    status_info = (new_status_box, message)
    state["containers"].append(status_info)
    state["current_status"] = status_info
    state["current_text"] = None
    state["final_response"] = ""

def stream_text(event, container, state):
    """テキストをストリーミング表示"""
    delta = event["contentBlockDelta"]["delta"]
    if "text" not in delta:
        return
    
    # テキスト出力開始時にステータスを完了に
    if state["current_text"] is None:
        if state["containers"]:
            status, first_message = state["containers"][0]
            if "思考中" in first_message:
                status.status("思考中", state="complete")
        if state["current_status"]:
            status, message = state["current_status"]
            status.status(message, state="complete")
    
    # テキスト処理
    text = delta["text"]
    state["final_response"] += text
    
    # テキストコンテナ更新
    if state["current_text"] is None:
        with container:
            state["current_text"] = st.empty()
    if state["current_text"]:
        response = state["final_response"]
        state["current_text"].markdown(response)

def finish(state):
    """表示の終了処理"""
    if state["current_text"]:
        response = state["final_response"]
        state["current_text"].markdown(response)
    for status, message in state["containers"]:
        status.status(message, state="complete")

# =============================================================================
# サブエージェント呼び出し
# =============================================================================

def extract_stream(data, container, state):
    """ストリーミングから内容を抽出"""
    if not isinstance(data, dict):
        return

    event = data.get("event", {})    
    if "subAgentProgress" in event:
        change_status(event, container, state)
    elif "contentBlockDelta" in event:
        stream_text(event, container, state)
    elif "error" in data:
        error_msg = data.get("error", "Unknown error")
        error_type = data.get("error_type", "Unknown")
        st.error(f"AgentCoreエラー: {error_msg}")
        state["final_response"] = f"エラー: {error_msg}"

async def invoke_agent(prompt, container, agent_core):
    """エージェントを呼び出し"""
    state = create_state()
    session_id = f"session_{str(uuid.uuid4())}"
    think(container, state)
    
    payload = json.dumps({
        "input": {"prompt": prompt, "session_id": session_id}
    }).encode()
    
    try:
        agent_response = agent_core.invoke_agent_runtime(
            agentRuntimeArn=os.getenv("AGENT_RUNTIME_ARN"),
            runtimeSessionId=session_id,
            payload=payload,
            qualifier="DEFAULT"
        )
        for line in agent_response["response"].iter_lines():
            decoded = line.decode("utf-8")
            if not line or not decoded.startswith("data: "):
                continue
            try:
                data = json.loads(decoded[6:])
                extract_stream(data, container, state)
            except json.JSONDecodeError:
                continue
        
        finish(state)
        return state["final_response"]
    
    except Exception as e:
        st.error(f"エラーが発生しました: {e}")
        return ""

# =============================================================================
# メイン画面
# =============================================================================

# タイトル表示
st.title("アマQ Unlimited")
st.write("AWSドキュメントや、あなたのアカウントを調査し放題！")

# セッションを初期化
if 'messages' not in st.session_state:
    st.session_state.messages = []

# メッセージ履歴を表示
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# AgentCore APIクライアントを初期化
agent_core = boto3.client('bedrock-agentcore')

# ユーザー入力を表示
if prompt := st.chat_input("メッセージを入力してね"):
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append(
        {"role": "user", "content": prompt}
    )
    
    # エージェントの応答を表示
    with st.chat_message("assistant"):
        container = st.container()
        try:
            response = asyncio.run(
                invoke_agent(prompt, container, agent_core)
            )
            if response:
                st.session_state.messages.append(
                    {"role": "assistant", "content": response}
                )
        except Exception as e:
            st.error(f"エラーが発生しました: {e}")