"""目录扫描：发现笔记文件 + mtime 预过滤。"""

from __future__ import annotations

import hashlib
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


@dataclass
class ScannedFile:
    path: Path
    source_type: str
    mtime: float

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
        if p.suffix.lower() not in exts:
            continue
        files.append(ScannedFile(path=p, source_type=note_dir.source_type, mtime=p.stat().st_mtime))
    return files
