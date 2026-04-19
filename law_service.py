"""法条编号解析、法条回查与引用展示。"""

import re


def extract_article_ids(text):
    if not text:
        return []
    ids = re.findall(
        r"(第[一二三四五六七八九十百千万零〇0-9]+条(?:第[一二三四五六七八九十百千万零〇0-9]+款)?)",
        text,
    )
    return list(dict.fromkeys(ids))


def cn_to_int(cn):
    if not cn:
        return None
    if cn.isdigit():
        return int(cn)

    digit_map = {"零": 0, "〇": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    unit_map = {"十": 10, "百": 100, "千": 1000}
    total, num = 0, 0
    for ch in cn:
        if ch in digit_map:
            num = digit_map[ch]
        elif ch in unit_map:
            unit = unit_map[ch]
            if num == 0:
                num = 1
            total += num * unit
            num = 0
        else:
            return None
    total += num
    return total if total > 0 else None


def parse_article_clause(article_text):
    if not article_text:
        return (None, None)
    m = re.search(
        r"第([一二三四五六七八九十百千万零〇0-9]+)条(?:第([一二三四五六七八九十百千万零〇0-9]+)款)?",
        article_text,
    )
    if not m:
        return (None, None)
    article_no = cn_to_int(m.group(1))
    clause_no = cn_to_int(m.group(2)) if m.group(2) else None
    return (article_no, clause_no)


def retrieve_law_refs(laws, related_laws, user_prompt, max_items=6, return_debug=False):
    if not laws:
        if return_debug:
            return [], {"article_ids": [], "matches": []}
        return []

    law_by_no = {}
    for item in laws:
        no = (item.get("法条编号") or "").strip()
        article_no, clause_no = parse_article_clause(no)
        if article_no is None:
            continue
        key_exact = (article_no, clause_no)
        key_article = (article_no, None)
        law_by_no.setdefault(key_exact, []).append(item)
        if key_exact != key_article:
            law_by_no.setdefault(key_article, []).append(item)

    combined_text = " ".join(related_laws) + "\n" + (user_prompt or "")
    article_ids = extract_article_ids(combined_text)
    results, seen, debug_matches = [], set(), []

    for aid in article_ids:
        article_no, clause_no = parse_article_clause(aid)
        if article_no is None:
            debug_matches.append({"source": aid, "normalized": None, "matched_count": 0})
            continue
        candidates = law_by_no.get((article_no, clause_no), [])
        if not candidates:
            candidates = law_by_no.get((article_no, None), [])

        debug_matches.append(
            {
                "source": aid,
                "normalized": f"{article_no}条" + (f"{clause_no}款" if clause_no is not None else ""),
                "matched_count": len(candidates),
                "matched_ids": list(dict.fromkeys([(c.get("法条编号") or "-") for c in candidates]))[:3],
            }
        )

        for c in candidates:
            key = (c.get("法条编号", ""), c.get("法条内容", ""))
            if key in seen:
                continue
            seen.add(key)
            results.append(c)
            if len(results) >= max_items:
                if return_debug:
                    return results, {"article_ids": article_ids, "matches": debug_matches}
                return results

    if return_debug:
        return results, {"article_ids": article_ids, "matches": debug_matches}
    return results


def retrieve_law_refs_by_crime_name(laws, crime_name, hints_map, max_items=3):
    if not laws:
        return []
    hints = hints_map.get(crime_name, [crime_name.replace("罪", ""), crime_name])
    results, seen = [], set()
    for item in laws:
        haystack = f"{item.get('法条编号', '')}\n{item.get('法条内容', '')}"
        if any(h and h in haystack for h in hints):
            key = (item.get("法条编号", ""), item.get("法条内容", ""))
            if key in seen:
                continue
            seen.add(key)
            results.append(item)
            if len(results) >= max_items:
                break
    return results


def build_case_refs_markdown(similar_cases, max_items=3):
    rows = ["| 案例 | 入库编号 | 相似度 |", "|---|---|---|"]
    for c in similar_cases[:max_items]:
        name = (c.get("案件名称") or "未命名案例").replace("|", " ")
        case_no = (c.get("入库编号") or "-").replace("|", " ")
        sim = c.get("_similarity", "-")
        sim_text = f"{sim:.3f}" if isinstance(sim, (int, float)) else str(sim)
        rows.append(f"| {name} | {case_no} | {sim_text} |")
    return "\n".join(rows)


def build_law_refs_markdown(law_refs):
    if not law_refs:
        return "未检索到可定位的法条原文。"
    rows = ["| 法条编号 | 法条内容摘录 |", "|---|---|"]
    for item in law_refs:
        no = (item.get("法条编号") or "-").replace("|", " ")
        content = (item.get("法条内容") or "").replace("|", " ")
        if len(content) > 120:
            content = content[:120] + "..."
        rows.append(f"| {no} | {content} |")
    return "\n".join(rows)


def build_law_debug_markdown(debug_info):
    if not debug_info:
        return "无调试信息。"
    ids = debug_info.get("article_ids", [])
    matches = debug_info.get("matches", [])
    lines = [f"- 抽取法条片段：{', '.join(ids) if ids else '无'}", "", "| 原始片段 | 标准化 | 命中数 | 命中法条示例 |", "|---|---|---:|---|"]
    for m in matches:
        source = str(m.get("source", "-")).replace("|", " ")
        normalized = str(m.get("normalized", "-")).replace("|", " ")
        matched_count = m.get("matched_count", 0)
        matched_ids = ", ".join(m.get("matched_ids", [])) if m.get("matched_ids") else "-"
        lines.append(f"| {source} | {normalized} | {matched_count} | {matched_ids.replace('|', ' ')} |")
    return "\n".join(lines)
