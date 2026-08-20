"""Embedding 客户端：OpenAI 兼容接口（qwen3-embedding:0.6b, 1024 维）。

Qwen3-Embedding 为非对称检索模型：
- 文档侧不加前缀
- 查询侧加 "query: " 前缀
"""

from __future__ import annotations

import time

from langchain_openai import OpenAIEmbeddings

# Qwen3-Embedding 指令格式：Instruct 描述任务，Query 为查询内容（大写 Q，必需）
INSTRUCT = "Given a note search query, retrieve relevant note chunks that answer the query"
QUERY_PREFIX = f"Instruct: {INSTRUCT}\nQuery: "


def make_embedder(base_url: str, model: str, api_key: str) -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        base_url=base_url,
        model=model,
        api_key=api_key,
        # qwen3-embedding 输出 1024 维
        dimensions=1024,
        check_embedding_ctx_length=False,
    )


def embed_query(embedder: OpenAIEmbeddings, query: str) -> list[float]:
    """查询侧：加 instruction 前缀。"""
    return embedder.embed_query(QUERY_PREFIX + query)


def embed_documents_batched(
    embedder: OpenAIEmbeddings,
    texts: list[str],
    batch_size: int,
    pause_ms: int = 0,
) -> list[list[float]]:
    """文档侧：不加前缀，批量 embedding。

    pause_ms: 批间停顿（毫秒），CPU 推理时给散热留间隙，避免持续满载。
    """
    vectors: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        if i and pause_ms:
            time.sleep(pause_ms / 1000)
        vectors.extend(embedder.embed_documents(texts[i : i + batch_size]))
    return vectors
