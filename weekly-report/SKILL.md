---
name: miningclawd-weekly-report
description: MiningClawd 产品经理工作周报生成器。按凌云智矿周报标准模板（五段式）生成 Word 周报，输出到桌面 MC周报 文件夹。
---

# MiningClawd 产品经理工作周报生成器

## 模板标准

严格遵循 `/Users/feast/Desktop/MC周报/LynAI_Weekly_Report_Template.docx` 凌云智矿周报标准模板 v1.0，采用五段式结构。

## 数据来源

| 文件 | 路径 | 用途 |
|---|---|---|
| 上周周报 | `/Users/feast/Desktop/MC周报/weekly/` 下按日期命名最新的 `YYYYMMDD_MC产品周报.docx` | 延续上周遗留问题与本周计划 |
| 本周代码审查报告 | `/Users/feast/Desktop/MC周报/weekly/` 下对应的 `YYYYMMDD_代码审查报告.xlsx` | 四人11维评分、优缺点、立即改正项，作为周报核心输入 |
| 开发排期表 | `/Users/feast/Desktop/MC周报/MiningClawd_开发排期表_3_个月.xlsx` | 产品经理当前周次任务、各开发人员任务 |
| 数据进度排期表 | `/Users/feast/Desktop/MC周报/mining_progress_v3.xlsx` | 功能点完成状态与进度（金山文档同步版：https://www.kdocs.cn/l/ctmnaZpzHz2g） |

## Step 0：代码审查（周报前置步骤，必须先执行）

每周生成周报前，**必须先完成代码审查**。审查结果作为周报「核心项目」「核心职能」「关键判断」的关键输入。

流程：
1. 克隆两个仓库到 `/tmp/lynai-review-data` 和 `/tmp/lynai-review-mono`
2. 按 git author 提取本周 4 位开发者的 commits（夏彤/薛娴/林素雅/慧怡）
3. 分析代码质量、测试覆盖、安全合规、commit 规范等
4. 按 `代码审查模板.xlsx` 格式（11项×10分=110分）生成评分表
5. 保存为 `weekly/YYYYMMDD_代码审查报告.xlsx`
6. 收尾三件套（叮声+语音+打开文件）

评分维度：配合度、加班、代码质量、效率、团队协作、测试覆盖、安全合规、AG任务编号接入、CI接入、Commit颗粒度、开发日志

模板路径：`/Users/feast/Desktop/MC周报/weekly/代码审查模板.xlsx`

**审查结果自动输入到周报的以下段落：**
- 01 核心项目：每人的具体产出和代码质量评估
- 03 关键判断：基于代码审查得出的团队工程化判断
- 05 风险预警：安全合规问题、测试覆盖不足等

## Step 1：收集信息

用户触发时主动询问（已有则跳过）：

1. **汇报周期**（如：3.17-3.21）
2. **本周实际完成的工作**（用户自由描述）
3. **本周新增问题 / 卡点**（可选）
4. **下周重点补充计划**（排期表自动推导，用户可补充）

汇报人默认：**赴宴**；汇报日期默认：**周五当天**。

## Step 1.5：汇总微信群消息（必须执行）

使用 `wechat-cli` 工具拉取本周微信群消息作为周报素材来源：

```bash
# 拉取 Mining claw冲刺群 本周消息
wechat-cli history "Mining claw冲刺" --start-time "{周一起}" --end-time "{周五+1}" --format text --limit 500

# 拉取王选策私聊（如需）
wechat-cli history "凌云智矿王选策+61420921816，13558234202" --start-time "{周一起}" --end-time "{周五+1}" --format text --limit 200
```

从群消息中提取：
- 每日 standup 进度汇报
- TODO 清单与完成情况
- 王选策的代码审查反馈与指令
- Bug 排查与修复进展
- 会议纪要与待办事项
- 各成员的交付状态

将提取内容按项目/模块归类，作为周报「核心项目」「核心职能」「关键判断」的素材输入。

