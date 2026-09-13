from pathlib import Path

from outreach import EMAIL_COPY_RULES
from watchlist_prompts import build_watchlist_prompt, write_watchlist_prompts


def test_prompt_carries_only_facts_from_the_config_entry() -> None:
    """Deterministic: no network, no LLM. Every line must be traceable to
    watchlist.yml, and a company with no board must say so rather than
    implying one exists."""
    prompt = build_watchlist_prompt(
        {
            "name": "Emergent",
            "site_url": "https://emergent.sh",
            "board_url": "",
            "description": "YC company,\n  ~75 staff.",
        }
    )
    assert "# Emergent: deep-dive research + outreach draft" in prompt
    assert "- Site: https://emergent.sh" in prompt
    assert "- Careers/board URL: not on file" in prompt
    # The YAML folded block's newlines are collapsed, not pasted raw.
    assert "YC company, ~75 staff." in prompt
    # Copy rules come from outreach.py, never a retyped copy that can drift.
    assert EMAIL_COPY_RULES[0] in prompt
    assert "/humanizer" in prompt


def test_write_skips_unusable_entries(tmp_path: Path) -> None:
    written = write_watchlist_prompts(
        {"companies": ["not a dict", {"name": ""}, {"name": "Lyzr AI"}]}, tmp_path
    )
    assert [path.name for path in written] == ["lyzr-ai.md"]
    assert "Lyzr AI" in written[0].read_text(encoding="utf-8")
