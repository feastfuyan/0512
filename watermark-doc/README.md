# 凌云智矿 · 文档水印技能 (watermark-doc v1.1.0)

给 PDF / Word 文档加满屏防删除水印（横版 logo + 中英双语警示文字）。

## 同事安装（macOS / Linux）

```bash
cd watermark-doc-skill
bash setup.sh          # 自动建 venv 并装好 PyMuPDF / Pillow
```

## 使用

```bash
.venv/bin/python scripts/watermark_pdf.py 你的文档.pdf
# → 生成 你的文档_水印版.pdf
```

| 参数 | 默认 | 说明 |
|---|---|---|
| --opacity | 0.35 | 水印浓度 0~1 |
| --text | 内部文件 禁止转载 + 英文 | 支持 `\n` 分行 |
| --logo | 自带凌云智矿横版 logo | 可换 png（透明底最佳） |
| --dpi-scale | 2 | 清晰度倍率 |

## 注意
1. 处理 .docx 需安装 LibreOffice（或先转 PDF）
2. 水印为图片栅格化，删除文本层去不掉水印
3. 仅本地运行，无网络依赖