## Step 2：读取文件

同时读取：
- 上周周报：提取上周"下一步行动"作为本周基准任务
- 开发排期表（Sheet: LynAgent开发排期表）：根据汇报周期匹配当前周次，提取产品经理职责及各开发人员任务
- 数据进度排期表：提取本周功能点状态与下周计划任务

## Step 3：生成 Word 文档

使用以下 Python 脚本生成 `.docx`，**严格按此代码结构和五段式模板**执行：

```python
from docx import Document
from docx.shared import Pt, RGBColor, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import datetime

doc = Document()

# 页边距
section = doc.sections[0]
section.top_margin = Cm(2.54)
section.bottom_margin = Cm(2.54)
section.left_margin = Cm(3.17)
section.right_margin = Cm(3.17)

CJK_FONT = 'PingFang SC'
LATIN_FONT = 'Arial'

# 品牌色
GOLD = RGBColor(0xC9, 0xA8, 0x4C)      # 金色 - 编号
DARK = RGBColor(0x0D, 0x11, 0x17)       # 深黑 - 主标题/强调
BODY_COLOR = RGBColor(0x1A, 0x1A, 0x1A) # 正文黑
GRAY = RGBColor(0x55, 0x55, 0x55)       # 辅助灰
LIGHT_GRAY = RGBColor(0x80, 0x80, 0x80) # 浅灰

def set_font(run, size, bold=False, color=None):
    run.font.name = LATIN_FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    rPr = run.element.get_or_add_rPr()
    rFonts = rPr.get_or_add_rFonts()
    rFonts.set(qn('w:eastAsia'), CJK_FONT)
    rFonts.set(qn('w:ascii'), LATIN_FONT)
    rFonts.set(qn('w:hAnsi'), LATIN_FONT)
    if color:
        run.font.color.rgb = color

def sp(p, before=0, after=4):
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after = Pt(after)

def add_hr(doc):
    p = doc.add_paragraph()
    sp(p, 4, 6)
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement('w:pBdr')
    bottom = OxmlElement('w:bottom')
    bottom.set(qn('w:val'), 'single')
    bottom.set(qn('w:sz'), '4')
    bottom.set(qn('w:space'), '1')
    bottom.set(qn('w:color'), 'CCCCCC')
    pBdr.append(bottom)
    pPr.append(pBdr)

def section_title(doc, num, title_cn, title_en):
    """五段式大标题：01 核心项目 / Core Projects"""
    p = doc.add_paragraph()
    sp(p, 14, 4)
    r = p.add_run(num)
    set_font(r, 16, bold=True, color=GOLD)
    r2 = p.add_run(f'  {title_cn} / {title_en}')
    set_font(r2, 13, bold=True, color=DARK)

def project_heading(doc, name):
    """项目标题：【项目名】"""
    p = doc.add_paragraph()
    sp(p, 8, 2)
    r = p.add_run(f'【{name}】')
    set_font(r, 11, bold=True, color=DARK)

def body_text(doc, text):
    """正文段落"""
    p = doc.add_paragraph()
    sp(p, 2, 4)
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    r = p.add_run(text)
    set_font(r, 11, color=BODY_COLOR)

def bullet(doc, text):
    """列表项"""
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Inches(0.3)
    p.paragraph_format.first_line_indent = Inches(-0.15)
    sp(p, 1, 3)
    r0 = p.add_run('• ')
    set_font(r0, 11, color=GRAY)
    r = p.add_run(text)
    set_font(r, 11, color=BODY_COLOR)

def action_item(doc, priority, text):
    """下一步行动项：P0/P1/P2"""
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Inches(0.3)
    p.paragraph_format.first_line_indent = Inches(-0.15)
    sp(p, 1, 3)
    r0 = p.add_run(f'[{priority}] ')
    color = RGBColor(0xB2, 0x22, 0x22) if priority == 'P0' else (RGBColor(0xE6, 0x8A, 0x00) if priority == 'P1' else GRAY)
    set_font(r0, 11, bold=True, color=color)
    r = p.add_run(text)
    set_font(r, 11, color=BODY_COLOR)

def risk_entry(doc, risk_type, likelihood, time_window, description, impact, mitigation):
    """风险条目：【风险类型 / 概率 / 时间窗口】描述"""
    p = doc.add_paragraph()
    sp(p, 4, 2)
    r = p.add_run(f'【{risk_type} / {likelihood} / {time_window}】')
    set_font(r, 11, bold=True, color=DARK)
    # 描述
    body_text(doc, description)
    # 影响
    p2 = doc.add_paragraph()
    p2.paragraph_format.left_indent = Inches(0.2)
    sp(p2, 0, 2)
    r2 = p2.add_run('影响：')
    set_font(r2, 11, bold=True, color=GRAY)
    r3 = p2.add_run(impact)
    set_font(r3, 11, color=BODY_COLOR)
    # 应对
    p3 = doc.add_paragraph()
    p3.paragraph_format.left_indent = Inches(0.2)
    sp(p3, 0, 4)
    r4 = p3.add_run('建议应对：')
    set_font(r4, 11, bold=True, color=GRAY)
    r5 = p3.add_run(mitigation)
    set_font(r5, 11, color=BODY_COLOR)

# ══════════════════════════════════════
# ── 页首：基础信息 ──
# ══════════════════════════════════════

# 品牌标题
p_brand = doc.add_paragraph()
sp(p_brand, 0, 2)
r = p_brand.add_run('凌云智矿')
set_font(r, 18, bold=True, color=DARK)
r2 = p_brand.add_run('  LynAI Mines')
set_font(r2, 14, bold=True, color=GOLD)

# 公司信息
p_company = doc.add_paragraph()
sp(p_company, 0, 6)
r = p_company.add_run('GeoVision AI Mining Pty Ltd  |  Perth · Hangzhou · Shanghai · Harare')
set_font(r, 9, color=GRAY)

add_hr(doc)

# 周报标题
p_title = doc.add_paragraph()
p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
sp(p_title, 6, 4)
r = p_title.add_run('凌云智矿周报')
set_font(r, 18, bold=True, color=DARK)

# 基础信息表
p_info = doc.add_paragraph()
p_info.alignment = WD_ALIGN_PARAGRAPH.CENTER
sp(p_info, 0, 4)
r = p_info.add_run(f'汇报周期：{period}    汇报人：{reporter}    汇报日期：{report_date}')
set_font(r, 10, color=LIGHT_GRAY)

# 岗位
p_role = doc.add_paragraph()
p_role.alignment = WD_ALIGN_PARAGRAPH.CENTER
sp(p_role, 0, 6)
r = p_role.add_run('岗位：产品经理')
set_font(r, 10, color=LIGHT_GRAY)

add_hr(doc)

# ══════════════════════════════════════
# ── 01 核心项目 ──
# ══════════════════════════════════════
section_title(doc, '01', '核心项目', 'Core Projects')

# 按用户描述的各项目，逐一用 project_heading + body_text/bullet 填充
# 每个项目须包含：本周推进与产出、当前阶段与里程碑、是否按计划（偏差说明）

add_hr(doc)

# ══════════════════════════════════════
# ── 02 核心职能 ──
# ══════════════════════════════════════
section_title(doc, '02', '核心职能', 'Core Function')

# 产品经理核心职能产出（需求管理、项目协调、验收把关等）

add_hr(doc)

# ══════════════════════════════════════
# ── 03 关键判断 ──
# ══════════════════════════════════════
section_title(doc, '03', '关键判断', 'Key Judgments')

# 基于本周观察的专业结论、认知更新、建议

add_hr(doc)

# ══════════════════════════════════════
# ── 04 下一步行动 ──
# ══════════════════════════════════════
section_title(doc, '04', '下一步行动', 'Next Actions')

# 用 action_item(doc, 'P0'/'P1'/'P2', '具体行动描述') 填充
# 按 P0 > P1 > P2 排序

add_hr(doc)

# ══════════════════════════════════════
# ── 05 风险预警 ──
# ══════════════════════════════════════
section_title(doc, '05', '风险预警', 'Risk Alerts')

# 用 risk_entry() 填充，或如无风险则写：
# body_text(doc, '本周无重大风险预警。')

add_hr(doc)

# ── 页脚 ──
foot = doc.add_paragraph()
foot.alignment = WD_ALIGN_PARAGRAPH.CENTER
sp(foot, 12, 0)
r = foot.add_run('凌云智矿  |  LynAI Mines')
set_font(r, 9, color=LIGHT_GRAY)

# ── 保存 ──
import os
OUT_DIR = '/Users/feast/Desktop/MC周报/weekly'
os.makedirs(OUT_DIR, exist_ok=True)
out = os.path.join(OUT_DIR, f'{date_str}_MC产品周报.docx')
doc.save(out)
```

