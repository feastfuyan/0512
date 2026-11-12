#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
contract_toolkit.py — 合同要素台账（contract-toolkit）

把散落的合同文件变成可核对的结构化台账。

设计前提（务必先读）：合同是**自由文本**，不是发票那样的半结构化数据。
字段位置随机、同一句话里可能有多个金额、当事人名称无法用正则可靠界定。
因此本技能的能力边界分三层，落在第三层的一律不做：

  · 第一层 确定性可做，可承诺 —— 字段归一化、中文大写金额解析、台账汇总、
    到期清单、跨合同比对、台账体检（恒等式与逻辑链）
  · 第二层 只给候选，必须人工确认 —— 合同金额归类、当事人名称、日期归类、
    付款节点拆分。全部带置信度，低置信进「待确认字段」列，另出「抽取候选」sheet
    把落选候选一并摊开，供人工核对
  · 第三层 不做 —— 合同效力判断、条款风险审查、自动续签决策

不做 OCR：扫描件请先用带 OCR 能力的技能（如 pdf-toolkit 的 `text --ocr`）
转成文本，再交回本技能。识别交给更擅长的工具，本技能专注「抽取 + 判定 + 台账」。

参见 SKILL.md「能力边界」一节。
"""

from __future__ import annotations

__version__ = "1.0.2"

import argparse
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Sequence

# Windows 控制台按 UTF-8 输出，避免中文乱码
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass


# ============================================================================
# 全局可调参数
# ============================================================================

# 置信度阈值：低于它的字段进「待确认字段」列，台账里整行标底色。
# 做成模块级变量而不是常量，是因为 ContractRecord.pending 是 property，
# 拿不到命令参数；由 main() 统一从 --conf-threshold 写入（默认 0.70）。
CONF_THRESHOLD = 0.70


def set_conf_threshold(value: float) -> None:
    """设置全局置信度阈值。取值须在 (0, 1] 区间内。"""
    global CONF_THRESHOLD
    CONF_THRESHOLD = float(value)


# ============================================================================
# 可选依赖探测
# ============================================================================

def _has(module: str) -> bool:
    try:
        __import__(module)
        return True
    except Exception:
        return False


HAS_PYPDF = _has("pypdf")
HAS_DOCX = _has("docx")
HAS_PANDAS = _has("pandas")


# ============================================================================
# 词表与常量
# ============================================================================

CN_DIGITS: dict[str, int] = {
    "零": 0, "壹": 1, "贰": 2, "叁": 3, "肆": 4,
    "伍": 5, "陆": 6, "柒": 7, "捌": 8, "玖": 9,
    "〇": 0, "一": 1, "二": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "两": 2,
}

CN_UNITS: dict[str, int] = {"拾": 10, "佰": 100, "仟": 1000, "十": 10, "百": 100, "千": 1000}
CN_SECTION_UNITS: dict[str, int] = {"万": 10000, "萬": 10000, "亿": 100000000, "億": 100000000}

# 总价类锚点：命中则倾向「这个是合同金额」
TOTAL_ANCHORS: tuple[str, ...] = (
    "合同总价", "合同总额", "合同总金额", "合同金额", "合同价款", "合同价格",
    "总价款", "价款合计", "合计金额", "总金额", "项目总额", "项目总价",
    "费用总计", "服务费总计", "总计", "合计", "总价", "总额", "价税合计", "价款",
)

# 排他锚点：命中说明该数字是**别的要素**，不能当合同总价
UNIT_ANCHORS: tuple[str, ...] = ("单价", "单位价格", "每台", "每个", "每件", "每份", "每人", "每套", "每吨")
TAX_ANCHORS: tuple[str, ...] = ("税率", "税额", "增值税", "所得税", "含税", "不含税", "征收率")
NODE_ANCHORS: tuple[str, ...] = (
    "预付款", "首付款", "首期款", "预收", "尾款", "余款", "质保金", "保证金",
    "押金", "进度款", "第一期", "第二期", "第三期", "分期", "定金",
)
# 扣留类节点：从合同金额里**扣下**的钱，不是额外的支付笔。
# 若不区分，一份「预付30% + 尾款70% + 质保金5%」的合同会被算成 105%，
# 于是「比例合计 = 100%」这条规则在真实数据上频繁误报。
RETAIN_NODES: tuple[str, ...] = (
    "质保金", "保修金", "质量保证金", "保证金", "押金", "履约保证金", "诚信保证金",
)
PENALTY_ANCHORS: tuple[str, ...] = ("违约金", "滞纳金", "赔偿金", "罚款", "罚息", "逾期利息")

# 当事人角色词
ROLE_WORDS: tuple[str, ...] = (
    "甲方", "乙方", "丙方", "丁方",
    "需方", "供方", "买方", "卖方", "购方", "销方",
    "委托方", "受托方", "委托单位", "受托单位",
    "发包方", "承包方", "发包人", "承包人",
    "出租方", "承租方", "出借方", "借款方",
    "采购方", "供应商", "采购人", "中标人", "招标人",
    "用人方", "受聘方", "出让方", "受让方",
)

# 组织名后缀词表 —— 有了它，当事人名称抽取才有可校验的边界
ORG_SUFFIX: tuple[str, ...] = (
    "有限责任公司", "股份有限公司", "有限公司", "集团有限公司", "集团公司",
    "合伙企业", "有限合伙", "普通合伙", "个人独资企业",
    "公司", "集团", "企业", "工厂", "厂", "商店", "商行", "店",
    "事务所", "研究院", "设计院", "研究所", "科学院",
    "大学", "学院", "学校", "中学", "小学", "幼儿园",
    "医院", "卫生院", "诊所", "疾病预防控制中心",
    "银行", "支行", "分行", "信用社", "农村商业银行",
    "中心", "合作社", "协会", "工会", "委员会", "工作室", "管理处",
    "律师事务所", "会计师事务所", "税务师事务所",
)

ORG_SUFFIX_RE: str = "(?:" + "|".join(sorted(ORG_SUFFIX, key=len, reverse=True)) + ")"

DATE_ANCHORS: dict[str, tuple[str, ...]] = {
    "签订日期": ("签订日期", "签署日期", "订立日期", "签约日期", "签订时间", "签署时间",
                 "签订于", "签署于", "订立于", "签订", "签署", "签约"),
    "生效日期": ("生效日期", "生效日", "生效时间", "开始日期", "起始日期", "起始日"),
    "到期日期": ("有效期限至", "有效期至", "终止日期", "到期日期", "到期日", "届满日",
                 "截止日期", "届满", "有效期限", "服务期限至"),
}

VALID_RATES: tuple[float, ...] = (0.0, 0.01, 0.03, 0.05, 0.06, 0.09, 0.13)

# 一个数字必须带货币标记才算「金额候选」——这是实测换来的：
# 不带货币标记的裸数字会把「50 台」「30 个工作日」「5%」全卷进来
MONEY_RE = re.compile(
    r"(?:人民币|RMB|rmb|RMB￥|¥|￥|\$)\s*"
    r"(\d{1,3}(?:[,，]\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)"
    r"\s*(亿元|万元|亿|万|元)?"
    r"|"
    r"(\d{1,3}(?:[,，]\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)"
    r"\s*(亿元|万元|万元整|亿|万|元)"
)

CN_AMOUNT_RE = re.compile(
    r"(?:人民币)?\s*([零壹贰叁肆伍陆柒捌玖〇一二三四五六七八九两拾佰仟十百千万萬亿億]{2,}"
    r"(?:元|圆)[零壹贰叁肆伍陆柒捌玖〇一二三四五六七八九两角分整正]*)"
)

# 末尾刻意不用 \s*：\s 会连换行一起吃掉，于是「日期的后缀窗口」会越到下一行，
# 把下一行的「到期日期：」当成这个日期的后置锚点（实测踩中：
# 「生效日期：2026-10-01\n到期日期：2027-09-30」里第一个日期被标成到期日）
DATE_RE = re.compile(r"(\d{4})[ \t]*[年\-/.][ \t]*(\d{1,2})[ \t]*[月\-/.][ \t]*(\d{1,2})[ \t]*日?")

RATE_RE = re.compile(r"税率\s*(?:为|是|:|：)?\s*(\d{1,2}(?:\.\d+)?)\s*%")

PERCENT_RE = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")


# ============================================================================
# 中文大写金额解析（第一层，可承诺 100%）
# ============================================================================

def _cn_int_to_number(text: str) -> int:
    """把「壹拾贰万叁仟肆佰伍拾陆」这类纯中文数字串转成整数。"""
    total = 0          # 亿及以上累计
    section = 0        # 当前「万」节累计
    number = 0         # 当前待用数字
    for ch in text:
        if ch in CN_DIGITS:
            number = CN_DIGITS[ch]
        elif ch in CN_UNITS:
            unit = CN_UNITS[ch]
            if number == 0:
                number = 1          # 「拾万」= 十万，省略了「壹」
            section += number * unit
            number = 0
        elif ch in CN_SECTION_UNITS:
            unit = CN_SECTION_UNITS[ch]
            if unit == 10000:
                section += number
                total += section * 10000
                section = 0
                number = 0
            else:                    # 亿
                section += number
                total = (total + section) * 100000000
                section = 0
                number = 0
    return total + section + number


def parse_cn_amount(raw: str | None) -> float | None:
    """解析中文大写金额。返回元为单位的浮点数；无法解析返回 None。

    覆盖：陆拾万元整 / 叁万壹仟贰佰伍拾元整 / 壹佰贰拾叁元肆角伍分 /
          壹亿贰仟万 / 人民币壹万元整 / 拾万元整（省略「壹」）
    """
    if not raw:
        return None
    s = unicodedata.normalize("NFKC", str(raw))
    for junk in ("人民币", "大写", "币种", "币", "：", ":", "（", "）", "(", ")", " ", "\u3000", "，", ","):
        s = s.replace(junk, "")
    s = s.replace("正", "整").replace("圆", "元").replace("萬", "万").replace("億", "亿")

    if not any(ch in CN_DIGITS or ch in CN_UNITS or ch in CN_SECTION_UNITS for ch in s):
        return None

    int_part, frac_part = s, ""
    if "元" in s:
        idx = s.index("元")
        int_part, frac_part = s[:idx], s[idx + 1:]
    else:
        # 没有「元」：只当它是纯数字串（如「陆拾万」）
        int_part = s.replace("整", "")

    int_part = re.sub(r"[整元]", "", int_part)
    value = float(_cn_int_to_number(int_part)) if int_part else 0.0

    m = re.search(r"([零壹贰叁肆伍陆柒捌玖〇一二三四五六七八九两])\s*角", frac_part)
    if m:
        value += CN_DIGITS[m.group(1)] * 0.1
    m = re.search(r"([零壹贰叁肆伍陆柒捌玖〇一二三四五六七八九两])\s*分", frac_part)
    if m:
        value += CN_DIGITS[m.group(1)] * 0.01

    return round(value, 2)


# ============================================================================
# 数值归一化
# ============================================================================

def parse_arabic_amount(text: str, unit: str | None = None) -> float | None:
    """把「1,234,567.89」「60万」「1.2亿」转成元为单位的浮点数。"""
    if not text:
        return None
    try:
        value = float(text.replace(",", "").replace("，", ""))
    except ValueError:
        return None
    if unit:
        if unit.startswith("亿"):
            value *= 100000000
        elif unit.startswith("万"):
            value *= 10000
    return round(value, 2)


def norm_amount(value: Any) -> str:
    """金额的输出归一：整数不带小数点，两位小数保留。"""
    if value is None or value == "":
        return ""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(f - round(f)) < 1e-9:
        return str(int(round(f)))
    return f"{f:.2f}"


def norm_date(y: Any, m: Any, d: Any) -> str | None:
    """三元素日期归一为 ISO 字符串；非法日期返回 None。"""
    try:
        return date(int(y), int(m), int(d)).isoformat()
    except (TypeError, ValueError):
        return None


# ============================================================================
# 候选数据结构
# ============================================================================

@dataclass
class Candidate:
    """一个字段的候选值。第二层的核心：候选全量保留，不轻易丢弃。"""
    field: str
    value: Any
    anchor: str = ""
    context: str = ""
    position: int = 0
    score: float = 0.0
    confidence: float = 0.0
    picked: bool = False
    reason: str = ""

    def as_row(self, contract_id: str) -> dict[str, Any]:
        return {
            "合同标识": contract_id,
            "字段": self.field,
            "是否采纳": "是" if self.picked else "否",
            "候选值": norm_amount(self.value) if isinstance(self.value, (int, float)) else (self.value or ""),
            "命中锚点": self.anchor,
            "候选得分": round(self.score, 2),
            "置信度": round(self.confidence, 2),
            "判定说明": self.reason,
            "原文片段": self.context,
        }


@dataclass
class PaymentNode:
    name: str
    ratio: float | None = None
    amount: float | None = None
    timing: str = ""
    context: str = ""
    confidence: float = 0.0
    kind: str = "pay"          # pay=支付节点 / retain=扣留项（质保金、保证金）

    def as_row(self, contract_id: str, index: int) -> dict[str, Any]:
        return {
            "合同标识": contract_id,
            "节点序号": index,
            "节点名称": self.name,
            "节点类型": "扣留项" if self.kind == "retain" else "支付节点",
            "比例(%)": round(self.ratio * 100, 4) if self.ratio is not None else "",
            "金额": round(self.amount, 2) if self.amount is not None else "",
            "约定时点": self.timing,
            "置信度": round(self.confidence, 2),
            "原文片段": self.context,
        }


@dataclass
class DocResult:
    """一份文件的读取结果。"""
    path: Path
    kind: str = "unknown"        # text / pdf_text / pdf_scanned / docx / txt / unsupported
    text: str = ""
    pages: int = 0
    chars: int = 0
    error: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class ContractRecord:
    """一份合同抽取出的台账记录。"""
    contract_id: str
    source: str
    kind: str = ""
    fields: dict[str, Any] = field(default_factory=dict)
    confidences: dict[str, float] = field(default_factory=dict)
    candidates: list[Candidate] = field(default_factory=list)
    nodes: list[PaymentNode] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def confidence(self) -> float:
        """整条记录的置信度 = 关键字段的最低值。"""
        keys = [k for k in ("对方名称", "合同金额") if k in self.confidences]
        if not keys:
            return 0.0
        return min(self.confidences[k] for k in keys)

    @property
    def pending(self) -> str:
        """待确认字段：置信度低于阈值的字段名，逗号分隔。

        阈值由 --conf-threshold 控制（默认 0.70）。
        """
        low = [k for k, v in self.confidences.items() if v < CONF_THRESHOLD]
        return "、".join(sorted(low))


# ============================================================================
# 文本获取
# ============================================================================

TEXT_EXT = {".txt", ".md", ".text"}
PDF_EXT = {".pdf"}
DOCX_EXT = {".docx"}
LEGACY_DOC_EXT = {".doc"}


def read_text_file(path: Path) -> str:
    for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk", "big5"):
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return path.read_bytes().decode("utf-8", errors="replace")


def read_pdf(path: Path) -> DocResult:
    res = DocResult(path=path)
    if not HAS_PYPDF:
        res.kind = "unsupported"
        res.error = "未安装 pypdf，无法读取 PDF。请先安装：python -m pip install \"pypdf>=5.0\""
        return res
    try:
        from pypdf import PdfReader
    except Exception as exc:  # pragma: no cover
        res.kind = "unsupported"
        res.error = f"pypdf 导入失败：{exc}"
        return res
    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        res.kind = "unsupported"
        res.error = f"PDF 打开失败：{exc}"
        return res

    if getattr(reader, "is_encrypted", False):
        try:
            reader.decrypt("")
        except Exception:
            pass

    chunks: list[str] = []
    empty_pages = 0
    total = len(reader.pages)
    for page in reader.pages:
        try:
            content = page.extract_text() or ""
        except Exception:
            content = ""
        if len(content.strip()) < 10:
            empty_pages += 1
        chunks.append(content)
    text = "\n".join(chunks)
    res.pages = total
    res.text = text
    res.chars = len(re.sub(r"\s", "", text))

    if total and empty_pages >= max(1, int(total * 0.6)) or res.chars < 30:
        res.kind = "pdf_scanned"
        res.warnings.append(
            "PDF 疑似扫描件或纯图件（无可用文本层）。本技能不做 OCR；"
            "请先用带 OCR 能力的技能转成文本，例如："
            f"pdf-toolkit 的 `text \"{path}\" --ocr --format txt`，再把输出文件交回本技能。"
        )
    else:
        res.kind = "pdf_text"
    if empty_pages and res.kind == "pdf_text":
        res.warnings.append(f"有 {empty_pages}/{total} 页未提取到文本，可能含图片页。")
    return res


def read_docx(path: Path) -> DocResult:
    res = DocResult(path=path)
    if not HAS_DOCX:
        res.kind = "unsupported"
        res.error = ("未安装 python-docx，无法读取 .docx。请先安装："
                     "python -m pip install \"python-docx>=1.1\"")
        return res
    try:
        import docx  # type: ignore

        document = docx.Document(str(path))
    except Exception as exc:
        res.kind = "unsupported"
        res.error = f"docx 打开失败：{exc}"
        return res

    parts: list[str] = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                parts.append("\t".join(cells))
    text = "\n".join(parts)
    res.kind = "docx"
    res.text = text
    res.chars = len(re.sub(r"\s", "", text))
    if res.chars < 30:
        res.warnings.append("docx 提取到的文本极少，可能是空文件或内容全在图片里。")
    return res


def load_document(path: Path) -> DocResult:
    suffix = path.suffix.lower()
    if suffix in PDF_EXT:
        return read_pdf(path)
    if suffix in DOCX_EXT:
        return read_docx(path)
    if suffix in TEXT_EXT:
        res = DocResult(path=path, kind="txt")
        res.text = read_text_file(path)
        res.chars = len(re.sub(r"\s", "", res.text))
        return res
    if suffix in LEGACY_DOC_EXT:
        res = DocResult(path=path, kind="unsupported")
        res.error = ("不支持旧版 .doc 格式。请先用 Word 或 WPS 另存为 .docx，"
                     "或另存为 PDF（需有文本层）后再处理。")
        return res
    res = DocResult(path=path, kind="unsupported")
    res.error = f"不支持的文件类型：{suffix or '(无扩展名)'}"
    return res


SUPPORTED_EXT = PDF_EXT | DOCX_EXT | TEXT_EXT

# 目录模式下要跳过的噪声：隐藏文件/隐藏目录，以及一带就上千个文件的目录
# （把技能指到一个含 node_modules 的目录时，不该产出几千行台账）
NOISE_DIRS = {
    "__pycache__", "node_modules", ".git", ".svn", ".hg", ".idea", ".vscode",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", "$recycle.bin",
    "system volume information",
}
NOISE_FILES = {"thumbs.db", "ehthumbs.db", "desktop.ini"}


def is_noise(p: Path, root: Path) -> bool:
    """隐藏文件 / Office 临时文件 / 噪声目录下的文件。"""
    name = p.name
    if name.startswith(".") or name.startswith("~$"):
        return True
    if name.lower() in NOISE_FILES:
        return True
    try:
        rel_dirs = p.relative_to(root).parts[:-1]
    except ValueError:
        rel_dirs = ()
    return any(d.startswith(".") or d.lower() in NOISE_DIRS for d in rel_dirs)


def collect_files(target: Path, recursive: bool = True) -> list[Path]:
    """收集待处理文件。

    **目录模式下不做扩展名过滤**（只排除隐藏文件与噪声目录）—— 单文件模式会为
    不支持的格式明确报错，目录模式若在过滤阶段就丢掉，用户会拿到一份
    「处理 3 个文件：正常 3」而完全看不到目录里那两份 .jpg / 附件.xlsx，
    属于静默忽略。收进来后它们以「不支持格式」状态进入台账并写进「解析告警」
    sheet，保证「输入里有什么」与「台账里有几行」对得上。

    （v1.0.0 只对旧版 .doc 做了这件事，其它扩展名仍然被静默过滤，是同一类缺陷
    只修了一半；v1.0.1 改为统一口径。）
    """
    if target.is_file():
        return [target]
    if not target.exists():
        return []
    it = target.rglob("*") if recursive else target.glob("*")
    files = [p for p in it if p.is_file() and not is_noise(p, target)]
    return sorted(files, key=lambda p: (str(p.parent).lower(), p.name.lower()))


# ============================================================================
# 我方名称的默认值来源
# ============================================================================

OUR_NAME_ENV = "CONTRACT_OUR_NAME"
OUR_NAME_CONFIG_NAMES = (".contract-toolkit.yaml", ".contract-toolkit.yml",
                         "contract-toolkit.yaml")


def _read_our_name_config(path: Path) -> str | None:
    """从配置文件里读 our_name。

    刻意不引 PyYAML：本技能的卖点之一是零重型依赖，为一行配置加一个解析器不划算。
    只支持两种写法，都足够表达一个键值：
      · 纯文本 `our_name: 北京星辰科技有限公司`（`#` 起注释，键名支持 - 或 _）
      · JSON `{"our_name": "北京星辰科技有限公司"}`（内容以 `{` 开头时按 JSON 读）
    """
    try:
        if not path.is_file():
            return None
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return None

    if text.lstrip().startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        for key in ("our_name", "our-name", "ourName"):
            v = data.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return None

    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, _, val = line.partition(":")
        if key.strip().replace("-", "_").lower() != "our_name":
            continue
        v = val.strip().strip("'\"")
        if v:
            return v
    return None


def _config_candidates(search_from: Path | None) -> list[Path]:
    """找配置文件的顺序：输入目录逐级向上（最多 6 级）→ 当前目录 → 用户主目录。"""
    dirs: list[Path] = []
    if search_from is not None:
        d = search_from if search_from.is_dir() else search_from.parent
        for _ in range(6):
            dirs.append(d)
            if d.parent == d:
                break
            d = d.parent
    dirs.append(Path.cwd())
    dirs.append(Path.home())

    out: list[Path] = []
    for d in dirs:
        for fn in OUR_NAME_CONFIG_NAMES:
            p = d / fn
            if p not in out:
                out.append(p)
    return out


def resolve_our_name(explicit: str | None,
                     search_from: Path | None = None) -> tuple[str | None, str]:
    """按 `--our-name` > 环境变量 > 配置文件 的优先级取我方名称。

    返回 (值, 来源说明)。来源说明只在使用默认值时有值 ——
    **命中的默认值必须显式告知**：静默套用比不套用更危险，用户会以为
    台账里的甲乙乙方是自己指定的，实际是上次遗留的配置在生效。
    """
    if explicit and explicit.strip():
        return explicit.strip(), ""
    env = os.environ.get(OUR_NAME_ENV, "").strip()
    if env:
        return env, f"环境变量 {OUR_NAME_ENV}"
    for p in _config_candidates(search_from):
        v = _read_our_name_config(p)
        if v:
            return v, f"配置文件 {p}"
    return None, ""


# ============================================================================
# 区域切分
# ============================================================================

# 条款正文开始的标志：出现「第一条」「一、」「甲方权利义务」这类结构标题
CLAUSE_START_RE = re.compile(
    r"^\s*(?:第\s*[一二三四五六七八九十百零〇\d]+\s*条"
    r"|[一二三四五六七八九十]+\s*[、.．]"
    r"|第\s*[一二三四五六七八九十]+\s*[章节部分])",
    re.MULTILINE,
)


@dataclass
class Regions:
    """合同文本的区域切分结果。"""
    head: str = ""       # 头部：当事人、合同名称、编号
    body: str = ""       # 条款正文
    tail: str = ""       # 落款：签字盖章、日期
    whole: str = ""

    def head_lines(self, limit: int = 20) -> list[str]:
        return [ln.strip() for ln in self.head.splitlines() if ln.strip()][:limit]


# 表格转文本后的列分隔特征：制表符，或两个以上连续空格/全角空格
_TABLE_SEP_RE = re.compile(r"\t| {2,}|　{2,}")


def looks_like_table(text: str, sample_lines: int = 60,
                     min_rows: int = 3, min_ratio: float = 0.3) -> bool:
    """粗判文本是否来自表格版式。

    表格转出来的文本有很强的特征：一行里用制表符或连续空格把单元格对齐，
    于是同一行会出现多个「列分隔」。表格版式最典型的后果就是金额与日期抽不到 ——
    它们的值在单元格里，后面既没有「元」字，也没有「生效日期：」这类标签。

    阈值刻意保守（≥3 行且占比 ≥30%）：宁可漏判，也不要把普通正文误判成表格 ——
    告警一旦开始误报，用户就不再逐条看，等于没有告警。
    """
    lines = [ln for ln in text.splitlines() if ln.strip()][:sample_lines]
    if len(lines) < min_rows:
        return False
    sep_rows = sum(1 for ln in lines if len(_TABLE_SEP_RE.findall(ln)) >= 2)
    return sep_rows >= min_rows and sep_rows / len(lines) >= min_ratio


def split_regions(text: str, head_chars: int = 600, tail_chars: int = 400) -> Regions:
    """把合同文本切成「头部 / 正文 / 落款」三块。

    切分策略：优先按条款标题切；找不到条款标题时按字符数兜底。
    头部信息（当事人、编号、名称）通常在开头，落款日期在结尾。
    """
    norm = "\n".join(ln.rstrip() for ln in (text or "").splitlines())
    regions = Regions(whole=norm)
    if not norm.strip():
        return regions

    match = CLAUSE_START_RE.search(norm)
    if match and match.start() > 0:
        cut = match.start()
        regions.head = norm[:cut]
        regions.body = norm[cut:]
    else:
        regions.head = norm[:head_chars]
        regions.body = norm[head_chars:]

    if len(norm) > tail_chars:
        regions.tail = norm[-tail_chars:]
    else:
        regions.tail = norm
    return regions


# ============================================================================
# 锚点判定（消歧的地基）
# ============================================================================

ANCHOR_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("total", TOTAL_ANCHORS),
    ("unit", UNIT_ANCHORS),
    ("tax", TAX_ANCHORS),
    ("node", NODE_ANCHORS),
    ("penalty", PENALTY_ANCHORS),
)


def nearest_anchor(text: str, pos: int, window: int = 32) -> tuple[str, str, int]:
    """在 pos 之前 window 字内找**距离最近**的锚点。

    返回 (类别, 锚点词, 距离)。找不到返回 ("", "", -1)。
    取「最近」而不是「最先命中」是关键 —— 「总价的 30%，即人民币 180,000 元」
    里最近的是「总价」，但「甲方支付预付款 30%，即人民币 180,000 元」里最近的是
    「预付款」，两者必须被分到不同类别。
    """
    prefix = text[max(0, pos - window):pos]
    best: tuple[int, str, str] | None = None
    for kind, anchors in ANCHOR_GROUPS:
        for anchor in anchors:
            idx = prefix.rfind(anchor)
            if idx < 0:
                continue
            dist = len(prefix) - idx - len(anchor)
            if best is None or dist < best[0]:
                best = (dist, kind, anchor)
    if best is None:
        return "", "", -1
    return best[1], best[2], best[0]


def _snippet(text: str, pos: int, width: int = 46) -> str:
    lo = max(0, pos - width // 2)
    hi = min(len(text), pos + width // 2)
    return text[lo:hi].replace("\n", " ").strip()


CLAUSE_SEPS = "。；;！？!?\n"


def _clause_bounds(text: str, pos: int) -> tuple[int, int]:
    """返回 pos 所在**分句**的起止下标。

    跨条款比较金额会产生假矛盾 —— 用固定字符窗口不行，必须按标点切分句。
    """
    left = max((text.rfind(ch, 0, pos) for ch in CLAUSE_SEPS), default=-1) + 1
    rights = [text.find(ch, pos) for ch in CLAUSE_SEPS]
    rights = [r for r in rights if r >= 0]
    right = min(rights) if rights else len(text)
    return left, right


# ============================================================================
# 金额候选抽取与消歧（第二层）
# ============================================================================

SCORE_TABLE: dict[str, float] = {
    "total": 5.0,
    "node": 1.0,
    "unknown": 0.0,
    "penalty": -2.0,
    "unit": -3.0,
    "tax": -5.0,
}

REASON_TEXT: dict[str, str] = {
    "total": "命中总价类锚点",
    "node": "属付款节点款，不是合同总价",
    "unknown": "无锚点，位置与数值推断",
    "penalty": "属违约金，不是合同总价",
    "unit": "属单价，不是合同总价",
    "tax": "属税率/税额，不是合同总价",
}


def extract_amounts(regions: Regions) -> list[Candidate]:
    """抽取全部金额候选，逐个打分。**此时不做取舍**。"""
    whole = regions.whole
    out: list[Candidate] = []

    for m in MONEY_RE.finditer(whole):
        raw_num = m.group(1) or m.group(3)
        unit = m.group(2) or m.group(4)
        if not raw_num:
            continue
        value = parse_arabic_amount(raw_num, unit)
        if value is None:
            continue
        kind, anchor, dist = nearest_anchor(whole, m.start())
        score = SCORE_TABLE.get(kind, 0.0)

        reasons = [REASON_TEXT.get(kind, "无锚点")]
        if kind == "unknown":
            score += 0.5
        if dist >= 0:
            score += max(0.0, 1.0 - dist / 40.0)
        if m.start() < len(whole) * 0.3:
            score += 0.5
        if value < 100:
            score -= 1.5
            reasons.append("数值过小")
        if value >= 1000 and abs(value - round(value)) < 1e-9:
            score += 0.3

        conf = 0.85 if kind == "total" else (0.55 if kind == "unknown" else 0.35)
        out.append(Candidate(
            field="合同金额", value=value, anchor=anchor or "(无)",
            context=_snippet(whole, m.start()), position=m.start(),
            score=score, confidence=conf, reason="；".join(reasons),
        ))

    # 中文大写金额单独成一类候选：它本身是确定性数据，且可用来校验阿拉伯数字
    for m in CN_AMOUNT_RE.finditer(whole):
        value = parse_cn_amount(m.group(1))
        if value is None:
            continue
        kind, anchor, dist = nearest_anchor(whole, m.start())
        score = SCORE_TABLE.get(kind, 0.0) + 2.0  # 大写金额可信度天生更高
        out.append(Candidate(
            field="合同金额",
            value=value,
            anchor=anchor or "(无)",
            context=_snippet(whole, m.start()),
            position=m.start(),
            score=score,
            confidence=0.92 if kind == "total" else 0.72,
            reason="中文大写金额" + ("；" + REASON_TEXT.get(kind, "") if kind else ""),
        ))

    _cross_validate_amounts(regions.whole, out)
    return out


def _cross_validate_amounts(whole: str, cands: list[Candidate]) -> None:
    """同一分句内大小写金额互相验证：一致则双向加分，不一致则标记矛盾。

    比较范围按标点切分句 —— 否则「合同总价款 600,000」会和隔壁条款的
    「预付款 180,000」被当成互相矛盾，给被采纳的候选打上误导性提示。
    """
    for a in cands:
        if a.value is None:
            continue
        lo, hi = _clause_bounds(whole, a.position)
        for b in cands:
            if b is a or b.value is None:
                continue
            if not (lo <= b.position <= hi):
                continue
            if abs(float(a.value) - float(b.value)) < 0.01:
                a.score += 2.5
                b.score += 2.5
                a.confidence = max(a.confidence, 0.98)
                b.confidence = max(b.confidence, 0.98)
                if "大小写金额一致" not in a.reason:
                    a.reason += "；与同句大小写金额一致"
            elif "同句存在不同金额" not in a.reason:
                a.reason += "；同句存在不同金额，需人工确认"


def pick_main_amount(cands: list[Candidate]) -> tuple[float | None, float, str]:
    """从候选里选合同金额。返回 (值, 置信度, 说明)。

    选不出来（无候选 / 全是低分）时返回 (None, 低置信度, 原因)，由调用方写入待确认。
    """
    usable = [c for c in cands if c.anchor != "(无)" or c.score > 0]
    if not usable:
        usable = list(cands)
    if not usable:
        return None, 0.0, "未找到任何金额候选"

    ranked = sorted(usable, key=lambda c: (-c.score, c.position))
    best = ranked[0]
    for c in cands:
        c.picked = c is best
    best.confidence = min(0.98, max(best.confidence, 0.5 + best.score / 20.0))
    # 只有「值不同」的候选才算真竞争 —— 大小写金额指向同一个数时不该降置信度
    runner_up = next(
        (c for c in ranked[1:]
         if c.value is not None and abs(float(c.value) - float(best.value)) > 0.005),
        None,
    )
    if runner_up is not None and abs(runner_up.score - best.score) < 0.8:
        best.confidence = min(best.confidence, 0.62)
        best.reason += "；与次优候选分差过小，需人工确认"
    return float(best.value), best.confidence, best.reason


# ============================================================================
# 当事人候选抽取（第二层）
# ============================================================================

NAME_CH = r"[\u4e00-\u9fa5A-Za-z0-9（）()·&，,]"
ROLE_ALT = "|".join(sorted(ROLE_WORDS, key=len, reverse=True))

PARTY_WITH_SEP_RE = re.compile(
    r"(" + ROLE_ALT + r")\s*(?:[（(][^）)]{0,24}[）)])?\s*(?:名称|全称)?\s*[：:]\s*"
    r"(" + NAME_CH + r"{2,40}?" + ORG_SUFFIX_RE + r")"
)
PARTY_WITH_GAP_RE = re.compile(
    r"(" + ROLE_ALT + r")\s*(?:[（(][^）)]{0,24}[）)])?\s+"
    r"(" + NAME_CH + r"{2,40}?" + ORG_SUFFIX_RE + r")"
)
ORG_ONLY_RE = re.compile(r"([\u4e00-\u9fa5A-Za-z0-9（）()·&]{2,40}?" + ORG_SUFFIX_RE + r")")


def _clean_org(name: str) -> str:
    """清洗组织名：去首尾分隔符与残留标点。"""
    name = name.strip(" \t:：,，。;；、（）()【】[]")
    name = re.sub(r"^(?:名称|全称|单位)\s*", "", name)
    name = re.sub(r"[。；;，,、]+$", "", name)
    return name.strip()


def extract_parties(regions: Regions) -> list[Candidate]:
    """抽取当事人名称。以「组织名后缀词」为边界，而不是靠长度猜。"""
    whole = regions.whole
    out: list[Candidate] = []

    seen: set[tuple[str, str]] = set()

    def add(role: str, name: str, pos: int, conf: float, reason: str) -> None:
        name = _clean_org(name)
        if len(name) < 4:
            return
        if re.search(r"\d", name) and not re.search(r"\d{4}", name):
            return                      # 名称里带纯数字基本是噪声
        key = (role, name)
        if key in seen:
            return
        seen.add(key)
        out.append(Candidate(
            field=role, value=name, anchor=role, context=_snippet(whole, pos),
            position=pos, score=conf * 10, confidence=conf, reason=reason,
        ))

    for m in PARTY_WITH_SEP_RE.finditer(whole):
        add(m.group(1), m.group(2), m.start(), 0.92, "角色词+分隔符+组织名后缀")
    for m in PARTY_WITH_GAP_RE.finditer(whole):
        add(m.group(1), m.group(2), m.start(), 0.85, "角色词+空白+组织名后缀")
    for m in ORG_ONLY_RE.finditer(whole):
        pos = m.start()
        # 角色词只在**同一行**里找：否则「采购方：北京星辰科技…\n乙方：上海云海…」
        # 会把「采购方」错配给下一行的乙方公司名
        line_start = whole.rfind("\n", 0, pos) + 1
        line_prefix = whole[line_start:pos]
        role = ""
        for word in sorted(ROLE_WORDS, key=len, reverse=True):
            if word in line_prefix:
                role = word
                break
        add(role or "未标明角色", m.group(1), pos,
            0.72 if role else 0.55,
            "组织名后缀" + ("+同行角色词" if role else "（同行无角色词）"))
    return out


def pick_parties(cands: list[Candidate]) -> tuple[dict[str, str], dict[str, float], str]:
    """按角色取最高分候选。返回 ({角色: 名称}, {角色: 置信度}, 待确认提示)。"""
    by_role: dict[str, Candidate] = {}
    for c in cands:
        cur = by_role.get(c.field)
        if cur is None or c.score > cur.score:
            by_role[c.field] = c
    names: dict[str, str] = {}
    confs: dict[str, float] = {}
    for role, cand in by_role.items():
        cand.picked = True
        names[role] = str(cand.value)
        confs[role] = cand.confidence
    notes: list[str] = []
    if not by_role:
        notes.append("未识别到任何当事人")
    elif "未标明角色" in by_role and len(by_role) == 1:
        notes.append("只找到组织名、未匹配到角色词")
    return names, confs, "；".join(notes)


# ============================================================================
# 日期候选抽取与归类（第二层）
# ============================================================================

# 后置锚点：日期**之后**的表述。元组顺序即匹配优先级。
#
# 这一组是实测换来的，起因是「生效日期」整列为空：
#   C) 「本合同自 2026-10-01 起至 2027-09-30 止」——起始日被错标成到期日；
#   G) 「本协议于 2026-10-01 起正式生效」——「起」与「生效」之间夹了「正式」；
#   I) 「自双方签署之日（2026-10-01）起生效」——日期在括号里，后置锚点被括号挡住。
# 教训：只看日期**前面**的 26 个字不够，中文合同里的起止结构大量使用后置表达。
_POST_DATE_RULES: tuple[tuple["re.Pattern[str]", str, str], ...] = (
    (re.compile(r"^[\s）)】」]*起\s*(?:至|到)"), "生效日期", "「起…至」区间起点"),
    (re.compile(r"^[\s）)】」]*起\s*(?:之日|之日起)?\s*"
                r"(?:正式|即|自动|均|同时|双方)?\s*(?:生效|执行|适用|履行)(?!日期|时间|日)"),
     "生效日期", "「起…生效」后置锚点"),
    (re.compile(r"^[\s）)】」]*起\s*(?:算|计算)"), "生效日期", "「起算」后置锚点"),
    (re.compile(r"^[\s）)】」]*(?:至|到)\s*\d{4}"), "生效日期", "「自…至/到…」区间起点"),
    # (?!日期|时间|日) 是必需的：否则同一行里紧跟的下一个字段名（「…：X 到期日期：Y」）
    # 会被当成这个日期的后置锚点，把 X 误标成 Y 的字段
    (re.compile(r"^[\s）)】」]*(?:之日|当日|即日)?\s*(?:生效|执行|适用)(?!日期|时间|日)"),
     "生效日期", "「生效」后置锚点"),
    (re.compile(r"^[\s）)】」]*(?:签订|签署|订立|签约)(?!日期|时间)"),
     "签订日期", "「签订/签署」后置锚点"),
    (re.compile(r"^[\s）)】」]*(?:止|届满|终止|截止|到期)(?!日期|时间|日)"),
     "到期日期", "「止/届满」后置锚点"),
)

# 同一日期兼作两个字段时，副字段的置信度（低于任何显式前置锚点的 0.93，
# 因此不会顶掉文档里真正写着「签订日期：」的那一处）
_SECONDARY_CONF = 0.70

# 前置锚点与日期之间的间隔超过这么多字，就不再认为它们是同一处表述
_ADJACENT_GAP = 6
_CLAUSE_PUNCT = re.compile(r"[，。；;：:！？!?、]")


def _post_anchor(suffix: str) -> tuple[str, str] | None:
    """日期之后的后置锚点，取优先级最高的一个。"""
    for pattern, field_name, label in _POST_DATE_RULES:
        if pattern.match(suffix):
            return field_name, label
    return None


def _pre_anchor(prefix: str) -> tuple[str, str, int] | None:
    """日期之前的前置锚点，返回 (字段, 锚点词, 距日期字数)。

    取**最靠近日期**的锚点，而不是固定的字段优先级：一行里同时写着
    「签订日期：X，生效日期：Y」时，只有比距离才能把两个日期分对。
    """
    tail = prefix[-26:]
    best: tuple[str, str, int] | None = None
    for field_name in ("签订日期", "生效日期", "到期日期"):
        for anchor in DATE_ANCHORS[field_name]:
            idx = tail.rfind(anchor)
            if idx < 0:
                continue
            dist = len(tail) - (idx + len(anchor))
            if best is None or dist < best[2]:
                best = (field_name, anchor, dist)
    return best


def _is_adjacent(prefix: str, pre: tuple[str, str, int]) -> bool:
    """前置锚点是否紧贴日期 —— 中间既不隔标点、也不隔别的句子。"""
    if pre[2] > _ADJACENT_GAP:
        return False
    gap = prefix[-pre[2]:] if pre[2] > 0 else ""
    return not _CLAUSE_PUNCT.search(gap)


def _date_signals(prefix: str, suffix: str) -> tuple[tuple[str, str], tuple[str, str] | None]:
    """返回 (主字段信息, 兼报字段信息)。

    优先级：后置锚点 > 前置锚点 > 「至/届满」前置词。
    「自双方签署之日（X）起生效」这类句子里，X 既是签订日也是生效日 ——
    主报生效日期（用户要找的正是它），同时兼报签订日期，不让任何一列落空。
    """
    post = _post_anchor(suffix)
    pre = _pre_anchor(prefix)
    if post is None and re.match(r"^[\s）)】」]*起", suffix) \
            and re.search(r"(自|从)[ \t]*$", prefix):
        # 「自 X 起」是合同里最主要的生效表述。这里刻意要求前面有「自/从」：
        # 否则「应于 X 起 30 日内交货」这类**期限窗口起点**会被误标成生效日期
        post = ("生效日期", "「自…起」结构")
    if post:
        secondary = None
        if pre and pre[0] != post[0] and _is_adjacent(prefix, pre):
            secondary = (pre[0], pre[1])
        return post, secondary
    if pre:
        return (pre[0], pre[1]), None
    if re.search(r"(至|到|届满|终止|截止)\s*$", prefix[-26:]):
        return ("到期日期", "「至/届满」前置锚点"), None
    return ("", ""), None


def _classify_date(prefix: str, suffix: str = "") -> tuple[str, str]:
    """按日期前后的文字判断它属于哪个日期字段（只返回主字段）。

    prefix 是日期**之前**的文本，suffix 是日期**之后**的文本 —— 两个方向都要看：
    「签订日期：X」的锚点在前，而「自 X 起生效」「自 X 起至 Y 止」的锚点在后。
    """
    return _date_signals(prefix, suffix)[0]


def extract_dates(regions: Regions) -> list[Candidate]:
    whole = regions.whole
    out: list[Candidate] = []
    prev_kind = ""
    for m in DATE_RE.finditer(whole):
        iso = norm_date(m.group(1), m.group(2), m.group(3))
        if not iso:
            out.append(Candidate(
                field="日期候选", value=m.group(0).strip(),
                context=_snippet(whole, m.start()), position=m.start(),
                score=-5.0, confidence=0.0, reason="非法日期（如 2 月 30 日）",
            ))
            continue
        # 前置锚点只在**同一行**内找：否则
        # 「签订日期：2026-12-01\n本合同自 2026-10-01 起生效」里，
        # 第二行的日期会被上一行残留的「签订日期」抢走，生效日期反而抽不到。
        # 后置锚点同样限定本行 —— 跨行匹配是同类误判的另一个入口。
        line_start = whole.rfind("\n", 0, m.start()) + 1
        line_end = whole.find("\n", m.end())
        if line_end < 0:
            line_end = len(whole)
        prefix = whole[max(line_start, m.start() - 26):m.start()]
        suffix = whole[m.end():min(line_end, m.end() + 14)]
        (field_name, anchor), secondary = _date_signals(prefix, suffix)
        if not field_name:
            if prev_kind == "生效日期" and re.search(r"(至|到|至\s*\d{4})", prefix):
                field_name, anchor = "到期日期", "承接起止结构"
            else:
                field_name, anchor = "日期候选", "无锚点"
        conf = 0.93 if field_name in DATE_ANCHORS else 0.5
        out.append(Candidate(
            field=field_name, value=iso, anchor=anchor,
            context=_snippet(whole, m.start()), position=m.start(),
            score=conf * 10, confidence=conf,
            reason=f"锚点「{anchor}」" if anchor else "无锚点",
        ))
        if field_name in DATE_ANCHORS:
            prev_kind = field_name
            # 兼报：同一日期同时被前置与后置锚点指向（「自签署之日（X）起生效」）
            if secondary:
                out.append(Candidate(
                    field=secondary[0], value=iso,
                    anchor=secondary[1] + "（同句兼报）",
                    context=_snippet(whole, m.start()), position=m.start(),
                    score=_SECONDARY_CONF * 10, confidence=_SECONDARY_CONF,
                    reason=f"同一日期被「{secondary[1]}」与后置锚点「{anchor}」共同指向",
                ))
    return out


def pick_dates(cands: list[Candidate]) -> tuple[dict[str, str], dict[str, float]]:
    best: dict[str, Candidate] = {}
    for c in cands:
        if c.field not in DATE_ANCHORS:
            continue
        cur = best.get(c.field)
        if cur is None or c.score > cur.score:
            best[c.field] = c
    values: dict[str, str] = {}
    confs: dict[str, float] = {}
    for k, cand in best.items():
        cand.picked = True
        values[k] = str(cand.value)
        confs[k] = cand.confidence
    return values, confs


# ============================================================================
# 付款节点抽取（第二层）
# ============================================================================

NODE_ALT = "|".join(sorted(NODE_ANCHORS, key=len, reverse=True))
# 「固定金额」「约定金额」里含子串「定金」，加前置否词避免把「不约定固定金额」
# 错当成一个「定金」付款节点
NODE_BLOCK_RE = re.compile(r"(?<!固)(?<!约)(" + NODE_ALT + r")")
WORKDAY_RE = re.compile(r"(\d{1,3})\s*(?:个)?\s*(?:工作日|日|天)")
PHASE_RE = re.compile(r"(?:第|前|后)?\s*(\d{1,3})\s*(?:个)?\s*(?:月|年)")


def extract_payment_nodes(regions: Regions) -> list[PaymentNode]:
    whole = regions.whole
    nodes: dict[str, PaymentNode] = {}

    for m in NODE_BLOCK_RE.finditer(whole):
        name = m.group(1)
        # 比例与金额：只在**节点词之后**、且**同一分句内**找 ——
        #   跨分句会把后面条款的违约金比例（20%）当成这个节点的付款比例；
        #   往前找则会把上一个节点的比例重复算进来
        _, clause_end = _clause_bounds(whole, m.end())
        after = whole[m.end():min(clause_end, m.end() + 90)]
        # 约定时点：在**整个分句**里找 —— 它常写在节点词之前，
        # 如「合同签订后 5 个工作日内，甲方支付预付款 30%」
        clause_start, _ = _clause_bounds(whole, m.start())
        clause = whole[max(clause_start, m.start() - 60):min(clause_end, m.end() + 90)]
        ratio = None
        amount = None
        timing = ""

        pm = PERCENT_RE.search(after)
        if pm:
            try:
                ratio = float(pm.group(1)) / 100.0
            except ValueError:
                ratio = None

        am = MONEY_RE.search(after)
        if am:
            amount = parse_arabic_amount(am.group(1) or am.group(3), am.group(2) or am.group(4))
        else:
            cm = CN_AMOUNT_RE.search(after)
            if cm:
                amount = parse_cn_amount(cm.group(1))

        wm = WORKDAY_RE.search(clause)
        if wm:
            day = wm.group(1)
            unit = "工作日" if "工作日" in wm.group(0) else "日"
            timing = f"{day} 个{unit}内" if unit == "工作日" else f"{day} 日内"
        else:
            fm = PHASE_RE.search(clause)
            if fm:
                timing = f"{fm.group(1)} 个月内" if "月" in fm.group(0) else f"{fm.group(1)} 年内"

        conf = 0.85 if ratio is not None else (0.7 if amount is not None else 0.45)
        node_kind = "retain" if any(r in name for r in RETAIN_NODES) else "pay"
        node = nodes.get(name)
        if node is None:
            nodes[name] = PaymentNode(
                name=name, ratio=ratio, amount=amount, timing=timing,
                context=_snippet(whole, m.start()), confidence=conf, kind=node_kind,
            )
        else:
            if node.ratio is None and ratio is not None:
                node.ratio = ratio
                node.confidence = max(node.confidence, conf)
            if node.amount is None and amount is not None:
                node.amount = amount
                node.confidence = max(node.confidence, conf)
            if not node.timing and timing:
                node.timing = timing

    return list(nodes.values())


# ============================================================================
# 其它要素
# ============================================================================

CONTRACT_NO_RE = re.compile(r"(?:合同编号|协议编号|合同号|编号|文件编号)\s*[：:]\s*([A-Za-z0-9\-—_/（）()]{3,40})")
DISPUTE_RE = re.compile(r"((?:提交|向)[^。；;\n]{2,40}?(?:仲裁委员会|人民法院|人民法院起诉|仲裁机构))")
# 比例类要素的锚点可能在数字前或后：「质保金为合同总价的 5%」
# 与「按合同总价的 0.5% 向甲方支付违约金」两种写法都要认
QUALITY_RE = re.compile(
    r"(?:质保金|保修金|质量保证金)[^。；;\n]{0,30}?(\d{1,3}(?:\.\d+)?)\s*%"
    r"|(\d{1,3}(?:\.\d+)?)\s*%[^。；;\n]{0,24}?(?:质保金|保修金|质量保证金)"
)
PENALTY_RE = re.compile(
    r"(?:违约金|滞纳金)[^。；;\n]{0,30}?(\d{1,3}(?:\.\d+)?)\s*%"
    r"|(\d{1,3}(?:\.\d+)?)\s*%[^。；;\n]{0,24}?(?:违约金|滞纳金)"
)
PAY_METHOD_RE = re.compile(r"(?:付款方式|支付方式)\s*[：:]?\s*([^。；;\n]{2,40})")


def extract_extras(regions: Regions) -> tuple[dict[str, Any], dict[str, float], list[Candidate]]:
    """抽取税率 / 违约金比例 / 质保金比例 / 争议解决 / 合同编号 / 付款方式。"""
    whole = regions.whole
    values: dict[str, Any] = {}
    confs: dict[str, float] = {}
    cands: list[Candidate] = []

    m = RATE_RE.search(whole)
    if m:
        try:
            rate = float(m.group(1)) / 100.0
            values["税率"] = norm_amount(round(rate * 100, 4)) + "%"
            confs["税率"] = 0.9
        except ValueError:
            pass

    for key, rx, label in (("质保金比例", QUALITY_RE, "质保金"),
                           ("违约金比例", PENALTY_RE, "违约金")):
        mm = rx.search(whole)
        if mm:
            ratio = mm.group(1) or mm.group(2)
            if ratio:
                values[key] = norm_amount(ratio) + "%"
                confs[key] = 0.85
                cands.append(Candidate(
                    field=key, value=values[key], anchor=label,
                    context=_snippet(whole, mm.start()), position=mm.start(),
                    score=8.5, confidence=0.85, reason=f"命中「{label}」锚点",
                ))

    m = CONTRACT_NO_RE.search(whole)
    if m:
        values["合同编号"] = m.group(1).strip()
        confs["合同编号"] = 0.8

    m = DISPUTE_RE.search(whole)
    if m:
        values["争议解决"] = m.group(1).strip()
        confs["争议解决"] = 0.75

    m = PAY_METHOD_RE.search(whole)
    if m:
        values["付款方式"] = m.group(1).strip()
        confs["付款方式"] = 0.7

    return values, confs, cands


def guess_contract_name(path: Path, regions: Regions) -> tuple[str, float]:
    """合同名称：优先取头部里的标题行，退化为文件名。"""
    for line in regions.head.splitlines()[:8]:
        line = line.strip()
        if 4 <= len(line) <= 40 and re.search(r"(合同|协议|契约|订单|意向书)", line):
            if not any(w in line for w in ROLE_WORDS):
                return line, 0.8
    stem = re.sub(r"[_\-\s]+", " ", path.stem).strip()
    return stem, 0.5


def guess_our_role(text: str, our_name: str | None) -> tuple[str, str, float]:
    """判断我方在合同中的角色。只能靠用户给出我方名称来匹配。

    返回 (我方角色, 对方角色, 置信度)。未提供我方名称时返回空，交人工填。
    """
    if not our_name:
        return "", "", 0.0
    for role, other in (("甲方", "乙方"), ("乙方", "甲方")):
        m = re.search(role + r"\s*(?:[（(][^）)]{0,24}[）)])?\s*(?:名称|全称)?\s*[：:]\s*"
                      r"([^\n]{2,40})", text)
        if m and our_name in m.group(1):
            return role, other, 0.9
    return "", "", 0.0


CREDIT_CODE_RE = re.compile(r"(?<![0-9A-Z])[0-9A-HJ-NPQRTUWXY]{18}(?![0-9A-Z])")


def extract_credit_code(regions: Regions) -> tuple[str, float]:
    """统一社会信用代码：18 位定长格式。只做格式匹配，不做校验位验证。"""
    for m in CREDIT_CODE_RE.finditer(regions.whole):
        return m.group(0), 0.80
    return "", 0.0


# ============================================================================
# 台账记录装配
# ============================================================================

LEDGER_COLUMNS: tuple[str, ...] = (
    "合同标识", "合同编号", "合同名称", "我方角色", "对方名称", "统一社会信用代码",
    "合同金额", "币种", "税率", "签订日期", "生效日期", "到期日期", "合同期限(天)",
    "付款方式", "质保金比例", "违约金比例", "争议解决", "源文件", "置信度",
    "待确认字段", "处理状态",
)

NODE_COLUMNS: tuple[str, ...] = (
    "合同标识", "节点序号", "节点名称", "节点类型", "比例(%)", "金额", "约定时点",
    "置信度", "原文片段",
)

CANDIDATE_COLUMNS: tuple[str, ...] = (
    "合同标识", "字段", "是否采纳", "候选值", "命中锚点", "候选得分", "置信度",
    "判定说明", "原文片段",
)

WARN_COLUMNS: tuple[str, ...] = ("合同标识", "源文件", "状态", "告警内容")


def build_record(path: Path, our_name: str | None = None) -> ContractRecord:
    """把一份文件变成一条合同记录。**只抽取，不判定**。"""
    doc = load_document(path)
    rec = ContractRecord(
        contract_id=path.stem,
        source=str(path),
        kind=doc.kind,
    )
    rec.warnings.extend(doc.warnings)

    if doc.error:
        rec.warnings.append(doc.error)
        rec.fields["处理状态"] = "不支持格式" if doc.kind == "unsupported" else "解析失败"
        return rec
    if doc.kind == "pdf_scanned":
        rec.fields["处理状态"] = "扫描件未提取"
        return rec
    if not doc.text.strip():
        rec.warnings.append("未抽取到任何文本")
        rec.fields["处理状态"] = "无文本内容"
        return rec

    regions = split_regions(doc.text)
    fields: dict[str, Any] = {}
    confs: dict[str, float] = {}

    # --- 合同名称 ---
    name, name_conf = guess_contract_name(path, regions)
    fields["合同名称"] = name
    confs["合同名称"] = name_conf

    # --- 金额（第二层：候选 + 消歧）---
    amount_cands = extract_amounts(regions)
    rec.candidates.extend(amount_cands)
    amount, amount_conf, amount_note = pick_main_amount(amount_cands)
    if amount is not None:
        # 写数值而非字符串 —— 财务用户要能在 Excel 里直接对金额列求和
        fields["合同金额"] = round(float(amount), 2)
        confs["合同金额"] = round(amount_conf, 2)
    else:
        # 关键字段缺失时登记 0 置信度 —— 否则置信度表里没有这个键，
        # 「待确认字段」列不会列出它，用户从台账上看不出「少了什么」
        confs["合同金额"] = 0.0
        rec.warnings.append("合同金额未抽出：" + amount_note)

    # --- 当事人（第二层）---
    party_cands = extract_parties(regions)
    rec.candidates.extend(party_cands)
    parties, party_confs, party_note = pick_parties(party_cands)
    if party_note:
        rec.warnings.append("当事人抽取：" + party_note)

    our_role, other_role, role_conf = guess_our_role(regions.whole, our_name)
    if our_role:
        fields["我方角色"] = our_role
        confs["我方角色"] = role_conf
        other_name = parties.get(other_role, "")
        if other_name:
            fields["对方名称"] = other_name
            confs["对方名称"] = party_confs.get(other_role, 0.5)
    else:
        # 没有我方名称：按角色优先序取一个作为「对方名称」并注明不确定
        for role in ("乙方", "甲方", "供方", "需方", "受托方", "委托方"):
            if role in parties:
                fields["对方名称"] = parties[role]
                confs["对方名称"] = min(party_confs.get(role, 0.5), 0.6)
                rec.warnings.append(
                    f"未提供我方名称，暂将「{role}」列为对方名称；"
                    "建议用 --our-name 指定我方全称以准确区分甲乙方")
                break
        else:
            for role, nm in parties.items():
                if role != "未标明角色":
                    fields["对方名称"] = nm
                    confs["对方名称"] = min(party_confs.get(role, 0.5), 0.6)
                    break
    if "对方名称" not in fields:
        confs["对方名称"] = 0.0
        rec.warnings.append("未识别到对方名称：合同里可能没有以组织名后缀结尾的主体，"
                            "或该文件不是合同（如询价单、收货单）")
    # 全部当事人另出一列备查
    if parties:
        fields["当事人(全部)"] = "；".join(
            f"{r}:{n}" for r, n in sorted(parties.items()))

    code, code_conf = extract_credit_code(regions)
    if code:
        fields["统一社会信用代码"] = code
        confs["统一社会信用代码"] = code_conf

    # --- 日期（第二层）---
    date_cands = extract_dates(regions)
    rec.candidates.extend(date_cands)
    dates, date_confs = pick_dates(date_cands)
    for k, v in dates.items():
        fields[k] = v
        confs[k] = date_confs.get(k, 0.5)
    loose = [c for c in date_cands if c.field == "日期候选"]
    if loose and not dates:
        rec.warnings.append(
            "抽到日期但无法归类（缺「签订/生效/到期」锚点）："
            + "、".join(str(c.value) for c in loose[:5]))

    # 表格版式的定向提示。只在「关键字段真的缺了」+「文本确实带表格特征」时报 ——
    # 不加第二个条件的话，每份不写金额的框架协议都会背一条毫无用处的告警。
    missing: list[str] = []
    if "合同金额" not in fields:
        missing.append("合同金额")
    if not any(k in fields for k in ("签订日期", "生效日期", "到期日期")):
        missing.append("日期")
    if missing and looks_like_table(regions.whole):
        rec.warnings.append(
            "疑似表格版式（未抽到 " + "、".join(missing) + "）：这类的数字在表格单元格里，"
            "后面既没有「元」字也没有「生效日期：」这样的标签。可先用 pdf-toolkit 的 "
            "tables 子命令把表格抽出来，或直接在台账里手工补齐这几列")

    # 期限（第一层：由两个日期直接算，确定）
    d1, d2 = _to_date(fields.get("生效日期")), _to_date(fields.get("到期日期"))
    if d1 and d2 and d2 >= d1:
        fields["合同期限(天)"] = (d2 - d1).days

    # --- 付款节点（第二层）---
    rec.nodes = extract_payment_nodes(regions)
    if rec.nodes:
        unknown_ratio = [n for n in rec.nodes if n.ratio is None and n.amount is None]
        if unknown_ratio:
            rec.warnings.append(
                "有付款节点未抽到比例或金额：" + "、".join(n.name for n in unknown_ratio))

    # --- 其它要素 ---
    extras, extra_confs, extra_cands = extract_extras(regions)
    rec.candidates.extend(extra_cands)
    for k, v in extras.items():
        fields[k] = v
        confs[k] = extra_confs.get(k, 0.5)

    fields["币种"] = "CNY"
    fields["处理状态"] = "正常"

    rec.fields = fields
    rec.confidences = confs
    return rec


def _to_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    s = str(value).strip()
    if len(s) > 10:
        s = s[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _is_number(value: Any) -> bool:
    if value is None or value == "":
        return False
    try:
        float(str(value).replace(",", "").replace("，", ""))
        return True
    except (TypeError, ValueError):
        return False


def record_row(rec: ContractRecord) -> dict[str, Any]:
    """把记录摊平成台账一行（列顺序固定）。"""
    row: dict[str, Any] = {c: rec.fields.get(c, "") for c in LEDGER_COLUMNS}
    row["合同标识"] = rec.contract_id
    row["源文件"] = rec.source
    row["置信度"] = round(rec.confidence, 2)
    row["待确认字段"] = rec.pending
    extra = rec.fields.get("当事人(全部)")
    if extra:
        row["当事人(全部)"] = extra
    return row


# ============================================================================
# 输出：xlsx / csv / html
# ============================================================================

# 需要整行标底的列与判据。xlsx 与 html 两种写出共用同一份规则 ——
# 分成两处写迟早会走偏（同一份台账两种格式标出的问题行不一致）。
WARN_ROW_RULES: tuple[tuple[str, "Any"], ...] = (
    ("置信度", lambda v: isinstance(v, (int, float)) and v < CONF_THRESHOLD),
    ("严重级别", lambda v: v == "高"),
    ("状态", lambda v: v in ("已到期", "异常")),
    ("处理状态", lambda v: v in ("解析失败", "不支持格式", "扫描件未提取", "无文本内容")),
)


def _disp_width(text: str) -> int:
    """按东亚字符宽度估算显示宽度，用于列宽自适应。"""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _write_styled_workbook(sheets: dict[str, "Any"], path: Path) -> Path:
    """写出多 sheet xlsx，样式与 reconcile-toolkit / invoice-toolkit 保持一致。

    警示底色规则：置信度 < CONF_THRESHOLD（默认 0.70，可用 --conf-threshold 调）、
    严重级别为「高」、状态为「已到期」的行整行着色。
    """
    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    header_fill = PatternFill("solid", fgColor="1FA055")
    header_font = Font(bold=True, color="FFFFFF")
    warn_fill = PatternFill("solid", fgColor="FCEBEB")
    header_align = Alignment(horizontal="center", vertical="center")

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook(write_only=True)
    for name, df in sheets.items():
        ws = wb.create_sheet(title=str(name)[:31])
        ws.freeze_panes = "A2"

        header_cells = []
        for col in df.columns:
            c = WriteOnlyCell(ws, value=col)
            c.fill = header_fill
            c.font = header_font
            c.alignment = header_align
            header_cells.append(c)
        ws.append(header_cells)

        warn_tests: list[tuple[int, Any]] = []
        cols = list(df.columns)
        for label, test in WARN_ROW_RULES:
            if label in cols:
                warn_tests.append((cols.index(label), test))

        for row in df.itertuples(index=False):
            # 空值写 None（真空单元格）而不是 ""，否则整列被读成 object，
            # 用户在 Excel 里对金额列求和会被当混合类型
            vals = [
                None if (v is None or (isinstance(v, float) and v != v)) else v
                for v in row
            ]
            hit = any(test(vals[i]) for i, test in warn_tests)
            if not hit:
                ws.append(vals)
                continue
            # write_only 模式下整行必须统一为 WriteOnlyCell —— 与普通值混用
            # 会让 lxml 序列化器状态错乱（LxmlSyntaxError: inconsistent exit action）
            cells = []
            for v in vals:
                c = WriteOnlyCell(ws, value=v)
                c.fill = warn_fill
                cells.append(c)
            ws.append(cells)

        for i, col in enumerate(cols, start=1):
            max_len = _disp_width(str(col))
            for v in df[col].head(200):
                s = "" if (v is None or (isinstance(v, float) and v != v)) else str(v)
                max_len = max(max_len, _disp_width(s))
            ws.column_dimensions[get_column_letter(i)].width = min(max_len + 2, 42)
    wb.save(str(path))
    return path


def _fmt_html_value(value: Any) -> str:
    """单元格值 → HTML 文本。数值去掉无意义的小数尾巴（600000.0 → 600000）。"""
    if value is None:
        return ""
    try:
        if value != value:          # 浮点 NaN；pd.NA / NaT 会在这里抛 TypeError
            return ""
    except (TypeError, ValueError):
        return ""
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else f"{value:g}"
    s = str(value)
    return "" if s in ("<NA>", "NaT", "None") else s


def _write_html_report(sheets: dict[str, "Any"], path: Path, max_rows: int = 300) -> Path:
    """写出单文件自包含 HTML 报告（内联 CSS，无外部资源、无 CDN）。

    给不装 Excel / WPS 的接收方看 —— 双击用浏览器打开即可，不需要任何网络。
    行数超过 max_rows 时只预览前 max_rows 行并注明：几百份合同的台账若全量内联，
    单文件会膨胀到几十 MB，浏览器打开会卡；完整数据本来就在同名的 xlsx / csv 里。
    """
    import html as _html

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    blocks: list[str] = []
    for name, df in sheets.items():
        cols = list(df.columns)
        warn_tests = [(cols.index(lb), t) for lb, t in WARN_ROW_RULES if lb in cols]
        total = len(df)
        shown = df.head(max_rows)
        head = "".join(f"<th>{_html.escape(str(c))}</th>" for c in cols)
        body: list[str] = []
        for row in shown.itertuples(index=False):
            vals = list(row)
            hit = any(t(vals[i]) for i, t in warn_tests)
            cls = ' class="warn"' if hit else ""
            tds = "".join(f"<td>{_html.escape(_fmt_html_value(v))}</td>" for v in vals)
            body.append(f"<tr{cls}>{tds}</tr>")
        note = ""
        if total > max_rows:
            note = (f'<p class="note">共 {total} 行，此处预览前 {max_rows} 行；'
                    f'完整数据见同名的 xlsx / csv。</p>')
        blocks.append(
            f'<section><h2>{_html.escape(str(name))}'
            f'<span class="count">{total} 行</span></h2>{note}'
            f'<div class="wrap"><table><thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div></section>'
        )

    doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_html.escape(path.stem)}</title>
<style>
:root{{color-scheme:light}}
body{{margin:0;padding:24px;background:#F5F5F3;color:#2C2C2A;
  font:400 13px/1.6 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}}
h1{{font-size:18px;font-weight:500;margin:0 0 4px}}
.sub{{color:#5F5E5A;margin:0 0 20px}}
section{{background:#fff;border:1px solid #E3E3DF;border-radius:12px;
  padding:16px;margin-bottom:16px}}
h2{{font-size:14px;font-weight:500;margin:0 0 12px}}
.count{{color:#5F5E5A;font-weight:400;margin-left:8px}}
.note{{color:#5F5E5A;margin:0 0 8px}}
.wrap{{overflow-x:auto}}
table{{border-collapse:collapse;width:100%;white-space:nowrap}}
thead th{{background:#1FA055;color:#fff;font-weight:500;text-align:left;
  padding:6px 10px;position:sticky;top:0}}
td{{padding:5px 10px;border-bottom:1px solid #EFEFEC}}
tr.warn td{{background:#FCEBEB}}
tbody tr:hover td{{background:#F7F7F5}}
tbody tr.warn:hover td{{background:#F7D9D9}}
</style>
</head>
<body>
<h1>合同要素台账 · 报告</h1>
<p class="sub">由 contract-toolkit v{__version__} 生成；低置信度与异常行已标底色。</p>
{"".join(blocks)}
</body>
</html>
"""
    path.write_text(doc, encoding="utf-8")
    return path


