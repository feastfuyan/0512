"""Fair Work 法案变更爬虫"""
import json
import re
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

AREA_MAP = {
    "workplace": "劳动法",
    "employment": "劳动法",
    "fair work": "劳动法",
    "superannuation": "养老金法",
    "super": "养老金法",
    "tax": "税法",
    "safety": "安全法",
    "discrimination": "反歧视法",
    "harassment": "反歧视法",
    "gender": "性别平等",
}


def classify_area(title: str) -> str:
    t = title.lower()
    for kw, area in AREA_MAP.items():
        if kw in t:
            return area
    return "劳动法"


def crawl_fair_work(since: str) -> list:
    items = []
    urls = [
        "https://www.fairwork.gov.au/about-us/workplace-laws/legislation-changes",
    ]
    for url in urls:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            for section in soup.select("h2, h3, .content-block, .accordion-item"):
                text = section.get_text(separator=" ", strip=True)
                if not text or len(text) < 20:
                    continue
                # 跳过导航文本
                if any(skip in text.lower() for skip in ["cookie", "subscribe", "newsletter"]):
                    continue

                items.append({
                    "title": text[:200],
                    "date": since,
                    "source": "Fair Work Ombudsman",
                    "url": url,
                    "summary": text[:300],
                    "jurisdiction": "Federal",
                    "area_of_law": classify_area(text),
                    "status": "已生效",
                })
                if len(items) >= 5:
                    break
        except Exception as e:
            print(f"  [fair_work] error: {e}")

    return items[:5]


if __name__ == "__main__":
    items = crawl_fair_work("2026-04-01")
    print(json.dumps(items[:2], ensure_ascii=False, indent=2))
