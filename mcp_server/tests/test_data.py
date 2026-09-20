import pytest
from app.data import KnowledgeBaseError, load_articles


def test_load_articles_rejects_malformed_data(tmp_path):
    bad = tmp_path / "data.json"
    bad.write_text('[{"id": 1, "title": "x"}]')  # missing keys
    with pytest.raises(KnowledgeBaseError, match="missing keys"):
        load_articles(bad)


def test_load_articles_rejects_invalid_json(tmp_path):
    bad = tmp_path / "data.json"
    bad.write_text("{not json")
    with pytest.raises(KnowledgeBaseError, match="invalid JSON"):
        load_articles(bad)