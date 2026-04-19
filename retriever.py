# retriever.py
import os

# 设置 Hugging Face 国内镜像源（放在所有导入之前）
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

import json
import faiss
import numpy as np
import re
from collections import Counter
from sentence_transformers import SentenceTransformer


def _normalize_crime_text(crime_name: str) -> str:
    crime_name = (crime_name or "").strip()
    if not crime_name:
        return ""
    if crime_name.endswith("罪"):
        return crime_name
    return f"{crime_name}罪"


def _extract_fact_snippet(text: str, max_len: int = 150) -> str:
    text = re.sub(r"\s+", "", (text or ""))
    if len(text) <= max_len:
        return text
    # 优先按句号截断，避免截到半句
    cut = text[: max_len + 30]
    m = re.search(r"[。；;]", cut)
    if m and m.start() > 20:
        return cut[: m.start() + 1]
    return text[:max_len]


def get_crime_info(crime_name, cases, model, index, top_k=10):
    """
    动态检索与指定罪名相关的案例，并提取典型事实模式

    参数:
        crime_name: 罪名名称，如"诈骗罪"
        cases: 所有案例列表
        model: 向量模型
        index: FAISS索引
        top_k: 检索案例数量

    返回:
        {
            "fact_patterns": ["事实模式1", ...],  # 最多5条
            "law_articles": ["法条1", ...],      # 最多5条
            "example_cases": ["案例名1", ...],   # 最多3条
            "case_count": 相关案例总数
        }
    """
    if index is None or model is None or not cases:
        return {"fact_patterns": [], "law_articles": [], "example_cases": [], "case_count": 0}

    crime_name = _normalize_crime_text(crime_name)
    if not crime_name:
        return {"fact_patterns": [], "law_articles": [], "example_cases": [], "case_count": 0}

    # 1) 用罪名作为查询，检索相似案例
    query_vec = model.encode([crime_name], normalize_embeddings=True).astype(np.float32)
    search_k = min(max(top_k * 3, top_k), len(cases))
    scores, indices = index.search(query_vec, search_k)

    # 2) 获取相关案例（优先关键词包含该罪名）
    ranked = []
    for idx, score in zip(indices[0], scores[0]):
        if idx < 0 or idx >= len(cases):
            continue
        case = cases[idx]
        keywords = case.get("关键词", "")
        name = case.get("案件名称", "")
        reason = case.get("裁判理由", "")
        hit = 1 if (crime_name in keywords or crime_name in name or crime_name in reason) else 0
        ranked.append((hit, float(score), case))

    ranked.sort(key=lambda x: (x[0], x[1]), reverse=True)
    related_cases = [x[2] for x in ranked[:top_k]]

    # 3) 提取事实模式（按频次排序）
    facts = []
    for case in related_cases:
        snippet = _extract_fact_snippet(case.get("基本案情", ""), max_len=150)
        if snippet and len(snippet) > 20:
            facts.append(snippet)
    fact_counter = Counter(facts)
    fact_patterns = [x for x, _ in fact_counter.most_common(5)]

    # 4) 提取法条
    law_articles = list(
        dict.fromkeys(
            [
                case.get("关联索引", "").strip()
                for case in related_cases
                if case.get("关联索引", "").strip()
            ]
        )
    )[:5]

    # 5) 提取案例名称
    example_cases = [
        case.get("案件名称", f"案例{i + 1}")
        for i, case in enumerate(related_cases[:3])
    ]

    return {
        "fact_patterns": fact_patterns,
        "law_articles": law_articles,
        "example_cases": example_cases,
        "case_count": len(related_cases),
    }


class CaseRetriever:
    def __init__(self, cases_path="resources/cases.json", index_path="resources/case_index.faiss",
                 fact_field="基本案情"):
        print("正在加载模型，首次运行需要下载 1.3GB 文件，请耐心等待...")
        # 使用原始模型名称，镜像源会自动加速
        self.model = SentenceTransformer('BAAI/bge-large-zh-v1.5')
        print("模型加载成功！")

        self.cases = json.load(open(cases_path, "r", encoding="utf-8"))
        self.fact_field = fact_field
        try:
            self.index = faiss.read_index(index_path)
        except:
            self.index = None

    def retrieve(self, query, top_k=5, sim_threshold=0.45):
        if self.index is None:
            return [], [], []
        if not query or not query.strip():
            return [], [], []

        query_vec = self.model.encode(
            [query],
            normalize_embeddings=True
        ).astype(np.float32)
        scores, indices = self.index.search(query_vec, top_k)

        similar_cases = []
        score_list = []
        for idx, score in zip(indices[0], scores[0]):
            if idx < 0 or idx >= len(self.cases):
                continue
            if score < sim_threshold:
                continue
            case = dict(self.cases[idx])
            case["_similarity"] = round(float(score), 4)
            similar_cases.append(case)
            score_list.append(float(score))

        laws = set()
        for c in similar_cases:
            if "关联索引" in c:
                laws.add(c["关联索引"])
        return similar_cases, list(laws), score_list

    def get_crime_info(self, crime_name, top_k=10):
        """实例方法封装，便于在业务侧直接调用。"""
        return get_crime_info(
            crime_name=crime_name,
            cases=self.cases,
            model=self.model,
            index=self.index,
            top_k=top_k,
        )
