"""会话持久化与读取。"""

import json
import os
from datetime import datetime


def generate_session_id():
    return datetime.now().strftime("%Y-%m-%d %H-%M-%S")


def save_session(session_state, sessions_dir="sessions"):
    session_id = session_state.get("session_id")
    if not session_id:
        return
    payload = {
        "session_id": session_id,
        "messages": session_state.get("messages", []),
        "last_conclusion": session_state.get("last_conclusion", ""),
    }
    os.makedirs(sessions_dir, exist_ok=True)
    with open(os.path.join(sessions_dir, f"{session_id}.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load_sessions(sessions_dir="sessions"):
    if not os.path.exists(sessions_dir):
        return []
    out = []
    for filename in os.listdir(sessions_dir):
        if filename.endswith(".json"):
            out.append(filename[:-5])
    out.sort(reverse=True)
    return out


def load_session(session_state, session_name, sessions_dir="sessions"):
    file_path = os.path.join(sessions_dir, f"{session_name}.json")
    if not os.path.exists(file_path):
        return False
    with open(file_path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    session_state["messages"] = payload.get("messages", [])
    session_state["session_id"] = session_name
    session_state["last_conclusion"] = payload.get("last_conclusion", "")
    return True


def delete_session(session_state, session_name, sessions_dir="sessions"):
    file_path = os.path.join(sessions_dir, f"{session_name}.json")
    if os.path.exists(file_path):
        os.remove(file_path)
    if session_name == session_state.get("session_id"):
        session_state["messages"] = []
        session_state["session_id"] = generate_session_id()
        session_state["last_conclusion"] = ""

