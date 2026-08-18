"""实测 embedding 吞吐：batch 32 条。"""
import time

import requests

texts = ["这是一段测试文本，用于测量 embedding 吞吐。" * 10] * 32
t0 = time.time()
r = requests.post(
    "http://localhost:11434/v1/embeddings",
    json={"model": "qwen3-embedding:0.6b", "input": texts},
    timeout=300,
)
dt = time.time() - t0
print(f"batch 32 条耗时 {dt:.1f}s -> {32/dt:.1f} 条/秒, status={r.status_code}")
