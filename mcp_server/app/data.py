import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DATA_PATH = Path(__file__).parent / "data.json"
_REQUIRED_KEYS = frozenset({"id", "title", "body", "product_area"})


class KnowledgeBaseError(RuntimeError):
    """Raised when the knowledge-base data is missing or malformed."""


def _validate_article(article: Any, index: int) -> dict:
    if not isinstance(article, dict):
        raise KnowledgeBaseError(
            f"article at index {index} is not a JSON object"
        )
    missing = _REQUIRED_KEYS - article.keys()
    if missing:
        raise KnowledgeBaseError(
            f"article at index {index} is missing keys: {sorted(missing)}"
        )
    if not isinstance(article["id"], int):
        raise KnowledgeBaseError(f"article at index {index}: 'id' must be an int")
    for key in ("title", "body", "product_area"):
        if not isinstance(article[key], str):
            raise KnowledgeBaseError(
                f"article at index {index}: '{key}' must be a string"
            )
    return article


def load_articles(path: Path = _DATA_PATH) -> list[dict]:
    """Load and validate the knowledge base. Fails fast on any problem."""
    assert path.is_file(), f"knowledge base not found: {path}"
    assert path.suffix == ".json", f"knowledge base must be a JSON file: {path}"
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise KnowledgeBaseError(f"knowledge base not found: {path}") from exc
    except OSError as exc:
        raise KnowledgeBaseError(f"cannot read {path}: {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise KnowledgeBaseError(f"invalid JSON in {path}: {exc}") from exc

    if not isinstance(data, list):
        raise KnowledgeBaseError(f"{path} must contain a JSON array of articles")

    articles = [_validate_article(a, i) for i, a in enumerate(data)]
    logger.info("Loaded %d articles from %s", len(articles), path)
    return articles
