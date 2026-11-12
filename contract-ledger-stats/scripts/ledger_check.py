#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""contract-ledger-stats 交付质检脚本（ledger_check）。

对 contract_ledger.py 产出的统计报表做交付前结构自检（纯标准库读 xlsx：xlsx 本质是
zip + XML，本脚本用 zipfile 解析，不依赖 openpyxl）：
  1. 五表齐备——00_统计总览 / 01_合同明细 / 02_付款分析 / 03_开票核销 / 04_预警清单；
  2. 口径标注——总览须出现「万元」单位标注，避免单位口径混淆；
  3. 勾稽可用——总览与明细须同时存在，便于「明细行数 vs 合同份数」人工核对；
  4. 预警联动——报出预警事项数时须同时存在 04_预警清单 表；
  5. 台账体检（--mode ledger）——输入台账是否含关键字段（合同名称 / 合同金额 / 已付款）。

用法：
  python3 scripts/ledger_check.py --file <统计报表.xlsx>
  python3 scripts/ledger_check.py --file <台账.xlsx|台账.csv> --mode ledger

退出码：
  0 = 质检通过
  1 = 存在须修项（按「降级路径与失败模式」表补救后重跑）
  2 = 用法错误或文件不可读/非预期格式

仅依赖 Python 标准库（zipfile / csv / html / re / argparse）。
"""
import argparse
import csv
import html
import io
import os
import re
import sys
import zipfile

REQUIRED_SHEETS = ["00_统计总览", "01_合同明细", "02_付款分析", "03_开票核销", "04_预警清单"]
KEY_LEDGER_FIELDS = ["合同名称", "合同金额", "已付款"]
SUM_ROW_HINT = ("合计", "小计", "总计")
SHEET_RE = re.compile(r'<sheet[^>]*name="([^"]+)"')
TEXT_RE = re.compile(r"<t[^>]*>([^<]*)</t>")


def read_text(path):
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return f.read()
    except OSError as exc:
        print("无法读取文件：%s（%s）" % (path, exc))
        sys.exit(2)


def escaped_form(word):
    """返回中文词的 XML 数字字符引用形式（xlsx 内联字符串以 &#NNNNN; 存储）。"""
    return "".join("&#%d;" % ord(ch) for ch in word)


def raw_xml(path):
    """返回 xlsx 内 workbook 与各工作表的原始 XML 文本。"""
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            chunks = []
            if "xl/workbook.xml" in names:
                chunks.append(zf.read("xl/workbook.xml").decode("utf-8", "ignore"))
            for name in names:
                if name.startswith("xl/worksheets/") and name.endswith(".xml"):
                    chunks.append(zf.read(name).decode("utf-8", "ignore"))
            if "xl/sharedStrings.xml" in names:
                chunks.append(zf.read("xl/sharedStrings.xml").decode("utf-8", "ignore"))
    except (zipfile.BadZipFile, OSError) as exc:
        print("非有效 xlsx（%s）：%s" % (path, exc))
        sys.exit(2)
    return " ".join(chunks)


def contains_word(raw, word):
    """中英文混排文本命中判断：兼顾明文与数字字符引用两种存储形式。"""
    return (word in raw) or (escaped_form(word) in raw)


def sheet_names(path):
    names = SHEET_RE.findall(raw_xml(path))
    return names


def sheet_text(path):
    raw = raw_xml(path)
    return html.unescape(" ".join(TEXT_RE.findall(raw)))


def check_report(path):
    issues = []
    names = sheet_names(path)
    if not names:
        return ["xlsx 未解析出任何工作表"]
    missing = [s for s in REQUIRED_SHEETS if not any(s in n for n in names)]
    if missing:
        issues.append("缺工作表：%s（现有：%s）" % ("、".join(missing), "、".join(names)))
    raw = raw_xml(path)
    if not contains_word(raw, "万元"):
        issues.append("总览未见「万元」单位标注——金额口径须统一为万元两位小数")
    if not any("预警清单" in n for n in names) and contains_word(raw, "预警"):
        issues.append("报出预警事项却无 04_预警清单 表，预警无法追溯")
    if any("统计总览" in n for n in names) and not any("合同明细" in n for n in names):
        issues.append("有总览无明细——无法执行「明细行数 vs 合同份数」勾稽核对")
    return issues


def check_ledger_xlsx(path):
    """台账字段体检：从表内文本判断关键字段是否在册。"""
    issues = []
    names = sheet_names(path)
    if not names:
        return ["xlsx 未解析出任何工作表"]
    raw = raw_xml(path)
    for field in KEY_LEDGER_FIELDS:
        if not contains_word(raw, field):
            issues.append("台账缺关键字段：%s（请对照字段映射表改名后重跑）" % field)
    return issues


def check_ledger_csv(path, text):
    issues = []
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return ["CSV 无内容"]
    header = [c.strip() for c in rows[0]]
    if not header:
        return ["表头为空"]
    for field in KEY_LEDGER_FIELDS:
        if not any(field in h for h in header):
            issues.append("台账缺关键字段：%s（请对照字段映射表改名后重跑）" % field)
    body = rows[1:]
    sum_rows = [r for r in body
                if r and any(hint in (r[0] or "") for hint in SUM_ROW_HINT)]
    if sum_rows:
        issues.append("检出 %d 行合计/小计行混入主体数据，须确认脚本已跳过" % len(sum_rows))
    if not body:
        issues.append("无数据行（仅表头），统计结果将为 0")
    return issues


def main():
    ap = argparse.ArgumentParser(description="合同台账统计交付质检（TRACE 有效性门禁）")
    ap.add_argument("--file", required=True, help="统计报表 .xlsx 或台账 .xlsx/.csv")
    ap.add_argument("--mode", default="report", choices=["report", "ledger"],
                    help="report=校验统计报表；ledger=校验输入台账字段")
    args = ap.parse_args()

    if not os.path.isfile(args.file):
        print("文件不存在：%s" % args.file)
        sys.exit(2)

    if args.mode == "report":
        if not args.file.lower().endswith((".xlsx", ".xlsm")):
            print("mode=report 仅接受 .xlsx/.xlsm；.xls 请先用 soffice 转换为 .xlsx")
            sys.exit(2)
        issues = check_report(args.file)
    else:
        if args.file.lower().endswith(".csv"):
            issues = check_ledger_csv(args.file, read_text(args.file))
        else:
            issues = check_ledger_xlsx(args.file)

    if issues:
        print("质检未通过（%d 项须修）：" % len(issues))
        for item in issues:
            print("  -", item)
        print("处置：按 SKILL.md「降级路径与失败模式」表补救（重跑 stats、统一万元口径、"
              "补预警表、改列名后重跑 inspect）后重跑本脚本。")
        sys.exit(1)

    print("质检通过：%s（mode=%s）" % (args.file, args.mode))
    sys.exit(0)


if __name__ == "__main__":
    main()
