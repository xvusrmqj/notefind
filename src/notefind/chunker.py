"""Chunking：按 Markdown 结构切分，heading 路径记录到 heading 字段。

策略（docs/1-basic.md）：
- MarkdownHeaderTextSplitter 按标题层级切分
- RecursiveCharacterTextSplitter 兜底到 300~500 字符
- 代码块保持完整（过长则整体作为一个 chunk）
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

CHUNK_TARGET = 400   # 目标大小（300~500 中值）
CHUNK_OVERLAP = 50
MAX_HEADING_PATH = 80  # heading 路径最大长度

_HEADER_SPLITTER = MarkdownHeaderTextSplitter(
    headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3"), ("####", "h4")],
    strip_headers=False,
)

# 代码块优先切分：避免把 ``` 块切碎
_CODE_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_TARGET,
    chunk_overlap=0,
    separators=["\n```\n", "\n\n", "\n", "。", "；", ". ", " ", ""],
    keep_separator=True,
)

_FALLBACK_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_TARGET,
    chunk_overlap=CHUNK_OVERLAP,
)


@dataclass
class Chunk:
    chunk_index: int
    heading: str | None
    content: str


def _heading_path(meta: dict) -> str | None:
    parts = [meta.get(f"h{i}") for i in range(1, 5)]
    parts = [p.strip() for p in parts if p and p.strip()]
    if not parts:
        return None
    path = " / ".join(parts)
    return path[:MAX_HEADING_PATH]


def _has_code_fence(text: str) -> bool:
    return "```" in text


def split_markdown(markdown: str) -> list[Chunk]:
    """把 Markdown 正文切成带 heading 路径的 chunks。"""
    sections = _HEADER_SPLITTER.split_text(markdown)
    chunks: list[Chunk] = []

    for sec in sections:
        heading = _heading_path(sec.metadata)
        text = sec.page_content.strip()
        if not text:
            continue

        if len(text) <= CHUNK_TARGET:
            chunks.append(Chunk(0, heading, text))
            continue

        if _has_code_fence(text):
            # 代码块优先策略：尽量沿代码块边界切
            pieces = _CODE_SPLITTER.split_text(text)
        else:
            pieces = _FALLBACK_SPLITTER.split_text(text)

        for piece in pieces:
            piece = piece.strip()
            if piece:
                chunks.append(Chunk(0, heading, piece))

    for i, c in enumerate(chunks):
        c.chunk_index = i
    return chunks
