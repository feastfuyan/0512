#!/bin/bash
# 一键安装水印技能依赖（macOS，Python3）
set -e
cd "$(dirname "$0")"
python3 -m venv .venv 2>/dev/null || true
./.venv/bin/pip install -q --upgrade pip
./.venv/bin/pip install -q -r requirements.txt
echo "环境就绪 ✅  用法: ./.venv/bin/python scripts/watermark_pdf.py <文档.pdf|docx>"
echo "可选: 处理 Word 文档需安装 LibreOffice (https://www.libreoffice.org) 或先把 docx 另存为 PDF"
