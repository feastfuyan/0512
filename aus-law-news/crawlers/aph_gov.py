"""澳洲联邦议会法案爬虫"""
import json
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}


def fetch_recent_bills(since: str) -> list:
    """从 aph.gov.au 抓取最近通过的法案"""
    url = "https://www.aph.gov.au/Parliamentary_Business/Bills_Legislation"
    items = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        # 解析法案列表
        for row in soup.select("table tbody tr, .bill-list-item, .search-results li"):
            text = row.get_text(separator=" ", strip=True)
            links = row.find_all("a", href=True)
            if not text or len(text) < 10:
                continue

            title = text[:200]
            link = ""
            for a in links:
                href = a["href"]
                if "/Bills_Legislation" in href or "Bill" in href:
                    link = href if href.startswith("http") else f"https://www.aph.gov.au{href}"
                    break

            # 提取日期
            date_match = re.search(r"(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4})", text)
            date_str = ""
            if date_match:
                try:
                    date_str = datetime.strptime(date_match.group(1), "%d %b %Y").strftime("%Y-%m-%d")
                except ValueError:
                    pass

            if date_str and date_str >= since:
                items.append({
                    "title": title,
                    "date": date_str,
                    "source": "Parliament of Australia",
                    "url": link,
                    "summary": title,
                    "jurisdiction": "Federal",
                    "area_of_law": "立法",
                    "status": "已公布",
                })
    except Exception as e:
        print(f"  [aph] fetch error: {e}")

    return items


def crawl_aph(since: str) -> list:
    results = fetch_recent_bills(since)
    # 去重
    seen = set()
    unique = []
    for item in results:
        key = item["title"][:80]
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


if __name__ == "__main__":
    items = crawl_aph("2026-04-01")
    print(json.dumps(items[:3], ensure_ascii=False, indent=2))
