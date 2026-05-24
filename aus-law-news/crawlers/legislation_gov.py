"""联邦立法注册表爬虫 - 抓取最新立法变更"""
import json
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}


def crawl_legislation(since: str) -> list:
    items = []
    try:
        url = "https://www.legislation.gov.au/Browse/Results/ByTitle/Acts/Current"
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        for link in soup.select("a[href*='/Details/']")[:20]:
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if not title or len(title) < 5:
                continue
            full_url = f"https://www.legislation.gov.au{href}" if not href.startswith("http") else href

            items.append({
                "title": title,
                "date": since,
                "source": "Federal Register of Legislation",
                "url": full_url,
                "summary": f"联邦立法注册表最新法案: {title}",
                "jurisdiction": "Federal",
                "area_of_law": "综合立法",
                "status": "已公布",
            })
    except Exception as e:
        print(f"  [legislation] error: {e}")

    return items


if __name__ == "__main__":
    items = crawl_legislation("2026-04-01")
    print(json.dumps(items[:2], ensure_ascii=False, indent=2))
