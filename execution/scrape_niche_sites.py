"""
scrape_niche_sites.py
----------------------
Scrapes legal internship sites (no Internshala per user request).
Uses simple requests for Lawctopus which has static content.

Targets:
- Lawctopus (legal internships)
- LawBhoomi (legal internships)

Outputs:
    .tmp/niche_clean.json - Combined normalized records
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
CLEAN_OUTPUT = os.path.join(TMP_DIR, "niche_clean.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}

# Niche sites with static content (scrapable via requests + BeautifulSoup)
# No Internshala per user request (TOS issues)
NICHE_SITES = [
    # Legal / Law Internships
    {
        "name": "Lawctopus",
        "url": "https://www.lawctopus.com/internships/",
        "card_selector": "article, .post, .entry",
        "title_selector": "h2, h3, .entry-title",
        "link_selector": "a"
    },
    {
        "name": "LawBhoomi",
        "url": "https://lawbhoomi.com/category/internships/",
        "card_selector": "article, .post, .entry",
        "title_selector": "h2, h3, .entry-title",
        "link_selector": "a"
    },
    # Tech / Startup Internships
    {
        "name": "HelloIntern",
        "url": "https://www.hellointern.com/internships",
        "card_selector": ".internship-card, .job-card, article",
        "title_selector": "h2, h3, .title, .job-title",
        "link_selector": "a"
    },
    {
        "name": "LetsIntern",
        "url": "https://www.letsintern.com/internships",
        "card_selector": ".internship-item, .listing, article",
        "title_selector": "h2, h3, .title",
        "link_selector": "a"
    },
    {
        "name": "FreshersWorld",
        "url": "https://www.freshersworld.com/internship-jobs",
        "card_selector": ".job-container, .listing, article",
        "title_selector": "h2, h3, .job-title, a",
        "link_selector": "a"
    },
    {
        "name": "Twenty19",
        "url": "https://www.twenty19.com/internships",
        "card_selector": ".internship-card, .card, article",
        "title_selector": "h2, h3, .title",
        "link_selector": "a"
    },
    {
        "name": "StudentTribe",
        "url": "https://studenttribe.in/internships/",
        "card_selector": ".job-listing, article, .post",
        "title_selector": "h2, h3, .listing-title",
        "link_selector": "a"
    },
    # Government / Research
    {
        "name": "SkillIndiaDigital",
        "url": "https://www.skillindiadigital.gov.in/internships",
        "card_selector": ".card, article, .internship-item",
        "title_selector": "h2, h3, .title",
        "link_selector": "a"
    }
]


def ensure_tmp_dir():
    os.makedirs(TMP_DIR, exist_ok=True)


def scrape_site(site_config: dict) -> list:
    """Scrape a static site using requests + BeautifulSoup."""
    results = []
    name = site_config["name"]
    url = site_config["url"]
    
    print(f"Scraping: {name} ({url})")
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        
        if response.status_code != 200:
            print(f"  HTTP {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        cards = soup.select(site_config["card_selector"])
        print(f"  Found {len(cards)} cards")
        
        for card in cards[:15]:
            try:
                title_elem = card.select_one(site_config["title_selector"])
                title = title_elem.get_text(strip=True) if title_elem else ""
                
                if not title or len(title) < 5:
                    continue
                
                link = card.select_one(site_config["link_selector"])
                if link:
                    href = link.get('href', '')
                    if href.startswith('http'):
                        full_url = href
                    elif href.startswith('/'):
                        base = url.split('/')[0] + '//' + url.split('/')[2]
                        full_url = base + href
                    else:
                        full_url = url.rstrip('/') + '/' + href
                else:
                    full_url = ""
                
                results.append({
                    'title': title[:200],
                    'company': 'See listing',
                    'location': 'India',
                    'url': full_url,
                    'source': name
                })
                
            except Exception:
                continue
        
        print(f"  Extracted {len(results)} items")
        
    except Exception as e:
        print(f"  Error: {e}")
    
    return results


def main():
    ensure_tmp_dir()
    
    all_clean = []
    seen_urls = set()
    
    for site in NICHE_SITES:
        results = scrape_site(site)
        for item in results:
            url = item.get('url', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_clean.append(item)
    
    print(f"\nTotal niche items: {len(all_clean)}")
    
    with open(CLEAN_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(all_clean, f, indent=2, ensure_ascii=False)
    
    return all_clean


if __name__ == "__main__":
    results = main()
    print(f"\nTotal unique listings: {len(results)}")