def write_report(sheets: dict[str, "Any"], path: Path) -> list[Path]:
    """写多 sheet 报告。非 xlsx / html 退化为每 sheet 一个同名文件，返回真实路径。"""
    import pandas as pd

    path = Path(path)
    if path.suffix.lower() == ".xlsx":
        return [_write_styled_workbook(sheets, path)]
    if path.suffix.lower() in (".html", ".htm"):
        return [_write_html_report(sheets, path)]

    path.parent.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, df in sheets.items():
        target = path.with_name(f"{path.stem}__{name}{path.suffix}")
        if path.suffix.lower() == ".csv":
            df.to_csv(target, index=False, encoding="utf-8-sig")
        elif path.suffix.lower() == ".tsv":
            df.to_csv(target, index=False, sep="\t", encoding="utf-8-sig")
        else:
            raise ValueError(f"不支持的输出格式：{path.suffix}（支持 .xlsx / .csv / .tsv / .html）")
        written.append(target)
    return written


def _read_ledger(path: Path) -> dict[str, "Any"]:
    import pandas as pd

    xls = pd.ExcelFile(path)
    return {name: xls.parse(name) for name in xls.sheet_names}


# ============================================================================
# 子命令实现
# ============================================================================

def cmd_info(args: argparse.Namespace) -> int:
    print(f"contract-toolkit v{__version__}")
    print("=" * 62)
    print("依赖自检：")
    for mod, hint, required in (
        ("pandas", "pandas>=2.0", True),
        ("openpyxl", "openpyxl>=3.1", True),
        ("pypdf", "pypdf>=5.0", False),
        ("docx", "python-docx>=1.1", False),
    ):
        ok = _has(mod)
        flag = "[OK  ]" if ok else ("[缺失]" if required else "[可选]")
        note = "" if ok else f"  → python -m pip install \"{hint}\""
        print(f"  {flag} {mod:<10}{note}")
    print("  说明：pypdf 缺失则无法读 PDF；python-docx 缺失则无法读 .docx。")
    print("  本技能不做 OCR，扫描件请先用 pdf-toolkit 的 text --ocr 转文本。" if not _has("pytesseract")
          else "  注意：本技能自身不调用 OCR，即使本机装了 pytesseract。")

    target = Path(args.path) if args.path else None
    if target is None:
        return 0
    files = collect_files(target, recursive=args.recursive)
    print()
    print(f"目录摸底：{target}")
    if target.is_dir():
        print("  范围：" + ("含子目录（只处理当前层请加 --no-recursive）" if args.recursive
                          else "仅当前层（要连子目录一起处理请加 --recursive）"))
    if not files:
        print("  目录内没有任何文件（已排除隐藏文件与噪声目录）")
        return 0

    stats: dict[str, int] = {}
    scanned: list[str] = []
    legacy: list[str] = []
    other: list[tuple[str, str]] = []
    order: list[str] = []
    ext_kind = {"pdf": "pdf", "docx": "docx", "txt": "txt", "md": "md"}

    # 与 collect_files 同一口径、同一份 files 列表 —— 分别统计「按类型」的分布
    # 与「需要人工处理」的两类（旧版 .doc 可救 / 其它格式不支持）。
    # 关键：这里的总数必须等于 collect_files 收进来的数量，否则「合计」会与
    # parse 的「处理 N 个文件」对不上。
    for f in files:
        ext = f.suffix.lower()
        if ext in LEGACY_DOC_EXT:
            kind = "doc(旧版)"
            legacy.append(f.name)
        elif ext not in SUPPORTED_EXT:
            kind = "其它格式"
            other.append((f.name, f"不支持的扩展名 {f.suffix or '(无)'}"))
        elif args.probe_text:
            kind = load_document(f).kind
            if kind == "pdf_scanned":
                scanned.append(f.name)
        else:
            kind = ext_kind.get(ext.lstrip("."), "其它格式")
        stats[kind] = stats.get(kind, 0) + 1
        if kind not in order:
            order.append(kind)

    total = len(files)
    for kind in order:
        print(f"  {kind:<14} {stats[kind]:>4} 个")
    print(f"  {'-' * 14} {'-' * 4}")
    line = f"  {'合计':<14} {total:>4} 个"
    notes = []
    if legacy:
        notes.append(f"{len(legacy)} 个旧版 .doc 需先转换")
    if other:
        notes.append(f"{len(other)} 个格式不支持")
    if notes:
        line += f"（{'、'.join(notes)}，不会参与抽取）"
    print(line)
    if scanned:
        print()
        print(f"  [!] 疑似扫描件 {len(scanned)} 个（无文本层，本技能不做 OCR）：")
        for n in scanned[:10]:
            print(f"      · {n}")
        if len(scanned) > 10:
            print(f"      … 另有 {len(scanned) - 10} 个")
    if legacy or other:
        print()
        print(f"  需人工处理 {len(legacy) + len(other)} 个（这些文件仍会进台账，"
              f"状态列为「不支持格式」）：")
        for n in legacy[:10]:
            print(f"      · {n} —— 旧版 .doc 格式，需另存为 .docx 或带文本层的 PDF 后再处理")
        for n, why in other[:10]:
            print(f"      · {n} —— {why}")
        rest = len(legacy) + len(other) - min(len(legacy), 10) - min(len(other), 10)
        if rest > 0:
            print(f"      … 另有 {rest} 个")
    if not args.probe_text:
        print()
        print("  提示：加 --probe-text 可实际读一遍文件，统计文本层覆盖率与扫描件占比。")
    return 0


