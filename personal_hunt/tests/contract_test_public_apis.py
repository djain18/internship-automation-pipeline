#!/usr/bin/env python3
"""Contract tests for Reddit and Hacker News public JSON endpoints.

Verifies the API shape and response format before wiring into production code.
Run this before implementing problem_research.py to confirm assumptions.
"""

import sys
from datetime import datetime

import requests

# Use a realistic company name from a real funding event to test
TEST_COMPANY = "Pixxel"  # Indian satellite imaging startup


def test_reddit_search():
    """Verify reddit.com/search.json endpoint shape."""
    print(f"\n=== Testing Reddit Search for '{TEST_COMPANY}' ===")
    try:
        url = "https://www.reddit.com/search.json"
        params = {
            "q": TEST_COMPANY,
            "sort": "new",
            "t": "year",
            "limit": 10,
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) InternshipResearch/0.1",
        }
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        print(f"Status: {response.status_code}")
        print(f"Response keys: {list(data.keys())}")

        if "data" in data and "children" in data["data"]:
            posts = data["data"]["children"]
            print(f"Found {len(posts)} posts")
            if posts:
                post = posts[0]["data"]
                print(f"\nFirst post keys: {list(post.keys())}")
                print(f"  title: {post.get('title', '')[:80]}...")
                print(f"  subreddit: {post.get('subreddit', '')}")
                print(f"  selftext length: {len(post.get('selftext', ''))}")
                print(f"  url: {post.get('url', '')}")
                print(f"  created_utc: {post.get('created_utc', '')}")
                print(f"  score: {post.get('score', '')}")

        print("\n[OK] Reddit API contract validated")
        return True
    except Exception as e:
        print(f"\n[FAIL] Reddit API failed: {e}")
        return False


def test_hackernews_search():
    """Verify HN Algolia endpoint shape."""
    print(f"\n=== Testing Hacker News Algolia for '{TEST_COMPANY}' ===")
    try:
        url = "https://hn.algolia.com/api/v1/search"
        params = {
            "query": TEST_COMPANY,
            "numericFilters": f"created_at_i>{int(datetime(2025, 9, 1).timestamp())}",
            "hitsPerPage": 10,
        }
        headers = {
            "User-Agent": "InternshipResearch/0.1 (learning contract)",
        }
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        print(f"Status: {response.status_code}")
        print(f"Response keys: {list(data.keys())}")
        print(f"Found {data.get('nbHits', 0)} total hits")

        hits = data.get("hits", [])
        print(f"Returned {len(hits)} items in this page")
        if hits:
            hit = hits[0]
            print(f"\nFirst hit keys: {list(hit.keys())}")
            print(f"  title: {hit.get('title', '')[:80]}...")
            print(f"  url: {hit.get('url', '')}")
            print(f"  author: {hit.get('author', '')}")
            print(f"  created_at: {hit.get('created_at', '')}")
            print(f"  points: {hit.get('points', '')}")
            print(f"  num_comments: {hit.get('num_comments', '')}")

        print("\n[OK] HN Algolia API contract validated")
        return True
    except Exception as e:
        print(f"\n[FAIL] HN Algolia API failed: {e}")
        return False


if __name__ == "__main__":
    print("Contract tests for public APIs used in problem_research.py")
    print("=" * 60)

    reddit_ok = test_reddit_search()
    hn_ok = test_hackernews_search()

    print("\n" + "=" * 60)
    reddit_status = "OK" if reddit_ok else "FAIL"
    hn_status = "OK" if hn_ok else "FAIL"
    print(f"Results: Reddit={reddit_status}, HN Algolia={hn_status}")

    sys.exit(0 if (reddit_ok and hn_ok) else 1)
