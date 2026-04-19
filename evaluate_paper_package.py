import argparse
import csv
import json
import math
import os
import random
from collections import defaultdict
from statistics import mean

from build_crime_patterns import extract_crimes_from_keywords, extract_crimes_from_text
from evaluate_retrieval import evaluate_thresholds
from retriever import CaseRetriever


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_case_labels(case):
    labels = extract_crimes_from_keywords(case.get("关键词", ""))
    if not labels:
        labels = extract_crimes_from_text(case)
    return list(dict.fromkeys(labels))


def get_query_text(case, max_chars=220):
    text = (case.get("基本案情", "") or case.get("裁判要旨", "") or "").strip()
    return text[:max_chars]


def merge_unique(a, b, limit):
    out = []
    for x in (a or []) + (b or []):
        x = str(x).strip()
        if x and x not in out:
            out.append(x)
        if len(out) >= limit:
            break
    return out


def stratified_sample_by_first_label(cases, sample_size, seed=42):
    random.seed(seed)
    groups = defaultdict(list)
    for c in cases:
        labels = get_case_labels(c)
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

    # 补齐剩余样本
    remain = sample_size - len(sampled)
    if remain > 0:
        pool = [c for lb in labels for c in groups[lb] if c not in sampled]
        random.shuffle(pool)
        sampled.extend(pool[:remain])
    return sampled[:sample_size]


def infer_predicted_labels(retrieved_cases):
    pred = set()
    for c in retrieved_cases:
        pred.update(get_case_labels(c))
    return pred


def precision_at_k(retrieved_cases, true_labels):
    if not retrieved_cases:
        return 0.0
    rel = 0
    for c in retrieved_cases:
        if set(get_case_labels(c)) & true_labels:
            rel += 1
    return rel / len(retrieved_cases)


def mrr_at_k(retrieved_cases, true_labels):
    for rank, c in enumerate(retrieved_cases, start=1):
        if set(get_case_labels(c)) & true_labels:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(retrieved_cases, true_labels):
    if not retrieved_cases:
        return 0.0
    dcg = 0.0
    rel_count = 0
    for rank, c in enumerate(retrieved_cases, start=1):
        rel = 1 if (set(get_case_labels(c)) & true_labels) else 0
        if rel:
            rel_count += 1
            dcg += rel / math.log2(rank + 1)
    if rel_count == 0:
        return 0.0
    # 理想排序下，相关文档应排在最前面
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, rel_count + 1))
    return dcg / idcg


def evaluate_retrieval_strict(cases, retriever, sample_size=200, top_k=5, threshold=0.45, seed=42):
    sampled = stratified_sample_by_first_label(cases, sample_size=sample_size, seed=seed)
    rows = []
    for case in sampled:
        query = get_query_text(case)
        if not query:
            continue
        true_labels = set(get_case_labels(case))
        if not true_labels:
            continue
        retrieved, _, scores = retriever.retrieve(query, top_k=top_k, sim_threshold=threshold)
        pred_labels = infer_predicted_labels(retrieved)

        rows.append(
            {
                "hit": 1 if (pred_labels & true_labels) else 0,
                "p_at_k": precision_at_k(retrieved, true_labels),
                "mrr_at_k": mrr_at_k(retrieved, true_labels),
                "ndcg_at_k": ndcg_at_k(retrieved, true_labels),
                "retrieved_count": len(retrieved),
                "avg_score": mean(scores) if scores else 0.0,
            }
        )

    if not rows:
        return {
            "sample_size": 0,
            "threshold": threshold,
            "hit_at_k": 0.0,
            "precision_at_k": 0.0,
            "mrr_at_k": 0.0,
            "ndcg_at_k": 0.0,
            "avg_retrieved_count": 0.0,
            "avg_similarity": 0.0,
        }

    return {
        "sample_size": len(rows),
        "threshold": threshold,
        "hit_at_k": round(mean([r["hit"] for r in rows]), 4),
        "precision_at_k": round(mean([r["p_at_k"] for r in rows]), 4),
        "mrr_at_k": round(mean([r["mrr_at_k"] for r in rows]), 4),
        "ndcg_at_k": round(mean([r["ndcg_at_k"] for r in rows]), 4),
        "avg_retrieved_count": round(mean([r["retrieved_count"] for r in rows]), 3),
        "avg_similarity": round(mean([r["avg_score"] for r in rows]), 4),
    }


def get_static_info(crime_name, crime_patterns):
    p = crime_patterns.get(crime_name, {})
    return {
        "fact_patterns": p.get("fact_patterns", [])[:5],
        "law_articles": p.get("law_articles", [])[:5],
        "example_cases": p.get("example_cases", [])[:3],
        "case_count": int(p.get("case_count", 0) or 0),
    }


