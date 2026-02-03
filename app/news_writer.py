from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class NewsHit:
    keyword: str
    source: str
    title: str
    url: str


def _default_news_md_dir() -> Path:
    # Default to qmd folder for this guild/channel (per your setup).
    home = Path.home()
    return home / ".openclaw" / "discord-qmd" / "1467563842417590416" / "1467610706932269056" / "news"


def append_news_markdown(*, now_utc: datetime, hits: list[NewsHit]) -> Path | None:
    """Append news hits to a daily markdown file.

    This is designed to reduce chat token usage: write to disk, one file per day.
    """
    if not hits:
        return None

    base_dir = Path(os.getenv("NEWS_MD_DIR", str(_default_news_md_dir())))
    base_dir.mkdir(parents=True, exist_ok=True)

    day = now_utc.date().isoformat()
    path = base_dir / f"{day}-news.md"

    lines: list[str] = []
    lines.append(f"\n## {now_utc.isoformat()}Z\n")

    # group by keyword
    hits_sorted = sorted(hits, key=lambda x: (x.keyword, x.source, x.title))
    current_kw: str | None = None
    for h in hits_sorted:
        if h.keyword != current_kw:
            current_kw = h.keyword
            lines.append(f"\n### keyword: {current_kw}\n")
        url = h.url or ""
        title = h.title.replace("\n", " ").strip()
        if url:
            lines.append(f"- [{title}]({url}) — {h.source}\n")
        else:
            lines.append(f"- {title} — {h.source}\n")

    with path.open("a", encoding="utf-8") as f:
        f.writelines(lines)

    return path
