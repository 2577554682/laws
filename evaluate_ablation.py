import argparse
import json
import os
from statistics import mean

from evaluate_paper_package import (
    get_case_labels,
    get_query_text,
    get_static_info,
    get_hybrid_info,
    stratified_sample_by_first_label,
)
from retriever import CaseRetriever


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def evaluate_mapping_ablation(cases, retriever, crime_patterns, sample_size=200, seed=42):
    sampled = stratified_sample_by_first_label(cases, sample_size=sample_size, seed=seed)

    modes = {
        "full_hybrid": lambda crime: get_hybrid_info(crime, retriever, crime_patterns),
        "w_o_static_mapping": lambda crime: retriever.get_crime_info(crime, top_k=12),
        "w_o_dynamic_retrieval": lambda crime: get_static_info(crime, crime_patterns),
    }

    rows = {k: [] for k in modes}
    for case in sampled:
        labels = get_case_labels(case)
        if not labels:
            continue
        crime = labels[0]
        for mode, fn in modes.items():
            info = fn(crime)
            laws = info.get("law_articles", []) or []
            rows[mode].append(
                {
                    "fact_cov": 1 if info.get("fact_patterns") else 0,
                    "law_cov": 1 if laws else 0,
                    "example_cov": 1 if info.get("example_cases") else 0,
                    "avg_case_count": int(info.get("case_count", 0) or 0),
                    "criminal_law_hit": 1 if any("刑法" in str(x) for x in laws) else 0,
                }
            )

    out = {}
    for mode, rs in rows.items():
        if not rs:
            out[mode] = {
                "sample_size": 0,
                "fact_coverage": 0.0,
                "law_coverage": 0.0,
                "example_coverage": 0.0,
                "avg_case_count": 0.0,
                "criminal_law_hit_rate": 0.0,
            }
            continue
        out[mode] = {
            "sample_size": len(rs),
            "fact_coverage": round(mean([r["fact_cov"] for r in rs]), 4),
            "law_coverage": round(mean([r["law_cov"] for r in rs]), 4),
            "example_coverage": round(mean([r["example_cov"] for r in rs]), 4),
            "avg_case_count": round(mean([r["avg_case_count"] for r in rs]), 3),
            "criminal_law_hit_rate": round(mean([r["criminal_law_hit"] for r in rs]), 4),
        }
    return out


def evaluate_judge_standard_ablation(cases, retriever, sample_size=200, top_k=5, threshold=0.45, seed=42):
    """
    近似离线评测：
    - full_with_judge_standard: 查询=案情 + 罪名提示（模拟法官标准注入）
    - w_o_judge_standard: 查询=案情
    指标：Hit@K（同罪名标签是否命中）
    """
    sampled = stratified_sample_by_first_label(cases, sample_size=sample_size, seed=seed)
    mode_rows = {"full_with_judge_standard": [], "w_o_judge_standard": []}

    for case in sampled:
        labels = get_case_labels(case)
        if not labels:
            continue
        true_labels = set(labels)
        crime = labels[0]
        q = get_query_text(case)
        if not q:
            continue

        q_with_std = f"{q}\n法官修订标准目标结论：{crime}"
        for mode, query in [("full_with_judge_standard", q_with_std), ("w_o_judge_standard", q)]:
            retrieved, laws, scores = retriever.retrieve(query, top_k=top_k, sim_threshold=threshold)
            pred = []
            for c in retrieved:
                pred.append(set(get_case_labels(c)))

            hit = 1 if any(true_labels & p for p in pred) else 0
            top1_hit = 1 if (pred and (true_labels & pred[0])) else 0

            rel_count = sum(1 for p in pred if (true_labels & p))
            precision_target = (rel_count / len(pred)) if pred else 0.0

            mrr = 0.0
            for rank, p in enumerate(pred, start=1):
                if true_labels & p:
                    mrr = 1.0 / rank
                    break

            mode_rows[mode].append(
                {
                    "hit_at_k": hit,
                    "top1_consistency": top1_hit,
                    "precision_target_at_k": precision_target,
                    "mrr_target_at_k": mrr,
                    "avg_similarity": mean(scores) if scores else 0.0,
                    "law_support": 1 if laws else 0,
                }
            )

    out = {}
    for mode, rows in mode_rows.items():
        out[mode] = {
            "sample_size": len(rows),
            "hit_at_k": round(mean([r["hit_at_k"] for r in rows]), 4) if rows else 0.0,
            "top1_consistency": round(mean([r["top1_consistency"] for r in rows]), 4) if rows else 0.0,
            "precision_target_at_k": round(mean([r["precision_target_at_k"] for r in rows]), 4) if rows else 0.0,
            "mrr_target_at_k": round(mean([r["mrr_target_at_k"] for r in rows]), 4) if rows else 0.0,
            "avg_similarity": round(mean([r["avg_similarity"] for r in rows]), 4) if rows else 0.0,
            "law_support_rate": round(mean([r["law_support"] for r in rows]), 4) if rows else 0.0,
            "note": "该项为离线近似评估，用于论文消融展示。"
        }
    # 差值用于直接观察法官标准注入效果
    if out["full_with_judge_standard"]["sample_size"] and out["w_o_judge_standard"]["sample_size"]:
        out["delta_full_minus_wo"] = {
            "hit_at_k": round(out["full_with_judge_standard"]["hit_at_k"] - out["w_o_judge_standard"]["hit_at_k"], 4),
            "top1_consistency": round(out["full_with_judge_standard"]["top1_consistency"] - out["w_o_judge_standard"]["top1_consistency"], 4),
            "precision_target_at_k": round(out["full_with_judge_standard"]["precision_target_at_k"] - out["w_o_judge_standard"]["precision_target_at_k"], 4),
            "mrr_target_at_k": round(out["full_with_judge_standard"]["mrr_target_at_k"] - out["w_o_judge_standard"]["mrr_target_at_k"], 4),
            "avg_similarity": round(out["full_with_judge_standard"]["avg_similarity"] - out["w_o_judge_standard"]["avg_similarity"], 4),
            "law_support_rate": round(out["full_with_judge_standard"]["law_support_rate"] - out["w_o_judge_standard"]["law_support_rate"], 4),
        }
    return out


