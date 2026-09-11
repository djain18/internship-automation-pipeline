"""Mint a Gmail send-only OAuth token for the digest sender.

Reads the existing Google OAuth client from .env (GOOGLE_CREDENTIALS_JSON),
opens a browser consent screen, and writes the resulting authorized-user
token to .tmp/gmail-token.json (gitignored). Paste that file's contents into
the Modal `internship-hunt-gmail` secret as GMAIL_TOKEN_JSON, then delete it.

Scope is gmail.send only: the pipeline can send mail, nothing else.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "personal_hunt" / "execution"))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env", override=False)

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
OUT_PATH = REPO_ROOT / ".tmp" / "gmail-token.json"


def main() -> int:
    from google_auth_oauthlib.flow import InstalledAppFlow

    client_config = os.getenv("GOOGLE_CREDENTIALS_JSON", "")
    if not client_config:
        raise RuntimeError("GOOGLE_CREDENTIALS_JSON is missing from .env")
    info = json.loads(client_config)
    if "installed" not in info and "web" not in info:
        info = {"installed": info}
    flow = InstalledAppFlow.from_client_config(info, SCOPES)
    credentials = flow.run_local_server(port=0, prompt="consent")
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(credentials.to_json(), encoding="utf-8")
    print("Wrote " + str(OUT_PATH) + " (" + str(OUT_PATH.stat().st_size) + " bytes)")
    print("Paste its contents as GMAIL_TOKEN_JSON, then delete the file.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
