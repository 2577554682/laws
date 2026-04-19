import json
import os
import re

import streamlit as st
from openai import OpenAI

import config
from crime_patterns import get_crime_patterns
from law_service import (
    build_case_refs_markdown,
    build_law_debug_markdown,
    build_law_refs_markdown,
    retrieve_law_refs,
)
from modification_service import generate_modification_basis
from prompts import OUTPUT_FORMAT_GUARD, SYSTEM_PROMPT
from retriever import CaseRetriever
from session_manager import generate_session_id, save_session
from ui_components import render_history, render_judge_workbench, render_sidebar


# 页面初始化
st.set_page_config(
    page_title=config.APP_PAGE_TITLE,
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={},
)


@st.cache_resource
def init_retriever():
    return CaseRetriever(
        cases_path=config.CASES_PATH,
        index_path=config.INDEX_PATH,
        fact_field=config.FACT_FIELD,
    )


@st.cache_resource
def init_laws():
    try:
        with open(config.LAWS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        st.warning(f" 法条库加载失败: {e}")
        return []


@st.cache_resource
def init_patterns():
    try:
        return get_crime_patterns(config.CRIME_PATTERNS_PATH)
    except Exception as e:
        st.warning(f" 映射表加载失败: {e}")
        return {}


def init_state():
    defaults = {
        "messages": [],
        "session_id": generate_session_id(),
        "last_conclusion": "",
        "last_facts": "",
        "dialogue_case_context": "",
        "judge_standard": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def build_crime_options_from_cases(cases, max_items=200):
    crimes = []
    for case in cases:
        keywords = case.get("关键词", "")
        for part in str(keywords).split(","):
            part = part.strip()
            if part and part != "刑事" and ("罪" in part):
                crimes.append(part)
        name = case.get("案件名称", "")
        for m in re.findall(r"([\u4e00-\u9fa5]{2,20}罪)", str(name)):
            crimes.append(m)
    unique = list(dict.fromkeys(crimes))
    return unique[:max_items]


def is_followup_query(text):
    text = (text or "").strip()
    if not text:
        return False
    if len(text) <= 14:
        return True
    cues = ["继续", "刚才", "前面", "上述", "这个", "那个", "再分析", "补充", "然后", "那"]
    return any(c in text for c in cues)


def build_recent_history(messages, max_turns=4):
    if not messages:
        return "无"
    recent = messages[-max_turns * 2 :]
    lines = []
    for m in recent:
        role = "用户" if m.get("role") == "user" else "助手"
        content = str(m.get("content", "")).strip()
        content = re.sub(r"\s+", " ", content)
        if len(content) > 180:
            content = content[:180] + "..."
        lines.append(f"{role}: {content}")
    return "\n".join(lines) if lines else "无"


def get_last_user_case_text(messages):
    for m in reversed(messages):
        if m.get("role") == "user":
            text = str(m.get("content", "")).strip()
            if text and len(text) >= 12:
                return text
    return ""


def extract_last_conclusion(full_response):
    if "步骤3 硬性结论" not in full_response:
        return ""
    lines = [ln.strip() for ln in full_response.split("\n") if ln.strip()]
    for i, line in enumerate(lines):
        if "步骤3 硬性结论" in line:
            candidate = line.replace("【步骤3 硬性结论】", "")
            candidate = candidate.replace("步骤3 硬性结论：", "").replace("步骤3 硬性结论:", "").strip()
            if not candidate and i + 1 < len(lines):
                candidate = lines[i + 1].strip()
            return candidate
    return ""


def main():
    st.title(config.APP_TITLE)
    st.caption(config.APP_CAPTION)

    init_state()
    sim_threshold, show_law_debug = render_sidebar(
        st.session_state,
        sim_threshold_default=config.SIM_THRESHOLD_DEFAULT,
        sim_threshold_min=config.SIM_THRESHOLD_MIN,
        sim_threshold_max=config.SIM_THRESHOLD_MAX,
        sim_threshold_step=config.SIM_THRESHOLD_STEP,
    )

    retriever = init_retriever()
    laws = init_laws()
    crime_patterns = init_patterns()
    crime_options = build_crime_options_from_cases(retriever.cases)
    # 混合映射时，把静态映射中的罪名也合并进下拉
    crime_options = list(dict.fromkeys(crime_options + list(crime_patterns.keys())))

    render_history(st.session_state.messages)
    render_judge_workbench(
        st.session_state,
        crime_options,
        retriever,
        laws,
        crime_patterns,
        generate_modification_basis,
    )

    client = OpenAI(
        api_key=os.environ.get(config.OPENAI_API_KEY_ENV),
        base_url=config.OPENAI_BASE_URL,
    )

    prompt = st.chat_input("请输入案件描述或法律问题...")
    if not prompt:
        return

    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})
    followup = is_followup_query(prompt)
    if followup:
        base_context = st.session_state.get("dialogue_case_context") or get_last_user_case_text(st.session_state.messages[:-1])
        if base_context:
            retrieval_query = base_context + "\n" + prompt
        else:
            retrieval_query = prompt
    else:
        retrieval_query = prompt
    # 每轮都更新最新案情上下文，保证“继续分析”可追溯
    st.session_state["dialogue_case_context"] = retrieval_query

    # 检索阶段：先找案例，再回查可定位法条原文
    with st.spinner("正在检索本地案例库..."):
        similar_cases, related_laws, scores = retriever.retrieve(
            retrieval_query,
            top_k=config.TOP_K,
            sim_threshold=sim_threshold,
        )
        if not similar_cases:
            retry_threshold = max(config.SIM_THRESHOLD_MIN, sim_threshold - 0.10)
            similar_cases, related_laws, scores = retriever.retrieve(
                retrieval_query,
                top_k=config.TOP_K,
                sim_threshold=retry_threshold,
            )

    st.session_state.last_facts = retrieval_query
    law_refs, law_debug_info = retrieve_law_refs(
        laws,
        related_laws,
        retrieval_query,
        max_items=config.LAW_REF_MAX_ITEMS,
        return_debug=True,
    )

    score_text = ", ".join([f"{s:.3f}" for s in scores[:5]]) if scores else "无"
    law_refs_text = "；".join([f"{x.get('法条编号', '-')}: {x.get('法条内容', '')[:60]}" for x in law_refs[:4]]) or "无"
    recent_history = build_recent_history(st.session_state.messages[:-1], max_turns=4)

    context = f"""
【作答边界】
你只能使用本次提供的本地资料作答；若资料不足，请明确写“本地资料不足以支持该结论”。

【法官修订标准】
{(
    f"目标结论：{st.session_state['judge_standard'].get('target', '')}\n"
    f"修订理由：{st.session_state['judge_standard'].get('reason', '')}\n"
    f"核验要点：{', '.join(st.session_state['judge_standard'].get('checks', []))}\n"
    f"更新时间：{st.session_state['judge_standard'].get('updated_at', '')}"
) if st.session_state.get('judge_standard') else "无（尚未提交法官修订标准）"}

【当前阶段】
{"连续追问分析" if followup else "首轮案情分析（未修改结论）"}

【本地相似案例】（共{len(similar_cases)}条）
{json.dumps(similar_cases, ensure_ascii=False, indent=2)[:2200]}

【关联法条（案例侧）】
{', '.join(related_laws) if related_laws else '无直接关联法条'}

【法条原文回查（laws.json）】
{law_refs_text}

【检索参数】
相似度阈值={sim_threshold:.2f}；命中相似度Top5={score_text}

【最近对话摘要】
{recent_history}

【用户输入】
{prompt}
"""

    response = client.chat.completions.create(
        model=config.MODEL_NAME,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + OUTPUT_FORMAT_GUARD},
            {"role": "user", "content": context},
        ],
        stream=True,
    )

    full_response = ""
    response_placeholder = st.empty()
    for chunk in response:
        if chunk.choices[0].delta.content:
            full_response += chunk.choices[0].delta.content
            with response_placeholder.chat_message("assistant"):
                st.markdown(full_response)

    case_refs_md = build_case_refs_markdown(similar_cases, max_items=config.CASE_REF_MAX_ITEMS)
    law_refs_md = build_law_refs_markdown(law_refs)
    citation_block = (
        "\n\n---\n"
        "**引用依据（自动检索）**\n\n"
        "**引用案例**\n\n"
        f"{case_refs_md}\n\n"
        "**引用法条（laws.json）**\n\n"
        f"{law_refs_md}"
    )
    if show_law_debug:
        citation_block += "\n\n**法条匹配调试**\n\n" + build_law_debug_markdown(law_debug_info)

    full_response += citation_block
    with response_placeholder.chat_message("assistant"):
        st.markdown(full_response)

    st.session_state.messages.append({"role": "assistant", "content": full_response})
    st.session_state.last_conclusion = extract_last_conclusion(full_response)

    save_session(st.session_state)
    st.rerun()


if __name__ == "__main__":
    main()
