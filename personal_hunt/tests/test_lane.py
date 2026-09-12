from config import load_all
from normalize import classify_lane


def test_short_ai_term_uses_word_boundary() -> None:
    roles = load_all()["roles"]
    assert classify_lane("Ressl AI GTM Intern", roles) == "ai"
    assert classify_lane("Retail operations intern", roles) == "consumer"


