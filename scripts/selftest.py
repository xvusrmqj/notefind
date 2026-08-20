"""快速自测：chunker + parsers。"""
from notefind.core.chunker import split_markdown
from notefind.core.parsers import parse_zim

md = """# 项目 A

简介段落。

## 设计

一些设计说明，超过目标长度时会按段落再切分。""" + "细节。" * 100 + """

```python
def foo():
    return 1
```

### 备注

- 点一
- 点二
"""

chunks = split_markdown(md)
for c in chunks:
    print(f"[{c.chunk_index}] ({c.heading}) len={len(c.content)}")
    print("   ", c.content[:60].replace("\n", "\\n"))

zim = """Content-Type: text/x-zim-wiki
Wiki-Format: zim 0.6

====== 标题一 ======
正文段落。

===== 子标题 =====
~~~python
code here
~~~
"""
parsed = parse_zim(zim)
print("\n--- zim -> markdown ---")
print(parsed.markdown)