def _parse_one(rec: ContractRecord, out_sheets: dict[str, list]) -> None:
    out_sheets["合同台账"].append(record_row(rec))
    for i, node in enumerate(rec.nodes, start=1):
        out_sheets["付款节点"].append(node.as_row(rec.contract_id, i))
    for cand in rec.candidates:
        out_sheets["抽取候选"].append(cand.as_row(rec.contract_id))
    for w in rec.warnings:
        status = rec.fields.get("处理状态", "告警")
        out_sheets["解析告警"].append({
            "合同标识": rec.contract_id,
            "源文件": rec.source,
            "状态": status,
            "告警内容": w,
        })


def _print_probe(rec: ContractRecord, doc: DocResult) -> None:
    print(f"探测：{rec.source}")
    print(f"  类型：{rec.kind}    页数：{doc.pages}    有效字符：{doc.chars}")
    print(f"  区域切分：头部 {len(split_regions(doc.text).head)} 字 / "
          f"正文 {len(split_regions(doc.text).body)} 字")
    print()
    print("  字段抽取结果：")
    for col in LEDGER_COLUMNS:
        if col in ("合同标识", "源文件", "置信度", "待确认字段", "处理状态"):
            continue
        value = rec.fields.get(col, "")
        conf = rec.confidences.get(col)
        mark = "  " if not value else ("!!" if conf is not None and conf < CONF_THRESHOLD else "OK")
        conf_s = f"(置信度 {conf:.2f})" if conf is not None else ""
        print(f"    {mark} {col:<16} {value!s:<34} {conf_s}")
    print()
    print("  金额候选（按得分排序）：")
    amount_cands = [c for c in rec.candidates if c.field == "合同金额"]
    for c in sorted(amount_cands, key=lambda x: -x.score)[:8]:
        flag = "采纳" if c.picked else "落选"
        print(f"    [{flag}] {norm_amount(c.value):>16}  锚点「{c.anchor}」  得分 {c.score:+.2f}")
        print(f"            {c.reason}")
    print()
    print("  当事人候选：")
    for c in sorted([x for x in rec.candidates if x.anchor in ROLE_WORDS or x.field == "未标明角色"],
                    key=lambda x: -x.score)[:8]:
        print(f"    {c.field:<8} {c.value!s:<28} 置信度 {c.confidence:.2f}  {c.reason}")
    if rec.nodes:
        print()
        print("  付款节点：")
        for node in rec.nodes:
            ratio = f"{node.ratio * 100:g}%" if node.ratio is not None else "-"
            print(f"    {node.name:<10} 比例 {ratio:<8} 金额 {norm_amount(node.amount) or '-':<12} "
                  f"时点 {node.timing or '-'}")
    if rec.warnings:
        print()
        print("  告警：")
        for w in rec.warnings:
            print(f"    · {w}")


