from poseidon import fallback


def test_is_no_route_exact_only():
    assert fallback.is_no_route("NO_ROUTE") is True
    assert fallback.is_no_route("  NO_ROUTE  ") is True
    assert fallback.is_no_route("NO_ROUTE because I lack a tool") is False
    assert fallback.is_no_route("Your depth is 12 metres.") is False
    assert fallback.is_no_route("") is False


def test_build_retry_prompt_includes_facts_and_query():
    p = fallback.build_retry_prompt(
        "where can we tuck in tonight",
        ["The Navigator handles where to anchor for the night."])
    assert "where can we tuck in tonight" in p
    assert "Navigator handles where to anchor" in p


def test_build_retry_prompt_no_facts_returns_none():
    assert fallback.build_retry_prompt("anything", []) is None
