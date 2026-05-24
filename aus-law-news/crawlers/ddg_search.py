"""DuckDuckGo 搜索爬虫 - 主力数据源，覆盖面最广"""
import json
import re
import time
import requests
from datetime import datetime, timedelta

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
}

AREA_MAP = {
    "employment": "劳动法", "workplace": "劳动法", "fair work": "劳动法",
    "superannuation": "养老金法", "super": "养老金法", "pension": "养老金法",
    "tax": "税法", "capital gains": "税法", "negative gearing": "税法",
    "immigration": "移民法", "visa": "移民法", "migration": "移民法",
    "competition": "竞争法", "consumer": "消费者法",
    "mining": "矿业法", "resources": "矿业法",
    "environment": "环境法", "climate": "环境法",
    "privacy": "数据隐私", "data": "数据隐私", "cybersecurity": "数据隐私",
    "crypto": "金融监管", "digital asset": "金融监管", "aml": "金融监管",
    "insurance": "保险法", "genetic": "保险法",
    "construction": "建筑法",
    "corporate": "公司法", "corporation": "公司法",
    "ndis": "社会保障法", "disability": "社会保障法",
    "gun": "刑法", "criminal": "刑法", "terror": "刑法",
    "health": "医疗卫生法", "medical": "医疗卫生法",
    "building": "建筑法",
    "worker": "劳动法", "compensation": "劳动法",
    "safety": "安全法",
    "discrimination": "反歧视法", "gender": "性别平等", "harassment": "反歧视法",
}

QUERIES = [
    "Australian legislation changes April 2026 new laws",
    "Australia law amendment bill passed 2026",
    "Australian federal regulation reform 2026",
    "NSW VIC QLD WA legislation amendment 2026",
    "Australia corporate tax immigration law changes 2026",
]


def classify_area(title: str) -> str:
    t = title.lower()
    for kw, area in AREA_MAP.items():
        if kw in t:
            return area
    return "综合法律"


def classify_jurisdiction(title: str) -> str:
    t = title.lower()
    for state in ["NSW", "Victoria", "VIC", "Queensland", "QLD", "Western Australia", "WA",
                   "South Australia", "SA", "Tasmania", "TAS", "NT", "ACT"]:
        if state.lower() in t:
            return state.replace("Victoria", "VIC").replace("Western Australia", "WA").replace("Queensland", "QLD").replace("South Australia", "SA").replace("Tasmania", "TAS").replace("Northern Territory", "NT").replace("Australian Capital Territory", "ACT")
    return "Federal"


def classify_status(title: str) -> str:
    t = title.lower()
    if any(w in t for w in ["passed", "assent", "royal assent", "effective", "commence", "生效"]):
        return "已生效"
    if any(w in t for w in ["proposed", "bill", "draft", "consultation", "exposure draft", "待通过"]):
        return "待通过"
    if any(w in t for w in ["consultation", "submissions", "feedback", "征求意见"]):
        return "征求意见中"
    return "已公布"


def ddg_search(query: str) -> list:
    """用 DuckDuckGo HTML 搜索接口"""
    url = "https://html.duckduckgo.com/html/"
    results = []
    try:
        resp = requests.post(url, data={"q": query, "kl": "au-en"}, headers=HEADERS, timeout=20)
        resp.raise_for_status()

        # 解析 DDG HTML 结果 - 提取 result 链接
        for m in re.finditer(
            r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            resp.text, re.DOTALL
        ):
            link = m.group(1)
            title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
            if not title or len(title) < 10:
                continue

            # 提取 snippet (紧跟其后的 result__snippet)
            snippet = ""
            snip_match = re.search(
                r'class="result__snippet"[^>]*>(.*?)</a>',
                resp.text[m.end():m.end()+2000], re.DOTALL
            )
            if snip_match:
                snippet = re.sub(r"<[^>]+>", "", snip_match.group(1)).strip()

            # 提取域名
            domain = re.sub(r'https?://([^/]+).*', r'\1', link)

            results.append({
                "title": title,
                "snippet": snippet,
                "url": link,
                "domain": domain,
            })
    except Exception as e:
        print(f"  [search] ddg error for '{query}': {e}")

    return results


def crawl_search(since: str) -> list:
    all_items = []
    seen_titles = set()

    for query in QUERIES:
        print(f"  [search] query: {query[:60]}...")
        raw = ddg_search(query)
        time.sleep(1)  # 限速

        for r in raw:
            title = r["title"]
            # 去重
            key = title[:80].lower()
            if key in seen_titles:
                continue
            seen_titles.add(key)

            all_items.append({
                "title": title,
                "date": since,
                "source": r["domain"],
                "url": r["url"],
                "summary": r["snippet"][:300] if r["snippet"] else title,
                "jurisdiction": classify_jurisdiction(title + " " + r["snippet"]),
                "area_of_law": classify_area(title + " " + r["snippet"]),
                "status": classify_status(title),
            })

    return all_items


if __name__ == "__main__":
    items = crawl_search("2026-04-01")
    print(json.dumps(items[:3], ensure_ascii=False, indent=2))