def get_hybrid_info(crime_name, retriever, crime_patterns):
    d = retriever.get_crime_info(crime_name, top_k=12)
    s = get_static_info(crime_name, crime_patterns)
    return {
        "fact_patterns": merge_unique(d.get("fact_patterns", []), s.get("fact_patterns", []), 5),
        "law_articles": merge_unique(d.get("law_articles", []), s.get("law_articles", []), 5),
        "example_cases": merge_unique(d.get("example_cases", []), s.get("example_cases", []), 3),
        "case_count": max(int(d.get("case_count", 0) or 0), int(s.get("case_count", 0) or 0)),
    }


def evaluate_mapping_modes(cases, retriever, crime_patterns, sample_size=200, seed=42):
    sampled = stratified_sample_by_first_label(cases, sample_size=sample_size, seed=seed)

    mode_records = {"dynamic": [], "static": [], "hybrid": []}
    for case in sampled:
        labels = get_case_labels(case)
        if not labels:
            continue
        crime = labels[0]

        dynamic = retriever.get_crime_info(crime, top_k=12)
        static = get_static_info(crime, crime_patterns)
        hybrid = get_hybrid_info(crime, retriever, crime_patterns)

        for mode, info in [("dynamic", dynamic), ("static", static), ("hybrid", hybrid)]:
            mode_records[mode].append(
                {
                    "has_fact": 1 if info.get("fact_patterns") else 0,
                    "has_law": 1 if info.get("law_articles") else 0,
                    "has_example": 1 if info.get("example_cases") else 0,
                    "case_count": int(info.get("case_count", 0) or 0),
                    "fact_count": len(info.get("fact_patterns", [])),
                    "law_count": len(info.get("law_articles", [])),
                    "example_count": len(info.get("example_cases", [])),
                }
            )

    result = {}
    for mode, rows in mode_records.items():
        if not rows:
            result[mode] = {
                "sample_size": 0,
                "fact_coverage": 0.0,
                "law_coverage": 0.0,
                "example_coverage": 0.0,
                "avg_case_count": 0.0,
                "avg_fact_count": 0.0,
                "avg_law_count": 0.0,
                "avg_example_count": 0.0,
            }
            continue

        result[mode] = {
            "sample_size": len(rows),
            "fact_coverage": round(mean([r["has_fact"] for r in rows]), 4),
            "law_coverage": round(mean([r["has_law"] for r in rows]), 4),
            "example_coverage": round(mean([r["has_example"] for r in rows]), 4),
            "avg_case_count": round(mean([r["case_count"] for r in rows]), 3),
            "avg_fact_count": round(mean([r["fact_count"] for r in rows]), 3),
            "avg_law_count": round(mean([r["law_count"] for r in rows]), 3),
            "avg_example_count": round(mean([r["example_count"] for r in rows]), 3),
        }
    return result