def write_md(report, out_dir):
    path = os.path.join(out_dir, "ablation_table.md")
    m = report["mapping_ablation"]
    j = report["judge_standard_ablation"]
    with open(path, "w", encoding="utf-8") as f:
        f.write("# 消融实验结果（自动生成）\n\n")
        f.write("## 表A 映射策略消融\n\n")
        f.write("| setting | fact_coverage | law_coverage | example_coverage | avg_case_count | criminal_law_hit_rate |\n")
        f.write("|---|---:|---:|---:|---:|---:|\n")
        f.write(f"| full_hybrid | {m['full_hybrid']['fact_coverage']} | {m['full_hybrid']['law_coverage']} | {m['full_hybrid']['example_coverage']} | {m['full_hybrid']['avg_case_count']} | {m['full_hybrid']['criminal_law_hit_rate']} |\n")
        f.write(f"| w/o static mapping | {m['w_o_static_mapping']['fact_coverage']} | {m['w_o_static_mapping']['law_coverage']} | {m['w_o_static_mapping']['example_coverage']} | {m['w_o_static_mapping']['avg_case_count']} | {m['w_o_static_mapping']['criminal_law_hit_rate']} |\n")
        f.write(f"| w/o dynamic retrieval | {m['w_o_dynamic_retrieval']['fact_coverage']} | {m['w_o_dynamic_retrieval']['law_coverage']} | {m['w_o_dynamic_retrieval']['example_coverage']} | {m['w_o_dynamic_retrieval']['avg_case_count']} | {m['w_o_dynamic_retrieval']['criminal_law_hit_rate']} |\n\n")

        f.write("## 表B 法官标准注入消融（离线近似）\n\n")
        f.write("| setting | hit_at_k | top1_consistency | precision_target@k | mrr_target@k | law_support_rate | sample_size |\n")
        f.write("|---|---:|---:|---:|---:|---:|---:|\n")
        f.write(
            f"| full (with judge standard) | {j['full_with_judge_standard']['hit_at_k']} | "
            f"{j['full_with_judge_standard']['top1_consistency']} | {j['full_with_judge_standard']['precision_target_at_k']} | "
            f"{j['full_with_judge_standard']['mrr_target_at_k']} | {j['full_with_judge_standard']['law_support_rate']} | "
            f"{j['full_with_judge_standard']['sample_size']} |\n"
        )
        f.write(
            f"| w/o judge standard | {j['w_o_judge_standard']['hit_at_k']} | "
            f"{j['w_o_judge_standard']['top1_consistency']} | {j['w_o_judge_standard']['precision_target_at_k']} | "
            f"{j['w_o_judge_standard']['mrr_target_at_k']} | {j['w_o_judge_standard']['law_support_rate']} | "
            f"{j['w_o_judge_standard']['sample_size']} |\n"
        )
        if "delta_full_minus_wo" in j:
            d = j["delta_full_minus_wo"]
            f.write(
                f"| delta(full-wo) | {d['hit_at_k']} | {d['top1_consistency']} | "
                f"{d['precision_target_at_k']} | {d['mrr_target_at_k']} | {d['law_support_rate']} | - |\n"
            )
    return path


def main():
    parser = argparse.ArgumentParser(description="论文消融实验脚本")
    parser.add_argument("--cases_path", default="resources/cases.json")
    parser.add_argument("--index_path", default="resources/case_index.faiss")
    parser.add_argument("--patterns_path", default="resources/crime_patterns.json")
    parser.add_argument("--sample_size", type=int, default=200)
    parser.add_argument("--top_k", type=int, default=5)
    parser.add_argument("--threshold", type=float, default=0.45)
    parser.add_argument("--output_dir", default="paper_package/results")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    cases = load_json(args.cases_path)
    patterns = load_json(args.patterns_path) if os.path.exists(args.patterns_path) else {}
    retriever = CaseRetriever(cases_path=args.cases_path, index_path=args.index_path, fact_field="基本案情")

    mapping_ablation = evaluate_mapping_ablation(
        cases=cases,
        retriever=retriever,
        crime_patterns=patterns,
        sample_size=args.sample_size,
    )
    judge_ablation = evaluate_judge_standard_ablation(
        cases=cases,
        retriever=retriever,
        sample_size=args.sample_size,
        top_k=args.top_k,
        threshold=args.threshold,
    )

    report = {
        "meta": {
            "cases_count": len(cases),
            "patterns_count": len(patterns),
            "sample_size": args.sample_size,
            "top_k": args.top_k,
            "threshold": args.threshold,
        },
        "mapping_ablation": mapping_ablation,
        "judge_standard_ablation": judge_ablation,
    }
    json_path = os.path.join(args.output_dir, "ablation_metrics.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    md_path = write_md(report, args.output_dir)

    print("消融评测完成：", json_path)
    print("消融表格：", md_path)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
