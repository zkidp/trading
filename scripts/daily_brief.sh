#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

# Generate daily brief markdown to BRIEF_MD_DIR (defaults to qmd path)
docker compose run --rm app python -m app.daily_brief

# Optional: send email if SMTP env is configured in .env
# docker compose run --rm app python -c 'from pathlib import Path; import os; from app.emailer import send_email; p=Path(os.environ.get("BRIEF_MD_DIR", Path.home()/".openclaw/discord-qmd/1467563842417590416/1467610706932269056/news/brief"))/f"{__import__("datetime").datetime.now(__import__("datetime").timezone.utc).date().isoformat()}-brief.md"; send_email(subject="Daily Brief", body_text=p.read_text(encoding="utf-8"))'
