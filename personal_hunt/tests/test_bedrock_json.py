import json

from research import _strip_fences


def test_strip_fences_removes_json_code_fence() -> None:
    fenced = '```json\n{"a": 1}\n```'
    assert json.loads(_strip_fences(fenced)) == {"a": 1}


def test_strip_fences_leaves_raw_json_untouched() -> None:
    raw = '{"a": 1}'
    assert _strip_fences(raw) == raw


def test_strip_fences_keeps_unparseable_output_unparseable() -> None:
    with_blank = "not json at all"
    try:
        json.loads(_strip_fences(with_blank))
    except ValueError:
        return
    raise AssertionError("expected unparseable output to stay unparseable")

