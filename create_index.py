import argparse
import json
import os
import re

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"


def clean_text(text):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text


def build_case_text(case, fact_field="基本案情"):
    """
    构造索引文本：
    1) 优先使用指定事实字段；
    2) 为空时回退到裁判要旨；
    3) 再回退到案件名称，避免空向量。
    """
    text = clean_text(case.get(fact_field, ""))
    if not text:
        text = clean_text(case.get("裁判要旨", ""))
    if not text:
        text = clean_text(case.get("案件名称", ""))
    return text


def create_index(
    cases_path="resources/cases.json",
    index_path="resources/case_index.faiss",
    model_name="BAAI/bge-large-zh-v1.5",
    fact_field="基本案情",
    batch_size=32,
):
    with open(cases_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    texts = [build_case_text(case, fact_field=fact_field) for case in cases]
    if not texts:
        raise ValueError("案例为空，无法创建索引。")

    model = SentenceTransformer(model_name, device="cpu")
    vectors = []
    total = len(texts)
    for i in range(0, total, batch_size):
        chunk = texts[i : i + batch_size]
        vec = model.encode(
            chunk,
            batch_size=batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        vectors.append(vec.astype("float32"))
        if (i // batch_size) % 20 == 0:
            print(f"编码进度: {min(i + batch_size, total)}/{total}")

    matrix = np.ascontiguousarray(np.vstack(vectors), dtype=np.float32)
    dimension = matrix.shape[1]
    index = faiss.IndexFlatIP(dimension)
    index.add(matrix)
    faiss.write_index(index, index_path)
    print(f"索引创建成功！共 {len(texts)} 条案例 -> {index_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="创建案例向量索引")
    parser.add_argument("--cases_path", default="resources/cases.json")
    parser.add_argument("--index_path", default="resources/case_index.faiss")
    parser.add_argument("--model_name", default="BAAI/bge-large-zh-v1.5")
    parser.add_argument("--fact_field", default="基本案情")
    parser.add_argument("--batch_size", type=int, default=32)
    args = parser.parse_args()

    create_index(
        cases_path=args.cases_path,
        index_path=args.index_path,
        model_name=args.model_name,
        fact_field=args.fact_field,
        batch_size=args.batch_size,
    )
