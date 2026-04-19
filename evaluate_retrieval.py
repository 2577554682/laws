import argparse
import json
import random
from collections import defaultdict
from statistics import mean

from retriever import CaseRetriever
from build_crime_patterns import extract_crimes_from_keywords, extract_crimes_from_text


def get_case_labels(case):
    labels = extract_crimes_from_keywords(case.get("关键词", ""))
    if not labels:
        labels = extract_crimes_from_text(case)
    return set(labels)


def get_query_text(case, max_chars=220):
    text = (case.get("基本案情", "") or case.get("裁判要旨", "") or "").strip()
    return text[:max_chars]


def infer_predicted_labels(retrieved_cases):
    pred = set()
    for c in retrieved_cases:
        labels = extract_crimes_from_keywords(c.get("关键词", ""))
        if not labels:
            labels = extract_crimes_from_text(c)
        pred.update(labels)
    return pred


def stratified_sample_by_first_label(cases, sample_size, seed=42):
    random.seed(seed)
    groups = defaultdict(list)
    for c in cases:
        labels = list(get_case_labels(c))
        if labels:
            groups[labels[0]].append(c)
    if not groups:
        return []

    labels = list(groups.keys())
    sampled = []
    per_group = max(1, sample_size // len(labels))
    for lb in labels:
        bucket = groups[lb]
        random.shuffle(bucket)
        sampled.extend(bucket[: min(per_group, len(bucket))])

    remain = sample_size - len(sampled)
    if remain > 0:
        pool = [c for lb in labels for c in groups[lb] if c not in sampled]
        random.shuffle(pool)
        sampled.extend(pool[:remain])
    return sampled[:sample_size]


def evaluate_thresholds(
    cases_path="resources/cases.json",
    index_path="resources/case_index.faiss",
    sample_size=200,
    top_k=5,
    thresholds=None,
    seed=42,
    sampling="stratified"
):
    if thresholds is None:
        thresholds = [round(x, 2) for x in [0.35, 0.40, 0.45, 0.50, 0.55, 0.60]]

    with open(cases_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    valid_cases = [c for c in cases if get_query_text(c) and get_case_labels(c)]
    if not valid_cases:
        raise ValueError("没有可用于评估的样本，请检查案例字段。")

    if sampling == "stratified":
        sampled = stratified_sample_by_first_label(valid_cases, min(sample_size, len(valid_cases)), seed=seed)
    else:
        random.seed(seed)
        sampled = random.sample(valid_cases, min(sample_size, len(valid_cases)))

    retriever = CaseRetriever(cases_path=cases_path, index_path=index_path, fact_field="基本案情")

    report = []
    for thr in thresholds:
        hit_flags = []
        retrieved_counts = []
        all_scores = []

        for case in sampled:
            query = get_query_text(case)
            true_labels = get_case_labels(case)
            retrieved, _, scores = retriever.retrieve(query, top_k=top_k, sim_threshold=thr)
            pred_labels = infer_predicted_labels(retrieved)

            hit = 1 if (true_labels & pred_labels) else 0
            hit_flags.append(hit)
            retrieved_counts.append(len(retrieved))
            all_scores.extend(scores)

        report.append({
            "threshold": thr,
            "sample_size": len(sampled),
            "hit_at_k": round(mean(hit_flags), 4) if hit_flags else 0.0,
            "avg_retrieved_count": round(mean(retrieved_counts), 3) if retrieved_counts else 0.0,
            "avg_similarity": round(mean(all_scores), 4) if all_scores else 0.0
        })

    # 优先高命中；命中接近时更偏好较高阈值（减少噪声）
    report_sorted = sorted(report, key=lambda x: (x["hit_at_k"], x["threshold"]), reverse=True)
    best = report_sorted[0]
    return {"best": best, "report": report_sorted, "sampling": sampling}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="检索阈值评估工具")
    parser.add_argument("--cases_path", default="resources/cases.json")
    parser.add_argument("--index_path", default="resources/case_index.faiss")
    parser.add_argument("--sample_size", type=int, default=200)
    parser.add_argument("--top_k", type=int, default=5)
    parser.add_argument("--sampling", default="stratified", choices=["stratified", "random"])
    args = parser.parse_args()

    result = evaluate_thresholds(
        cases_path=args.cases_path,
        index_path=args.index_path,
        sample_size=args.sample_size,
        top_k=args.top_k,
        sampling=args.sampling
    )

    print("推荐阈值：", result["best"]["threshold"])
    print(json.dumps(result, ensure_ascii=False, indent=2))
