import re

with open('misora.py', encoding='utf-8') as f:
    src = f.read()

# Find _bind_shortcuts method content
m = re.search(r'def _bind_shortcuts\(self\)(.*?)(?=\n    def )', src, re.DOTALL)
if m:
    print(m.group(0)[:3000])
