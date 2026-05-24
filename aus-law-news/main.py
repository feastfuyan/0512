#!/usr/bin/env python3
"""
澳洲法律变更新闻爬虫 - 单文件版
用法: python3 run.py [--days 30]
"""
import argparse
import json
import os
import re
import sys
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "requests", "beautifulsoup4", "lxml"])
    import requests
    from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
}

AREA_MAP = {
    "employment": "劳动法", "workplace": "劳动法", "fair work": "劳动法",
    "superannuation": "养老金法", "tax": "税法", "capital gains": "税法",
    "immigration": "移民法", "visa": "移民法", "migration": "移民法",
    "competition": "竞争法", "consumer": "消费者法",
    "mining": "矿业法", "environment": "环境法", "privacy": "数据隐私",
    "crypto": "金融监管", "digital asset": "金融监管", "aml": "金融监管",
    "insurance": "保险法", "construction": "建筑法", "corporate": "公司法",
    "ndis": "社会保障法", "gun": "刑法", "criminal": "刑法",
    "health": "医疗卫生法", "discrimination": "反歧视法", "gender": "性别平等",
}

QUERIES = [
    "Australian legislation changes 2026 new laws",
    "Australia law amendment bill passed 2026",
    "Australian federal regulation reform 2026",
    "NSW VIC QLD WA legislation amendment 2026",
    "Australia corporate tax immigration law changes 2026",
]


def classify_area(title):
    t = title.lower()
    for kw, area in AREA_MAP.items():
        if kw in t:
            return area
    return "综合法律"


def classify_jurisdiction(title):
    t = title.lower()
    for state in ["NSW", "Victoria", "VIC", "Queensland", "QLD", "Western Australia", "WA",
                   "South Australia", "SA", "Tasmania", "TAS", "NT", "ACT"]:
        if state.lower() in t:
            return state.replace("Victoria", "VIC").replace("Western Australia", "WA").replace("Queensland", "QLD").replace("South Australia", "SA")
    return "Federal"


def classify_status(title):
    t = title.lower()
    if any(w in t for w in ["passed", "assent", "royal assent", "effective", "commence"]):
        return "已生效"
    if any(w in t for w in ["proposed", "bill", "draft", "exposure draft"]):
        return "待通过"
    if any(w in t for w in ["consultation", "submissions", "feedback"]):
        return "征求意见中"
    return "已公布"


def ddg_search(query):
    url = "https://html.duckduckgo.com/html/"
    results = []
    try:
        resp = requests.post(url, data={"q": query, "kl": "au-en"}, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        for m in re.finditer(
            r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            resp.text, re.DOTALL
        ):
            link = m.group(1)
            title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
            if not title or len(title) < 10:
                continue
            snippet = ""
            snip_match = re.search(
                r'class="result__snippet"[^>]*>(.*?)</a>',
                resp.text[m.end():m.end() + 2000], re.DOTALL
            )
            if snip_match:
                snippet = re.sub(r"<[^>]+>", "", snip_match.group(1)).strip()
            domain = re.sub(r'https?://([^/]+).*', r'\1', link)
            results.append({"title": title, "snippet": snippet, "url": link, "domain": domain})
    except Exception as e:
        print(f"  [search] ddg error for '{query[:50]}': {e}")
    return results


def run_all(days=30):
    import time
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    print(f"[main] 抓取 {since} 至今的澳洲法律变更 (约{days}天)")

    all_items = []
    seen_titles = set()

    for query in QUERIES:
        print(f"  [search] query: {query[:60]}...")
        raw = ddg_search(query)
        time.sleep(1)
        for r in raw:
            key = r["title"][:80].lower()
            if key in seen_titles:
                continue
            seen_titles.add(key)
            all_items.append({
                "title": r["title"],
                "date": since,
                "source": r["domain"],
                "url": r["url"],
                "summary": r["snippet"][:300] if r["snippet"] else r["title"],
                "jurisdiction": classify_jurisdiction(r["title"] + " " + r["snippet"]),
                "area_of_law": classify_area(r["title"] + " " + r["snippet"]),
                "status": classify_status(r["title"]),
            })

    all_items.sort(key=lambda x: x.get("date", ""), reverse=True)

    # 写 JSON
    root_json = "aus-law-news.json"
    with open(root_json, "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)
    print(f"[main] 共 {len(all_items)} 条 -> {root_json}")

    # 打包 data.zip
    with zipfile.ZipFile("data.zip", "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(root_json, "aus-law-news.json")
    print(f"[main] 打包 -> data.zip")

    return all_items


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="澳洲法律变更爬虫")
    parser.add_argument("--days", type=int, default=30, help="抓取最近N天")
    args = parser.parse_args()
    results = run_all(days=args.days)
    print(f"\n完成，共 {len(results)} 条法律变更记录")
