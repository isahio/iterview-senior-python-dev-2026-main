"""
Tiny FastMCP server exposing a toy knowledge-base search tool.

Run standalone with:
    uv run python -m mcp_server.main
"""

import logging
import os

from fastmcp import FastMCP

from .data import load_articles

logger = logging.getLogger(__name__)

_ARTICLES: list[dict] = load_articles()
# Common words excluded so they don't inflate every article's score just by
# appearing in ordinary English sentences.
_STOPWORDS = {
    "the", "and", "for", "are", "was", "you", "your", "with", "that", "this",
    "what", "why", "how", "when", "does", "did", "has", "have", "not", "but",
    "can", "get", "got", "out", "our", "who", "its", "it's", "i'm", "i've",
}

mcp = FastMCP("support-kb")


@mcp.tool()
def search_kb(query: str, max_results: int = 3) -> list[dict]:
    """
    Search the support knowledge base by simple keyword overlap.

    Args:
        query: Free-text description of the issue.
        max_results: Max number of articles to return.

    Returns:
        A list of {"id": int, "title": str, "body": str, "product_area": str}
        dicts, ranked by keyword overlap with the query, most relevant
        first. Empty list if nothing matches.
    """
    query_terms = {
        w.lower().strip(".,!?")
        for w in query.split()
        if len(w) > 2 and w.lower() not in _STOPWORDS
    }

    def score(article: dict) -> int:
        text = f"{article['title']} {article['body']}".lower()
        return sum(1 for term in query_terms if term in text)

    ranked = [a for a in _ARTICLES if score(a) > 0]
    ranked.sort(key=score, reverse=True)
    return ranked[:max_results]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8001")),
    )
