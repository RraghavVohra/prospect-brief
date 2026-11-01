"""web_search tool: the reasoner asks a question, an OpenAI model searches the web and answers."""
from functools import lru_cache

from openai import AsyncOpenAI

from config import settings

# Tool definition shown to the reasoner.
WEB_SEARCH_TOOL = {
    "type": "function",
    "name": "web_search",
    "description": (
        "Search the live web and get back a short factual summary plus source URLs. "
        "Use one focused query per call, e.g. 'Jane Doe Acme Corp VP Sales LinkedIn' "
        "or 'Acme Corp funding announcement 2026'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What to search for."},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    "strict": True,
}

SEARCH_INSTRUCTIONS = (
    "You are a web research assistant. Search the web for the query and report only "
    "facts you found, with dates where available. Be concise. If nothing relevant "
    "is found, say so."
)


@lru_cache
def _client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=settings.openai_api_key)


async def web_search(query: str) -> dict:
    """Run one search and return {"query", "findings", "sources"}."""
    response = await _client().responses.create(
        model=settings.search_model,
        tools=[{"type": "web_search"}],
        instructions=SEARCH_INSTRUCTIONS,
        input=query,
    )
    return {
        "query": query,
        "findings": response.output_text,
        "sources": _extract_sources(response),
    }


def _extract_sources(response) -> list[dict]:
    """Collect unique cited URLs from the response's url_citation annotations."""
    sources, seen = [], set()
    for item in response.output:
        if item.type != "message":
            continue
        for part in item.content:
            for annotation in getattr(part, "annotations", None) or []:
                if annotation.type == "url_citation" and annotation.url not in seen:
                    seen.add(annotation.url)
                    sources.append({"title": annotation.title, "url": annotation.url})
    return sources
