#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

# Generate daily brief markdown to BRIEF_MD_DIR (defaults to qmd path)
docker compose run --rm app-lite python -m app.daily_brief

# Send email if SMTP env is configured in .env. If not configured, this step is skipped.
docker compose run --rm app-lite python - <<'PY'
import os
from pathlib import Path
from datetime import datetime, timezone

from app.emailer import send_email

mail_to = os.getenv("MAIL_TO")
smtp_host = os.getenv("SMTP_HOST")
if not mail_to or not smtp_host:
    print("[brief] SMTP not configured; skip sending email")
    raise SystemExit(0)

brief_dir = Path(os.environ.get(
    "BRIEF_MD_DIR",
    str(Path.home()/".openclaw/discord-qmd/1467563842417590416/1467610706932269056/news/brief"),
))
path = brief_dir / f"{datetime.now(timezone.utc).date().isoformat()}-brief.md"
body = path.read_text(encoding="utf-8") if path.exists() else "(brief file missing)"

send_email(subject=f"Daily Brief {datetime.now(timezone.utc).date().isoformat()}", body_text=body)
print(f"[brief] sent email to {mail_to} (len={len(body)})")
PY
