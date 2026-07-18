"""生成 Security/FileHash.txt：对 Release-Package 下所有文件计算 SHA256。

用法：python build/make_hash.py
输出：Release-Package/Security/FileHash.txt （每行: <sha256>  <相对路径>）
"""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "Release-Package"
lines = []
for p in sorted(ROOT.rglob("*")):
    if p.is_file() and p.name != "FileHash.txt":
        rel = p.relative_to(ROOT).as_posix()
        sha = hashlib.sha256(p.read_bytes()).hexdigest()
        lines.append(f"{sha}  {rel}")

out = ROOT / "Security" / "FileHash.txt"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"wrote {out} ({len(lines)} files)")
