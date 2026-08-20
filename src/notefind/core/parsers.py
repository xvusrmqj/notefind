"""解析器：把不同格式的笔记文件转成统一的 Markdown 文本。

统一输出 Markdown，后续 chunker 只需处理一种格式。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ParsedDoc:
    markdown: str  # 转成 Markdown 后的正文（不含 front matter）
    front_matter: dict = field(default_factory=dict)
    title: str | None = None


def parse_file(path: Path, source_type: str) -> ParsedDoc:
    text = path.read_text(encoding="utf-8", errors="replace")
    if source_type == "zim":
        return parse_zim(text)
    return parse_markdown(text)


# ---------------------------------------------------------------- markdown

FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_markdown(text: str) -> ParsedDoc:
    front_matter: dict = {}
    m = FRONT_MATTER_RE.match(text)
    if m:
        # 简单 key: value 解析（不引入 yaml 依赖）
        for line in m.group(1).splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                front_matter[k.strip()] = v.strip()
        text = text[m.end():]
    title = front_matter.get("title")
    if not title:
        h1 = re.search(r"^# (.+)$", text, re.MULTILINE)
        title = h1.group(1).strip() if h1 else None
    return ParsedDoc(markdown=text, front_matter=front_matter, title=title)


# ---------------------------------------------------------------- zim

ZIM_HEADER_RE = re.compile(r"\AContent-Type: text/x-zim-wiki(\r?\n|\r)")
ZIM_HEADING_RE = re.compile(r"^(={1,6})\s*(.+?)\s*\1\s*$", re.MULTILINE)
ZIM_CODEBLOCK_RE = re.compile(r"~~~(\w*)\s*\n(.*?)\n~~~", re.DOTALL)


def parse_zim(text: str) -> ParsedDoc:
    m = ZIM_HEADER_RE.match(text)
    if not m:
        # 不是 zim 文件，按纯文本处理
        return ParsedDoc(markdown=text)
    text = text[m.end():]

    # 去掉 wiki header 行（Creation-Date 等）
    lines = text.splitlines()
    body_start = 0
    for i, line in enumerate(lines):
        if re.match(r"^\S[\w-]*:", line):  # 如 Creation-Date: ...
            body_start = i + 1
        else:
            break
    text = "\n".join(lines[body_start:])

    # 代码块 ~~~ → ```（先转代码块，避免标题正则误伤内容）
    def _code(m: re.Match) -> str:
        return f"```{m.group(1)}\n{m.group(2)}\n```"

    text = ZIM_CODEBLOCK_RE.sub(_code, text)

    # 标题 ====== Title ====== → # Title（zim 的 = 个数与 md 级别相反：zim 6 个 = 是一级标题）
    def _heading(m: re.Match) -> str:
        level = 7 - len(m.group(1))  # zim: 6 -> md h1, 1 -> md h6
        return f"{'#' * level} {m.group(2)}"

    text = ZIM_HEADING_RE.sub(_heading, text)

    title = None
    h1 = re.search(r"^# (.+)$", text, re.MULTILINE)
    if h1:
        title = h1.group(1).strip()
    return ParsedDoc(markdown=text, title=title)
