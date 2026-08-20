"""RAG 问答：检索 → 拼 context → LLM → 答案 + 引用。"""

from __future__ import annotations

from collections.abc import Iterator

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI

from .config import Settings
from .embedding import embed_query, make_embedder
from .retriever import RetrievalMode, SearchHit, hybrid_search

SYSTEM_PROMPT = """\
你是一个本地笔记检索助手。请仅根据下面的参考资料回答用户问题。
如果参考资料不足以回答，请明确说明"笔记中未找到相关信息"，不要编造。
回答末尾请列出引用来源。

参考资料：
{context}\
"""


def _format_context(hits: list[SearchHit]) -> str:
    parts = []
    for i, h in enumerate(hits, 1):
        heading = f"（{h.heading}）" if h.heading else ""
        parts.append(f"[{i}] {h.file_path}{heading}\n{h.content}")
    return "\n\n".join(parts)


def build_qa_chain(settings: Settings) -> Runnable:
    llm = ChatOpenAI(
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        temperature=0.1,
    )
    prompt = ChatPromptTemplate.from_messages(
        [("system", SYSTEM_PROMPT), ("human", "{question}")]
    )
    return prompt | llm | StrOutputParser()


def retrieve(
    settings: Settings,
    question: str,
    mode: RetrievalMode = RetrievalMode.hybrid,
) -> list[SearchHit]:
    embedder = make_embedder(
        settings.embed_base_url, settings.embed_model, settings.embed_api_key
    )
    query_vec = embed_query(embedder, question)
    return hybrid_search(
        query_vec,
        question,
        k=settings.top_k,
        tsv_config=settings.tsv_config,
        mode=mode,
    )


def ask(
    settings: Settings,
    question: str,
    mode: RetrievalMode = RetrievalMode.hybrid,
) -> tuple[str, list[SearchHit]]:
    """返回 (答案, 引用列表)。"""
    hits = retrieve(settings, question, mode=mode)
    if not hits:
        return "数据库中没有可检索的笔记，请先运行 `notefind sync`。", []
    chain = build_qa_chain(settings)
    answer = chain.invoke(
        {"question": question, "context": _format_context(hits)}
    )
    return answer, hits


def ask_stream(
    settings: Settings,
    question: str,
    mode: RetrievalMode = RetrievalMode.hybrid,
) -> tuple[list[SearchHit], Iterator[str]]:
    """流式问答：返回 (引用列表, token 迭代器)。

    检索（阻塞）先完成，随后 chain.stream() 逐 token 产出答案增量。
    """
    hits = retrieve(settings, question, mode=mode)
    if not hits:
        return [], iter(["数据库中没有可检索的笔记，请先运行 `notefind sync`。"])
    chain = build_qa_chain(settings)
    tokens = chain.stream(
        {"question": question, "context": _format_context(hits)}
    )
    return hits, tokens
