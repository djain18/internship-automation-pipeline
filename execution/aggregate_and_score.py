"""
aggregate_and_score.py
-----------------------
Aggregates all scraped internships, deduplicates, and ranks by quality score.
Enforces quota system: target 10 from each source, fill remainder to reach 60 total.

Inputs:
    .tmp/linkedin_posts_clean.json
    .tmp/linkedin_jobs_clean.json
    .tmp/niche_clean.json
    .tmp/unstop_clean.json
    .tmp/company_clean.json
    .tmp/gov_clean.json

Output:
    .tmp/final_ranked_internships.json
"""

import os
import json
import re
from difflib import SequenceMatcher
from datetime import datetime

# Constants
TMP_DIR = ".tmp"
OUTPUT_FILE = os.path.join(TMP_DIR, "final_ranked_internships.json")
TARGET_TOTAL = 130

# Per-source quotas (User Request: NO LinkedIn Jobs, Focus on Posts)
SOURCE_QUOTAS = {
    "LinkedIn Posts": 130,  # Main source
    "Niche Communities": 0,
    "Unstop": 0,
    "Notion (Manual)": 0,
    "Company Careers": 0,  # Backup
    "Government Portals": 0, # Backup
}

# Source files with their source names and priority scores
# Priority order: LinkedIn Posts > Niche > Unstop > Notion > Company > Govt
SOURCE_FILES = [
    {"file": "linkedin_posts_clean.json", "source": "LinkedIn Posts", "priority": 50},  # TOP PRIORITY
    {"file": "niche_internships.json", "source": "Niche Communities", "priority": 45},  # HIGH PRIORITY
    {"file": "unstop_internships.json", "source": "Unstop", "priority": 40},  # HIGH PRIORITY
    {"file": "notion_internships.json", "source": "Notion (Manual)", "priority": 35},
    {"file": "government_internships.json", "source": "Government Portals", "priority": 15},
]


def load_json_file(filepath: str) -> list:
    """Load JSON file if exists, otherwise return empty list."""
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return []
    
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return []


def parse_hours_old(posted_time: str) -> int | None:
    """Parse posted time string to hours old."""
    if not posted_time:
        return None
    
    posted_lower = posted_time.lower().strip()
    
    hours_match = re.search(r"(\d+)\s*h(our)?", posted_lower)
    if hours_match:
        return int(hours_match.group(1))
    
    if re.search(r"(\d+)\s*m(in)?", posted_lower):
        return 0
    
    days_match = re.search(r"(\d+)\s*d(ay)?", posted_lower)
    if days_match:
        return int(days_match.group(1)) * 24
    
    weeks_match = re.search(r"(\d+)\s*w(eek)?", posted_lower)
    if weeks_match:
        return int(weeks_match.group(1)) * 24 * 7
    
    if "just" in posted_lower or "now" in posted_lower:
        return 0
    
    return None


def calculate_freshness_score(item: dict) -> int:
    """Calculate freshness score (max 25 pts)."""
    posted_time = item.get("posted_time") or item.get("posted_date") or ""
    hours_old = parse_hours_old(posted_time)
    
    if hours_old is None:
        return 10
    
    if hours_old < 6:
        return 25
    elif hours_old < 12:
        return 20
    elif hours_old < 24:
        return 15
    elif hours_old < 48:
        return 10
    else:
        return 5


def calculate_score(item: dict, source_priority: int) -> int:
    """Calculate total score."""
    freshness = calculate_freshness_score(item)
    return source_priority + freshness


def normalize_company(company: str) -> str:
    """Normalize company name for comparison."""
    normalized = company.lower().strip()
    for suffix in [" pvt ltd", " pvt. ltd.", " private limited", " inc", " inc.", " llc", " ltd", " ltd."]:
        normalized = normalized.replace(suffix, "")
    normalized = re.sub(r'[^\w\s]', '', normalized)
    normalized = re.sub(r'\s+', ' ', normalized)
    return normalized


def normalize_title(title: str) -> str:
    normalized = title.lower().strip()
    normalized = re.sub(r'[^\w\s]', '', normalized)
    normalized = re.sub(r'\s+', ' ', normalized)
    return normalized


