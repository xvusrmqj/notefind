# 第四步：附件向量化

目标：把笔记中引用的附件（PDF / Office 文档等）提取文本、切分、向量化并入库，
让检索结果不只覆盖笔记正文，也覆盖附件内容。

> 范围说明：只处理**能提取出文本**的附件（PDF / docx / pptx / xlsx / txt 等）。
> 图片、音频、视频不做 —— qwen3-embedding 是纯文本模型，图片需要 OCR 才有文本，
> 收益低、依赖重（tesseract/PaddleOCR），第一版先不引入。

## 现状与差距

第一版（sync + ask）只处理笔记正文：

```
scanner(发现 .md) → parsers(markdown→纯文本) → chunker → embedding → chunks
```

附件目前被 scanner 直接跳过，`documents` 表里也没有任何附件记录。

## 设计

### 1. 附件的发现

两种来源：

- **显式引用**：解析 markdown 中的 `![[xxx.pdf]]`、`[附件](a.docx)` 等链接，
  从笔记所在目录解析出附件的绝对路径。
- **同目录扫描**：笔记目录下的 `assets/`、`attachments/` 等文件夹中的文件，
  即使未被引用也纳入（可配置开关）。

### 2. 表结构变更

复用现有 `documents` + `chunks` 表，扩展字段：

```sql
ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'note',
    -- kind: 'note' | 'attachment'
    ADD COLUMN IF NOT EXISTS mime_type TEXT,
    ADD COLUMN IF NOT EXISTS referenced_by BIGINT[],
    -- 引用该附件的笔记 document_id 列表（用于溯源展示）
```

附件同样走 `content_hash` + `mtime` 增量逻辑，与笔记一致。

### 3. 提取管线（LangChain loader 按类型分发）

统一用 LangChain 的 document loader 提取文本，loader 输出的 `Document` 自带
`source` / `page` 等元数据，直接映射到 chunk 元数据：

| 类型 | Loader | 备注 |
| --- | --- | --- |
| PDF | `langchain_community.document_loaders.PyPDFLoader` | 逐页一个 Document，页码进 chunk 元数据 |
| docx | `Docx2txtLoader` | 整篇一个 Document |
| pptx | `UnstructuredPowerPointLoader` | 逐页一个 Document |
| xlsx | `UnstructuredExcelLoader` / `DataFrameLoader` | 按 sheet/行切 |
| 纯文本类 (txt/csv/json) | `TextLoader` / `CSVLoader` | 已基本支持 |
| 图片/音频/视频/压缩包 | 跳过，不入库 | 纯文本 embedding 模型无法处理 |

> 为什么可行：loader 只负责"文件 → 文本"这一步，提取出的文本和笔记正文一样
> 走 `chunker → embedding`，qwen3-embedding 对来源无感知。

提取失败不阻塞 sync：记录状态，CLI 打 warning。

### 4. 切分与向量化

- 复用现有 `chunker`，PDF 按页预切后再走通用切分；
- embedding 走现有 `embedding.embed_documents_batched()`，无新依赖；
- 检索侧无需改动 —— 附件 chunk 与笔记 chunk 在同一张 `chunks` 表，天然参与召回。

### 5. CLI / 展示

- `notefind sync`：进度输出区分 `[i/total] note|attach path`；
- `notefind ask`：回答引用来源时，附件 chunk 展示
  `文件名 + 页码/位置 + 引用它的笔记`（利用 `referenced_by` 反查）。

## 实施顺序

1. `documents` 加列（幂等迁移脚本 `scripts/migrate_002.py`）
2. `parsers` 增加附件提取器（LangChain loader 分发：PDF / docx / pptx / xlsx）
3. `scanner` 支持附件发现 + markdown 引用解析
4. `sync` 接入附件管线，`qa`/CLI 展示来源类型
