项目名称： notefind
使用RAG技术将本地笔记本嵌入到postgres中，支持一切离线文档的embedding, 如logseq, zim wiki, obsidian. 支持自然语言搜索。

已有本地chat llm model
```sh
curl --request post \
  --url http://localhost:8317/v1/chat/completions \
  --header 'Authorization: Bearer your-api-key-1' \
  --header 'Content-Type: application/json' \
  --data '{
  "model": "glm-5.1",
  "messages": [
    {
      "role": "user",
      "content": "Hello!"
    }
  ]
}'
```

已有本地embedding llm model
```sh
curl --request POST \
  --url http://localhost:11434/v1/embeddings \
  --header 'Content-Type: application/json' \
  --data '{
  "model": "qwen3-embedding:0.6b",
  "input": [
    "First sentence",
    "Second sentence",
    "Third sentence"
  ]
}'
```


## Roadmap

- [x] 第一步：基础版 —— 扫描入库 + 向量检索 + CLI 问答（docs/1-basic.md）
- [ ] 第二步：混合检索 —— 向量 + 全文 RRF 融合（docs/2-hybrid-search.md）
- [ ] 第三步：Web UI —— 搜索 / 问答 / 同步管理（docs/3-web-ui.md）
- [ ] 第四步：附件向量化 —— 用 LangChain loader 提取 PDF / Office 附件文本并入库（docs/4-attachments.md）

thinking：
- 笔记更新， 数据库中的向量怎么更新？
  - 每次全量找一遍就行（mtime 预过滤 + SHA-256 判断变化，详见 docs/1-basic.md）。
- 检索：向量 + 全文混合检索（RRF 融合），Qwen3 查询侧加 "query:" 前缀。
- 文件删除：同步删除 documents 行，cascade 清理 chunks。
