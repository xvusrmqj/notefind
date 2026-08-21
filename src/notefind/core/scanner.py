"""目录扫描：发现笔记文件 + mtime 预过滤。"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from .config import NoteDir

# 各 source_type 对应的文件扩展名
EXTENSIONS: dict[str, tuple[str, ...]] = {
    "zim": (".txt",),
    "obsidian": (".md",),
    "logseq": (".md",),
    "markdown": (".md",),
}

# 跳过的目录名
SKIP_DIRS = {".git", ".obsidian", ".trash", "node_modules", ".logseq", ".smart-env"}

# 跳过的文件名模式（画板/附件元数据，无检索价值）
SKIP_NAME_PARTS = (".excalidraw", ".canvas")


@dataclass
class ScannedFile:
    path: Path
    source_type: str
    mtime: float
    kind: str = "note"  # 'note' | 'attachment'

    @property
    def file_path(self) -> str:
        return str(self.path)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def scan_dir(note_dir: NoteDir) -> list[ScannedFile]:
    """递归扫描目录，返回全部笔记文件（含 mtime）。"""
    exts = EXTENSIONS.get(note_dir.source_type, (".md",))
    files: list[ScannedFile] = []
    if not note_dir.path.is_dir():
        return files
    for p in sorted(note_dir.path.rglob("*")):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if any(part in p.name.lower() for part in SKIP_NAME_PARTS):
            continue
        if p.suffix.lower() not in exts:
            continue
        files.append(ScannedFile(path=p, source_type=note_dir.source_type, mtime=p.stat().st_mtime))
    return files


# ---------------------------------------------------------------- 附件发现

# 支持提取文本的附件后缀（与 parsers.ATTACH_MIME 保持一致）
ATTACH_EXTS = {".pdf", ".docx", ".txt", ".csv", ".json"}

# markdown / zim 中的附件引用语法
MD_EMBED_RE = re.compile(r"!\[\[([^\]|#]+?)(?:\|[^\]]*)?\]\]")  # ![[x.pdf]] / ![[x.pdf|400]]
MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+?\.(?:pdf|docx|txt|csv|json))\)", re.IGNORECASE)
# zim {{x.pdf}}（限定附件后缀，避免误捕 {{code: ...}} 等插件块）
ZIM_ATTACH_RE = re.compile(
    r"\{\{([^}|{}\s]+?\.(?:pdf|docx|txt|csv|json))(?:[|?][^}]*)?\}\}", re.IGNORECASE
)


def _resolve_attachment(note: ScannedFile, name: str) -> Path | None:
    """把笔记中的附件引用名解析为绝对路径（笔记所在目录 + 上级目录）。"""
    name = name.strip()
    if not name or name.startswith(("http://", "https://", "mailto:")):
        return None
    if not Path(name).suffix.lower() in ATTACH_EXTS:
        return None
    cand = (note.path.parent / name).resolve()
    if cand.is_file():
        return cand
    # Obsidian 惯例：附件常放 assets/ attachments/ 等子目录
    for sub in ("assets", "attachments", "files"):
        cand2 = (note.path.parent / sub / name).resolve()
        if cand2.is_file():
            return cand2
    return None


def find_attachments(notes: list[ScannedFile]) -> dict[str, list[Path]]:
    """解析笔记中的显式附件引用。

    返回 附件绝对路径(str) -> 引用它的笔记 Path 列表（去重）。
    """
    refs: dict[str, list[Path]] = {}
    for note in notes:
        try:
            text = note.path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        names: list[str] = []
        names += MD_EMBED_RE.findall(text)
        names += MD_LINK_RE.findall(text)
        if note.source_type == "zim":
            names += ZIM_ATTACH_RE.findall(text)
        for name in names:
            p = _resolve_attachment(note, name)
            if p is not None:
                lst = refs.setdefault(str(p), [])
                if note.path not in lst:
                    lst.append(note.path)
    return refs
