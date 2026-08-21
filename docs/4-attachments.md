# 第四步：附件向量化（已实施）

目标：把笔记中引用的附件（PDF / docx 等）提取文本、切分、向量化并入库，
让检索结果不只覆盖笔记正文，也覆盖附件内容。

> 范围说明：只处理**能提取出文本**的附件。图片、音频、视频不做 ——
> qwen3-embedding 是纯文本模型，图片需要 OCR 才有文本，收益低、依赖重
> （tesseract/PaddleOCR），不引入。

## 实施决策（2026-08-20）

| 决策点 | 选择 | 理由 |
| --- | --- | --- |
| 附件发现 | **仅显式引用**（不做 assets/ 目录扫描） | 范围可控、噪音少；目录扫描可作后续开关 |
| 格式范围 | **PDF + docx + 纯文本类**（txt/csv/json） | pypdf + docx2txt 轻依赖；pptx/xlsx 需 unstructured（系统级依赖重），列为后续迭代 |
| 迁移脚本 | **新建 `scripts/migrate_003.py`** | 与 002（全文检索）职责分离，均幂等 |
| 页码存储 | 写入现有 `chunks.heading`（如 `p.3`） | 免加列迁移；heading 本就是展示用字段 |

## 设计

### 1. 附件的发现（scanner.find_attachments）

只解析笔记中的**显式引用**，从笔记所在目录解析附件绝对路径：

- markdown：`![[xxx.pdf]]`（含 `![[x.pdf|400]]` 变体）、`[附件](a.docx)`
- zim：`{{xxx.pdf}}`（含 `{{x.pdf?width=400}}` 变体）

解析顺序：笔记同目录 → `assets/` / `attachments/` / `files/` 子目录（Obsidian 惯例）。
http(s)/mailto 链接跳过。返回 `附件路径 -> 引用它的笔记列表`。

### 2. 表结构变更（scripts/migrate_003.py，幂等）

复用现有 `documents` + `chunks` 表，扩展字段：

```sql
ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'note',
    -- kind: 'note' | 'attachment'
    ADD COLUMN IF NOT EXISTS mime_type TEXT,
    ADD COLUMN IF NOT EXISTS referenced_by BIGINT[]
    -- 引用该附件的笔记 document_id 列表（用于溯源展示）
```

附件同样走 `content_hash` + `mtime` 增量逻辑，与笔记一致。

### 3. 提取管线（parsers.extract_attachment，按后缀分发）

| 类型 | 提取方式 | 备注 |
| --- | --- | --- |
| PDF | `pypdf.PdfReader` 逐页 | 页码写入 chunk 的 `heading`（`p.3`） |
| docx | `docx2txt` 整篇 | 单个提取单元 |
| txt/csv/json | 直接读文本 | 单个提取单元 |
| 其他（图片/音视频/压缩包等） | 返回 None，跳过不入库 | 纯文本 embedding 模型无法处理 |

> 未用 langchain_community 的 loader：PyPDFLoader/Docx2txtLoader 只是薄封装，
> 直接用 pypdf/docx2txt 依赖更轻（无需 unstructured 系统库）。

提取失败不阻塞 sync：记录到 `stats.errors`，CLI 打错误列表。

### 4. 切分与向量化（sync）

- PDF 逐页预切后，每页再走现有 `chunker.split_markdown()`；
- embedding 走现有 `embedding.embed_documents_batched()`，无新依赖；
- 检索侧零改动 —— 附件 chunk 与笔记 chunk 在同一张 `chunks` 表，天然参与召回；
- `referenced_by` 在每次 sync 末尾**全量重算**回填（附件量少成本低，
  且能正确处理笔记增删引用链的情况）。

### 5. CLI / 展示

- `notefind sync`：附件与笔记统一编号，进度行 `[i/total] action path`；
- `notefind ask`：附件引用加 `[附件]` 前缀，heading 显示页码（`p.3`）；
- Web UI：检索/问答引用中附件显示「附件」标签 + 页码；
  `referenced_by` 字段已透传到 API（`Citation.referenced_by`），前端可反查引用笔记。

## 实施结果

1. [x] `scripts/migrate_003.py`：documents 加 kind/mime_type/referenced_by；check_schema.py 校验
2. [x] `parsers.extract_attachment()`：pypdf / docx2txt / 纯文本分发
3. [x] `scanner.find_attachments()`：markdown/zim 引用解析 + 路径解析
4. [x] `sync` 接入附件管线（增量逻辑复用 + referenced_by 全量回填）
5. [x] `retriever`/`webapi`/CLI/前端：kind/mime_type/referenced_by 透传与展示

## 后续迭代（可选）

- pptx / xlsx 支持（需 unstructured + 系统依赖）
- assets/attachments 目录扫描开关（覆盖未被引用的附件）
- 前端用 referenced_by 反查并展示引用笔记名
