"""UI 组件：侧边栏、聊天历史、法官操作台。"""

import streamlit as st
from datetime import datetime

from session_manager import (
    delete_session,
    generate_session_id,
    load_session,
    load_sessions,
    save_session,
)


def render_sidebar(
    session_state,
    sim_threshold_default,
    sim_threshold_min,
    sim_threshold_max,
    sim_threshold_step,
):
    with st.sidebar:
        st.subheader("控制面板")
        sim_threshold = st.slider(
            "检索相似度阈值",
            sim_threshold_min,
            sim_threshold_max,
            sim_threshold_default,
            sim_threshold_step,
        )
        show_law_debug = st.checkbox("显示法条匹配调试信息", value=False)

        if st.button("新建会话", use_container_width=True):
            save_session(session_state)
            if session_state.messages:
                session_state.messages = []
                session_state.session_id = generate_session_id()
                session_state.last_conclusion = ""
                session_state.dialogue_case_context = ""
                session_state.judge_standard = None
                save_session(session_state)
                st.rerun()

        st.text("历史会话")
        for session in load_sessions():
            col1, col2 = st.columns([4, 1])
            with col1:
                if st.button(
                    session,
                    use_container_width=True,
                    key=f"load{session}",
                    type="primary" if session == session_state.session_id else "secondary",
                ):
                    try:
                        load_session(session_state, session)
                        st.rerun()
                    except Exception:
                        st.error("加载会话失败！")
            with col2:
                if st.button("删除", use_container_width=True, key=f"delete{session}"):
                    try:
                        delete_session(session_state, session)
                        st.rerun()
                    except Exception:
                        st.error("删除会话失败！")

        st.divider()
        st.caption("使用说明")
        st.caption("1. 输入案例描述，系统输出步骤1-3")
        st.caption("2. 输入法律问题，系统直接回答")
        st.caption("3. 法官可在操作台修订结论并生成纪要")

    return sim_threshold, show_law_debug


def render_history(messages):
    for message in messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])


def render_judge_workbench(session_state, crime_options, retriever, laws, crime_patterns, generate_modification_basis):
    st.divider()
    st.subheader("法官操作台（结论修订）")
    with st.expander("进入修订流程", expanded=False):
        original = session_state.get("last_conclusion", "") or "（暂无可识别结论）"
        st.markdown(f"**原结论**：{original}")

        options = ["自定义输入"] + crime_options[:120]
        selected = st.selectbox("拟修改结论（可选标准罪名）", options, key="judge_conclusion_select")
        custom_target = st.text_input(
            "自定义结论（当上方选择“自定义输入”时填写）",
            key="judge_conclusion_custom",
            placeholder="例如：受贿罪、诈骗罪、不构成犯罪",
        )
        reason = st.text_area(
            "修改理由（必填）",
            key="judge_reason",
            placeholder="请简要写明为何需要从原结论修订为新结论。",
        )
        checks = st.multiselect(
            "证据核验清单（至少选择1项）",
            [
                "主体身份是否明确",
                "客观行为证据是否充分",
                "金额/次数/时间链是否闭环",
                "法条构成要件是否逐项对应",
                "资金流向与书证/电子数据是否一致",
            ],
            key="judge_checks",
        )

        if st.button("生成修订纪要", type="primary", use_container_width=True):
            target = custom_target.strip() if selected == "自定义输入" else selected.strip()
            if not target:
                st.warning("请填写拟修改结论")
                return
            if not reason.strip():
                st.warning("请填写修改理由")
                return
            if not checks:
                st.warning("请至少勾选1项证据核验清单")
                return

            basis = generate_modification_basis(target, retriever, laws, crime_patterns=crime_patterns)
            now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            memo = (
                "**法官修订纪要**\n\n"
                f"- 修订时间：{now_text}\n"
                f"- 原结论：{original}\n"
                f"- 拟修订结论：{target}\n"
                f"- 修改理由：{reason.strip()}\n"
                f"- 已核验要点：{', '.join(checks)}\n\n"
                f"{basis}\n\n"
                "> 该纪要用于办案过程留痕，不替代有权机关最终认定。"
            )
            # 固化法官标准：后续轮次与本地知识库同级约束
            session_state["judge_standard"] = {
                "target": target,
                "reason": reason.strip(),
                "checks": checks,
                "updated_at": now_text,
            }
            with st.chat_message("assistant"):
                st.markdown(memo)
            session_state.messages.append({"role": "assistant", "content": memo})
            save_session(session_state)
