import argparse
import json
import re
from collections import Counter, defaultdict

# ========== 配置区域 ==========
CASES_PATH = "resources/cases.json"  # 案例文件路径
OUTPUT_PATH = "resources/crime_patterns.json"  # 输出路径


# ============================

# 常见罪名别称归一，便于提升映射覆盖和命中稳定性
CRIME_ALIASES = {
    "故意伤害": "故意伤害罪",
    "故意杀人": "故意杀人罪",
    "诈骗": "诈骗罪",
    "抢劫": "抢劫罪",
    "盗窃": "盗窃罪",
    "受贿": "受贿罪",
    "贪污": "贪污罪",
    "危险驾驶": "危险驾驶罪",
    "交通肇事": "交通肇事罪",
    "寻衅滋事": "寻衅滋事罪",
    "非法经营": "非法经营罪",
    "职务侵占": "职务侵占罪",
    "挪用资金": "挪用资金罪",
    "挪用公款": "挪用公款罪",
    "行贿": "行贿罪",
    "聚众斗殴": "聚众斗殴罪"
}


def normalize_crime_name(name):
    if not name:
        return None
    name = name.strip()
    if not name:
        return None
    if name in CRIME_ALIASES:
        return CRIME_ALIASES[name]
    if "罪" in name:
        return name
    return f"{name}罪"


def extract_crimes_from_keywords(keywords_str):
    """从关键词字段提取罪名列表（允许一案多罪）"""
    if not keywords_str:
        return []
    # 关键词格式通常是 "刑事,强制猥亵罪,未成年人,隔空猥亵"
    parts = keywords_str.split(",")
    crimes = []
    for part in parts:
        part = part.strip()
        if part and part != "刑事" and ("罪" in part or part in CRIME_ALIASES):
            normalized = normalize_crime_name(part)
            if normalized:
                crimes.append(normalized)
    return list(dict.fromkeys(crimes))


def extract_crimes_from_text(case):
    """当关键词缺失时，从案件名称/裁判理由兜底提取罪名"""
    candidates = []
    case_name = case.get("案件名称", "")
    reason = case.get("裁判理由", "")

    # 案件名称中常见“XXX罪案”形式
    for match in re.findall(r"([\u4e00-\u9fa5]{2,20}罪)", case_name):
        normalized = normalize_crime_name(match)
        if normalized:
            candidates.append(normalized)

    # 裁判理由中的“构成XX罪”
    for match in re.findall(r"构成([\u4e00-\u9fa5]{2,20}罪)", reason):
        normalized = normalize_crime_name(match)
        if normalized:
            candidates.append(normalized)

    return list(dict.fromkeys(candidates))


def extract_law_articles(raw_law):
    """从关联索引中提取刑法条文（支持一条字段里多法条）"""
    if not raw_law:
        return []
    raw_law = raw_law.strip()
    if not raw_law:
        return []

    matches = re.findall(
        r"(《[^》]*刑法[^》]*》?第[一二三四五六七八九十百千万零〇0-9]+条(?:第[一二三四五六七八九十百千万零〇0-9]+款)?)",
        raw_law,
    )
    out = list(dict.fromkeys([m.strip() for m in matches if "刑法" in m]))
    return out[:10]


def extract_fact_pattern(case):
    text = case.get("基本案情", "") or case.get("裁判要旨", "")
    text = re.sub(r"\s+", "", text)
    if not text:
        return ""
    # 取首句作为模式候选，长度上限控制在160
    m = re.search(r"[。；;]", text)
    if m and m.start() > 20:
        return text[: m.start() + 1][:160]
    return text[:160]


def extract_sentence_from_reason(reason_str):
    """从裁判理由中提取刑期"""
    if not reason_str:
        return None
    # 匹配 "判处有期徒刑X年" 或 "判处X年"
    patterns = [
        r'判处有期徒刑(\d+)年',
        r'判处(\d+)年有期徒刑',
        r'判处(\d+)年',
        r'拘役(\d+)个月',
        r'处(\d+)年'
    ]
    for pattern in patterns:
        match = re.search(pattern, reason_str)
        if match:
            return f"{match.group(1)}年"
    return None


def build_crime_patterns(cases_path, output_path):
    print("=" * 50)
    print("开始构建罪名→事实模式映射表")
    print("=" * 50)

    # 1. 加载案例
    print(f"\n[1/3] 加载案例文件: {cases_path}")
    with open(cases_path, "r", encoding="utf-8") as f:
        cases = json.load(f)
    print(f"      共加载 {len(cases)} 条案例")

    # 2. 聚合数据
    print("\n[2/3] 聚合案例数据...")
    crime_patterns = defaultdict(lambda: {
        "fact_patterns": [],
        "law_articles": set(),
        "example_cases": [],
        "sentence_range": [],
        "count": 0
    })

    for case in cases:
        # 提取罪名（关键词优先，文本兜底）
        keywords = case.get("关键词", "")
        crimes = extract_crimes_from_keywords(keywords)
        if not crimes:
            crimes = extract_crimes_from_text(case)
        if not crimes:
            crimes = ["未知罪名"]

        # 提取事实模式（首句优先）
        fact_summary = extract_fact_pattern(case)

        # 提取法条（可能多条）
        laws = extract_law_articles(case.get("关联索引", ""))

        # 提取刑期
        reason = case.get("裁判理由", "")
        sentence = extract_sentence_from_reason(reason)

        # 存入（支持一案多罪）
        for crime in crimes:
            if fact_summary:
                crime_patterns[crime]["fact_patterns"].append(fact_summary)
            for law in laws:
                crime_patterns[crime]["law_articles"].add(law)
            if sentence:
                crime_patterns[crime]["sentence_range"].append(sentence)
            crime_patterns[crime]["example_cases"].append(case.get("案件名称", ""))
            crime_patterns[crime]["count"] += 1

    # 3. 后处理：去重、限制数量、排序
    print("\n[3/3] 后处理...")
    result = {}
    for crime, data in crime_patterns.items():
        # 事实模式按频次排序并限制最多5条
        fact_counter = Counter(data["fact_patterns"])
        unique_facts = [x for x, _ in fact_counter.most_common(5)]

        # 刑期范围（取最常见的）
        if data["sentence_range"]:
            most_common_sentence = Counter(data["sentence_range"]).most_common(1)[0][0]
        else:
            most_common_sentence = "无明确刑期信息"

        # 示例案例去重并限制最多3条
        unique_examples = list(dict.fromkeys(data["example_cases"]))[:3]

        result[crime] = {
            "fact_patterns": unique_facts,
            "law_articles": sorted(list(data["law_articles"]))[:10],
            "example_cases": unique_examples,
            "typical_sentence": most_common_sentence,
            "case_count": data["count"]
        }

    # 按案例数量排序
    result = dict(sorted(result.items(), key=lambda x: x[1]["case_count"], reverse=True))

    # 保存
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n      共生成 {len(result)} 个罪名的映射")
    print(f"      保存位置: {output_path}")

    # 打印前10个罪名
    print("\n[预览] 前10个罪名及案例数量:")
    for i, (crime, data) in enumerate(list(result.items())[:10]):
        print(f"      {i + 1}. {crime}: {data['case_count']}条案例")

    print("\n" + "=" * 50)
    print("构建完成！")
    print("=" * 50)

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="构建罪名映射表")
    parser.add_argument("--cases_path", default=CASES_PATH)
    parser.add_argument("--output_path", default=OUTPUT_PATH)
    args = parser.parse_args()
    build_crime_patterns(args.cases_path, args.output_path)