def cmd_parse(args: argparse.Namespace) -> int:
    import pandas as pd

    target = Path(args.input)
    if not target.exists():
        print(f"错误：输入不存在 —— {target}", file=sys.stderr)
        return 1

    our_name, our_src = resolve_our_name(args.our_name, target)
    if our_src:
        print(f"我方名称：{our_name}（取自{our_src}；用 --our-name 可覆盖）")

    files = collect_files(target, recursive=args.recursive)

    if args.probe:
        if target.is_dir():
            print("错误：--probe 只接受单个文件；目录请直接跑 parse。", file=sys.stderr)
            return 1
        doc = load_document(target)
        rec = build_record(target, our_name)
        _print_probe(rec, doc)
        return 0

    if not files:
        print(f"错误：{target} 下没有找到任何文件（已排除隐藏文件与噪声目录）",
              file=sys.stderr)
        return 1

    out_sheets: dict[str, list] = {
        "合同台账": [], "付款节点": [], "抽取候选": [], "解析告警": [],
    }
    ok = 0
    for f in files:
        rec = build_record(f, our_name)
        _parse_one(rec, out_sheets)
        if rec.fields.get("处理状态") == "正常":
            ok += 1
        if args.verbose:
            print(f"  {f.name:<40} {rec.fields.get('处理状态', '')}")

    frames = {k: pd.DataFrame(v) for k, v in out_sheets.items()}
    frames["合同台账"] = frames["合同台账"].reindex(columns=LEDGER_COLUMNS)
    if not frames["付款节点"].empty:
        frames["付款节点"] = frames["付款节点"].reindex(columns=NODE_COLUMNS)
    else:
        frames["付款节点"] = pd.DataFrame(columns=NODE_COLUMNS)
    frames["抽取候选"] = frames["抽取候选"].reindex(columns=CANDIDATE_COLUMNS)
    frames["解析告警"] = frames["解析告警"].reindex(columns=WARN_COLUMNS)

    print(f"处理 {len(files)} 个文件：正常 {ok}，异常/未提取 {len(files) - ok}")
    if args.dry_run:
        print("--dry-run：未写出报告。")
        table = frames["合同台账"]
        if not table.empty:
            print(table[["合同标识", "对方名称", "合同金额", "到期日期", "置信度"]].to_string(index=False))
        return 0

    written = write_report(frames, Path(args.output))
    print(f"台账记录 {len(frames['合同台账'])} 行，付款节点 {len(frames['付款节点'])} 行，"
          f"候选 {len(frames['抽取候选'])} 条，告警 {len(frames['解析告警'])} 条")
    for p in written:
        print(f"已写出：{p}")
    print()
    print(f"提醒：置信度 < {CONF_THRESHOLD:.2f} 的字段已列入「待确认字段」列，"
          "「抽取候选」sheet 保留了全部落选候选，请人工核对后再使用。")
    if not our_name:
        print("     未指定我方名称（--our-name）—— 「我方角色 / 对方名称」两列是按"
              "「先出现的角色」猜的，建议补上后重跑。")
    return 0


