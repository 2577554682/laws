"""法官修改结论：动态从案例库提取依据（不依赖静态crime_patterns）。"""

import re

from law_service import retrieve_law_refs


def _normalize_crime_name(text):
    text = (text or "").strip()
    if not text:
        return ""
    m = re.search(r"([\u4e00-\u9fa5]{2,20}罪)", text)
    if m:
        return m.group(1)
    return text if text.endswith("罪") else f"{text}罪"


def _compact(text, max_len=90):
    text = re.sub(r"\s+", "", str(text or ""))
    return text[:max_len] + ("..." if len(text) > max_len else "")


def _merge_unique(items_a, items_b, limit):
    out = []
    for x in (items_a or []) + (items_b or []):
        x = str(x).strip()
        if x and x not in out:
            out.append(x)
        if len(out) >= limit:
            break
    return out


def generate_modification_basis(new_conclusion, retriever, laws, crime_patterns=None):
    crime_name = _normalize_crime_name(new_conclusion)
    if not crime_name:
        return "未识别到有效罪名，请输入如“诈骗罪”“受贿罪”等标准罪名。"

    # 动态层：向量检索实时抽取
    dynamic = retriever.get_crime_info(crime_name, top_k=12)
    dynamic_facts = dynamic.get("fact_patterns", [])
    dynamic_laws = dynamic.get("law_articles", [])
    dynamic_cases = dynamic.get("example_cases", [])
    dynamic_count = dynamic.get("case_count", 0)

    # 静态层：crime_patterns 映射表补全
    static = (crime_patterns or {}).get(crime_name, {})
    static_facts = static.get("fact_patterns", [])
    static_laws = static.get("law_articles", [])
    static_cases = static.get("example_cases", [])
    static_count = int(static.get("case_count", 0) or 0)

    # 混合结果：动态优先，静态兜底
    fact_patterns = _merge_unique(dynamic_facts, static_facts, limit=5)
    law_articles = _merge_unique(dynamic_laws, static_laws, limit=5)
    example_cases = _merge_unique(dynamic_cases, static_cases, limit=3)
    case_count = max(dynamic_count, static_count)

    # 优先保留刑法条文，避免程序法混入
    law_articles = [x for x in law_articles if "刑法" in str(x)] or law_articles[:3]
    law_refs = retrieve_law_refs(laws, law_articles, "", max_items=3) if law_articles else []

    basis = (
        "**修改依据（混合映射：动态+静态）**：\n\n"
        f"- 用户输入：{new_conclusion}\n"
        f"- 识别罪名：{crime_name}\n"
        f"- 动态命中案例数：{dynamic_count}\n"
        f"- 静态映射样本数：{static_count}\n"
        f"- 综合参考样本数：{case_count}\n\n"
        "**典型事实特征（综合）**："
    )
    if fact_patterns:
        basis += "\n" + "\n".join([f"- {_compact(x)}" for x in fact_patterns])
    else:
        basis += "\n- 本地案例中未提取到稳定事实模式。"

    basis += "\n\n**关联法条（动态）**："
    if law_articles:
        basis += "\n" + "\n".join([f"- {x}" for x in law_articles[:5]])
    else:
        basis += "\n- 本地案例未检索到明确关联法条。"

    basis += "\n\n**法条原文（laws.json）**："
    if law_refs:
        for item in law_refs:
            basis += f"\n- {item.get('法条编号', '-')}: {_compact(item.get('法条内容', ''), max_len=80)}"
    else:
        basis += "\n- 未在 laws.json 命中对应条文原文。"

    basis += "\n\n**参考案例（Top3）**："
    if example_cases:
        basis += "\n" + "\n".join([f"- {x}" for x in example_cases])
    else:
        basis += "\n- 无可展示参考案例。"

    basis += "\n\n> 以上依据由本地案例库实时提取生成，不替代有权机关最终认定。"
    return basis
