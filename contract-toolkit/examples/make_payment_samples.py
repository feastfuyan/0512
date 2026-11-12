#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成「合同付款核销」演示用的银行流水。

contract-toolkit 只负责把合同变成台账 —— **核销**（该付的付了没）是
`reconcile-toolkit` 的事。两个技能各管一段，中间用台账的「付款节点」sheet 衔接。

这个脚本造一份示例流水，好让那条跨技能链路能照着跑通：

    合同文件 --parse--> 合同台账 --recon--> 核销报告
                          银行流水 ^

数据刻意留了缺口，而不是全部匹配：
  · 三笔实付合计 580,000，比合同金额 600,000 少 20,000 —— 演示「该付的没付够」
  · 另有一笔 HT-2026-0007 与现有合同对不上 —— 演示「右表独有的记录」

对账工具的价值在于把差异摆出来；一份全部匹配的样例证明不了任何事。

**对账键用「合同编号」而不是「合同标识」**：台账的「合同标识」是文件名
（存量合同常常没有编号，用编号当主键会让去重与关联失效），流水里写的却是
合同编号 —— 两者字面上对不上，拿「合同标识」做键会得到 0 个匹配。
没有编号的合同，其编号列为空，reconcile-toolkit 会把它们单独归进
「键缺失」而不是拉去乱配（缺失值绝不参与配对）。

若你的流水没有「合同编号」这一列（财务导出的通常只有摘要文本），
可先用 `excel-toolkit` 从摘要里拆出编号列，再交给 recon。

用法：python examples/make_payment_samples.py [输出路径]
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

HEADER = ["交易日期", "合同编号", "对方名称", "收付方向", "金额", "摘要"]

ROWS = [
    ("2026-10-08", "XC-2026-1001", "上海云海电子设备有限公司", "付",
     180000.00, "XC-2026-1001 采购合同预付款 30%"),
    ("2027-01-15", "XC-2026-1001", "上海云海电子设备有限公司", "付",
     200000.00, "XC-2026-1001 采购合同进度款"),
    ("2027-10-20", "XC-2026-1001", "上海云海电子设备有限公司", "付",
     200000.00, "XC-2026-1001 采购合同尾款（尚欠 20000 未付）"),
    ("2026-11-03", "HT-2026-0007", "深圳市恒信信息技术有限公司", "付",
     35200.00, "HT-2026-0007 技术服务费首期款 40%"),
]


def main(argv: list[str]) -> int:
    out = (Path(argv[1]) if len(argv) > 1
           else Path(__file__).parent / "samples" / "示例银行流水.csv")
    out.parent.mkdir(parents=True, exist_ok=True)

    # utf-8-sig：Excel / WPS 直接双击打开不会把中文显示成乱码
    with out.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(HEADER)
        writer.writerows(ROWS)

    print(f"已生成：{out}（{len(ROWS)} 笔）")
    print(f"  XC-2026-1001 三笔合计 {180000 + 200000 + 200000}，"
          f"对合同金额 600000 差 20000 —— 这是刻意留的差异")
    print("\n接着跑合同级核销（键用合同编号，金额按同键汇总）：")
    print('  python <reconcile-toolkit>/scripts/reconcile_toolkit.py recon \\')
    print('      合同台账.xlsx "示例银行流水.csv" 核销结果.xlsx \\')
    print('      --left-sheet 合同台账 --on 合同编号 \\')
    print("      --left-amount 合同金额 --right-amount 金额 \\")
    print("      --aggregate --tolerance 0.01")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
