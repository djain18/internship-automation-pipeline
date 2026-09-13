"""Mint a Gmail OAuth token for the pipeline.

Reads the existing Google OAuth client from .env (GOOGLE_CREDENTIALS_JSON),
opens a browser consent screen, and writes the resulting authorized-user
token to .tmp/ (gitignored). Paste that file's contents into the Modal secret
named below, then delete the file.

Default: gmail.send only, for the self-digest sender. Paste into
`internship-hunt-gmail` as GMAIL_TOKEN_JSON.

--readonly: gmail.readonly only, for the outcome sync that fills the Sheet's
Outreach tab from what Daksh actually sent and received. Sign in with the
account Daksh sends outreach FROM. Paste into `internship-hunt-gmail-read` as
GMAIL_OUTCOMES_TOKEN_JSON. It can read mail, not send, label or delete it.
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

SEND_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
READ_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def main() -> int:
    from google_auth_oauthlib.flow import InstalledAppFlow

    readonly = "--readonly" in sys.argv[1:]
    scopes = READ_SCOPES if readonly else SEND_SCOPES
    out_path = REPO_ROOT / ".tmp" / ("gmail-read-token.json" if readonly else "gmail-token.json")
    secret, variable = (
        ("internship-hunt-gmail-read", "GMAIL_OUTCOMES_TOKEN_JSON")
        if readonly
        else ("internship-hunt-gmail", "GMAIL_TOKEN_JSON")
    )
    client_config = os.getenv("GOOGLE_CREDENTIALS_JSON", "")
    if not client_config:
        raise RuntimeError("GOOGLE_CREDENTIALS_JSON is missing from .env")
    info = json.loads(client_config)
    if "installed" not in info and "web" not in info:
        info = {"installed": info}
    flow = InstalledAppFlow.from_client_config(info, scopes)
    credentials = flow.run_local_server(port=0, prompt="consent")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(credentials.to_json(), encoding="utf-8")
    print("Wrote " + str(out_path) + " (" + str(out_path.stat().st_size) + " bytes)")
    print(f"Paste its contents into Modal secret {secret} as {variable}, then delete the file.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
