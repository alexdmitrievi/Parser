"""Тесты извлечения вида деятельности и предложений/запросов."""

from leads.activity import extract_activity, extract_offers, extract_requests


def test_extract_offers_finds_manufacturing_phrases():
    text = (
        "We are a leading manufacturer of agricultural machinery. "
        "Our factory produces tractors and combine harvesters. "
        "Established in 2005, we employ 300 people."
    )
    offers = extract_offers(text)
    assert any("agricultural machinery" in o for o in offers)
    assert any("tractors" in o for o in offers)


def test_extract_requests_finds_import_phrases():
    text = (
        "We import wheat and barley from major producers. "
        "We are looking for reliable suppliers of feed grain. "
        "Our company purchases corn in bulk."
    )
    requests = extract_requests(text)
    assert any("wheat" in r for r in requests)
    assert any("suppliers" in r for r in requests)


def test_extract_activity_returns_first_sentences():
    text = (
        "Shandong Agri Machinery Co., Ltd. is a professional manufacturer. "
        "We export tractors to over 20 countries. "
        "Contact us for a quote."
    )
    activity = extract_activity(text)
    assert "manufacturer" in activity
    assert len(activity) <= 300


def test_empty_input_returns_empty():
    assert extract_offers("") == []
    assert extract_requests("") == []
    assert extract_activity("") == ""


def test_offers_limit_is_respected():
    text = " ".join(f"We produce product number {i} for export." for i in range(20))
    assert len(extract_offers(text, limit=5)) == 5


def test_no_false_positive_on_neutral_text():
    text = "Our history dates back to 1990. The office is open Monday to Friday."
    assert extract_offers(text) == []
    assert extract_requests(text) == []
