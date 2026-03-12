"""
scrape_company_careers.py
--------------------------
Scrapes company career pages using direct Lever and Greenhouse APIs.
These ATS platforms have structured JSON endpoints that don't require heavy scraping.

Outputs:
    .tmp/company_raw.json   - Raw scraped data
    .tmp/company_clean.json - Internship-only, normalized records
"""

import os
import json
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Constants
TMP_DIR = ".tmp"
RAW_OUTPUT = os.path.join(TMP_DIR, "company_raw.json")
CLEAN_OUTPUT = os.path.join(TMP_DIR, "company_careers_clean.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# Lever companies (JSON API: https://api.lever.co/v0/postings/{company})
# Expanded to 30 companies for better yield
LEVER_COMPANIES = [
    # Indian Startups
    "razorpay", "cred", "groww", "unacademy", "urbancompany",
    "cars24", "sharechat", "slice", "paytm", "meesho",
    "swiggy", "zepto", "dream11", "rapido", "licious",
    "dunzo", "ola", "oyo", "byju", "vedantu",
    "upgrad", "physics-wallah", "zomato", "flipkart", "myntra",
    # Global Tech
    "coinbase", "stripe", "twilio", "databricks", "mongodb"
]

# Greenhouse companies (JSON API: https://boards-api.greenhouse.io/v1/boards/{company}/jobs)
# Expanded to 25 companies for better yield
GREENHOUSE_COMPANIES = [
    # Indian Tech
    "postman", "browserstack", "chargebee", "inmobi", "phonepe",
    "lenskart", "nykaa", "mamaearth", "boat", "noise",
    # Global Tech
    "notion", "figma", "airtable", "intercom", "canva",
    "gitlab", "airbnb", "doordash", "instacart", "lyft",
    "pinterest", "reddit", "robinhood", "square", "zapier"
]


def ensure_tmp_dir():
    os.makedirs(TMP_DIR, exist_ok=True)


def scrape_lever(company: str) -> list:
    """
    Fetch jobs from Lever's public JSON API.
    """
    url = f"https://api.lever.co/v0/postings/{company}"
    print(f"Fetching Lever: {company}")
    
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            jobs = r.json()
            print(f"  Found {len(jobs)} jobs at {company}")
            return [
                {
                    "title": job.get("text", ""),
                    "company": company.title(),
                    "location": job.get("categories", {}).get("location", "Not specified"),
                    "url": job.get("hostedUrl", ""),
                    "source": "Lever"
                }
                for job in jobs
            ]
        else:
            print(f"  {company}: HTTP {r.status_code}")
            return []
    except Exception as e:
        print(f"  Error: {e}")
        return []


def scrape_greenhouse(company: str) -> list:
    """
    Fetch jobs from Greenhouse's public JSON API.
    """
    url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs"
    print(f"Fetching Greenhouse: {company}")
    
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            data = r.json()
            jobs = data.get("jobs", [])
            print(f"  Found {len(jobs)} jobs at {company}")
            return [
                {
                    "title": job.get("title", ""),
                    "company": company.title(),
                    "location": job.get("location", {}).get("name", "Not specified"),
                    "url": job.get("absolute_url", ""),
                    "source": "Greenhouse"
                }
                for job in jobs
            ]
        else:
            print(f"  {company}: HTTP {r.status_code}")
            return []
    except Exception as e:
        print(f"  Error: {e}")
        return []


def filter_internships(items: list) -> list:
    """
    Filter for internship-related roles.
    """
    keywords = ["intern", "trainee", "fresher", "graduate", "entry", "campus", "university"]
    filtered = []
    
    for item in items:
        title_lower = item.get("title", "").lower()
        if any(kw in title_lower for kw in keywords):
            item["ats"] = item.get("source", "Unknown")
            item["source"] = "company_career"
            filtered.append(item)
    
    return filtered


def main():
    ensure_tmp_dir()
    
    all_raw = []
    
    # Scrape Lever companies
    print("\n=== LEVER COMPANIES ===")
    for company in LEVER_COMPANIES:
        all_raw.extend(scrape_lever(company))
    
    # Scrape Greenhouse companies
    print("\n=== GREENHOUSE COMPANIES ===")
    for company in GREENHOUSE_COMPANIES:
        all_raw.extend(scrape_greenhouse(company))
    
    print(f"\nTotal raw jobs: {len(all_raw)}")
    
    # Save raw
    with open(RAW_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(all_raw, f, indent=2, ensure_ascii=False)
    
    # Filter for internships
    clean = filter_internships(all_raw)
    
    # Dedup by URL
    seen = set()
    unique = []
    for item in clean:
        url = item.get("url", "")
        if url and url not in seen:
            seen.add(url)
            unique.append(item)
    
    print(f"Total internships: {len(unique)}")
    
    # Save clean
    with open(CLEAN_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(unique, f, indent=2, ensure_ascii=False)
    
    return unique


if __name__ == "__main__":
    results = main()
    print(f"\nTotal internships found: {len(results)}")
    
    # Summary
    sources = {}
    for item in results:
        src = item.get("ats", "Unknown")
        sources[src] = sources.get(src, 0) + 1
    
    print("\nBy ATS:")
    for src, count in sources.items():
        print(f"  {src}: {count}")
