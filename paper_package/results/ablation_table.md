# 消融实验结果（自动生成）

## 表A 映射策略消融

| setting | fact_coverage | law_coverage | example_coverage | avg_case_count | criminal_law_hit_rate |
|---|---:|---:|---:|---:|---:|
| full_hybrid | 1 | 1 | 1 | 16.97 | 1 |
| w/o static mapping | 1 | 1 | 1 | 12 | 1 |
| w/o dynamic retrieval | 1 | 0.995 | 1 | 10.31 | 0.995 |

## 表B 法官标准注入消融（离线近似）

| setting | hit_at_k | top1_consistency | precision_target@k | mrr_target@k | law_support_rate | sample_size |
|---|---:|---:|---:|---:|---:|---:|
| full (with judge standard) | 1 | 0.995 | 0.454 | 0.9975 | 1 | 200 |
| w/o judge standard | 1 | 0.995 | 0.405 | 0.9975 | 1 | 200 |
| delta(full-wo) | 0 | 0.0 | 0.049 | 0.0 | 0 | - |
