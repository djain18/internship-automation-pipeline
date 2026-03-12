"""
scrape_unstop.py
-----------------
Scrapes Unstop internship listings using Apify Web Scraper with residential proxies.
Uses browser rendering and residential IPs to bypass Cloudflare protection.

Outputs:
    .tmp/unstop_raw.json   - Raw scraped data
    .tmp/unstop_clean.json - Filtered, normalized records
"""

import os
import json
from apify_client import ApifyClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Constants
TMP_DIR = ".tmp"
RAW_OUTPUT = os.path.join(TMP_DIR, "unstop_raw.json")
CLEAN_OUTPUT = os.path.join(TMP_DIR, "unstop_clean.json")

UNSTOP_URL = "https://unstop.com/internships?oppstatus=open"


def ensure_tmp_dir():
    os.makedirs(TMP_DIR, exist_ok=True)


def scrape_with_apify() -> list:
    """
    Scrape Unstop using Apify Web Scraper with residential proxies.
    """
    api_token = os.getenv("APIFY_API_TOKEN")
    if not api_token:
        print("APIFY_API_TOKEN not set, returning empty")
        return []
    
    client = ApifyClient(api_token)
    
    # Use Web Scraper with residential proxies and browser rendering
    run_input = {
        "startUrls": [{"url": UNSTOP_URL}],
        "pageFunction": """
async function pageFunction(context) {
    const { page, request, log } = context;
    
    log.info('Waiting for page to load...');
    
    // Wait for the internship listings to appear
    await page.waitForTimeout(5000);
    
    // Scroll to load more content
    await page.evaluate(() => {
        window.scrollTo(0, document.body.scrollHeight / 2);
    });
    await page.waitForTimeout(2000);
    
    // Extract internship data
    const items = await page.evaluate(() => {
        const results = [];
        
        // Try multiple selector patterns that Unstop uses
        const selectors = [
            '.single_internship',
            '.opp_card', 
            '.listing-item',
            '[class*="internship"]',
            '[class*="opportunity"]',
            'a[href*="/internship"]'
        ];
        
        for (const selector of selectors) {
            const cards = document.querySelectorAll(selector);
            if (cards.length > 0) {
                cards.forEach((card, i) => {
                    if (i >= 15) return;
                    
                    // Try to find title, company, and link
                    const titleEl = card.querySelector('h2, h3, h4, [class*="title"], strong');
                    const companyEl = card.querySelector('[class*="company"], [class*="org"], span');
                    const linkEl = card.tagName === 'A' ? card : card.querySelector('a');
                    
                    const title = titleEl?.innerText?.trim() || card.innerText?.substring(0, 100)?.trim();
                    const company = companyEl?.innerText?.trim() || 'Unstop';
                    const url = linkEl?.href || '';
                    
                    if (title && title.length > 3 && url.includes('unstop.com')) {
                        results.push({
                            title: title.substring(0, 200),
                            company: company.substring(0, 100),
                            url: url
                        });
                    }
                });
                
                if (results.length > 0) break;
            }
        }
        
        return results;
    });
    
    log.info(`Found ${items.length} internships`);
    return items;
}
        """,
        "proxyConfiguration": {
            "useApifyProxy": True,
            "apifyProxyGroups": ["RESIDENTIAL"]
        },
        "maxPagesPerCrawl": 3,
        "maxConcurrency": 2,
        "waitUntil": ["networkidle"]
    }
    
    print("Running Apify Web Scraper on Unstop (with residential proxies)...")
    
    try:
        run = client.actor("apify/web-scraper").call(run_input=run_input)
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        
        # Flatten results
        flat = []
        for item in items:
            if isinstance(item, list):
                flat.extend(item)
            elif isinstance(item, dict) and 'title' in item:
                flat.append(item)
        
        print(f"Found {len(flat)} internships from Unstop")
        return flat
        
    except Exception as e:
        print(f"Apify error: {e}")
        return []


def main():
    ensure_tmp_dir()
    
    results = scrape_with_apify()
    
    # Add source tag and location
    for item in results:
        item['source'] = 'Unstop'
        item['location'] = item.get('location', 'India')
    
    # Save raw
    with open(RAW_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Saved raw: {RAW_OUTPUT} ({len(results)} items)")
    
    # Dedup by URL
    seen = set()
    unique = []
    for item in results:
        url = item.get('url', '')
        if url and url not in seen:
            seen.add(url)
            unique.append(item)
    
    # Save clean
    with open(CLEAN_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(unique, f, indent=2, ensure_ascii=False)
    print(f"Saved clean: {CLEAN_OUTPUT} ({len(unique)} internships)")
    
    return unique


if __name__ == "__main__":
    results = main()
    print(f"\nTotal filtered internships: {len(results)}")
