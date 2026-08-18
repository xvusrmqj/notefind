"""配置：从 .env / 环境变量读取。"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class NoteDir(BaseModel):
    """一个笔记目录：source_type + 路径。"""

    source_type: str
    path: Path

    @classmethod
    def parse(cls, raw: str) -> "NoteDir":
        """格式: source_type:/abs/path"""
        source_type, _, path = raw.partition(":")
        source_type = source_type.strip().lower()
        path = path.strip()
        if not source_type or not path:
            raise ValueError(f"非法的 NOTE_DIRS 条目: {raw!r}，应为 'source_type:/abs/path'")
        return cls(source_type=source_type, path=Path(path).expanduser().resolve())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql://notefind:123456@localhost:5432/notefind"

    llm_base_url: str = "http://localhost:8317/v1"
    llm_model: str = "glm-5.1"
    llm_api_key: str = "your-api-key-1"

    embed_base_url: str = "http://localhost:11434/v1"
    embed_model: str = "qwen3-embedding:0.6b"
    embed_api_key: str = "ollama"

    note_dirs_raw: str = Field(default="", alias="NOTE_DIRS")
    top_k: int = 10
    embed_batch_size: int = Field(default=32, ge=1, le=256)

    @field_validator("note_dirs_raw")
    @classmethod
    def _check_dirs(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("NOTE_DIRS 未配置，格式: zim:/path,obsidian:/path")
        return v

    @property
    def note_dirs(self) -> list[NoteDir]:
        return [NoteDir.parse(item) for item in self.note_dirs_raw.split(",") if item.strip()]


def load_settings() -> Settings:
    return Settings()
