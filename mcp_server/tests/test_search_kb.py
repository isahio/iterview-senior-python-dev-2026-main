from app.main import search_kb


def test_search_kb_returns_relevant_articles():
    results = search_kb("I can't log in, my 2FA code never arrives")
    assert results
    assert any(
        "2fa" in r["title"].lower() or "login" in r["title"].lower() for r in results
    )


def test_search_kb_case_insensitivity():
    results = search_kb("LOGIN issues with 2FA")
    assert results
    assert any(
        "2fa" in r["title"].lower() or "login" in r["title"].lower() for r in results
    )


def test_search_kb_returns_empty_for_irrelevant_query():
    results = search_kb("completely unrelated query")
    assert results == []


def test_search_kb_empty_for_unrelated_query():
    assert search_kb("what is the airspeed velocity of an unladen swallow") == []