CHECK_RULES: tuple[tuple[str, str], ...] = (
    ("节点合计", "付款节点金额合计是否等于合同金额"),
    ("比例合计", "付款节点比例合计是否为 100%"),
    ("日期逻辑", "签订日期 ≤ 生效日期 ≤ 到期日期"),
    ("金额为正", "合同金额应大于 0"),
    ("大写一致", "大写金额与数字金额应一致"),
    ("税率区间", "税率应在常见档位内"),
    ("关键字段", "对方名称与合同金额应非空"),
    ("到期状态", "到期日期是否已过"),
)


def cmd_check(args: argparse.Namespace) -> int:
    import pandas as pd

    ledger = Path(args.input)
    if not ledger.exists():
        print(f"错误：台账不存在 —— {ledger}", file=sys.stderr)
        return 1
    sheets = _read_ledger(ledger)
    if "合同台账" not in sheets:
        print("错误：台账里没有「合同台账」sheet。请传 parse 生成的台账文件。", file=sys.stderr)
        return 1

    table = sheets["合同台账"].fillna("")
    nodes = sheets.get("付款节点")
    if nodes is not None:
        nodes = nodes.fillna("")
    only = set(args.rules.split(",")) if args.rules else None

    def want(name: str) -> bool:
        return only is None or name in only

    summary: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []

    def record(rule: str, level: str, desc: str, checked: int, passed: int,
               rows: list[tuple[str, str, str, str]]) -> None:
        summary.append({
            "规则": rule,
            "严重级别": level,
            "说明": desc,
            "校验行数": checked,
            "通过": passed,
            "不通过": checked - passed,
            "通过率": f"{(passed / checked * 100):.1f}%" if checked else "-",
        })
        for contract_id, col, problem, value in rows:
            issues.append({
                "合同标识": contract_id,
                "规则": rule,
                "列名": col,
                "问题": problem,
                "当前值": value,
                "严重级别": level,
            })

    # --- 规则 1：付款节点金额合计 vs 合同金额 ---
    if want("节点合计") and nodes is not None and not nodes.empty:
        checked = passed = 0
        bad: list[tuple[str, str, str, str]] = []
        for _, row in table.iterrows():
            cid = row["合同标识"]
            mine = nodes[nodes["合同标识"] == cid]
            if "节点类型" in mine.columns:
                # 扣留项（质保金等）不参与「收款 = 合同额」的合计
                mine = mine[mine["节点类型"] == "支付节点"]
            amounts = [float(v) for v in mine["金额"] if str(v).strip() not in ("", "nan")]
            total = float(row["合同金额"]) if str(row["合同金额"]).strip() not in ("", "nan") else None
            if not amounts or total is None:
                continue
            checked += 1
            node_sum = round(sum(amounts), 2)
            if abs(node_sum - total) <= float(args.tolerance):
                passed += 1
            else:
                bad.append((cid, "合同金额", "付款节点金额合计与合同金额不符",
                            f"节点合计 {norm_amount(node_sum)} vs 合同金额 {norm_amount(total)}"))
        record("节点合计", "高", CHECK_RULES[0][1], checked, passed, bad)

    # --- 规则 2：比例合计 ---
    if want("比例合计") and nodes is not None and not nodes.empty:
        checked = passed = 0
        bad = []
        pay_nodes = nodes
        if "节点类型" in nodes.columns:
            pay_nodes = nodes[nodes["节点类型"] == "支付节点"]
        for cid, group in pay_nodes.groupby("合同标识"):
            ratios = [float(v) / 100.0 for v in group["比例(%)"]
                      if str(v).strip() not in ("", "nan")]
            if not ratios:
                continue
            checked += 1
            total = round(sum(ratios), 4)
            if abs(total - 1.0) <= 0.0001:
                passed += 1
            else:
                bad.append((str(cid), "比例(%)", "付款节点比例合计不等于 100%",
                            f"合计 {total * 100:g}%"))
        record("比例合计", "中", CHECK_RULES[1][1], checked, passed, bad)

    # --- 规则 3：日期逻辑链 ---
    if want("日期逻辑"):
        checked = passed = 0
        bad = []
        for _, row in table.iterrows():
            d_sign = _to_date(row.get("签订日期"))
            d_start = _to_date(row.get("生效日期"))
            d_end = _to_date(row.get("到期日期"))
            if not (d_sign and d_start) and not (d_start and d_end):
                continue
            checked += 1
            problems = []
            if d_sign and d_start and d_sign > d_start:
                problems.append(f"签订 {d_sign} 晚于生效 {d_start}")
            if d_start and d_end and d_start > d_end:
                problems.append(f"生效 {d_start} 晚于到期 {d_end}")
            if problems:
                bad.append((str(row["合同标识"]), "日期", "；".join(problems), ""))
            else:
                passed += 1
        record("日期逻辑", "高", CHECK_RULES[2][1], checked, passed, bad)

    # --- 规则 4：金额为正 ---
    if want("金额为正"):
        checked = passed = 0
        bad = []
        for _, row in table.iterrows():
            raw = str(row.get("合同金额", "")).strip()
            if raw in ("", "nan"):
                continue
            checked += 1
            try:
                value = float(raw)
            except ValueError:
                bad.append((str(row["合同标识"]), "合同金额", "金额不是数值", raw))
                continue
            if value > 0:
                passed += 1
            else:
                bad.append((str(row["合同标识"]), "合同金额", "金额不为正数", raw))
        record("金额为正", "高", CHECK_RULES[3][1], checked, passed, bad)

    # --- 规则 5：大写一致（从抽取候选里核）---
    if want("大写一致") and "抽取候选" in sheets:
        cands = sheets["抽取候选"].fillna("")
        checked = passed = 0
        bad = []
        for _, row in table.iterrows():
            cid = str(row["合同标识"])
            raw = str(row.get("合同金额", "")).strip()
            if raw in ("", "nan"):
                continue
            mine = cands[(cands["合同标识"] == cid) & (cands["字段"] == "合同金额")]
            cn_values = [str(r["候选值"]).strip() for _, r in mine.iterrows()
                         if "大写" in str(r["判定说明"])]
            if not cn_values:
                continue
            checked += 1
            # 只比「大写金额」与「台账采纳的金额」。落选的单价 / 节点款
            # 本来就该是不同的数，拿它们比会误报成「大小写不一致」
            numeric = [v for v in cn_values if _is_number(v)]
            if numeric and all(
                abs(float(v) - float(raw)) <= float(args.tolerance) for v in numeric
            ):
                passed += 1
            else:
                bad.append((cid, "合同金额", "大写金额与台账采纳金额不一致",
                            f"大写 {'/'.join(sorted(set(cn_values)))} vs 台账 {raw}"))
        record("大写一致", "高", CHECK_RULES[4][1], checked, passed, bad)

    # --- 规则 6：税率区间 ---
    if want("税率区间"):
        valid = {f"{r * 100:g}%" for r in VALID_RATES}
        checked = passed = 0
        bad = []
        for _, row in table.iterrows():
            raw = str(row.get("税率", "")).strip()
            if raw in ("", "nan"):
                continue
            checked += 1
            if raw in valid:
                passed += 1
            else:
                bad.append((str(row["合同标识"]), "税率", "税率不在常见档位",
                            f"{raw}（常见：{'、'.join(sorted(valid))}）"))
        record("税率区间", "低", CHECK_RULES[5][1], checked, passed, bad)

    # --- 规则 7：关键字段非空 ---
    if want("关键字段"):
        checked = passed = 0
        bad = []
        for _, row in table.iterrows():
            checked += 1
            missing = [c for c in ("对方名称", "合同金额")
                       if str(row.get(c, "")).strip() in ("", "nan")]
            if not missing:
                passed += 1
            else:
                bad.append((str(row["合同标识"]), "、".join(missing), "关键字段为空", ""))
        record("关键字段", "高", CHECK_RULES[6][1], checked, passed, bad)

    # --- 规则 8：到期状态 ---
    if want("到期状态"):
        today = _to_date(args.as_of) or date.today()
        checked = passed = 0
        bad = []
        for _, row in table.iterrows():
            d_end = _to_date(row.get("到期日期"))
            if not d_end:
                continue
            checked += 1
            if d_end >= today:
                passed += 1
            else:
                bad.append((str(row["合同标识"]), "到期日期", "合同已到期", str(d_end)))
        record("到期状态", "中", CHECK_RULES[7][1], checked, passed, bad)

    frames = {
        "体检汇总": pd.DataFrame(summary) if summary else
                    pd.DataFrame(columns=["规则", "严重级别", "说明", "校验行数", "通过", "不通过", "通过率"]),
        "问题明细": pd.DataFrame(issues) if issues else
                    pd.DataFrame(columns=["合同标识", "规则", "列名", "问题", "当前值", "严重级别"]),
    }
    print(f"体检完成：{len(summary)} 条规则，发现 {len(issues)} 处问题")
    for row in summary:
        print(f"  {row['规则']:<8} [{row['严重级别']}] {row['通过']}/{row['校验行数']} 通过"
              f"  {'' if not row['不通过'] else '→ ' + str(row['不通过']) + ' 处不通过'}")
    written = write_report(frames, Path(args.output))
    for p in written:
        print(f"已写出：{p}")
    return 0


