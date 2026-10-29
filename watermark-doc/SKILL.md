---
name: watermark-doc
description: '给 PDF/Word 文档加防删除水印：每页渲染成图片后满屏平铺凌云智矿横版 logo + 中英双语警示文字（内部文件 禁止转载 / CONFIDENTIAL DO NOT DISTRIBUTE），再合成 PDF。水印已栅格化，无法通过删除文本层去除。Triggers: 打水印, 加水印, 水印版, 文档加密水印, 保密水印; NOT for: PDF加密口令、PDF编辑限制。'
version: 1.1.0
metadata:
  openclaw:
    requires:
      bins: ["python3"]
      python_pkgs: ["PyMuPDF", "Pillow"]
    os: ["darwin", "linux"]
---

# Watermark Doc（文档水印）

## 首次安装

```bash
bash {baseDir}/setup.sh
```

处理 Word(.docx) 文档需本机装有 LibreOffice（soffice）；否则请先把 docx 转成 PDF。

## 用法

```bash
{baseDir}/.venv/bin/python {baseDir}/scripts/watermark_pdf.py <文档.pdf|docx> [选项]

# 常用示例
... ~/Desktop/合同.docx                      # 输出 同名_水印版.pdf
... report.pdf --opacity 0.25               # 调浓一点（默认0.35）
... report.pdf --text "机密 · 严禁外传\nTOP SECRET"   # 自定义水印文字（\n 分行）
```

选项：
- `--logo PATH` 默认自带 `assets/lynai_mines_wordmark.png`（凌云智矿横版 logo）
- `--text TEXT` 默认两行：中文行 + 英文行；留空 `--text ""` 则只打 logo
- `--opacity 0~1` 整体浓度（默认 0.35；logo 浓度不会低于 0.35，保证品牌可辨识）
- `--dpi-scale N` 渲染倍率（默认 2，越高越清晰、越慢）

## 原理与安全特性

每页 → 高分辨率图片 → PIL 平铺水印（30° 斜角、logo 居上/两行文字居下）→ 图片合成 PDF。
**正文与水印全部栅格化，输出无文本层，水印无法通过删文本方式去除。**

## 治理

- 仅本地处理，不联网上传
- 输出文件名：`<原名>_水印版.pdf`（同目录）
- 只读源文件，不修改原件
