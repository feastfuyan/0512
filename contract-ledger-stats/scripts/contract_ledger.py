#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
合同台账统计引擎 — 统计合同台账的付款及开票情况

功能：
  inspect  解析台账结构，输出识别的字段映射（先跑这个确认字段识别正确）
  stats    统计并输出 Excel 报表（总览/明细/付款分析/开票核销/预警清单）

兼容两种台账结构（自动识别）：
  宽表（合同执行台账）: 一行一合同，含合同金额/已付款/累计开票/执行状态等列
  长表（付款明细表）  : 一行一次付款，含支付日期/支付金额列，按合同名称聚合

用法示例：
  python3 contract_ledger.py inspect --file 台账.xlsx
  python3 contract_ledger.py stats --file 台账.xlsx --out 统计报表.xlsx [--unit 万元] [--ratio-threshold 0.8]
"""

import argparse
import re
import sys
from collections import defaultdict
from datetime import datetime

try:
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
except ImportError:
    sys.exit("缺少依赖 openpyxl，请先执行：pip install openpyxl")

# ============================================================
# 一、字段关键词映射（按优先级排列，命中即止）
# ============================================================
FIELD_KEYWORDS = {
    'contract_name': ['合同名称', '公司名称（合同名称）', '公司名称', '合同名', '项目名称', '名称'],
    'contract_no':   ['合同编号', '编号'],
    'party_a':       ['合同甲方', '甲方', '发包人', '委托方', '购买方', '建设单位'],
    'party_b':       ['合同乙方', '乙方', '承包方', '受托方', '服务方', '供应商', '销售方', '施工单位'],
    'sign_date':     ['签订日期', '签约日期', '签署日期', '合同日期'],
    'contract_amount': ['合同金额', '签约合同价', '合同总价', '合同价', '合同额', '签约价', '合同价款', '签约合同金额', '完成产值', '产值'],
    'paid_ratio':    ['已付款比例', '付款比例', '支付比例', '付款率', '已付比例'],
    'paid_amount':   ['累计支付总额', '累计支付', '累计付款', '已付款金额', '已付款', '已支付', '付款金额', '支付金额', '累计已付'],
    'unpaid_amount': ['未付款', '欠付', '未支付', '应付未付', '未付金额'],
    'invoice_amount': ['累计开票金额', '累计开票', '开票金额', '已开票', '发票金额', '开票'],
    'status':        ['执行情况', '执行状态', '合同状态', '状态', '完成情况', '履约情况'],
    'pay_date':      ['收/支付日期', '支付日期', '付款日期', '收付款日期'],
    'pay_count':     ['收/支付次数', '支付次数', '付款次数'],
    'pay_basis':     ['付款时间/付款依据', '付款依据', '付款节点', '支付依据', '依据'],
    'change':        ['是否有变更', '变更协议', '补充合同', '变更'],
    'remark':        ['备注', '说明'],
}

# 金额单位识别
UNIT_KW = {'万元': 1.0, '万': 1.0, '元': 0.0001}

# 汇总小计行关键词（跳过）
SUM_KW = re.compile(r'(合计|小计|总计|汇总|总计合计)')

# ============================================================
# 二、工具函数
# ============================================================
def norm(s):
    """列名规范化：去空白/换行/括号注记"""
    if s is None:
        return ''
    s = str(s)
    s = re.sub(r'[（(].*?[)）]', '', s)  # 去括号注记如"合同金额（万元）"→"合同金额"
    return s.replace(' ', '').replace('\n', '').replace('\u3000', '')


def match_field(col):
    """按关键词匹配列名 → 标准字段名，返回 None 表示未识别"""
    n = norm(col)
    for field, kws in FIELD_KEYWORDS.items():
        for kw in kws:
            if kw in n:
                return field
    return None


def parse_amount(v, unit_mult=1.0):
    """金额解析：数字/千分位字符串/带'万'/'元' → float（已乘单位系数）"""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v) * unit_mult
    s = str(v).strip()
    if s in ('', '-', '—', '/', 'None', 'nan'):
        return 0.0
    m = re.search(r'[-+]?\d[\d,]*(?:\.\d+)?', s)
    if not m:
        return 0.0
    num = float(m.group().replace(',', ''))
    mult = 1.0
    if '万' in s:
        mult = 10000.0
    elif '元' in s:
        mult = 1.0
    return num * mult * unit_mult


def parse_date(v):
    """日期解析：支持 datetime/date/各种分隔符格式，失败返回 None"""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    if hasattr(v, 'year'):
        try:
            return datetime(v.year, v.month, v.day)
        except Exception:
            return None
    s = str(v).strip().replace('/', '-').replace('.', '-')
    if not s or s in ('-', '—'):
        return None
    for fmt in ('%Y-%m-%d', '%Y-%m', '%Y'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    try:
        return datetime.strptime(s, '%Y%m%d')
    except ValueError:
        return None


def is_summary_row(v):
    """判断是否为合计/小计行"""
    if v is None:
        return False
    return bool(SUM_KW.search(str(v)))

# ============================================================
# 三、台账解析
# ============================================================
class Ledger:
    def __init__(self):
        self.contracts = []      # 合同级数据（宽表直接取 / 长表聚合）
        self.structure = None    # 'wide' | 'long'
        self.fields = {}         # 列名 → 标准字段
        self.unit = '万元'
        self.payments = []       # 长表：付款明细 [{name, date, amount, basis, count}]
        self.source_rows = 0
        self.meta_rows = 0       # 跳过的表头/合计行数

    def load(self, path):
        wb = load_workbook(path, data_only=True)
        ws = wb.worksheets[0] if wb.worksheets else None
        if ws is None:
            raise ValueError('Excel 中无工作表')
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            raise ValueError('工作表为空')

        # ---- 定位表头行：扫描前 15 行找含字段关键词最多的行 ----
        header_idx, best_score = 0, 0
        for i, row in enumerate(rows[:15]):
            if row is None:
                continue
            score = sum(1 for c in row[:20] if c is not None and match_field(c))
            if score > best_score:
                best_score, header_idx = score, i
        if best_score == 0:
            raise ValueError('未识别到表头，请人工确认列名（如"合同名称/合同金额/已付款金额"）')

        header = [norm(c) if c is not None else '' for c in rows[header_idx]]
        # 两级表头补全：仅当前列名为空时，用上一行同列名补全
        if header_idx > 0:
            prev = [norm(c) if c is not None else '' for c in rows[header_idx - 1]]
            header = [(prev[j] if header[j] == '' else header[j]) for j in range(min(len(header), len(prev)))]
        self.fields = {i: f for i, f in enumerate(header) if f}
        col_map = {}  # 列索引 → 标准字段
        for idx, cname in self.fields.items():
            f = match_field(cname)
            if f:
                col_map[idx] = f

        # ---- 单位识别：从列名/单位行，内部统一按"万元"计算 ----
        unit_mult = 1.0
        for row in rows[max(0, header_idx - 1):header_idx + 1]:
            for c in row:
                if isinstance(c, str) and '单位' in c:
                    for kw, m in UNIT_KW.items():
                        if kw in c:
                            self.unit = '万元'  # 内部统一口径，输出均标"万元"
                            unit_mult = m       # 万元:1.0 元:0.0001
                            break

        # ---- 结构识别：宽表（含合同金额+已付款/开票） vs 长表（含支付日期+支付金额） ----
        has_contract_amt = 'contract_amount' in col_map.values()
        has_pay_date = 'pay_date' in col_map.values()
        has_paid = 'paid_amount' in col_map.values() or 'invoice_amount' in col_map.values()
        if has_contract_amt and has_paid and not has_pay_date:
            self.structure = 'wide'
        elif has_pay_date and has_contract_amt:
            self.structure = 'long'
        elif has_pay_date and 'paid_amount' in col_map.values():
            self.structure = 'long'
        else:
            raise ValueError('无法识别台账结构：宽表需含"合同金额+已付款/开票"列，长表需含"支付日期+支付金额"列')

        # ---- 数据行解析 ----
        data_rows = rows[header_idx + 1:]
        for row in data_rows:
            if not row or all(c is None or str(c).strip() == '' for c in row):
                continue
            first_val = row[0] if row else None
            # 跳过"单位：元"等元信息行
            if isinstance(first_val, str) and ('单位' in first_val or '合计' in first_val or '金额' == first_val):
                self.meta_rows += 1
                continue
            # 跳过合计/小计行（合同名称列或付款依据列命中"合计"等关键词）
            skip = False
            for idx, f in col_map.items():
                if f in ('contract_name', 'pay_basis') and is_summary_row(row[idx]):
                    skip = True
                    break
            if skip:
                self.meta_rows += 1
                continue
            self._parse_row(row, col_map, unit_mult)

        if not self.contracts:
            raise ValueError('未解析到有效数据行')

        # 长表 → 按合同聚合
        if self.structure == 'long':
            self._aggregate_long()
        self.source_rows = len(data_rows)
        return self

    def _get(self, row, col_map, field):
        for idx, f in col_map.items():
            if f == field:
                return row[idx]
        return None

    def _parse_row(self, row, col_map, unit_mult):
        """解析单行 → 存入 contracts 或 payments"""
        name = self._get(row, col_map, 'contract_name')
        if name is None:
            name = self._get(row, col_map, 'party_b') or '未命名合同'
        name = str(name).strip()
        amt = parse_amount(self._get(row, col_map, 'contract_amount'), unit_mult)
        if self.structure == 'wide':
            paid = parse_amount(self._get(row, col_map, 'paid_amount'), unit_mult)
            inv = parse_amount(self._get(row, col_map, 'invoice_amount'), unit_mult)
            ratio_raw = self._get(row, col_map, 'paid_ratio')
            ratio = None
            if ratio_raw is not None:
                try:
                    ratio = float(str(ratio_raw).replace('%', '').strip())
                    if ratio > 1:
                        ratio = ratio / 100.0
                except ValueError:
                    ratio = None
            if ratio is None and amt > 0:
                ratio = paid / amt
            self.contracts.append({
                'name': name,
                'no': str(self._get(row, col_map, 'contract_no') or '').strip(),
                'party_a': str(self._get(row, col_map, 'party_a') or '').strip(),
                'party_b': str(self._get(row, col_map, 'party_b') or '').strip(),
                'sign_date': parse_date(self._get(row, col_map, 'sign_date')),
                'amount': amt,
                'paid': paid,
                'paid_ratio': ratio,
                'unpaid': parse_amount(self._get(row, col_map, 'unpaid_amount'), unit_mult),
                'invoice': inv,
                'status': str(self._get(row, col_map, 'status') or '').strip(),
                'change': str(self._get(row, col_map, 'change') or '').strip(),
                'remark': str(self._get(row, col_map, 'remark') or '').strip(),
            })
        else:  # long
            pd_ = self._get(row, col_map, 'pay_date')
            pa_ = self._get(row, col_map, 'paid_amount')
            self.payments.append({
                'name': name,
                'date': parse_date(pd_),
                'amount': parse_amount(pa_, unit_mult),
                'basis': str(self._get(row, col_map, 'pay_basis') or '').strip(),
                'count': self._get(row, col_map, 'pay_count'),
            })
            # 同时登记合同（金额从行内合同金额列取）
            amt_row = self._get(row, col_map, 'contract_amount')
            if amt_row is not None and not self._contract_exists(name):
                self.contracts.append({
                    'name': name,
                    'no': str(self._get(row, col_map, 'contract_no') or '').strip(),
                    'party_a': str(self._get(row, col_map, 'party_a') or '').strip(),
                    'party_b': str(self._get(row, col_map, 'party_b') or '').strip(),
                    'sign_date': parse_date(self._get(row, col_map, 'sign_date')),
                    'amount': parse_amount(amt_row, unit_mult),
                    'paid': 0.0, 'paid_ratio': None, 'unpaid': 0.0,
                    'invoice': 0.0, 'status': '', 'change': '', 'remark': '',
                })

    def _contract_exists(self, name):
        return any(c['name'] == name for c in self.contracts)

    def _aggregate_long(self):
        """长表：付款明细聚合回合同"""
        by = defaultdict(list)
        for p in self.payments:
            by[p['name']].append(p)
        for name, plist in by.items():
            paid = sum(p['amount'] for p in plist)
            c = next((c for c in self.contracts if c['name'] == name), None)
            if c is None:
                c = {'name': name, 'no': '', 'party_a': '', 'party_b': '', 'sign_date': None,
                     'amount': 0.0, 'paid': 0.0, 'paid_ratio': None, 'unpaid': 0.0,
                     'invoice': 0.0, 'status': '', 'change': '', 'remark': ''}
                self.contracts.append(c)
            c['paid'] = paid
            c['paid_ratio'] = (paid / c['amount']) if c['amount'] > 0 else None
            c['unpaid'] = max(c['amount'] - paid, 0.0) if c['amount'] > 0 else 0.0
            c['first_pay'] = min((p['date'] for p in plist if p['date']), default=None)
            c['last_pay'] = max((p['date'] for p in plist if p['date']), default=None)
            c['pay_times'] = sum(1 for p in plist if p['amount'] > 0)

# ============================================================
# 四、统计计算
# ============================================================
def compute_stats(led, use_ledger_unpaid=False):
    cs = [c for c in led.contracts if c['amount'] > 0 or c['paid'] > 0]
    total_amt = sum(c['amount'] for c in cs)
    total_paid = sum(c['paid'] for c in cs)
    total_inv = sum(c['invoice'] for c in cs)
    if use_ledger_unpaid:
        # 台账"按合同约定应付未付"为业务权威口径（可为负=超付待扣回），只计正数欠付
        total_unpaid = sum(max(c['unpaid'], 0) for c in cs)
    else:
        total_unpaid = max(total_amt - total_paid, 0)
    stats = {
        'total_contracts': len(cs),
        'total_amount': total_amt,
        'total_paid': total_paid,
        'total_unpaid': total_unpaid,
        'total_invoice': total_inv,
        'pay_ratio': (total_paid / total_amt) if total_amt > 0 else 0,
        'inv_ratio': (total_inv / total_amt) if total_amt > 0 else 0,
        'unit': led.unit,
    }
    # 按状态分组
    status_groups = defaultdict(lambda: {'count': 0, 'amount': 0.0, 'paid': 0.0})
    for c in cs:
        k = c['status'] or '未标注'
        status_groups[k]['count'] += 1
        status_groups[k]['amount'] += c['amount']
        status_groups[k]['paid'] += c['paid']
    stats['status'] = dict(status_groups)
    # 按乙方分组（top 10）
    party_groups = defaultdict(lambda: {'count': 0, 'amount': 0.0, 'paid': 0.0})
    for c in cs:
        k = c['party_b'] or '未标注'
        party_groups[k]['count'] += 1
        party_groups[k]['amount'] += c['amount']
        party_groups[k]['paid'] += c['paid']
    stats['parties'] = dict(sorted(party_groups.items(), key=lambda x: -x[1]['amount'])[:10])
    # 月度付款趋势（长表）
    monthly = defaultdict(float)
    for p in led.payments:
        if p['date']:
            monthly[p['date'].strftime('%Y-%m')] += p['amount']
    stats['monthly'] = dict(sorted(monthly.items()))
    return stats

def build_alerts(led, ratio_threshold=0.8, use_ledger_unpaid=False):
    """预警清单"""
    alerts = []
    for c in led.contracts:
        if c['amount'] <= 0:
            continue
        # 1. 未付款合同（有余额未付）
        if use_ledger_unpaid:
            unpaid = max(c['unpaid'], 0)  # 台账业务口径（可为负=超付）
        else:
            unpaid = max(c['amount'] - c['paid'], 0)
        if unpaid > 0.01:
            alerts.append(('欠付合同', c, f"未付 {unpaid:,.2f}，付款率 {(c['paid']/c['amount'])*100:.1f}%"))
        # 2. 付款率低于阈值
        if c['paid_ratio'] is not None and c['paid_ratio'] < ratio_threshold and unpaid > 0.01:
            alerts.append(('付款率偏低', c, f"付款率 {(c['paid_ratio'])*100:.1f}% < {ratio_threshold*100:.0f}%"))
        # 3. 已付未开票（付款>开票，乙方欠票）
        if c['invoice'] >= 0 and c['paid'] > c['invoice'] + 0.01:
            alerts.append(('已付未开票', c, f"已付 {c['paid']:,.2f} > 已开票 {c['invoice']:,.2f}，差额 {(c['paid']-c['invoice']):,.2f}"))
        # 4. 无开票记录
        if c['invoice'] == 0 and c['paid'] > 0:
            alerts.append(('未开票', c, "已付款但无开票记录"))
    return alerts

# ============================================================
# 五、Excel 输出（遵循公文表格规范）
# ============================================================
THIN = Side(style='thin', color='000000')
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEADER_FILL = PatternFill('solid', fgColor='CCCCCC')
F_TITLE = Font(name='方正小标宋简体', size=16, bold=True)
F_HEAD = Font(name='微软雅黑', size=11, bold=True)
F_BODY = Font(name='微软雅黑', size=11)
F_TOTAL = Font(name='微软雅黑', size=11, bold=True)
ALIGN_C = Alignment(horizontal='center', vertical='center')
ALIGN_L = Alignment(horizontal='left', vertical='center')

def _sheet_title(ws, text, ncols, row=1):
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=ncols)
    cell = ws.cell(row, 1, text)
    cell.font = F_TITLE
    cell.alignment = ALIGN_C
    ws.row_dimensions[row].height = 29

def _header_row(ws, headers, row=2):
    for j, h in enumerate(headers, 1):
        c = ws.cell(row, j, h)
        c.font = F_HEAD
        c.fill = HEADER_FILL
        c.alignment = ALIGN_C
        c.border = BORDER
    ws.row_dimensions[row].height = 22

def _fmt_cell(c, kind='num'):
    c.border = BORDER
    c.alignment = ALIGN_C
    c.font = F_BODY
    if kind == 'num':
        c.number_format = '#,##0.00'
    elif kind == 'pct':
        c.number_format = '0.0%'

def _auto_width(ws, widths):
    for j, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(j)].width = w

def _fmt_date(d):
    return d.strftime('%Y-%m-%d') if d else ''

def export_excel(led, stats, alerts, ratio_threshold, out_path, use_ledger_unpaid=False):
    wb = Workbook()
    ws0 = wb.active
    ws0.title = '00_统计总览'
    _sheet_title(ws0, f"合同台账付款及开票统计总览（单位：{led.unit}）", 4)
    items = [
        ('合同总份数', f"{stats['total_contracts']} 份"),
        ('合同总金额', f"{stats['total_amount']:,.2f}"),
        ('累计已付款', f"{stats['total_paid']:,.2f}"),
        ('尚欠未付款', f"{stats['total_unpaid']:,.2f}"),
        ('累计开票金额', f"{stats['total_invoice']:,.2f}"),
        ('综合付款比例', f"{stats['pay_ratio']*100:.1f}%"),
        ('综合开票比例', f"{stats['inv_ratio']*100:.1f}%"),
        ('预警事项数', f"{len(alerts)} 项"),
    ]
    for i, (k, v) in enumerate(items):
        r = 2 + i
        c1 = ws0.cell(r, 1, k); c1.font = F_HEAD; c1.border = BORDER; c1.alignment = ALIGN_C
        c2 = ws0.cell(r, 2, v); c2.font = F_BODY; c2.border = BORDER; c2.alignment = ALIGN_C
        ws0.merge_cells(start_row=r, start_column=2, end_row=r, end_column=4)
    _auto_width(ws0, [16, 14, 14, 14])

    # ---- 01 合同明细 ----
    ws1 = wb.create_sheet('01_合同明细')
    headers = ['序号', '合同名称', '合同编号', '甲方', '乙方', '签订日期', '合同金额', '已付款', '付款比例', '未付款', '累计开票', '开票-付款差额', '执行状态', '变更协议', '备注']
    _sheet_title(ws1, f"合同明细表（单位：{led.unit}）", len(headers))
    _header_row(ws1, headers)
    for i, c in enumerate(led.contracts, 1):
        r = 2 + i
        unpaid_cell = c['unpaid'] if use_ledger_unpaid else max(c['amount'] - c['paid'], 0)
        vals = [i, c['name'], c['no'], c['party_a'], c['party_b'], _fmt_date(c['sign_date']),
                c['amount'], c['paid'], c['paid_ratio'], unpaid_cell, c['invoice'],
                c['invoice'] - c['paid'], c['status'], c['change'], c['remark']]
        for j, v in enumerate(vals, 1):
            cell = ws1.cell(r, j, v)
            if j in (7, 8, 10, 11, 12):
                _fmt_cell(cell, 'num')
            elif j == 9:
                _fmt_cell(cell, 'pct')
            else:
                _fmt_cell(cell, 'txt')
                cell.alignment = ALIGN_L if j in (2, 3, 4, 5, 14, 15) else ALIGN_C
    # 合计行
    r = 2 + len(led.contracts) + 1
    ws1.cell(r, 2, '合计').font = F_TOTAL
    for j, v in [(7, stats['total_amount']), (8, stats['total_paid']), (11, stats['total_invoice'])]:
        cell = ws1.cell(r, j, v); _fmt_cell(cell, 'num'); cell.font = F_TOTAL
    _auto_width(ws1, [5, 32, 14, 18, 22, 12, 12, 12, 10, 12, 12, 12, 10, 10, 20])

    # ---- 02 付款分析 ----
    ws2 = wb.create_sheet('02_付款分析')
    # 状态分组
    h2 = ['合同执行状态', '合同份数', '合同金额', '已付款', '付款比例']
    _sheet_title(ws2, f"按执行状态汇总（单位：{led.unit}）", len(h2))
    _header_row(ws2, h2)
    for i, (k, v) in enumerate(stats['status'].items(), 1):
        r = 2 + i
        vals = [k, v['count'], v['amount'], v['paid'], v['paid'] / v['amount'] if v['amount'] else 0]
        for j, val in enumerate(vals, 1):
            cell = ws2.cell(r, j, val)
            _fmt_cell(cell, 'pct' if j == 5 else ('num' if j in (3, 4) else 'txt'))
    r0 = 2 + len(stats['status']) + 2  # TOP10 标题行（状态数据后空一行）
    h2b = ['乙方名称', '合同份数', '合同金额', '已付款', '付款比例']
    _sheet_title(ws2, f"乙方合同金额 TOP10（单位：{led.unit}）", len(h2b), row=r0)
    _header_row(ws2, h2b, row=r0 + 1)
    for i, (k, v) in enumerate(stats['parties'].items(), 1):
        r = r0 + 1 + i
        vals = [k, v['count'], v['amount'], v['paid'], v['paid'] / v['amount'] if v['amount'] else 0]
        for j, val in enumerate(vals, 1):
            cell = ws2.cell(r, j, val)
            _fmt_cell(cell, 'pct' if j == 5 else ('num' if j in (3, 4) else 'txt'))
    # 月度付款趋势
    if stats['monthly']:
        r1 = r0 + 1 + len(stats['parties']) + 2  # 月度趋势标题行
        h3 = ['月份', '付款金额']
        _sheet_title(ws2, f"付款月度趋势（单位：{led.unit}）", len(h3), row=r1)
        _header_row(ws2, h3, row=r1 + 1)
        for i, (k, v) in enumerate(stats['monthly'].items(), 1):
            c1 = ws2.cell(r1 + 1 + i, 1, k); _fmt_cell(c1, 'txt')
            c2 = ws2.cell(r1 + 1 + i, 2, v); _fmt_cell(c2, 'num')
        _auto_width(ws2, [24, 12, 12, 12, 10])

    # ---- 03 开票核销 ----
    ws3 = wb.create_sheet('03_开票核销')
    h3 = ['合同名称', '合同金额', '已付款', '累计开票', '开票比例', '已付未开差额', '核销状态']
    _sheet_title(ws3, f"开票与付款核销表（单位：{led.unit}）", len(h3))
    _header_row(ws3, h3)
    row = 2
    for c in led.contracts:
        if c['amount'] <= 0 and c['paid'] <= 0:
            continue
        diff = c['paid'] - c['invoice']
        if diff > 0.01:
            st = '已付未开（欠票）'
        elif diff < -0.01:
            st = '已开未付（预付开票）'
        elif c['invoice'] > 0:
            st = '已核销'
        else:
            st = '未开票'
        vals = [c['name'], c['amount'], c['paid'], c['invoice'],
                c['invoice'] / c['amount'] if c['amount'] > 0 else 0, diff, st]
        for j, v in enumerate(vals, 1):
            cell = ws3.cell(row, j, v)
            if j in (2, 3, 4, 6):
                _fmt_cell(cell, 'num')
            elif j == 5:
                _fmt_cell(cell, 'pct')
            else:
                _fmt_cell(cell, 'txt')
        row += 1
    _auto_width(ws3, [34, 12, 12, 12, 10, 14, 14])

    # ---- 04 预警清单 ----
    ws4 = wb.create_sheet('04_预警清单')
    h4 = ['序号', '预警类型', '合同名称', '乙方', '合同金额', '已付款', '预警说明']
    _sheet_title(ws4, f"合同风险预警清单（付款率阈值 {ratio_threshold*100:.0f}%）", len(h4))
    _header_row(ws4, h4)
    for i, (kind, c, msg) in enumerate(alerts, 1):
        r = 2 + i
        vals = [i, kind, c['name'], c['party_b'], c['amount'], c['paid'], msg]
        for j, v in enumerate(vals, 1):
            cell = ws4.cell(r, j, v)
            if j in (5, 6):
                _fmt_cell(cell, 'num')
            else:
                _fmt_cell(cell, 'txt')
    _auto_width(ws4, [5, 12, 34, 22, 12, 12, 44])

    wb.save(out_path)

# ============================================================
# 六、主入口
# ============================================================
def cmd_inspect(args):
    led = Ledger().load(args.file)
    print(f"台账结构：{'宽表（合同执行台账）' if led.structure == 'wide' else '长表（付款明细表）'}")
    print(f"金额单位：{led.unit}    数据行：{led.source_rows}   解析合同：{len(led.contracts)}")
    print("\n字段识别结果（列 → 标准字段）：")
    for idx, cname in led.fields.items():
        f = led.fields[idx]
        print(f"  第{idx + 1}列  {f!r:30s} → {match_field(f) or '（未识别）'}")
    print(f"\n提示：如字段识别有误，请检查列名是否含关键词，或人工调整台账列名后重试")

def cmd_stats(args):
    led = Ledger().load(args.file)
    stats = compute_stats(led, args.use_ledger_unpaid)
    alerts = build_alerts(led, args.ratio_threshold, args.use_ledger_unpaid)
    export_excel(led, stats, alerts, args.ratio_threshold, args.out, args.use_ledger_unpaid)
    # 控制台摘要
    print(f"台账结构：{'宽表' if led.structure == 'wide' else '长表'}（单位：{led.unit}）")
    print(f"合同份数：{stats['total_contracts']}    合同总金额：{stats['total_amount']:,.2f} {led.unit}")
    print(f"累计已付款：{stats['total_paid']:,.2f} {led.unit}（比例 {stats['pay_ratio']*100:.1f}%）")
    print(f"尚欠未付款：{stats['total_unpaid']:,.2f} {led.unit}")
    print(f"累计开票：{stats['total_invoice']:,.2f} {led.unit}（比例 {stats['inv_ratio']*100:.1f}%）")
    print(f"预警事项：{len(alerts)} 项")
    print(f"报表已生成：{args.out}")

def main():
    ap = argparse.ArgumentParser(description='合同台账统计引擎')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p1 = sub.add_parser('inspect', help='解析台账结构，输出字段识别结果')
    p1.add_argument('--file', required=True, help='台账文件路径（.xlsx；.xls 请先用 soffice 转换）')
    p2 = sub.add_parser('stats', help='统计并输出 Excel 报表')
    p2.add_argument('--file', required=True)
    p2.add_argument('--out', default='合同台账统计报表.xlsx')
    p2.add_argument('--unit', default=None, help='金额单位：万元/元（默认自动识别表头）')
    p2.add_argument('--ratio-threshold', type=float, default=0.8, help='付款率预警阈值，默认 0.8')
    p2.add_argument('--use-ledger-unpaid', action='store_true',
                    help='未付款用台账"应付未付"列原值（业务口径，可为负=超付待扣回）；默认用"金额-已付款"统一测算口径')
    args = ap.parse_args()
    if args.cmd == 'inspect':
        cmd_inspect(args)
    else:
        cmd_stats(args)

if __name__ == '__main__':
    main()
