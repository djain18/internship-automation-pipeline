"""
scrape_government.py
---------------------
Scrapes government internship portals using requests + BeautifulSoup.
Completely free, no API costs.

Targets:
- NITI Aayog
- Digital India (MyGov)
- AICTE Internship Portal

Outputs:
    .tmp/government_clean.json - Normalized records
"""

import os
import json
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Constants
TMP_DIR = ".tmp"
CLEAN_OUTPUT = os.path.join(TMP_DIR, "government_clean.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}

# Government portals
GOV_PORTALS = [
    {
        "name": "NITI Aayog",
        "url": "https://www.niti.gov.in/careers",
        "card_selector": ".views-row, .career-item, article",
        "title_selector": "h3, h4, .title, a"
    },
    {
        "name": "MyGov",
        "url": "https://www.mygov.in/task/",
        "card_selector": ".views-row, .task-item, article",
        "title_selector": "h3, h4, .title, a"
    },
    {
        "name": "AICTE Internship",
        "url": "https://internship.aicte-india.org/",
        "card_selector": ".internship-card, .opportunity, article",
        "title_selector": "h3, h4, .title"
    }
]


def ensure_tmp_dir():
    os.makedirs(TMP_DIR, exist_ok=True)


def scrape_gov_portal(portal: dict) -> list:
    """
    Scrape internships from a government portal.
    """
    results = []
    name = portal["name"]
    url = portal["url"]
    
    print(f"Scraping: {name}")
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=30, verify=False)
        
        if response.status_code != 200:
            print(f"  HTTP {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find cards
        cards = soup.select(portal["card_selector"])
        print(f"  Found {len(cards)} items")
        
        for card in cards[:10]:  # Limit to 10
            try:
                title_elem = card.select_one(portal["title_selector"])
                title = title_elem.get_text(strip=True) if title_elem else ""
                
                if not title or len(title) < 5:
                    continue
                
                # Check if it's internship related
                title_lower = title.lower()
                if not any(kw in title_lower for kw in ['intern', 'trainee', 'fellowship', 'apprentice', 'young']):
                    continue
                
                # Get URL
                link = card.select_one('a[href]')
                href = link.get('href', '') if link else ""
                if href and not href.startswith('http'):
                    base = url.split('/')[0] + '//' + url.split('/')[2]
                    href = base + href
                
                results.append({
                    'title': title[:200],
                    'company': name,
                    'location': 'India',
                    'url': href or url,
                    'source': 'Government'
                })
                
            except:
                continue
        
        print(f"  Extracted {len(results)} internships")
        
    except Exception as e:
        print(f"  Error: {e}")
    
    return results


def main():
    ensure_tmp_dir()
    
    all_results = []
    
    for portal in GOV_PORTALS:
        results = scrape_gov_portal(portal)
        all_results.extend(results)
    
    # Dedup
    seen = set()
    unique = []
    for item in all_results:
        key = item['title'][:50]
        if key not in seen:
            seen.add(key)
            unique.append(item)
    
    print(f"\nTotal government internships: {len(unique)}")
    
    # Save
    with open(CLEAN_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(unique, f, indent=2, ensure_ascii=False)
    
    return unique


if __name__ == "__main__":
    # Suppress SSL warnings
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    results = main()
    print(f"\nTotal filtered: {len(results)}")