def cmd_expire(args: argparse.Namespace) -> int:
    import pandas as pd

    ledger = Path(args.input)
    if not ledger.exists():
        print(f"错误：台账不存在 —— {ledger}", file=sys.stderr)
        return 1
    sheets = _read_ledger(ledger)
    if "合同台账" not in sheets:
        print("错误：台账里没有「合同台账」sheet。", file=sys.stderr)
        return 1

    table = sheets["合同台账"].fillna("")
    today = _to_date(args.as_of) or date.today()
    within = int(args.within)

    rows: list[dict[str, Any]] = []
    no_date = 0
    for _, row in table.iterrows():
        d_end = _to_date(row.get("到期日期"))
        if not d_end:
            no_date += 1
            if not args.only_dated:
                rows.append({
                    "合同标识": row["合同标识"], "对方名称": row.get("对方名称", ""),
                    "合同金额": row.get("合同金额", ""), "到期日期": "",
                    "距到期(天)": "", "剩余金额风险": "", "状态": "无到期日期",
                    "合同名称": row.get("合同名称", ""),
                })
            continue
        days = (d_end - today).days
        if days < 0:
            status = "已到期"
        elif days <= within:
            status = "即将到期"
        else:
            status = "正常"
        if args.only_expiring and status == "正常":
            continue
        rows.append({
            "合同标识": row["合同标识"],
            "对方名称": row.get("对方名称", ""),
            "合同金额": row.get("合同金额", ""),
            "到期日期": str(d_end),
            "距到期(天)": days,
            "剩余金额风险": "",
            "状态": status,
            "合同名称": row.get("合同名称", ""),
        })

    def sort_key(item: dict[str, Any]) -> tuple[int, float]:
        v = item["距到期(天)"]
        return (1, 0) if v == "" else (0, float(v))

    rows.sort(key=sort_key)
    frame = pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["合同标识", "对方名称", "合同金额", "到期日期", "距到期(天)", "状态", "合同名称"])
    order = ["合同标识", "合同名称", "对方名称", "合同金额", "到期日期", "距到期(天)", "状态"]
    frame = frame.reindex(columns=[c for c in order if c in frame.columns])

    counts: dict[str, int] = {}
    for item in rows:
        counts[item["状态"]] = counts.get(item["状态"], 0) + 1
    print(f"到期清单（基准日 {today}，阈值 {within} 天）：共 {len(rows)} 条")
    for key in ("已到期", "即将到期", "正常", "无到期日期"):
        if counts.get(key):
            print(f"  {key:<8} {counts[key]} 条")
    if no_date:
        print(f"  提示：{no_date} 条没有到期日期，未能参与分档（多为未抽到或合同本身无期限）。")
    written = write_report({"到期清单": frame}, Path(args.output))
    for p in written:
        print(f"已写出：{p}")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    import pandas as pd

    ledger = Path(args.input)
    if not ledger.exists():
        print(f"错误：台账不存在 —— {ledger}", file=sys.stderr)
        return 1
    sheets = _read_ledger(ledger)
    if "合同台账" not in sheets:
        print("错误：台账里没有「合同台账」sheet。", file=sys.stderr)
        return 1
    table = sheets["合同台账"].fillna("")

    group_col = args.group_by
    if group_col not in table.columns:
        print(f"错误：台账里没有「{group_col}」列。可选列："
              f"{'、'.join(str(c) for c in table.columns)}", file=sys.stderr)
        return 1

    summary_rows: list[dict[str, Any]] = []
    for key, group in table.groupby(group_col):
        key_s = str(key).strip()
        if key_s in ("", "nan"):
            key_s = "(未填)"
        amounts = []
        for v in group["合同金额"]:
            try:
                amounts.append(float(v))
            except (TypeError, ValueError):
                continue
        ends = [str(v) for v in group["到期日期"] if str(v).strip() not in ("", "nan")]
        summary_rows.append({
            group_col: key_s,
            "合同数": len(group),
            "金额合计": norm_amount(sum(amounts)) if amounts else "",
            "金额均值": norm_amount(round(sum(amounts) / len(amounts), 2)) if amounts else "",
            "已抽到金额": f"{len(amounts)}/{len(group)}",
            "最早到期": min(ends) if ends else "",
            "最晚到期": max(ends) if ends else "",
        })
    summary = pd.DataFrame(summary_rows).sort_values(
        "合同数", ascending=False) if summary_rows else pd.DataFrame()

    frames: dict[str, Any] = {f"按{group_col}汇总": summary}

    fields = [f.strip() for f in (args.fields or "").split(",") if f.strip()]
    if fields:
        dist_rows: list[dict[str, Any]] = []
        for f in fields:
            if f not in table.columns:
                print(f"  提示：台账里没有「{f}」列，已跳过。")
                continue
            for key, group in table.groupby(group_col):
                counts = group[f].astype(str).str.strip().replace("", "(空)").value_counts()
                for value, cnt in counts.items():
                    dist_rows.append({
                        "字段": f, group_col: str(key),
                        "取值": value, "出现次数": int(cnt),
                    })
        frames["要素取值分布"] = pd.DataFrame(dist_rows) if dist_rows else pd.DataFrame(
            columns=["字段", group_col, "取值", "出现次数"])

    print(f"按「{group_col}」汇总 {len(summary_rows)} 组")
    if not summary.empty:
        print(summary.head(15).to_string(index=False))
        if len(summary) > 15:
            print(f"  … 另有 {len(summary) - 15} 组，详见输出文件")
    written = write_report(frames, Path(args.output))
    for p in written:
        print(f"已写出：{p}")
    return 0


