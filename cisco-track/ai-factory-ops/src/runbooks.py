"""Runbook parsing and lightweight retrieval."""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel


class RunbookSection(BaseModel):
    """Parsed runbook section."""

    title: str
    body: str
    keywords: set[str]


def _tokenize(text: str) -> set[str]:
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    normalized = normalized.replace("_", " ")
    return {token for token in re.findall(r"[a-z0-9]+", normalized.lower()) if len(token) >= 3}


def parse_runbooks(path: str | Path) -> list[RunbookSection]:
    """Parse markdown runbooks by ## heading sections."""
    source = Path(path)
    content = source.read_text(encoding="utf-8")

    parts = re.split(r"^##\s+", content, flags=re.MULTILINE)
    sections: list[RunbookSection] = []
    for raw in parts[1:]:
        lines = raw.strip().splitlines()
        if not lines:
            continue
        title = lines[0].strip()
        body = "\n".join(lines[1:]).strip()
        keywords = _tokenize(f"{title}\n{body}")
        sections.append(RunbookSection(title=title, body=body, keywords=keywords))
    return sections


def retrieve_best_runbook(
    query_text: str,
    sections: list[RunbookSection],
) -> tuple[RunbookSection | None, float]:
    """Return top-1 section using keyword overlap score."""
    query_tokens = _tokenize(query_text)
    if not query_tokens:
        return None, 0.0

    best_section: RunbookSection | None = None
    best_score = 0.0
    for section in sections:
        overlap = query_tokens & section.keywords
        score = len(overlap) / len(query_tokens)
        if score > best_score:
            best_score = score
            best_section = section

    return best_section, best_score