## Step 4：生成/更新后操作（每次必须执行）

```bash
xattr -d com.apple.quarantine '<文件完整路径>' 2>/dev/null
rm -f '/Users/feast/Desktop/MC周报/weekly/.~_*.docx' 2>/dev/null
afplay /System/Library/Sounds/Glass.aiff &
open '<文件完整路径>' &
open '/Users/feast/Desktop/MC周报/weekly/'
```

## 写作规范

遵循凌云智矿周报标准模板要求：
- **不是流水账**，而是岗位价值的周度交付证明
- **核心项目**：每个项目须回答三个问题——本周推进与产出（可量化）、当前阶段与里程碑、是否按计划及偏差原因
- **核心职能**：岗位核心职能的本周产出，零产出须说明原因
- **关键判断**：不是"做了什么"，而是"看到了什么、得出了什么结论"
- **下一步行动**：SMART 原则，按 P0/P1/P2 优先级排序
- **风险预警**：须明确【类型/概率/时间窗口】，包含影响范围和建议应对

## 数据验收跟进

产品经理需在每周周报中包含数据验收进度，内容来源为 `mining_progress_v3.xlsx`：
- 提取本周各数据模块的完成状态（✅/⚠️/❌）
- 标注验收通过 / 待修复 / 阻塞的具体数据项
- 纳入"核心项目"或"核心职能"中

