"""法律媒体新闻爬虫 - Lexology/律所洞察"""
import json
import re
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

AREA_MAP = {
    "competition": "竞争法",
    "consumer": "消费者法",
    "employment": "劳动法",
    "immigration": "移民法",
    "tax": "税法",
    "mining": "矿业法",
    "environment": "环境法",
    "privacy": "数据隐私",
    "crypto": "金融监管",
    "digital": "金融监管",
    "insurance": "保险法",
    "construction": "建筑法",
    "corporate": "公司法",
}


def classify_area(title: str) -> str:
    t = title.lower()
    for kw, area in AREA_MAP.items():
        if kw in t:
            return area
    return "综合法律"


def crawl_lexology(since: str) -> list:
    """抓取 Lexology 澳洲法律更新"""
    items = []
    queries = [
        "https://www.lexology.com/search?q=australia+legislation+amendment+2026",
    ]
    for url in queries:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            for article in soup.select("article, .search-result-item, .title-link"):
                text = article.get_text(separator=" ", strip=True)
                link_tag = article.find("a", href=True)
                if not link_tag:
                    link_tag = article if article.name == "a" else None
                link = link_tag["href"] if link_tag else ""
                if link and not link.startswith("http"):
                    link = f"https://www.lexology.com{link}"

                title = link_tag.get_text(strip=True) if link_tag else text[:150]
                if not title or len(title) < 10:
                    continue

                items.append({
                    "title": title[:200],
                    "date": since,
                    "source": "Lexology",
                    "url": link,
                    "summary": text[:300],
                    "jurisdiction": "Federal",
                    "area_of_law": classify_area(title),
                    "status": "已公布",
                })
                if len(items) >= 5:
                    break
        except Exception as e:
            print(f"  [lexology] error: {e}")

    return items[:5]


if __name__ == "__main__":
    items = crawl_lexology("2026-04-01")
    print(json.dumps(items[:2], ensure_ascii=False, indent=2))
