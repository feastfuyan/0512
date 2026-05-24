---
name: aus-law-news
version: 2.0.0
description: |
  澳洲法律变更新闻爬虫。Python 多爬虫架构，抓取澳洲联邦/州级法律变更、
  法规修订、政策更新。运行后输出 aus-law-news.json + data.zip。
triggers:
  - "澳洲法律新闻"
  - "澳洲法律变更"
  - "Australian law changes"
  - "澳洲法规更新"
  - "抓取澳洲法律"
tools:
  - exec
mutating: false
---

# 澳洲法律变更新闻爬虫 v2

## 项目结构

```
aus-law-news/
├── main.py                    # 主入口，运行全部爬虫并打包
├── requirements.txt           # Python 依赖
├── SKILL.md
├── crawlers/
│   ├── __init__.py
│   ├── aph_gov.py            # 联邦议会法案
│   ├── fair_work.py          # Fair Work 劳动法变更
│   ├── legislation_gov.py    # 联邦立法注册表
│   ├── ato_tax.py            # ATO 税法变更
│   └── lexology.py           # Lexology 法律媒体
└── output/                    # 各爬虫独立输出目录
    ├── aph_gov/results.json
    ├── fair_work/results.json
    ├── legislation_gov/results.json
    ├── ato_tax/results.json
    └── lexology/results.json
```

## 运行后产出

| 文件 | 说明 |
|------|------|
| `aus-law-news.json` | 汇总 JSON，工作区根目录 |
| `data.zip` | 打包压缩，工作区根目录 |
| `output/*/results.json` | 各爬虫独立结果 |

## 运行方式

```bash
cd skills/aus-law-news
pip install -r requirements.txt
python main.py --days 30
```

## 输出 JSON 格式

```json
[
  {
    "title": "新闻标题",
    "date": "2026-04-15",
    "source": "来源",
    "url": "https://...",
    "summary": "摘要",
    "jurisdiction": "Federal|NSW|VIC|QLD|WA|SA",
    "area_of_law": "劳动法|税法|竞争法|...",
    "status": "已生效|待通过|征求意见中|已公布"
  }
]
```

## 新增爬虫

在 `crawlers/` 下新建 `.py` 文件，实现 `crawl_xxx(since: str) -> list` 函数，
然后在 `main.py` 的 crawlers 列表中注册即可。

## Anti-Patterns

- 勿传整包桌面工程，仅提交 `crawlers/*.py` + `main.py`
- 不要编造不存在的法律或新闻
- 不要返回无效 JSON
- 各爬虫 output/ 独立，平台自动打包
