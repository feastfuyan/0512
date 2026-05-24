"""ATO 税法变更爬虫"""
import json
import re
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}


def crawl_ato(since: str) -> list:
    items = []
    try:
        url = "https://www.ato.gov.au/about-ato/new-legislation/latest-news-on-tax-law-and-policy"
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        for block in soup.select("h2, h3, .card, .content-section, article"):
            text = block.get_text(separator=" ", strip=True)
            if not text or len(text) < 15:
                continue
            link_tag = block.find("a", href=True) if block.name in ("h2", "h3") else block.find_parent("a", href=True)
            link = ""
            if link_tag:
                link = link_tag["href"]
                if link.startswith("/"):
                    link = f"https://www.ato.gov.au{link}"

            items.append({
                "title": text[:200],
                "date": since,
                "source": "Australian Taxation Office",
                "url": link or url,
                "summary": text[:300],
                "jurisdiction": "Federal",
                "area_of_law": "税法",
                "status": "已公布",
            })
            if len(items) >= 5:
                break
    except Exception as e:
        print(f"  [ato] error: {e}")

    return items[:5]


if __name__ == "__main__":
    items = crawl_ato("2026-04-01")
    print(json.dumps(items[:2], ensure_ascii=False, indent=2))
