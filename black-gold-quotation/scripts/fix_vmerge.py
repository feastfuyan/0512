#!/usr/bin/env python3
"""
fix_vmerge.py — 修复 docx 表格纵向合并单元格（vMerge）缺失的宽度与底色

背景：docx 库的 rowSpan 会自动生成 vMerge continue 延续格，但这些延续格
     只有 <w:vMerge w:val="continue"/>，缺少：
       1. tcW 单元格宽度 —— 导致渲染器（尤其腾讯文档/WPS 线上转换）列宽计算错乱
       2. shd 底色 —— 导致合并列与斑马纹底色不一致（一段灰一段白）
     本脚本遍历所有表格，将 restart 格的 tcW / shd 复制到后续 continue 格，
     并按 OOXML schema 顺序重排 tcPr 子元素。

用法：
    python3 fix_vmerge.py 输入.docx [输出.docx]
    （不传输出名则原地修复；建议先备份）
"""
import re
import sys
import zipfile

# tcPr 子元素 schema 顺序
ORDER = [
    "tcW", "gridSpan", "hMerge", "vMerge", "tcBorders", "shd",
    "noWrap", "tcMar", "textDirection", "tcFitText", "vAlign", "hideMark",
]

_TAG_RE = re.compile(r"<w:(\w+)")
_CHILD_RE = re.compile(
    r"<w:(?:tcW|gridSpan|hMerge|vMerge|shd|noWrap|textDirection|tcFitText|vAlign|hideMark)[^>]*/>"
    r"|<w:tcBorders>.*?</w:tcBorders>"
    r"|<w:tcMar>.*?</w:tcMar>",
    re.S,
)


def reorder_tcpr(tcpr: str) -> str:
    """把 tcPr 内的子元素按 schema 顺序重排。"""
    inner = _CHILD_RE.findall(tcpr)
    if not inner:
        return tcpr

    def key(el: str) -> int:
        m = _TAG_RE.match(el)
        tag = m.group(1) if m else ""
        return ORDER.index(tag) if tag in ORDER else len(ORDER)

    inner.sort(key=key)
    return "<w:tcPr>" + "".join(inner) + "</w:tcPr>"


def fix_document_xml(xml: str) -> str:
    """修复 document.xml 中所有表格的 vMerge 延续格。"""

    def fix_table(tbl_m):
        tbl = tbl_m.group(0)
        # 保留 tblPr / tblGrid 等表头结构，只重建行
        tr_start = tbl.find("<w:tr")
        prefix = tbl[:tr_start] if tr_start > 0 else "<w:tbl>"
        rows = re.findall(r"<w:tr[ >].*?</w:tr>", tbl, re.S)
        new_rows = []
        restarts = {}  # 列索引 -> {'tcw': str, 'shd': str|None}
        for row in rows:
            cells = re.findall(r"<w:tc>.*?</w:tc>", row, re.S)
            new_cells = []
            col = 0
            for cell in cells:
                tcpr_m = re.search(r"<w:tcPr>.*?</w:tcPr>", cell, re.S)
                if not tcpr_m:
                    new_cells.append(cell)
                    col += 1
                    continue
                tcpr = tcpr_m.group(0)
                is_restart = "<w:vMerge w:val=\"restart\"/>" in tcpr
                is_cont = "<w:vMerge w:val=\"continue\"/>" in tcpr

                if is_restart:
                    tcw = re.search(r"<w:tcW [^/]*/>", tcpr)
                    shd = re.search(r"<w:shd [^/]*/>", tcpr)
                    restarts[col] = {
                        "tcw": tcw.group(0) if tcw else None,
                        "shd": shd.group(0) if shd else None,
                    }
                elif is_cont and col in restarts:
                    info = restarts[col]
                    # 补 tcW（放在 vMerge 之前）
                    if info["tcw"] and "<w:tcW " not in tcpr:
                        tcpr = tcpr.replace(
                            "<w:vMerge w:val=\"continue\"/>",
                            info["tcw"] + "<w:vMerge w:val=\"continue\"/>",
                            1,
                        )
                    # 补 shd（schema 顺序：vMerge 之后、tcMar 之前；用 reorder 兜底）
                    if info["shd"] and "<w:shd " not in tcpr:
                        tcpr = tcpr.replace("</w:tcPr>", info["shd"] + "</w:tcPr>", 1)
                    tcpr = reorder_tcpr(tcpr)
                    cell = cell[: tcpr_m.start()] + tcpr + cell[tcpr_m.end():]
                elif is_cont:
                    # 找不到 restart（异常表），仍重排 tcPr 保证合法
                    tcpr = reorder_tcpr(tcpr)
                    cell = cell[: tcpr_m.start()] + tcpr + cell[tcpr_m.end():]

                new_cells.append(cell)
                # gridSpan 会占多列
                gs = re.search(r"<w:gridSpan w:val=\"(\d+)\"/>", tcpr)
                if gs:
                    col += int(gs.group(1))
                else:
                    col += 1

            new_rows.append("<w:tr>" + "".join(new_cells) + "</w:tr>")
        return prefix + "".join(new_rows) + "</w:tbl>"

    return re.sub(r"<w:tbl>.*?</w:tbl>", fix_table, xml, flags=re.S)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else src

    # 安全：先读全量数据再写临时文件，成功后原子替换，绝不在原地以 "w" 模式打开
    zin = zipfile.ZipFile(src)
    items = list(zin.infolist())
    payloads = {it.filename: zin.read(it.filename) for it in items}
    xml = payloads["word/document.xml"].decode("utf-8")
    fixed = fix_document_xml(xml)
    payloads["word/document.xml"] = fixed.encode("utf-8")
    zin.close()

    n_cont_before = xml.count("<w:vMerge w:val=\"continue\"/>")

    import os
    tmp = dst + ".tmp"
    zout = zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED)
    for it in items:
        zout.writestr(it, payloads[it.filename])
    zout.close()
    os.replace(tmp, dst)  # 原子替换，避免半写损坏

    print("vMerge continue 格: %d 个，已补齐 tcW/shd" % n_cont_before)
    print("修复完成:", dst)


if __name__ == "__main__":
    main()
