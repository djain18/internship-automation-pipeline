import json
from execution.aggregate_and_score import is_duplicate

with open(".tmp/linkedin_posts_clean.json", "r", encoding="utf-8") as f:
    items = json.load(f)

seen = []
dups = 0
for item in items:
    is_dup = False
    for s in seen:
        if is_duplicate(item, s):
            print(f"Duplicate found:\n  1: {item.get('company')} - {item.get('title')}\n  2: {s.get('company')} - {s.get('title')}\n")
            is_dup = True
            dups += 1
            break
    if not is_dup:
        seen.append(item)

print(f"Total items: {len(items)}")
print(f"Total dups: {dups}")
print(f"Unique: {len(seen)}")
