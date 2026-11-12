#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""contract-toolkit 单元测试。

测试样本**不依赖任何真实合同文件**（合同含商业隐私，不可随包分发），全部由
`examples/make_samples.py` 现场生成，或在本文件内以文本常量给出，可审阅、可复现。

两条本项目踩过的铁律，写测试时必须遵守：

1. **不要重复定义同名测试函数**。Python 用后定义覆盖前定义，旧断言被静默丢弃，
   而 pytest 照常全绿、不报任何错（`skill-preflight-check/scripts/check_tests.py`
   可检出）。本文件按分节注释组织，新增用例请追加到对应分节末尾。
2. **断言要按实测写，不要按「看起来合理」写**。写之前先跑一遍把真实取值打印出来。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts"
EXAMPLES_DIR = ROOT / "examples"
for _p in (SCRIPTS_DIR, EXAMPLES_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import contract_toolkit as ct  # noqa: E402
import make_samples as ms  # noqa: E402


# ---------------------------------------------------------------------------
# 公用测试文本
# ---------------------------------------------------------------------------

TXT_CLAUSE = """
甲方（采购方）：北京星辰科技有限公司
乙方（供货方）：上海云海电子设备有限公司

第一条 合同标的
甲方向乙方采购服务器设备一批，单价为人民币 12,000 元/台，共计 50 台。

第二条 合同价款
本合同总价款为人民币陆拾万元整（600,000.00元），含增值税，税率 13%。

第三条 付款方式
合同签订后 5 个工作日内，甲方支付预付款 30%，即人民币 180,000 元；
货到验收合格后 30 日内支付尾款 70%，即人民币 420,000 元。
质保金为合同总价的 5%，从尾款中扣留。

第四条 违约责任
乙方逾期交货的，每逾期一日按合同总价的 0.5% 向甲方支付违约金。

第六条 合同期限
本合同自 2026 年 10 月 1 日起生效，有效期至 2027 年 9 月 30 日止。
"""

TXT_SENTENCE_TRAP = """
甲方支付预付款 30%，即人民币 180,000 元。
甲方应于协议签署之日起三日内支付首期款 40%。
本协议不约定固定金额，各批次货款按订单确认的单价结算。
"""

TXT_SPAN = "服务期限自 2026 年 11 月 1 日至 2027 年 4 月 30 日。"


def regions_of(text: str) -> ct.Regions:
    return ct.split_regions(text)


def record_of(tmp_path: Path, text: str, name: str = "c.txt", our: str | None = None):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return ct.build_record(p, our)


# ===========================================================================
# 分节 1 · 中文大写金额解析（第一层，确定性）
# ===========================================================================

def test_cn_amount_wu_wan():
    assert ct.parse_cn_amount("陆拾万元整") == 600000.0


def test_cn_amount_with_yuan_and_jiao():
    assert ct.parse_cn_amount("叁万壹仟贰佰伍拾元整") == 31250.0


def test_cn_amount_jiao_fen():
    assert ct.parse_cn_amount("壹佰贰拾叁元肆角伍分") == 123.45


def test_cn_amount_omitted_leading_one():
    """「拾万」= 十万，省略了「壹」。"""
    assert ct.parse_cn_amount("拾万元整") == 100000.0


def test_cn_amount_yi_section():
    assert ct.parse_cn_amount("壹亿贰仟万元整") == 120000000.0


def test_cn_amount_with_rmb_prefix():
    assert ct.parse_cn_amount("人民币壹万元整") == 10000.0


def test_cn_amount_simplified_characters():
    assert ct.parse_cn_amount("一百二十三元") == 123.0


def test_cn_amount_zero():
    assert ct.parse_cn_amount("零元整") == 0.0


def test_cn_amount_full_width_colon_stripped():
    assert ct.parse_cn_amount("（人民币）：壹万元整") == 10000.0


def test_cn_amount_none_and_empty_return_none():
    assert ct.parse_cn_amount(None) is None
    assert ct.parse_cn_amount("") is None


def test_cn_amount_without_chinese_digits_returns_none():
    assert ct.parse_cn_amount("abc123") is None


def test_cn_amount_wan_yi_combination():
    """「壹亿零伍佰万」这类跨节数字。"""
    assert ct.parse_cn_amount("壹亿元整") == 100000000.0


# ===========================================================================
# 分节 2 · 阿拉伯金额解析与数值归一
# ===========================================================================

def test_arabic_amount_with_thousand_separator():
    assert ct.parse_arabic_amount("1,234,567.89") == 1234567.89


def test_arabic_amount_wan_unit():
    assert ct.parse_arabic_amount("60", "万") == 600000.0


def test_arabic_amount_yi_unit():
    assert ct.parse_arabic_amount("1.2", "亿") == 120000000.0


def test_arabic_amount_invalid_returns_none():
    assert ct.parse_arabic_amount("abc") is None


def test_norm_amount_integer_has_no_decimal():
    assert ct.norm_amount(600000.0) == "600000"


def test_norm_amount_two_decimals_kept():
    assert ct.norm_amount(1234.5) == "1234.50"


def test_norm_amount_empty_input():
    assert ct.norm_amount(None) == ""


def test_norm_date_valid():
    assert ct.norm_date(2026, 10, 1) == "2026-10-01"


def test_norm_date_rejects_illegal_day():
    assert ct.norm_date(2026, 2, 30) is None


# ===========================================================================
# 分节 3 · 区域切分
# ===========================================================================

def test_split_regions_cuts_at_clause_header():
    r = regions_of(TXT_CLAUSE)
    assert "甲方（采购方）" in r.head
    assert "第二条" in r.body


def test_split_regions_without_headers_falls_back_to_char_count():
    r = regions_of("这是一份没有条款标题的简单协议。" * 40)
    assert len(r.head) == 600


def test_split_regions_empty_text():
    r = regions_of("")
    assert r.head == "" and r.body == "" and r.whole == ""


def test_split_regions_tail_present():
    r = regions_of(TXT_CLAUSE)
    assert len(r.tail) > 0


# ===========================================================================
# 分节 4 · 锚点判定（消歧的地基）
# ===========================================================================

def test_nearest_anchor_total():
    text = "本合同总价款为人民币 600,000 元"
    kind, anchor, _ = ct.nearest_anchor(text, text.index("600"))
    assert kind == "total"
    assert anchor == "总价款"


def test_nearest_anchor_prefers_closest_not_first():
    """「预付款」比更早出现的「总价」更近，必须判为 node。"""
    text = "合同总价的 30%，即人民币 180,000 元"
    text = "甲方支付预付款 30%，即人民币 180,000 元"
    kind, _, _ = ct.nearest_anchor(text, text.index("180"))
    assert kind == "node"


def test_nearest_anchor_unit_price():
    text = "单价为人民币 12,000 元/台"
    kind, _, _ = ct.nearest_anchor(text, text.index("12"))
    assert kind == "unit"


def test_nearest_anchor_none_when_no_anchor():
    kind, anchor, dist = ct.nearest_anchor("共计人民币 500 元", 2)
    assert kind == "" and anchor == "" and dist == -1


# ===========================================================================
# 分节 5 · 金额抽取与消歧（第二层核心）
# ===========================================================================

def test_amount_percent_not_treated_as_money():
    """「合同总价的 5%」里的 5 不是金额 —— 没有货币标记就必须排除。"""
    cands = ct.extract_amounts(regions_of(TXT_CLAUSE))
    values = {float(c.value) for c in cands}
    assert 5.0 not in values
    assert 0.5 not in values


def test_amount_unit_price_scored_negative():
    cands = ct.extract_amounts(regions_of(TXT_CLAUSE))
    unit = [c for c in cands if c.anchor == "单价"]
    assert unit, "应抽到单价候选"
    assert all(c.score < 0 for c in unit), "单价候选必须是负分，不能当选合同金额"


def test_amount_node_payment_not_chosen_as_total():
    cands = ct.extract_amounts(regions_of(TXT_CLAUSE))
    value, _, _ = ct.pick_main_amount(cands)
    assert value == 600000.0
    picked = [c for c in cands if c.picked]
    assert len(picked) == 1
    assert float(picked[0].value) == 600000.0


def test_amount_cross_validation_lifts_confidence():
    """同句大小写金额一致时应双向提分到 0.98。"""
    cands = ct.extract_amounts(regions_of(TXT_CLAUSE))
    top = max(cands, key=lambda c: c.score)
    assert top.confidence >= 0.98


def test_amount_node_candidates_are_kept_not_dropped():
    """第二层原则：落选候选也要保留，供人工核对。"""
    cands = ct.extract_amounts(regions_of(TXT_CLAUSE))
    values = {float(c.value) for c in cands}
    assert {180000.0, 420000.0, 12000.0} <= values


def test_pick_main_amount_returns_none_on_empty():
    value, conf, note = ct.pick_main_amount([])
    assert value is None and conf == 0.0 and "未找到" in note


def test_pick_main_amount_same_value_is_not_conflict():
    """大写 600000 与数字 600000 指向同一个数，不该被判为「分差过小需确认」。"""
    cands = [
        ct.Candidate("合同金额", 600000.0, "总价款", score=12.0, confidence=0.92),
        ct.Candidate("合同金额", 600000.0, "总价款", score=11.5, confidence=0.85),
    ]
    value, conf, _ = ct.pick_main_amount(cands)
    assert value == 600000.0
    assert conf >= 0.9, f"同值次优候选不应压低置信度，实际 {conf}"


def test_pick_main_amount_different_runner_up_lowers_confidence():
    cands = [
        ct.Candidate("合同金额", 600000.0, "总价款", score=12.0, confidence=0.92),
        ct.Candidate("合同金额", 500000.0, "价款", score=11.5, confidence=0.85),
    ]
    _, conf, note = ct.pick_main_amount(cands)
    assert conf <= 0.62
    assert "人工确认" in note


def test_pick_main_amount_marks_exactly_one_picked():
    cands = ct.extract_amounts(regions_of(TXT_CLAUSE))
    value, _, _ = ct.pick_main_amount(cands)
    assert value is not None
    assert sum(1 for c in cands if c.picked) == 1


# ===========================================================================
# 分节 6 · 当事人抽取（第二层）
# ===========================================================================

def test_party_with_separator_high_confidence():
    cands = ct.extract_parties(regions_of(TXT_CLAUSE))
    hits = [c for c in cands if c.value == "北京星辰科技有限公司"]
    assert hits
    assert max(c.confidence for c in hits) >= 0.9


def test_party_rejects_verb_fragment_as_name():
    """历史上「甲方支付预付款 30%」会被抽成名字（把 50/00/0% 当公司名）。"""
    cands = ct.extract_parties(regions_of(TXT_SENTENCE_TRAP))
    for c in cands:
        assert not str(c.value).startswith(("支付", "应于"))
        assert "%" not in str(c.value)


def test_party_role_word_must_be_on_same_line():
    """「采购方：A 公司\\n乙方：B 公司」不能把「采购方」配给 B 公司。"""
    text = "甲方（采购方）：北京星辰科技有限公司\n乙方（供货方）：上海云海电子设备有限公司"
    cands = ct.extract_parties(regions_of(text))
    mis = [c for c in cands if c.field == "采购方" and c.value == "上海云海电子设备有限公司"]
    assert not mis, "角色词不得跨行关联到另一行的公司名"


def test_party_requires_org_suffix():
    """「日内」这类不含组织后缀的片段不能被当成当事人。"""
    cands = ct.extract_parties(regions_of("甲方应于协议签署之日起三日内支付全部款项。"))
    assert all("日内" != str(c.value) for c in cands)


def test_party_arbitration_commission_not_labelled_as_party():
    cands = ct.extract_parties(regions_of("双方发生争议的，提交北京仲裁委员会仲裁。"))
    labelled = [c for c in cands if c.field in ct.ROLE_WORDS]
    assert not labelled, "仲裁委员会不应被标注成甲方/乙方等角色"


def test_pick_parties_returns_best_per_role():
    cands = ct.extract_parties(regions_of(TXT_CLAUSE))
    names, confs, _ = ct.pick_parties(cands)
    assert names.get("甲方") == "北京星辰科技有限公司"
    assert names.get("乙方") == "上海云海电子设备有限公司"
    assert confs["甲方"] >= 0.9


def test_pick_parties_empty_input():
    names, confs, note = ct.pick_parties([])
    assert names == {} and confs == {}
    assert "未识别" in note


# ===========================================================================
# 分节 7 · 日期抽取与归类（第二层）
# ===========================================================================

def test_date_classify_by_prefix_anchor():
    assert ct._classify_date("签订日期：")[0] == "签订日期"


def test_date_classify_effect_by_postfix():
    """「自 X 起生效」的锚点在日期之后。"""
    assert ct._classify_date("本合同自", "起生效，有效期至")[0] == "生效日期"


def test_date_classify_expire_by_prefix():
    assert ct._classify_date("有效期至")[0] == "到期日期"


def test_date_classify_span_start_is_effect():
    """「自 X 至 Y」结构里 X 是生效日期。"""
    assert ct._classify_date("服务期限自", "至 2027 年 4 月")[0] == "生效日期"


def test_date_classify_no_anchor():
    assert ct._classify_date("随便一句话")[0] == ""


def test_dates_extracted_from_clause_text():
    cands = ct.extract_dates(regions_of(TXT_CLAUSE))
    values, confs = ct.pick_dates(cands)
    assert values["生效日期"] == "2026-10-01"
    assert values["到期日期"] == "2027-09-30"
    assert confs["生效日期"] >= 0.9


def test_dates_span_structure():
    cands = ct.extract_dates(regions_of(TXT_SPAN))
    values, _ = ct.pick_dates(cands)
    assert values["生效日期"] == "2026-11-01"
    assert values["到期日期"] == "2027-04-30"


def test_date_illegal_value_becomes_zero_confidence():
    cands = ct.extract_dates(regions_of("有效期至 2026 年 2 月 30 日"))
    bad = [c for c in cands if c.field == "日期候选"]
    assert bad and bad[0].confidence == 0.0
    assert "非法日期" in bad[0].reason


def test_dates_without_anchor_are_not_forced_into_main_table():
    cands = ct.extract_dates(regions_of("双方于 2026 年 5 月 6 日见面洽谈。"))
    values, _ = ct.pick_dates(cands)
    assert not values


# --- 生效日期抽不到：2026-10-04 实测挖出的三个缺陷 + 同类边界 ---
# 每一条都写明「除列出字段外，其余字段必须为空」，防止把日期错配到别的列

DATE_CASES: tuple[tuple[str, str, dict[str, str]], ...] = (
    # ① 起止区间：「自 X 起至 Y 止」的起点曾被错标成到期日，导致生效日期整列为空
    ("本合同自 2026 年 10 月 1 日起至 2027 年 9 月 30 日止。",
     {"生效日期": "2026-10-01", "到期日期": "2027-09-30"}),
    ("合同期限自 2026-10-01 至 2027-09-30。",
     {"生效日期": "2026-10-01", "到期日期": "2027-09-30"}),
    ("本合同自 2026 年 10 月 1 日起，有效期至 2027 年 9 月 30 日止。",
     {"生效日期": "2026-10-01", "到期日期": "2027-09-30"}),
    # ② 后置锚点被括号挡住 / 中间夹词
    ("本合同自双方签署之日（2026 年 10 月 1 日）起生效。",
     {"生效日期": "2026-10-01", "签订日期": "2026-10-01"}),
    ("本协议于 2026 年 10 月 1 日起正式生效。",
     {"生效日期": "2026-10-01"}),
    ("本合同自 2026 年 10 月 1 日起算，至项目验收通过之日止。",
     {"生效日期": "2026-10-01"}),
    ("工程执行期自 2026 年 10 月 1 日起 90 日。",
     {"生效日期": "2026-10-01"}),
    # ③ 换行处：DATE_RE 末尾的 \s* 曾吃掉换行，后缀窗口越到下一行，
    #    把下一行的「到期日期：」当成上一个日期的后置锚点
    ("生效日期：2026-10-01\n到期日期：2027-09-30",
     {"生效日期": "2026-10-01", "到期日期": "2027-09-30"}),
    ("生效日期：2026 年 10 月 1 日\n到期日期：2027 年 9 月 30 日",
     {"生效日期": "2026-10-01", "到期日期": "2027-09-30"}),
    ("签订日期：2026 年 9 月 25 日\n本合同自 2026 年 10 月 1 日起生效",
     {"签订日期": "2026-09-25", "生效日期": "2026-10-01"}),
    # ④ 同行两个标签挨在一起（下一行的字段名曾被吃进来，同行同理）
    ("生效日期：2026-10-01；到期日期：2027-09-30",
     {"生效日期": "2026-10-01", "到期日期": "2027-09-30"}),
    ("签订日期：2026年9月25日；生效日期：2026年10月1日",
     {"签订日期": "2026-09-25", "生效日期": "2026-10-01"}),
    # ⑤ 后置「签订」「止」
    ("本合同于 2026 年 9 月 1 日签订。",
     {"签订日期": "2026-09-01"}),
    ("本合同有效期至 2026 年 12 月 31 日止。",
     {"到期日期": "2026-12-31"}),
    # ⑥ 「自…起」的保守边界：期限窗口起点不得被当成生效日期
    ("乙方应于 2026 年 10 月 1 日到货 50 台。", {}),
    ("合同期限\t2026-10-01\t2027-09-30", {}),
)


@pytest.mark.parametrize("text,expect", DATE_CASES, ids=[
    f"{i:02d}" for i in range(1, len(DATE_CASES) + 1)])
def test_date_cases(text, expect):
    values, _ = ct.pick_dates(ct.extract_dates(regions_of(text)))
    assert values == expect


def test_date_span_start_never_labelled_expire():
    """「自 X 起至 Y 止」的 X 不得被标成到期日 —— 这条曾让生效日期整列为空。"""
    cands = ct.extract_dates(regions_of("本合同自 2026 年 10 月 1 日起至 2027 年 9 月 30 日止。"))
    start = [c for c in cands if c.value == "2026-10-01"][0]
    assert start.field == "生效日期"


def test_date_postfix_anchor_with_bracket():
    """日期写在括号里、锚点在括号后（「（X）起生效」）。"""
    assert ct._classify_date("本合同自双方签署之日（", "）起生效。")[0] == "生效日期"


def test_date_rule_does_not_eat_next_line_label():
    """「…：2026-10-01\\n到期日期：…」里第一个日期不得被下一行的标签吃掉。"""
    assert ct._classify_date("生效日期：", "")[0] == "生效日期"


def test_date_regex_does_not_swallow_newline():
    """DATE_RE 末尾不能用 \\s*，否则换行被吃掉、行边界判断全部失效。"""
    m = ct.DATE_RE.search("2026-10-01\n到期日期")
    assert m is not None and m.group(0) == "2026-10-01"


# ===========================================================================
# 分节 8 · 付款节点抽取（第二层）
# ===========================================================================

def test_node_ratio_and_amount_extracted():
    nodes = ct.extract_payment_nodes(regions_of(TXT_CLAUSE))
    by_name = {n.name: n for n in nodes}
    assert by_name["预付款"].ratio == 0.3
    assert by_name["预付款"].amount == 180000.0
    assert by_name["尾款"].ratio == 0.7


def test_node_retention_is_marked_retain():
    """质保金是扣留项，不是支付节点 —— 否则比例合计会算成 105%。"""
    nodes = ct.extract_payment_nodes(regions_of(TXT_CLAUSE))
    by_name = {n.name: n for n in nodes}
    assert by_name["质保金"].kind == "retain"
    assert by_name["预付款"].kind == "pay"


def test_node_timing_found_before_node_word():
    """「合同签订后 5 个工作日内，甲方支付预付款」—— 时点写在节点词之前。"""
    nodes = ct.extract_payment_nodes(regions_of(TXT_CLAUSE))
    by_name = {n.name: n for n in nodes}
    assert "5 个工作日" in by_name["预付款"].timing


def test_node_ratio_does_not_cross_clause_boundary():
    """「余款…付清。…支付 20% 违约金」不能把违约金比例算作余款的付款比例。"""
    text = "余款于项目验收通过后十日内付清。\n任何一方违约，应向对方支付总额 20% 的违约金。"
    nodes = ct.extract_payment_nodes(regions_of(text))
    by_name = {n.name: n for n in nodes}
    assert by_name["余款"].ratio is None, "不得跨句抓到违约金比例"


def test_node_fixed_amount_phrase_does_not_create_dingjin():
    """「不约定固定金额」含子串「定金」，不得凭空造出一个定金节点。"""
    nodes = ct.extract_payment_nodes(regions_of("本协议不约定固定金额，按订单结算。"))
    assert all(n.name != "定金" for n in nodes)


def test_node_without_ratio_or_amount_has_low_confidence():
    nodes = ct.extract_payment_nodes(regions_of("余款于验收后付清。"))
    assert nodes[0].confidence < 0.5


# ===========================================================================
# 分节 9 · 其它要素（税率 / 违约金 / 质保金 / 编号 / 争议解决）
# ===========================================================================

def test_extract_rate():
    extras, confs, _ = ct.extract_extras(regions_of(TXT_CLAUSE))
    assert extras["税率"] == "13%"
    assert confs["税率"] >= 0.85


def test_extract_penalty_with_postfix_anchor():
    """「按合同总价的 0.5% 向甲方支付违约金」—— 锚点在数字之后。"""
    extras, _, _ = ct.extract_extras(regions_of(TXT_CLAUSE))
    assert extras["违约金比例"] == "0.50%"


def test_extract_penalty_with_prefix_anchor():
    extras, _, _ = ct.extract_extras(regions_of("违约金为合同总价的 10%。"))
    assert extras["违约金比例"] == "10%"


def test_extract_retention_ratio():
    extras, _, _ = ct.extract_extras(regions_of(TXT_CLAUSE))
    assert extras["质保金比例"] == "5%"


def test_extract_contract_no():
    extras, _, _ = ct.extract_extras(regions_of("合同编号：XC-2026-1001\n甲方：某某公司"))
    assert extras["合同编号"] == "XC-2026-1001"


def test_extract_dispute_resolution():
    extras, _, _ = ct.extract_extras(regions_of("双方发生争议的，提交北京仲裁委员会仲裁。"))
    assert "仲裁委员会" in extras["争议解决"]


def test_extract_extras_on_plain_text_returns_empty():
    extras, _, cands = ct.extract_extras(regions_of("就是一段普通的话。"))
    assert extras == {} and cands == []


# ===========================================================================
# 分节 10 · 记录装配
# ===========================================================================

def test_build_record_from_sample_one(tmp_path):
    rec = record_of(tmp_path, ms.SAMPLES["01_采购合同_星辰科技.txt"])
    assert rec.fields["合同金额"] == 600000.0
    assert rec.fields["签订日期"] == "2026-09-25"
    assert rec.fields["生效日期"] == "2026-10-01"
    assert rec.fields["到期日期"] == "2027-09-30"
    assert rec.fields["合同期限(天)"] == 364
    assert rec.fields["处理状态"] == "正常"
    assert rec.fields["合同编号"] == "XC-2026-1001"


def test_build_record_table_layout_falls_back_to_cn_amount(tmp_path):
    """表格版式里数字后无「元」字，只能靠中文大写金额兜底。"""
    rec = record_of(tmp_path, ms.SAMPLES["03_设备采购_鼎盛.txt"])
    assert rec.fields["合同金额"] == 31250.0


def test_build_record_framework_leaves_key_fields_empty(tmp_path):
    rec = record_of(tmp_path, ms.SAMPLES["04_框架采购协议.txt"])
    assert rec.fields.get("合同金额", "") == ""
    assert "合同金额" in rec.pending
    assert rec.warnings


def test_build_record_our_name_identifies_counterparty(tmp_path):
    rec = record_of(tmp_path, ms.SAMPLES["01_采购合同_星辰科技.txt"],
                    our="北京星辰科技有限公司")
    assert rec.fields["我方角色"] == "甲方"
    assert rec.fields["对方名称"] == "上海云海电子设备有限公司"
    assert rec.confidences["对方名称"] >= 0.9


def test_build_record_without_our_name_warns(tmp_path):
    rec = record_of(tmp_path, ms.SAMPLES["01_采购合同_星辰科技.txt"])
    assert any("我方名称" in w for w in rec.warnings)
    assert rec.confidences["对方名称"] <= 0.7


def test_record_confidence_is_min_of_key_fields(tmp_path):
    rec = record_of(tmp_path, ms.SAMPLES["01_采购合同_星辰科技.txt"])
    key = [rec.confidences[k] for k in ("对方名称", "合同金额") if k in rec.confidences]
    assert rec.confidence == min(key)


def test_record_pending_lists_low_confidence_fields(tmp_path):
    rec = record_of(tmp_path, ms.SAMPLES["01_采购合同_星辰科技.txt"])
    assert "对方名称" in rec.pending


def test_record_nodes_carry_retain_type(tmp_path):
    rec = record_of(tmp_path, ms.SAMPLES["01_采购合同_星辰科技.txt"])
    kinds = {n.name: n.kind for n in rec.nodes}
    assert kinds["质保金"] == "retain"
    assert kinds["预付款"] == "pay"


def test_record_row_has_all_ledger_columns(tmp_path):
    rec = record_of(tmp_path, ms.SAMPLES["01_采购合同_星辰科技.txt"])
    row = ct.record_row(rec)
    for col in ct.LEDGER_COLUMNS:
        assert col in row, f"台账缺少列：{col}"


def test_load_document_unsupported_extension(tmp_path):
    p = tmp_path / "x.xlsx"
    p.write_text("x", encoding="utf-8")
    doc = ct.load_document(p)
    assert doc.kind == "unsupported"
    assert "不支持" in doc.error


def test_load_document_legacy_doc_gives_actionable_hint(tmp_path):
    p = tmp_path / "old.doc"
    p.write_text("x", encoding="utf-8")
    doc = ct.load_document(p)
    assert doc.kind == "unsupported"
    assert "docx" in doc.error


def test_load_document_txt(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("合同内容", encoding="utf-8")
    doc = ct.load_document(p)
    assert doc.kind == "txt" and doc.chars == 4


def test_collect_files_collects_all_non_noise_files(tmp_path):
    """目录模式**不做扩展名过滤** —— 只排除隐藏文件与噪声目录。

    回归用例（v1.0.1）：v1.0.0 只把「旧版 .doc」从过滤里放出来，其它扩展名
    （`.jpg` / `.xlsx`）在过滤阶段仍被丢掉，于是 SKILL.md 写着的
    「parse 会给它们各写一行台账（状态为 不支持格式），保证输入里有什么和
    台账里有几行对得上」是**没兑现的承诺** —— 实测 5 个文件的目录只产出 3 行。
    同一类缺陷只修了一半，这类「修 A 时同侧还有 B」最隐蔽。
    """
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    (tmp_path / "b.pdf").write_text("x", encoding="utf-8")
    (tmp_path / "c.xlsx").write_text("x", encoding="utf-8")
    (tmp_path / "d.jpg").write_bytes(b"\xff\xd8\xff")
    (tmp_path / "e.doc").write_bytes(b"fake-old-doc")
    names = sorted(p.name for p in ct.collect_files(tmp_path))
    assert names == ["a.txt", "b.pdf", "c.xlsx", "d.jpg", "e.doc"]


def test_collect_files_skips_hidden_and_noise(tmp_path):
    """.git / node_modules / __pycache__ / 隐藏文件 / Office 临时文件都要跳过。

    不做扩展名过滤的代价是「把技能指到一个含 node_modules 的目录会产出几千行」
    —— 这个用例就是那道闸门。
    """
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    (tmp_path / ".hidden.txt").write_text("x", encoding="utf-8")
    (tmp_path / "~$临时.docx").write_bytes(b"x")
    (tmp_path / "Thumbs.db").write_bytes(b"x")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("x", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "p.js").write_text("x", encoding="utf-8")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "m.pyc").write_bytes(b"x")
    assert [p.name for p in ct.collect_files(tmp_path)] == ["a.txt"]


def test_info_total_matches_parse_file_count(tmp_path, capsys):
    """info 的「合计」必须等于 parse 的「处理 N 个文件」，台账行数也要等于它。

    两个命令各说各话时，用户无法判断到底漏没漏 —— 这正是 v1.0.0 的状态
    （info 只数被收进来的 3 个，parse 也只处理 3 个，而目录里其实有 5 个文件）。
    """
    (tmp_path / "a.txt").write_text(
        "甲方：北京星辰科技有限公司\n乙方：上海云海电子设备有限公司\n",
        encoding="utf-8",
    )
    (tmp_path / "附件清单.xlsx").write_text("x", encoding="utf-8")
    (tmp_path / "照片.jpg").write_bytes(b"\xff\xd8\xff")

    assert ct.main(["info", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert re.search(r"合计\s+3 个", out), out
    assert "需人工处理 2 个" in out

    out_path = tmp_path / "o.xlsx"
    assert ct.main(["parse", str(tmp_path), str(out_path)]) == 0
    assert "处理 3 个文件" in capsys.readouterr().out
    df = pd.read_excel(out_path, sheet_name="合同台账")
    assert len(df) == 3
    statuses = dict(zip(df["合同标识"], df["处理状态"]))
    assert statuses["附件清单"] == "不支持格式"
    assert statuses["照片"] == "不支持格式"
    assert statuses["a"] == "正常"


def test_collect_files_on_single_unsupported_file_still_returns_it(tmp_path):
    """单文件不做扩展名过滤 —— 交给 load_document 给出明确报错。"""
    p = tmp_path / "c.xlsx"
    p.write_text("x", encoding="utf-8")
    assert ct.collect_files(p) == [p]


def test_collect_files_missing_path():
    assert ct.collect_files(Path("D:/no/such/dir/xyz")) == []


def test_collect_files_includes_legacy_doc_in_directory_mode(tmp_path):
    """目录模式必须收 .doc。

    回归用例：曾经目录模式只收 SUPPORTED_EXT，`.doc` 在过滤阶段就被丢掉，
    用户拿到一份「处理 5 个文件：正常 5」的台账，却不知道目录里那份 .doc
    根本没被处理过 —— 属静默忽略。单文件模式当时会明确报错，两条路径行为
    不一致，所以这个缺陷只在「传目录」时才暴露。
    """
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    (tmp_path / "b.doc").write_bytes(b"fake-old-doc")
    names = sorted(p.name for p in ct.collect_files(tmp_path))
    assert names == ["a.txt", "b.doc"]


def test_legacy_doc_in_directory_counts_as_failed_not_skipped(tmp_path, capsys):
    """parse 目录时 .doc 要计入「异常/未提取」，不能从计数里悄悄消失。"""
    (tmp_path / "a.txt").write_text(
        "甲方：北京星辰科技有限公司\n本合同总价款为人民币壹万元整（10,000.00元）。\n",
        encoding="utf-8",
    )
    (tmp_path / "b.doc").write_bytes(b"fake-old-doc")
    out = tmp_path / "out.xlsx"
    assert ct.main(["parse", str(tmp_path), str(out)]) == 0
    captured = capsys.readouterr().out
    assert "异常/未提取 1" in captured, captured
    assert "处理 2 个文件" in captured, captured


def test_info_marks_legacy_doc_as_convertible(tmp_path, capsys):
    """info 要给出「另存为 .docx」这类可操作提示，而不是笼统的「不支持」。"""
    (tmp_path / "a.txt").write_text("合同", encoding="utf-8")
    (tmp_path / "b.doc").write_bytes(b"fake-old-doc")
    assert ct.main(["info", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "b.doc" in out, out
    assert "docx" in out, out
    assert "doc(旧版)" in out, out


# ===========================================================================
# 分节 11 · CLI 端到端
# ===========================================================================

def make_samples_dir(tmp_path: Path) -> Path:
    d = tmp_path / "samples"
    d.mkdir(exist_ok=True)
    for name, content in ms.SAMPLES.items():
        (d / name).write_text(content, encoding="utf-8", newline="\n")
    return d


def make_ledger(tmp_path: Path, source: Path, name: str = "台账.xlsx") -> Path:
    out = tmp_path / name
    assert ct.main(["parse", str(source), str(out)]) == 0
    return out


def read_sheets(path: Path) -> dict[str, pd.DataFrame]:
    xls = pd.ExcelFile(path)
    return {n: xls.parse(n) for n in xls.sheet_names}


def test_cli_info_without_path(capsys):
    assert ct.main(["info"]) == 0
    out = capsys.readouterr().out
    assert "pandas" in out and "openpyxl" in out


def test_cli_info_scans_directory(tmp_path, capsys):
    src = make_samples_dir(tmp_path)
    assert ct.main(["info", str(src)]) == 0
    out = capsys.readouterr().out
    assert "txt" in out and "合计" in out


def test_cli_info_probe_text_counts_files(tmp_path, capsys):
    src = make_samples_dir(tmp_path)
    assert ct.main(["info", str(src), "--probe-text"]) == 0
    out = capsys.readouterr().out
    assert "合计" in out
    assert "txt" in out


def test_cli_parse_probe_prints_candidates(tmp_path, capsys):
    src = make_samples_dir(tmp_path)
    f = src / "01_采购合同_星辰科技.txt"
    assert ct.main(["parse", str(f), "--probe"]) == 0
    out = capsys.readouterr().out
    assert "金额候选" in out and "当事人候选" in out
    assert "付款节点" in out


def test_cli_parse_probe_rejects_directory(tmp_path, capsys):
    src = make_samples_dir(tmp_path)
    assert ct.main(["parse", str(src), "--probe"]) == 1
    assert "单个文件" in capsys.readouterr().err


def test_cli_parse_writes_four_sheets(tmp_path):
    src = make_samples_dir(tmp_path)
    out = make_ledger(tmp_path, src)
    sheets = read_sheets(out)
    assert list(sheets.keys()) == ["合同台账", "付款节点", "抽取候选", "解析告警"]
    assert len(sheets["合同台账"]) == len(ms.SAMPLES)


def test_cli_parse_amount_column_is_numeric(tmp_path):
    """金额列必须是数值，否则用户在 Excel 里无法求和。"""
    src = make_samples_dir(tmp_path)
    ledger = read_sheets(make_ledger(tmp_path, src))["合同台账"]
    assert ledger["合同金额"].dtype == "float64"


def test_cli_parse_dry_run_writes_nothing(tmp_path, capsys):
    src = make_samples_dir(tmp_path)
    out = tmp_path / "无.xlsx"
    assert ct.main(["parse", str(src), str(out), "--dry-run"]) == 0
    assert not out.exists()
    assert "--dry-run" in capsys.readouterr().out


def test_cli_parse_missing_input_returns_one(tmp_path, capsys):
    rc = ct.main(["parse", str(tmp_path / "nope"), str(tmp_path / "o.xlsx")])
    assert rc == 1
    assert "不存在" in capsys.readouterr().err


def test_cli_parse_empty_dir_returns_one(tmp_path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    rc = ct.main(["parse", str(empty), str(tmp_path / "o.xlsx")])
    assert rc == 1
    assert "没有找到任何文件" in capsys.readouterr().err


def test_cli_parse_our_name_changes_counterparty(tmp_path):
    src = make_samples_dir(tmp_path)
    out = tmp_path / "带我方.xlsx"
    assert ct.main(["parse", str(src / "01_采购合同_星辰科技.txt"), str(out),
                    "--our-name", "上海云海电子设备有限公司"]) == 0
    row = read_sheets(out)["合同台账"].iloc[0]
    assert row["我方角色"] == "乙方"
    assert row["对方名称"] == "北京星辰科技有限公司"


def test_cli_check_writes_summary_and_issues(tmp_path):
    src = make_samples_dir(tmp_path)
    ledger = make_ledger(tmp_path, src)
    report = tmp_path / "体检.xlsx"
    assert ct.main(["check", str(ledger), str(report), "--as-of", "2026-10-04"]) == 0
    sheets = read_sheets(report)
    assert set(sheets) == {"体检汇总", "问题明细"}
    assert len(sheets["体检汇总"]) == len(ct.CHECK_RULES)


def test_cli_check_missing_ledger_returns_one(tmp_path, capsys):
    rc = ct.main(["check", str(tmp_path / "nope.xlsx"), str(tmp_path / "o.xlsx")])
    assert rc == 1
    assert "不存在" in capsys.readouterr().err


def test_cli_expire_writes_list_and_buckets(tmp_path, capsys):
    src = make_samples_dir(tmp_path)
    ledger = make_ledger(tmp_path, src)
    out = tmp_path / "到期.xlsx"
    assert ct.main(["expire", str(ledger), str(out),
                    "--as-of", "2026-10-04", "--within", "400"]) == 0
    text = capsys.readouterr().out
    assert "即将到期" in text and "无到期日期" in text
    frame = read_sheets(out)["到期清单"]
    assert len(frame) == len(ms.SAMPLES)


def test_cli_expire_only_expiring_filters_normals(tmp_path):
    src = make_samples_dir(tmp_path)
    ledger = make_ledger(tmp_path, src)
    out = tmp_path / "到期.xlsx"
    assert ct.main(["expire", str(ledger), str(out), "--as-of", "2026-10-04",
                    "--within", "1", "--only-expiring", "--only-dated"]) == 0
    frame = read_sheets(out)["到期清单"]
    assert all(s != "正常" for s in frame["状态"])


def test_cli_compare_groups_by_counterparty(tmp_path, capsys):
    src = make_samples_dir(tmp_path)
    ledger = make_ledger(tmp_path, src)
    out = tmp_path / "汇总.xlsx"
    assert ct.main(["compare", str(ledger), str(out), "--group-by", "对方名称",
                    "--fields", "违约金比例"]) == 0
    sheets = read_sheets(out)
    assert "按对方名称汇总" in sheets
    assert "要素取值分布" in sheets
    assert len(sheets["按对方名称汇总"]) == len(ms.SAMPLES)


def test_cli_compare_rejects_unknown_group_column(tmp_path, capsys):
    src = make_samples_dir(tmp_path)
    ledger = make_ledger(tmp_path, src)
    rc = ct.main(["compare", str(ledger), str(tmp_path / "o.xlsx"), "--group-by", "不存在的列"])
    assert rc == 1
    assert "没有" in capsys.readouterr().err


def test_cli_version_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        ct.main(["--version"])
    assert exc.value.code == 0
    assert ct.__version__ in capsys.readouterr().out


# ===========================================================================
# 分节 12 · Excel 输出
# ===========================================================================

def test_write_report_xlsx_single_file(tmp_path):
    frame = pd.DataFrame({"a": [1, 2]})
    written = ct.write_report({"S1": frame}, tmp_path / "o.xlsx")
    assert len(written) == 1 and written[0].exists()


def test_write_report_csv_falls_back_to_per_sheet_files(tmp_path):
    written = ct.write_report({"甲": pd.DataFrame({"a": [1]}),
                               "乙": pd.DataFrame({"b": [2]})}, tmp_path / "o.csv")
    assert len(written) == 2
    assert all(p.exists() for p in written)
    assert {p.name for p in written} == {"o__甲.csv", "o__乙.csv"}


def test_write_report_creates_parent_directory(tmp_path):
    written = ct.write_report({"S": pd.DataFrame({"a": [1]})}, tmp_path / "深" / "层" / "o.xlsx")
    assert written[0].exists()


def test_write_report_rejects_unsupported_format(tmp_path):
    with pytest.raises(ValueError):
        ct.write_report({"S": pd.DataFrame({"a": [1]})}, tmp_path / "o.parquet")


def test_styled_workbook_freezes_header_and_fills_warn_rows(tmp_path):
    from openpyxl import load_workbook

    frame = pd.DataFrame({"名称": ["低", "高"], "置信度": [0.5, 0.95]})
    path = ct.write_report({"S": frame}, tmp_path / "o.xlsx")[0]
    ws = load_workbook(path)["S"]
    assert ws.freeze_panes == "A2"
    assert ws["A1"].font.bold is True
    low_fill = ws["A2"].fill.fgColor.rgb
    high_fill = ws["A3"].fill.fgColor.rgb
    assert "FCEBEB" in str(low_fill), "低置信度行应整行着色"
    assert "FCEBEB" not in str(high_fill)


def test_styled_workbook_empty_frame_keeps_columns(tmp_path):
    frame = pd.DataFrame(columns=["合同标识", "对方名称"])
    path = ct.write_report({"空表": frame}, tmp_path / "o.xlsx")[0]
    result = pd.read_excel(path, sheet_name="空表")
    assert list(result.columns) == ["合同标识", "对方名称"]
    assert result.empty


# ===========================================================================
# 分节 13 · check 规则（造错数据验证，不读代码推测）
# ===========================================================================

CHECK_A_OK = """
甲方：北京星辰科技有限公司
乙方：上海云海电子设备有限公司
本合同总价款为人民币壹拾万元整（100,000.00元）。
合同签订后 5 个工作日内支付预付款 30%，即人民币 30,000 元；
验收后支付尾款 70%，即人民币 70,000 元。
质保金为合同总价的 5%。
签订日期：2026 年 9 月 1 日
本合同自 2026 年 9 月 10 日起生效，有效期至 2027 年 9 月 9 日止。
"""

CHECK_B_NODE_MISMATCH = """
甲方：北京星辰科技有限公司
本合同总价款为人民币壹拾万元整（100,000.00元）。
合同签订后支付预付款 30%，即人民币 30,000 元；
验收后支付尾款 40%，即人民币 40,000 元。
"""

CHECK_C_BAD_DATES = """
甲方：北京星辰科技有限公司
本合同总价款为人民币壹拾万元整（100,000.00元）。
签订日期：2026 年 12 月 1 日
本合同自 2026 年 10 月 1 日起生效，有效期至 2027 年 9 月 30 日止。
"""


def check_of(tmp_path: Path, text: str, name: str) -> dict[str, pd.DataFrame]:
    src = tmp_path / f"src_{name}"
    src.mkdir(exist_ok=True)
    (src / f"{name}.txt").write_text(text, encoding="utf-8")
    ledger = make_ledger(tmp_path, src, name=f"ledger_{name}.xlsx")
    report = tmp_path / f"report_{name}.xlsx"
    assert ct.main(["check", str(ledger), str(report), "--as-of", "2026-10-04"]) == 0
    return read_sheets(report)


def rule_row(sheets: dict[str, pd.DataFrame], rule: str) -> pd.Series:
    summary = sheets["体检汇总"]
    hit = summary[summary["规则"] == rule]
    assert not hit.empty, f"体检汇总里没有规则「{rule}」"
    return hit.iloc[0]


def test_check_clean_sample_all_rules_pass(tmp_path):
    sheets = check_of(tmp_path, CHECK_A_OK, "clean")
    summary = sheets["体检汇总"].fillna(0)
    failing = summary[summary["不通过"].astype(float) > 0]
    assert failing.empty, f"干净样本不应有问题，实际：{failing.to_dict('records')}"


def test_check_detects_node_sum_mismatch(tmp_path):
    """节点合计 7 万 vs 合同额 10 万 —— 必须报出。"""
    sheets = check_of(tmp_path, CHECK_B_NODE_MISMATCH, "mismatch")
    assert float(rule_row(sheets, "节点合计")["不通过"]) == 1


def test_check_detects_ratio_total_not_full(tmp_path):
    """预付 30% + 尾款 40% = 70%，不是 100%。"""
    sheets = check_of(tmp_path, CHECK_B_NODE_MISMATCH, "ratio")
    assert float(rule_row(sheets, "比例合计")["不通过"]) == 1


def test_check_allows_retention_above_hundred_percent_rule(tmp_path):
    """「预付30% + 尾款70% + 质保金5%」的质保金是扣留项，比例合计仍应通过。"""
    sheets = check_of(tmp_path, CHECK_A_OK, "retain")
    assert float(rule_row(sheets, "比例合计")["不通过"]) == 0


def test_check_detects_broken_date_chain(tmp_path):
    """签订 12-01 晚于生效 10-01 —— 逻辑链断裂。"""
    sheets = check_of(tmp_path, CHECK_C_BAD_DATES, "dates")
    assert float(rule_row(sheets, "日期逻辑")["不通过"]) == 1
    issues = sheets["问题明细"]
    assert any("晚于生效" in str(v) for v in issues["问题"])


def test_check_daxie_rule_not_fooled_by_losing_candidates(tmp_path):
    """落选的单价/节点款不是「大写金额不一致」。"""
    sheets = check_of(tmp_path, CHECK_A_OK, "daxie")
    assert float(rule_row(sheets, "大写一致")["不通过"]) == 0


def test_check_reports_missing_key_fields(tmp_path):
    src = make_samples_dir(tmp_path)
    ledger = make_ledger(tmp_path, src)
    report = tmp_path / "r.xlsx"
    assert ct.main(["check", str(ledger), str(report), "--as-of", "2026-10-04"]) == 0
    sheets = read_sheets(report)
    assert float(rule_row(sheets, "关键字段")["不通过"]) >= 1
    issues = sheets["问题明细"]
    assert "04_框架采购协议" in set(issues["合同标识"])


def test_check_rules_filter_limits_executed_rules(tmp_path):
    src = make_samples_dir(tmp_path)
    ledger = make_ledger(tmp_path, src)
    report = tmp_path / "r.xlsx"
    assert ct.main(["check", str(ledger), str(report), "--rules", "日期逻辑",
                    "--as-of", "2026-10-04"]) == 0
    summary = read_sheets(report)["体检汇总"]
    assert list(summary["规则"]) == ["日期逻辑"]


def test_check_expiry_rule_flags_past_end_date(tmp_path):
    text = """
甲方：北京星辰科技有限公司
本合同总价款为人民币壹万元整（10,000.00元）。
签订日期：2024 年 1 月 1 日
本合同自 2024 年 1 月 1 日起生效，有效期至 2024 年 12 月 31 日止。
"""
    sheets = check_of(tmp_path, text, "expired")
    assert float(rule_row(sheets, "到期状态")["不通过"]) == 1


def test_check_tolerance_absorbs_float_noise(tmp_path):
    """节点合计 0.1+0.2 vs 0.30 的浮点噪声不该报差异。"""
    text = """
甲方：北京星辰科技有限公司
本合同总价款为人民币叁角整（0.30元）。
合同签订后支付预付款 33.33%，即人民币 0.10 元；
验收后支付尾款 66.67%，即人民币 0.20 元。
"""
    sheets = check_of(tmp_path, text, "float")
    assert float(rule_row(sheets, "节点合计")["不通过"]) == 0


# ===========================================================================
# 分节 14 · v1.0.2 新增能力
#   （阈值可配 / 递归默认开启 / 我方名称默认值 / 表格版式定向提示 / HTML 报告）
# ===========================================================================

TXT_TABLE_STYLE = (
    "合同名称\t对方名称\t合同金额\t签订日期\t生效日期\t到期日期\n"
    "采购合同\t上海云海电子设备有限公司\t600000\t2026-09-25\t2026-10-01\t2027-09-30\n"
    "技术服务协议\t深圳市恒信信息技术有限公司\t88000\t2026-04-01\t2026-05-01\t2027-04-30\n"
    "设备采购\t杭州明阳包装材料厂\t31250\t2026-03-01\t2026-03-15\t2027-03-14\n"
)


@pytest.fixture(autouse=True)
def _isolate_globals(monkeypatch):
    """隔离本机环境与全局状态，保证测试可复现。

    两件事必须挡掉：
      · `CONTRACT_OUR_NAME` 环境变量、本机的 `.contract-toolkit.yaml` —— 它们一旦存在，
        所有 parse 用例的甲乙方判定都会跟着变；
      · 模块级 `CONF_THRESHOLD` —— `main()` 会改它，用例之间会互相污染。
    需要验证环境变量 / 配置文件的用例自己 setenv / 落盘。
    """
    original = ct.CONF_THRESHOLD
    monkeypatch.delenv(ct.OUR_NAME_ENV, raising=False)

    def only_under(target):
        if target is None:
            return []
        d = target if target.is_dir() else target.parent
        return [d / fn for fn in ct.OUR_NAME_CONFIG_NAMES]

    monkeypatch.setattr(ct, "_config_candidates", only_under)
    yield
    ct.set_conf_threshold(original)


def test_conf_threshold_default_is_070():
    assert ct.CONF_THRESHOLD == 0.70


def test_conf_threshold_widens_pending_fields(tmp_path):
    """未指定我方名称时「对方名称」的置信度被压到 0.6，默认阈值下就已在待确认里。"""
    rec = record_of(tmp_path, TXT_CLAUSE)
    assert rec.pending == "合同名称、对方名称"
    ct.set_conf_threshold(0.99)
    assert rec.pending == ("付款方式、到期日期、合同名称、合同金额、对方名称、"
                           "生效日期、税率、质保金比例、违约金比例")


@pytest.mark.parametrize("bad", ["0", "1.5", "abc", "-0.1"])
def test_cli_conf_threshold_rejects_invalid(tmp_path, bad):
    f = tmp_path / "c.txt"
    f.write_text(TXT_CLAUSE, encoding="utf-8")
    rc = ct.main(["parse", str(f), str(tmp_path / "o.xlsx"), "--conf-threshold", bad])
    assert rc == 2


def test_cli_conf_threshold_changes_pending_column(tmp_path):
    f = tmp_path / "c.txt"
    f.write_text(TXT_CLAUSE, encoding="utf-8")
    loose, tight = tmp_path / "loose.xlsx", tmp_path / "tight.xlsx"
    assert ct.main(["parse", str(f), str(loose), "--conf-threshold", "0.70"]) == 0
    assert ct.main(["parse", str(f), str(tight), "--conf-threshold", "0.99"]) == 0
    p_loose = pd.read_excel(loose, sheet_name="合同台账")["待确认字段"].iloc[0]
    p_tight = pd.read_excel(tight, sheet_name="合同台账")["待确认字段"].iloc[0]
    assert p_loose == "合同名称、对方名称"
    assert p_tight != p_loose and "税率" in p_tight


def test_collect_files_recurses_by_default(tmp_path):
    """v1.0.2 改默认行为：不再递归就等于「子目录里的合同被静默漏掉」。

    老实现是 `--recursive` 才递归，但 help 文字写的是「默认开启」——
    用户按 help 理解不传参，子目录里的合同就此消失，且没有任何提示。
    按本项目「宁可多收也不要静默跳过」的口径，默认改成递归。
    """
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.txt").write_text(TXT_CLAUSE, encoding="utf-8")
    (tmp_path / "sub" / "b.txt").write_text(TXT_CLAUSE, encoding="utf-8")
    assert sorted(p.name for p in ct.collect_files(tmp_path)) == ["a.txt", "b.txt"]
    assert sorted(p.name for p in ct.collect_files(tmp_path, recursive=False)) == ["a.txt"]


def test_cli_parse_no_recursive_limits_to_top_level(tmp_path):
    src = tmp_path / "src"
    (src / "sub").mkdir(parents=True)
    (src / "a.txt").write_text(TXT_CLAUSE, encoding="utf-8")
    (src / "sub" / "b.txt").write_text(TXT_CLAUSE, encoding="utf-8")
    out = tmp_path / "o.xlsx"
    assert ct.main(["parse", str(src), str(out), "--no-recursive"]) == 0
    assert len(pd.read_excel(out, sheet_name="合同台账")) == 1


def test_cli_parse_recursive_includes_subdirectory_files(tmp_path):
    src = tmp_path / "src"
    (src / "sub").mkdir(parents=True)
    (src / "a.txt").write_text(TXT_CLAUSE, encoding="utf-8")
    (src / "sub" / "b.txt").write_text(TXT_CLAUSE, encoding="utf-8")
    out = tmp_path / "o.xlsx"
    assert ct.main(["parse", str(src), str(out)]) == 0
    assert len(pd.read_excel(out, sheet_name="合同台账")) == 2


def test_resolve_our_name_returns_nothing_when_unset(tmp_path):
    assert ct.resolve_our_name(None, tmp_path) == (None, "")


def test_resolve_our_name_prefers_explicit_over_env(tmp_path, monkeypatch):
    monkeypatch.setenv(ct.OUR_NAME_ENV, "环境变量公司")
    assert ct.resolve_our_name("显式公司", tmp_path) == ("显式公司", "")


def test_resolve_our_name_reads_env(tmp_path, monkeypatch):
    monkeypatch.setenv(ct.OUR_NAME_ENV, "环境变量公司")
    value, source = ct.resolve_our_name(None, tmp_path / "c.txt")
    assert value == "环境变量公司"
    assert source == "环境变量 CONTRACT_OUR_NAME"


def test_resolve_our_name_reads_config_file(tmp_path):
    (tmp_path / ".contract-toolkit.yaml").write_text(
        "# 我方主体，用于区分甲乙方\nour_name: 配置文件公司\n", encoding="utf-8")
    value, source = ct.resolve_our_name(None, tmp_path / "c.txt")
    assert value == "配置文件公司"
    assert "配置文件" in source and ".contract-toolkit.yaml" in source


def test_read_our_name_config_supports_json(tmp_path):
    p = tmp_path / "c.json"
    p.write_text('{"our_name": "JSON 公司"}', encoding="utf-8")
    assert ct._read_our_name_config(p) == "JSON 公司"


def test_read_our_name_config_ignores_other_keys_and_comments(tmp_path):
    p = tmp_path / ".contract-toolkit.yaml"
    p.write_text("other: 值\n# our_name: 注释里的不算\n", encoding="utf-8")
    assert ct._read_our_name_config(p) is None


def test_read_our_name_config_missing_file(tmp_path):
    assert ct._read_our_name_config(tmp_path / "nope.yaml") is None


def test_cli_parse_announces_our_name_source(tmp_path, capsys, monkeypatch):
    """命中的默认值必须显式告知 —— 静默套用会让人以为是自己指定的。"""
    monkeypatch.setenv(ct.OUR_NAME_ENV, "北京星辰科技有限公司")
    f = tmp_path / "c.txt"
    f.write_text(TXT_CLAUSE, encoding="utf-8")
    assert ct.main(["parse", str(f), str(tmp_path / "o.xlsx")]) == 0
    assert "取自环境变量 CONTRACT_OUR_NAME" in capsys.readouterr().out


def test_looks_like_table_distinguishes_prose_from_table():
    assert ct.looks_like_table(TXT_TABLE_STYLE) is True
    assert ct.looks_like_table(TXT_CLAUSE) is False


def test_looks_like_table_needs_enough_rows():
    assert ct.looks_like_table("甲方\t乙方\n") is False


def test_table_style_record_gets_targeted_warning(tmp_path):
    rec = record_of(tmp_path, TXT_TABLE_STYLE, "table.txt")
    hit = [w for w in rec.warnings if "疑似表格版式" in w]
    assert len(hit) == 1
    assert "合同金额" in hit[0] and "日期" in hit[0]
    assert "pdf-toolkit" in hit[0]


def test_prose_record_has_no_table_warning(tmp_path):
    """反向断言：普通条款式合同一条表格告警都不该有，否则告警就没人看了。"""
    rec = record_of(tmp_path, TXT_CLAUSE)
    assert not [w for w in rec.warnings if "疑似表格版式" in w]


def test_write_report_html_is_single_self_contained_file(tmp_path):
    frame = pd.DataFrame({"合同标识": ["a"], "金额": [600000.0]})
    written = ct.write_report({"合同台账": frame}, tmp_path / "r.html")
    assert len(written) == 1 and written[0].suffix == ".html"
    html = written[0].read_text(encoding="utf-8")
    assert "<table>" in html and "合同台账" in html
    assert "600000" in html and "600000.0" not in html
    assert "http://" not in html and "https://" not in html


def test_write_report_html_marks_low_confidence_rows(tmp_path):
    frame = pd.DataFrame({"合同标识": ["a", "b"], "置信度": [0.9, 0.4]})
    html = ct.write_report({"合同台账": frame}, tmp_path / "r.html")[0].read_text(encoding="utf-8")
    assert html.count('class="warn"') == 1


def test_write_report_html_truncates_long_tables(tmp_path):
    frame = pd.DataFrame({"n": list(range(400))})
    written = ct.write_report({"大表": frame}, tmp_path / "r.html")
    html = written[0].read_text(encoding="utf-8")
    assert "共 400 行，此处预览前 300 行" in html


def test_cli_parse_writes_html_report(tmp_path, capsys):
    src = tmp_path / "src"
    src.mkdir()
    (src / "c.txt").write_text(TXT_CLAUSE, encoding="utf-8")
    out = tmp_path / "台账.html"
    assert ct.main(["parse", str(src), str(out)]) == 0
    html = out.read_text(encoding="utf-8")
    assert "抽取候选" in html and "解析告警" in html
    assert "<!DOCTYPE html>" in html