def write_tables(final_report, output_dir):
    retrieval = final_report["retrieval"]
    mapping = final_report["mapping_modes"]

    csv_path = os.path.join(output_dir, "paper_metrics_table.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["section", "metric", "value"])
        w.writerow(["meta", "cases_count", final_report["meta"]["cases_count"]])
        w.writerow(["meta", "laws_count", final_report["meta"]["laws_count"]])
        w.writerow(["meta", "patterns_count", final_report["meta"]["patterns_count"]])
        w.writerow(["meta", "sample_size", final_report["meta"]["sample_size"]])
        w.writerow(["meta", "top_k", final_report["meta"]["top_k"]])
        w.writerow(["meta", "sampling", retrieval["scan"].get("sampling", "stratified")])
        w.writerow(["retrieval_scan", "best_threshold", retrieval["scan"]["best"]["threshold"]])
        w.writerow(["retrieval_scan", "best_hit_at_k", retrieval["scan"]["best"]["hit_at_k"]])
        w.writerow(["retrieval", "threshold", retrieval["strict"]["threshold"]])
        w.writerow(["retrieval", "hit_at_k", retrieval["strict"]["hit_at_k"]])
        w.writerow(["retrieval", "precision_at_k", retrieval["strict"]["precision_at_k"]])
        w.writerow(["retrieval", "mrr_at_k", retrieval["strict"]["mrr_at_k"]])
        w.writerow(["retrieval", "ndcg_at_k", retrieval["strict"]["ndcg_at_k"]])
        for mode in ["dynamic", "static", "hybrid"]:
            row = mapping[mode]
            w.writerow([mode, "fact_coverage", row["fact_coverage"]])
            w.writerow([mode, "law_coverage", row["law_coverage"]])
            w.writerow([mode, "example_coverage", row["example_coverage"]])
            w.writerow([mode, "avg_case_count", row["avg_case_count"]])

    md_path = os.path.join(output_dir, "paper_metrics_table.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# 自动生成结果表\n\n")
        f.write("## 数据与设置\n\n")
        f.write(
            f"- 案例数：{final_report['meta']['cases_count']}，法条数：{final_report['meta']['laws_count']}，映射罪名数：{final_report['meta']['patterns_count']}\n"
        )
        f.write(
            f"- sample_size={final_report['meta']['sample_size']}，top_k={final_report['meta']['top_k']}，sampling={retrieval['scan'].get('sampling', 'stratified')}\n\n"
        )
        f.write("## 检索阈值扫描（best）\n\n")
        best = retrieval["scan"]["best"]
        f.write("| best_threshold | hit_at_k | avg_retrieved_count | avg_similarity |\n")
        f.write("|---:|---:|---:|---:|\n")
        f.write(f"| {best['threshold']} | {best['hit_at_k']} | {best['avg_retrieved_count']} | {best['avg_similarity']} |\n\n")
        f.write("## 检索严格评测\n\n")
        f.write("| threshold | hit@k | precision@k | mrr@k | ndcg@k | avg_retrieved_count |\n")
        f.write("|---:|---:|---:|---:|---:|---:|\n")
        s = retrieval["strict"]
        f.write(
            f"| {s['threshold']} | {s['hit_at_k']} | {s['precision_at_k']} | {s['mrr_at_k']} | {s['ndcg_at_k']} | {s['avg_retrieved_count']} |\n\n"
        )
        f.write("## 映射模式对比\n\n")
        f.write("| mode | fact_coverage | law_coverage | example_coverage | avg_case_count | avg_fact_count | avg_law_count |\n")
        f.write("|---|---:|---:|---:|---:|---:|---:|\n")
        for mode in ["dynamic", "static", "hybrid"]:
            r = mapping[mode]
            f.write(
                f"| {mode} | {r['fact_coverage']} | {r['law_coverage']} | {r['example_coverage']} | {r['avg_case_count']} | {r['avg_fact_count']} | {r['avg_law_count']} |\n"
            )
    return csv_path, md_path


def main():
    parser = argparse.ArgumentParser(description="论文实验一键评测（严格版）")
    parser.add_argument("--cases_path", default="resources/cases.json")
    parser.add_argument("--index_path", default="resources/case_index.faiss")
    parser.add_argument("--patterns_path", default="resources/crime_patterns.json")
    parser.add_argument("--sample_size", type=int, default=200)
    parser.add_argument("--top_k", type=int, default=5)
    parser.add_argument("--eval_threshold", type=float, default=0.45)
    parser.add_argument("--output_dir", default="paper_package/results")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    cases = load_json(args.cases_path)
    crime_patterns = load_json(args.patterns_path) if os.path.exists(args.patterns_path) else {}
    laws = load_json("resources/laws.json")
    retriever = CaseRetriever(cases_path=args.cases_path, index_path=args.index_path, fact_field="基本案情")

    # 兼容旧指标（阈值扫描）
    retrieval_scan = evaluate_thresholds(
        cases_path=args.cases_path,
        index_path=args.index_path,
        sample_size=args.sample_size,
        top_k=args.top_k,
        sampling="stratified",
    )
    # 新增严格指标
    retrieval_strict = evaluate_retrieval_strict(
        cases=cases,
        retriever=retriever,
        sample_size=args.sample_size,
        top_k=args.top_k,
        threshold=args.eval_threshold,
    )
    mapping_report = evaluate_mapping_modes(
        cases=cases,
        retriever=retriever,
        crime_patterns=crime_patterns,
        sample_size=args.sample_size,
    )

    final_report = {
        "meta": {
            "cases_count": len(cases),
            "laws_count": len(laws),
            "patterns_count": len(crime_patterns),
            "sample_size": args.sample_size,
            "top_k": args.top_k,
        },
        "retrieval": {
            "scan": retrieval_scan,
            "strict": retrieval_strict,
        },
        "mapping_modes": mapping_report,
    }

    out_path = os.path.join(args.output_dir, "paper_metrics.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(final_report, f, ensure_ascii=False, indent=2)

    csv_path, md_path = write_tables(final_report, args.output_dir)

    print("评测完成，输出文件：", out_path)
    print("表格文件：", csv_path, md_path)
    print(json.dumps(final_report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
