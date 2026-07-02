"""
eval_filters.py
---------------
Measures how well the deterministic filters (execution/filters.py) separate real,
India-eligible internships from scams, personal stories, foreign roles, and noise.

Run:
    python execution/eval/eval_filters.py

It loads a hand-labeled dataset (labeled_posts.json), runs `filters.classify`
on each post, and reports precision / recall / F1 for the "keep as a real
internship" decision, plus a breakdown of *why* each rejected post was dropped.

Exit code is non-zero if precision or recall falls below the threshold, so this
can double as a regression gate in CI.
"""

from __future__ import annotations

import json
import os
import sys

# Make `import filters` work when run directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import filters  # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "labeled_posts.json")

# A post should be kept iff it is a genuine, India-eligible internship.
POSITIVE_LABEL = "real"

# Regression thresholds (the filters are conservative; tune as the set grows).
MIN_PRECISION = 0.85
MIN_RECALL = 0.85


def main() -> int:
    with open(DATA, encoding="utf-8") as f:
        posts = json.load(f)

    tp = fp = tn = fn = 0
    reasons: dict[str, int] = {}
    mistakes: list[str] = []

    for p in posts:
        expected_keep = p["label"] == POSITIVE_LABEL
        keep, reason = filters.classify(
            p.get("text", ""), p.get("location", ""), p.get("company", "")
        )
        reasons[reason] = reasons.get(reason, 0) + 1

        if keep and expected_keep:
            tp += 1
        elif keep and not expected_keep:
            fp += 1
            mistakes.append(f"  FALSE POSITIVE [{p['label']}] kept: {p['text'][:70]}...")
        elif not keep and not expected_keep:
            tn += 1
        else:
            fn += 1
            mistakes.append(f"  FALSE NEGATIVE [real] dropped ({reason}): {p['text'][:60]}...")

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    accuracy = (tp + tn) / len(posts) if posts else 0.0

    print("=" * 60)
    print(f"FILTER EVAL — {len(posts)} labeled posts")
    print("=" * 60)
    print(f"  Kept real internships (TP):      {tp}")
    print(f"  Wrongly kept junk    (FP):       {fp}")
    print(f"  Correctly dropped    (TN):       {tn}")
    print(f"  Wrongly dropped real (FN):       {fn}")
    print("-" * 60)
    print(f"  Precision: {precision:.1%}   (of kept posts, how many were real)")
    print(f"  Recall:    {recall:.1%}   (of real posts, how many we kept)")
    print(f"  F1:        {f1:.1%}")
    print(f"  Accuracy:  {accuracy:.1%}")
    print("-" * 60)
    print("  Rejection reasons:")
    for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
        print(f"    {reason:20s} {count}")
    if mistakes:
        print("-" * 60)
        print("  Misclassifications:")
        for m in mistakes:
            print(m)
    print("=" * 60)

    ok = precision >= MIN_PRECISION and recall >= MIN_RECALL
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