def is_duplicate(item1, item2):
    """Check if duplicate by URL or fuzzy company+title match."""
    # Strict URL check
    if item1.get('url') and item2.get('url') and item1['url'] == item2['url']:
        role1 = item1.get('role', '').strip().lower()
        role2 = item2.get('role', '').strip().lower()
        if role1 == role2:
            return True
        return False
        
    # Fuzzy match
    c1, c2 = normalize_company(item1.get('company', '')), normalize_company(item2.get('company', ''))
    
    # Don't fuzzy match if company is unknown
    if c1 == 'unknown' or c2 == 'unknown' or not c1 or not c2:
        return False
        
    if c1 != c2:
        return False
        
    t1, t2 = normalize_title(item1.get('title', '')), normalize_title(item2.get('title', ''))
    if t1 == 'internship' or t2 == 'internship' or not t1 or not t2:
        return False
        
    return SequenceMatcher(None, t1, t2).ratio() > 0.85


def main():
    print("="*60)
    print("Aggregating with Quota System (Target: 60 total, 10/source)")
    print("="*60)
    
    all_source_items = {}
    
    # 1. Load and Score all items
    for source_conf in SOURCE_FILES:
        filepath = os.path.join(TMP_DIR, source_conf["file"])
        raw_items = load_json_file(filepath)
        source_name = source_conf["source"]
        
        scored_items = []
        for item in raw_items:
            # Basic normalization
            if not item.get("source"):
                item["source"] = source_name
            
            # Mapping for LinkedIn Posts (which lack title/company keys)
            if source_name == "LinkedIn Posts":
                if not item.get("title"):
                    # Use role as title if available to distinguish multiple roles from same post
                    if item.get("role"):
                        item["title"] = item["role"]
                    elif item.get("post_text"):
                        item["title"] = item["post_text"][:100].replace('\n', ' ')
                if not item.get("company") and item.get("author_name"):
                    item["company"] = item["author_name"]
                # Location: Use LLM-extracted location or fallback
                if not item.get("location"):
                    item["location"] = "Not specified"
            
            # Ensure role field exists for all sources (preserve LLM-extracted roles!)
            if not item.get("role") or item.get("role") == "":
                item["role"] = "Internship"
            
            # Ensure location field exists for all sources
            if not item.get("location") or item.get("location") == "":
                item["location"] = "Not specified"
                    
            # Calculate score
            item["score"] = calculate_score(item, source_conf["priority"])
            scored_items.append(item)
            
        # Sort by score descending
        scored_items.sort(key=lambda x: x["score"], reverse=True)
        all_source_items[source_name] = scored_items
        
        print(f"{source_name}: {len(scored_items)} items")

    # 2. Global Deduplication Pool
    # We need to pick items carefully to avoid duplicates across sources
    final_selection = []
    seen_items = []  # Keep track for dedup
    
    # 3. Quota Selection (Round 1: Top 10 from each)
    remaining_pool = []
    
    for source_name, items in all_source_items.items():
        # Try to take top 10 unique items
        count = 0
        for item in items:
            # Check dup
            is_dup = False
            for seen in seen_items:
                if is_duplicate(item, seen):
                    is_dup = True
                    break
            
            if is_dup:
                continue
                
            # Get quota for this specific source (default to 10 if not found)
            target = SOURCE_QUOTAS.get(source_name, 10)
            
            if count < target:
                final_selection.append(item)
                seen_items.append(item)
                count += 1
            else:
                remaining_pool.append(item)
    
    print(f"\nAfter Quota Selection: {len(final_selection)} items")
    
    # 4. Fill Remainder (Round 2: Best of the rest)
    # Sort remaining pool by score
    remaining_pool.sort(key=lambda x: x["score"], reverse=True)
    
    needed = TARGET_TOTAL - len(final_selection)
    if needed > 0:
        print(f"Need {needed} more items to reach {TARGET_TOTAL}...")
        added_count = 0
        for item in remaining_pool:
            if added_count >= needed:
                break
            
            # Check dup (against already selected)
            is_dup = False
            for seen in seen_items:
                if is_duplicate(item, seen):
                    is_dup = True
                    break
            
            if not is_dup:
                final_selection.append(item)
                seen_items.append(item)
                added_count += 1
        print(f"Added {added_count} fill-up items")
    
    # 5. Final Sort and Save
    final_selection.sort(key=lambda x: x["score"], reverse=True)
    
    # Trim to exactly 60 if somehow over (shouldn't be, but safe)
    final_selection = final_selection[:TARGET_TOTAL]
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(final_selection, f, indent=2, ensure_ascii=False)
        
    print(f"\nSaved {len(final_selection)} ranked internships to {OUTPUT_FILE}")
    print("="*60)
    
    # Print Distribution
    dist = {}
    for item in final_selection:
        src = item.get("source", "Unknown")
        dist[src] = dist.get(src, 0) + 1
        
    print("Final Distribution:")
    for src, count in dist.items():
        print(f"  {src}: {count}")

if __name__ == "__main__":
    main()