## 文件命名与输出

- 命名：`YYYYMMDD_MC产品周报.docx`（日期为汇报日期）
- 输出路径：`/Users/feast/Desktop/MC周报/weekly/`

## 代码审查模板

生成代码审查评分表时，使用固定模板：`/Users/feast/Desktop/MC周报/weekly/代码审查模板.xlsx`

模板结构（11项评分，满分110分）：

| 分组 | 维度 | 说明 |
|---|---|---|
| 个人表现（50分） | 配合度 | 响应指令/按时交付/接受反馈 |
| | 加班 | 额外投入/紧急响应 |
| | 代码质量 | 架构/规范/可维护性 |
| | 效率 | 产出量/速度/返工率 |
| | 团队协作 | 沟通/协助他人 |
| 安全质量（20分） | 测试覆盖 | 单元测试/集成测试/smoke test |
| | 安全合规 | 凭据管理/API安全/异常处理 |
| 工程规范（40分） | AG任务编号接入 | commit关联ticket号/研发日志 |
| | CI接入 | 自动化测试/部署流水线 |
| | Commit颗粒度 | conventional commits/提交大小合理/无junk commit |
| | 开发日志 | 是否有开发日志/日志质量 |

模板包含5行空行供填写，每人附带优点/缺点/立即改正三栏。

等级标准：A（80+）优秀 | B+（70-79）良好+ | B（60-69）良好 | D（<60）不合格

## 触发示例

- "帮我生成本周周报"
- "写一下 3.17-3.21 的周报"
- "输出周报 Word"
