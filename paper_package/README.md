# 论文可投包（最小版）

本目录用于快速生成“可写论文”的实验材料，包含：
- 一键评测脚本（检索 + 动态/静态/混合映射）
- 论文大纲模板
- 结果表模板

## 1. 一键运行实验

在项目根目录执行：

```bash
python evaluate_paper_package.py --sample_size 200 --top_k 5
```

输出文件：
- `paper_package/results/paper_metrics.json`

## 2. 指标含义

- `retrieval.hit_at_k`：检索结果中是否命中同罪名标签（弱监督）
- `retrieval.avg_retrieved_count`：平均返回案例数
- `retrieval.avg_similarity`：平均相似度
- `mapping_modes.*.fact_coverage`：是否能提取到事实模式
- `mapping_modes.*.law_coverage`：是否能提取到关联法条
- `mapping_modes.*.example_coverage`：是否能提取到参考案例

## 3. 论文写作建议

- 先写“系统设计+实验设置+结果分析+案例研究”
- 对比四组：`LLM-only`、`RAG-only`、`Static-only`、`Hybrid`
- 保留失败案例分析，提升审稿说服力

