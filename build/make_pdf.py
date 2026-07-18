#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将 Docs/用户手册.md 渲染为带中文排版的 HTML，再用 Edge/Chrome headless 打印为 PDF。

用法:
    python build/make_pdf.py
产物:
    Release-Package/Docs/用户手册.pdf
"""
import subprocess
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "Release-Package" / "Docs" / "用户手册.md"
OUT = ROOT / "Release-Package" / "Docs" / "用户手册.pdf"
TMP = ROOT / "build" / "_manual_tmp.html"

CSS = """
@page { size: A4; margin: 18mm 16mm; }
* { box-sizing: border-box; }
body {
  font-family: "Microsoft YaHei", "SimHei", "SimSun", "Source Han Serif SC", sans-serif;
  color: #1f1b26; font-size: 11pt; line-height: 1.75;
}
.container { max-width: 760px; margin: 0 auto; }
h1 { color: #6d28d9; font-size: 22pt; border-bottom: 3px solid #a855f7; padding-bottom: 8px; }
h2 { color: #7c3aed; font-size: 15pt; margin-top: 26px; border-left: 5px solid #a855f7; padding-left: 10px; }
h3 { color: #9333ea; font-size: 12.5pt; }
a { color: #a855f7; text-decoration: none; }
code, pre {
  font-family: "Cascadia Code", Consolas, "Microsoft YaHei", monospace;
  background: #f3eefb; border: 1px solid #e3d5f7; border-radius: 6px;
}
code { padding: 1px 5px; font-size: 9.5pt; }
pre { padding: 10px 12px; overflow-x: auto; line-height: 1.5; }
blockquote {
  margin: 12px 0; padding: 8px 14px; color: #4b4458;
  background: #f7f4fc; border-left: 4px solid #a855f7; border-radius: 4px;
}
table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 10pt; }
th, td { border: 1px solid #d8cdee; padding: 7px 9px; text-align: left; vertical-align: top; }
thead th { background: linear-gradient(90deg, #a855f7, #7c3aed); color: #fff; }
tbody tr:nth-child(even) { background: #faf7fe; }
hr { border: none; border-top: 1px solid #e3d5f7; margin: 22px 0; }
strong { color: #6d28d9; }
h1, h2, h3 { page-break-after: avoid; }
table, pre, blockquote { page-break-inside: avoid; }
"""


def find_browser():
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for c in candidates:
        if pathlib.Path(c).exists():
            return c
    return None


def main():
    try:
        import markdown
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "markdown"], check=True)
        import markdown

    if not SRC.exists():
        print(f"源文件不存在: {SRC}")
        sys.exit(1)

    md_text = SRC.read_text(encoding="utf-8")
    body = markdown.markdown(md_text, extensions=["tables", "fenced_code", "toc"])
    html = (
        "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>"
        f"<style>{CSS}</style></head><body><div class='container'>{body}</div></body></html>"
    )
    TMP.write_text(html, encoding="utf-8")

    browser = find_browser()
    if not browser:
        print("未找到 Edge/Chrome，无法生成 PDF")
        sys.exit(1)

    out_arg = f"--print-to-pdf={OUT}"
    cmd = [
        browser, "--headless", "--no-sandbox", "--disable-gpu",
        "--no-pdf-header-footer", out_arg, TMP.as_uri(),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=150)
    if OUT.exists() and OUT.stat().st_size > 0:
        print(f"OK PDF 已生成: {OUT} ({OUT.stat().st_size} 字节)")
    else:
        print("PDF 生成失败")
        print("returncode:", r.returncode)
        print("stderr:", r.stderr[-800:])
        sys.exit(1)


if __name__ == "__main__":
    main()
