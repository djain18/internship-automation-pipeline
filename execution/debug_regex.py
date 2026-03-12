import json
import os
import sys

# Add execution dir to path to import llm_post_analyzer
sys.path.append(os.path.join(os.getcwd(), 'execution'))

from llm_post_analyzer import analyze_post_regex

RAW_FILE = ".tmp/mnc_run_raw.json"

def test_regex():
    if not os.path.exists(RAW_FILE):
        print(f"File not found: {RAW_FILE}")
        return

    with open(RAW_FILE, "r", encoding="utf-8") as f:
        posts = json.load(f)

    print(f"Loaded {len(posts)} raw posts.")
    print("Testing Regex Analysis on first 10 posts...\n")

    for i, post in enumerate(posts[:10]):
        text = post.get("text", "")
        posted_time = post.get("timeSincePosted") or "Unknown"
        
        print(f"--- Post {i+1} ---")
        print(f"Time: {posted_time}")
        print(f"Snippet: {text[:100]}...")
        
        analysis = analyze_post_regex(text, posted_time)
        print("Analysis Result:")
        print(json.dumps(analysis, indent=2))
        print("--------------------------------------------------\n")

if __name__ == "__main__":
    test_regex()
