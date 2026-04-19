# 结果表（已填充当前实验数据，sample_size=200）

## 表1 检索阈值对比（scan，sample_size=200）

| threshold | sample_size | hit_at_k | avg_retrieved_count | avg_similarity |
|---|---:|---:|---:|---:|
| 0.35 | 200 | 1.0000 | 5 | 0.8485 |
| 0.40 | 200 | 1.0000 | 5 | 0.8485 |
| 0.45 | 200 | 1.0000 | 5 | 0.8485 |
| 0.50 | 200 | 1.0000 | 5 | 0.8485 |
| 0.55 | 200 | 1.0000 | 5 | 0.8485 |
| 0.60 | 200 | 1.0000 | 5 | 0.8485 |

## 表2 严格检索指标（strict）

| threshold | sample_size | hit_at_k | precision_at_k | mrr_at_k | ndcg_at_k | avg_retrieved_count | avg_similarity |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.45 | 200 | 1.0000 | 0.4050 | 0.9975 | 0.9703 | 5 | 0.8424 |

## 表3 映射模式对比（dynamic/static/hybrid，sample_size=200）

| mode | sample_size | fact_coverage | law_coverage | example_coverage | avg_case_count | avg_fact_count | avg_law_count |
|---|---:|---:|---:|---:|---:|---:|---:|
| dynamic | 200 | 1.0000 | 1.0000 | 1.0000 | 12.000 | 5.000 | 5.000 |
| static | 200 | 1.0000 | 0.9950 | 1.0000 | 10.310 | 3.220 | 2.650 |
| hybrid | 200 | 1.0000 | 1.0000 | 1.0000 | 16.970 | 5.000 | 5.000 |

## 表4 消融实验A：映射策略（sample_size=200）

| setting | fact_coverage | law_coverage | example_coverage | avg_case_count | criminal_law_hit_rate |
|---|---:|---:|---:|---:|---:|
| full_hybrid | 1.0000 | 1.0000 | 1.0000 | 16.970 | 1.0000 |
| w/o static mapping | 1.0000 | 1.0000 | 1.0000 | 12.000 | 1.0000 |
| w/o dynamic retrieval | 1.0000 | 0.9950 | 1.0000 | 10.310 | 0.9950 |

## 表5 消融实验B：法官标准注入（离线近似，sample_size=200）

| setting | hit_at_k | top1_consistency | precision_target_at_k | mrr_target_at_k | avg_similarity | law_support_rate |
|---|---:|---:|---:|---:|---:|---:|
| full (with judge standard) | 1.0000 | 0.9950 | 0.4540 | 0.9975 | 0.8368 | 1.0000 |
| w/o judge standard | 1.0000 | 0.9950 | 0.4050 | 0.9975 | 0.8424 | 1.0000 |
| delta(full-wo) | 0.0000 | 0.0000 | 0.0490 | 0.0000 | -0.0056 | 0.0000 |
