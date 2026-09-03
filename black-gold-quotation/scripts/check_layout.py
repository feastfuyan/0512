#!/usr/bin/env python3
"""黑金报价单生成后门禁校验：确保 docx 表格布局兼容线上格式（腾讯文档/WPS）。

用法: python3 check_layout.py <file.docx>

检查项（任一失败即退出码 1）：
  1. 所有 tblW / tcW 均为 dxa 类型（禁止 pct 百分比——转线上格式会列宽错乱）
  2. 每个 tblGrid 的 gridCol 均为真实列宽（>500 twips；≤500 的窄列必须与表内
     声明同宽的 dxa tcW 匹配，即刻意设计的装饰性窄列——如封面金色竖条——才放行）
  3. 每个表格均声明 tblLayout w:type="fixed"
  4. 每个单元格均有 tcW 定义；vMerge 延续格（continue）必须有与 restart 格一致的 tcW 和 shd
  5. XML 可被解析、zip 结构完整
"""
import re
import sys
import zipfile

def fail(msgs, msg):
    msgs.append("FAIL " + msg)

def main(path):
    msgs = []
    ok = True
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8")
    except Exception as e:
        print("FAIL 无法读取 document.xml: %s" % e)
        return 1

    tables = re.findall(r"<w:tbl>.*?</w:tbl>", xml, re.S)
    if not tables:
        print("FAIL 未找到任何表格（黑金报价单应含功能清单/报价汇总/付款方式表）")
        return 1

    pct_w = re.findall(r'<w:(?:tblW|tcW) [^>]*w:type="pct"[^>]*/>', xml)
    if pct_w:
        fail(msgs, "发现 %d 处百分比宽度(pct)，线上格式转换会排版错乱: %s" % (len(pct_w), pct_w[0]))

    for i, tbl in enumerate(tables, 1):
        cols = re.findall(r'<w:gridCol w:w="(\d+)"', tbl)
        if not cols:
            fail(msgs, "表 %d: tblGrid 缺失" % i)
        bad = []
        for c in cols:
            if int(c) <= 500:
                # 窄列合法条件：表内存在声明为同一宽度的 dxa tcW —— 说明是刻意设计的
                # 装饰性窄列（如封面金色竖条），而非百分比表格残留的占位假 gridCol
                if not re.search(r'<w:tcW w:type="dxa" w:w="%s"' % c, tbl):
                    bad.append(c)
        if bad:
            fail(msgs, "表 %d: gridCol 存在占位假值 %s（应为真实 dxa 列宽）" % (i, bad))
        if sum(int(c) for c in cols) < 4000:
            fail(msgs, "表 %d: gridCol 合计宽 %s 过小，疑似假网格" % (i, sum(int(c) for c in cols)))
        if '<w:tblLayout w:type="fixed"' not in tbl:
            fail(msgs, "表 %d: 缺少 tblLayout fixed 声明" % i)
        rows = re.findall(r"<w:tr[ >].*?</w:tr>", tbl, re.S)
        restarts = {}  # 列索引 -> (tcW, shd)
        for r_i, row in enumerate(rows, 1):
            cells = re.findall(r"<w:tc>.*?</w:tc>", row, re.S)
            col = 0
            for c_i, cell in enumerate(cells, 1):
                tcpr_m = re.search(r"<w:tcPr>.*?</w:tcPr>", cell, re.S)
                tcpr = tcpr_m.group(0) if tcpr_m else ""
                is_restart = '<w:vMerge w:val="restart"' in tcpr
                is_cont = '<w:vMerge w:val="continue"' in tcpr
                has_tcw = '<w:tcW ' in tcpr
                has_shd = '<w:shd ' in tcpr
                if is_restart:
                    tcw = re.search(r'<w:tcW [^/]*/>', tcpr)
                    shd = re.search(r'<w:shd [^/]*/>', tcpr)
                    restarts[col] = (tcw.group(0) if tcw else None, shd.group(0) if shd else None)
                    if not has_tcw:
                        fail(msgs, "表 %d 行 %d 单元格 %d: vMerge restart 格缺 tcW" % (i, r_i, c_i))
                elif is_cont:
                    info = restarts.get(col)
                    if not has_tcw:
                        fail(msgs, "表 %d 行 %d 单元格 %d: vMerge 延续格缺 tcW（渲染时列宽错乱，用 fix_vmerge.py 补）" % (i, r_i, c_i))
                    elif info and info[0]:
                        cur = re.search(r'<w:tcW [^/]*/>', tcpr)
                        if cur and cur.group(0) != info[0]:
                            fail(msgs, "表 %d 行 %d 单元格 %d: vMerge 延续格 tcW 与 restart 不一致" % (i, r_i, c_i))
                    if info and info[1] and not has_shd:
                        fail(msgs, "表 %d 行 %d 单元格 %d: vMerge 延续格缺 shd 底色（与 restart 不一致，视觉断裂）" % (i, r_i, c_i))
                else:
                    if not has_tcw:
                        fail(msgs, "表 %d 行 %d 单元格 %d: 缺 tcW 宽度" % (i, r_i, c_i))
                gs = re.search(r'<w:gridSpan w:val="(\d+)"', tcpr)
                col += int(gs.group(1)) if gs else 1

    if msgs:
        ok = False
        for m in msgs:
            print(m)
    n_layout = len(re.findall(r'<w:tblLayout w:type="fixed"', xml))
    print("PASS 表格 %d 个 | fixed 布局 %d 处 | 无百分比宽度" % (len(tables), n_layout)) if ok else None
    return 0 if ok else 1

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法: python3 check_layout.py <file.docx>")
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
