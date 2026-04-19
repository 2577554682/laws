# 自动生成结果表

## 数据与设置

- 案例数：2001，法条数：452，映射罪名数：618
- sample_size=200，top_k=5，sampling=stratified

## 检索阈值扫描（best）

| best_threshold | hit_at_k | avg_retrieved_count | avg_similarity |
|---:|---:|---:|---:|
| 0.6 | 1 | 5 | 0.8485 |

## 检索严格评测

| threshold | hit@k | precision@k | mrr@k | ndcg@k | avg_retrieved_count |
|---:|---:|---:|---:|---:|---:|
| 0.45 | 1 | 0.405 | 0.9975 | 0.9703 | 5 |

## 映射模式对比

| mode | fact_coverage | law_coverage | example_coverage | avg_case_count | avg_fact_count | avg_law_count |
|---|---:|---:|---:|---:|---:|---:|
| dynamic | 1 | 1 | 1 | 12 | 5 | 5 |
| static | 1 | 0.995 | 1 | 10.31 | 3.22 | 2.65 |
| hybrid | 1 | 1 | 1 | 16.97 | 5 | 5 |