# ============================================================================
# 命令行
# ============================================================================

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="contract_toolkit.py",
        description="合同要素台账 —— 把散落的合同文件变成可核对的结构化台账",
    )
    p.add_argument("--version", action="version", version=f"contract-toolkit {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("info", help="依赖自检与目录摸底")
    sp.add_argument("path", nargs="?", help="可选：要摸底的目录或文件")
    sp.add_argument("--recursive", action=argparse.BooleanOptionalAction, default=True,
                    help="递归处理子目录（默认开启；只处理当前层用 --no-recursive）")
    sp.add_argument("--probe-text", action="store_true",
                    help="实际读取文件，统计文本层覆盖率与扫描件占比（较慢）")
    sp.set_defaults(func=cmd_info)

    sp = sub.add_parser("parse", help="抽取要素并生成台账")
    sp.add_argument("input", help="合同文件或目录")
    sp.add_argument("output", nargs="?",
                    help="台账输出路径：.xlsx（推荐）/ .csv / .tsv / .html"
                         "（.html 出单文件自包含报告，给不装 Excel 的人看）")
    sp.add_argument("--probe", action="store_true",
                    help="只对单个文件打印抽取详情（区域、字段、候选、节点），不写台账")
    sp.add_argument("--dry-run", action="store_true", help="只统计不写文件（需配合 output 占位）")
    sp.add_argument("--our-name", default=None,
                    help="我方全称，用于准确区分甲乙方并定位对方名称。省略时依次取"
                         f"环境变量 {OUR_NAME_ENV}、输入目录及其上级目录下的 .contract-toolkit.yaml")
    sp.add_argument("--recursive", action=argparse.BooleanOptionalAction, default=True,
                    help="递归处理子目录（默认开启；只处理当前层用 --no-recursive）")
    sp.add_argument("--conf-threshold", default="0.70", metavar="0-1",
                    help="置信度阈值：低于它的字段进「待确认字段」列并整行标底色（默认 0.70）")
    sp.add_argument("-v", "--verbose", action="store_true", help="逐文件打印处理状态")
    sp.set_defaults(func=cmd_parse)

    sp = sub.add_parser("check", help="台账体检（确定性规则）")
    sp.add_argument("input", help="台账 xlsx")
    sp.add_argument("output", help="体检报告输出路径（.xlsx / .csv / .html）")
    sp.add_argument("--rules", default=None,
                    help="只跑指定规则，逗号分隔：" + "、".join(r[0] for r in CHECK_RULES))
    sp.add_argument("--tolerance", default="0.01", help="金额比对容差（默认 0.01）")
    sp.add_argument("--as-of", default=None, help="基准日期 YYYY-MM-DD（默认今天）")
    sp.add_argument("--conf-threshold", default="0.70", metavar="0-1",
                    help="置信度阈值：影响报告中低置信度行的标底色（默认 0.70）")
    sp.set_defaults(func=cmd_check)

    sp = sub.add_parser("expire", help="到期清单")
    sp.add_argument("input", help="台账 xlsx")
    sp.add_argument("output", help="清单输出路径（.xlsx / .csv / .html）")
    sp.add_argument("--within", default="30", help="提前多少天算「即将到期」（默认 30）")
    sp.add_argument("--as-of", default=None, help="基准日期 YYYY-MM-DD（默认今天）")
    sp.add_argument("--only-expiring", action="store_true", help="只输出已到期与即将到期")
    sp.add_argument("--only-dated", action="store_true", help="排除没有到期日期的记录")
    sp.set_defaults(func=cmd_expire)

    sp = sub.add_parser("compare", help="跨合同汇总与要素一致性比对")
    sp.add_argument("input", help="台账 xlsx")
    sp.add_argument("output", help="输出路径（.xlsx / .csv / .html）")
    sp.add_argument("--group-by", default="对方名称", help="分组列（默认 对方名称）")
    sp.add_argument("--fields", default="", help="要统计取值分布的要素列，逗号分隔，"
                                                "如 违约金比例,税率,质保金比例")
    sp.set_defaults(func=cmd_compare)

    return p


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # 置信度阈值是模块级的（ContractRecord.pending 是 property，拿不到命令参数），
    # 所以在这里统一校验并写入，而不是在各子命令里各写一遍
    raw = getattr(args, "conf_threshold", None)
    if raw is not None:
        try:
            thr = float(raw)
        except (TypeError, ValueError):
            print(f"错误：--conf-threshold 需要 0–1 之间的小数，收到 {raw!r}", file=sys.stderr)
            return 2
        if not 0 < thr <= 1:
            print(f"错误：--conf-threshold 需在 (0, 1] 区间内，收到 {raw}", file=sys.stderr)
            return 2
        set_conf_threshold(thr)

    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        print("已中断。", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"执行失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
