from __future__ import annotations

import json
import os
from typing import Any

from models import Record, json_dumps


TAB_SCHEMAS: dict[str, list[str]] = {
    "Companies": [
        "id", "company", "company_url", "lane", "employee_count", "last_seen",
        "confidence", "source_urls", "status", "next_action",
    ],
    "Opportunities": [
        "id", "company", "title", "location", "location_class", "score", "source",
        "source_url", "apply_url", "resume", "posted_date", "posted_date_basis",
        "source_confidence", "verification_status", "llm_rank", "llm_fit_score",
        "llm_relevant", "llm_spam", "llm_rank_reason", "llm_rank_status",
        "digest_approved", "status", "last_seen",
    ],
    "Outreach": [
        "id", "opportunity_id", "company", "contact_name", "contact_role",
        "contact_email", "contact_status", "subject", "claude_prompt", "linkedin_note",
        "send_status", "mailsuite_status", "next_action", "sent_at",
        "reply_outcome", "interview_outcome", "strategy_id", "human_quality_rating",
    ],
    "Artifacts": [
        "id", "opportunity_id", "company", "artifact_status", "evidence_pack_path",
        "artifact_path", "public_url", "human_approved",
    ],
    "Runs": [
        "id", "run_kind", "run_date", "status", "raw_count", "eligible_count",
        "primary_count", "remote_count", "digest_primary_count",
        "digest_remote_count", "funding_primary_count", "funding_extended_count",
        "completed_at",
    ],
    "Source Health": [
        "id", "run_id", "source_id", "status", "record_count", "latency_ms",
        "error_type", "error_message", "checked_at", "human_action",
    ],
    "Config": ["id", "key", "value", "updated_at"],
    "Funding Signals": [
        "id", "company", "event_date", "funding_window", "headline",
        "source_name", "source_url", "source_confidence", "verification_status",
        "problem_hypothesis", "problem_status", "last_seen", "status",
    ],
}

HUMAN_OWNED: dict[str, set[str]] = {
    "Companies": {"status", "next_action"},
    "Opportunities": {"status"},
    "Outreach": {
        "send_status", "mailsuite_status", "next_action", "sent_at",
        "reply_outcome", "interview_outcome", "strategy_id", "human_quality_rating",
    },
    "Artifacts": {"public_url", "human_approved", "artifact_status"},
    "Funding Signals": {"status"},
}


def _credentials():
    from google.oauth2 import service_account
    from google.oauth2.credentials import Credentials

    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    path = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "")
    oauth_raw = os.getenv("GOOGLE_OAUTH_TOKEN_JSON", "")
    oauth_path = os.getenv("GOOGLE_OAUTH_TOKEN_FILE", "")
    if oauth_raw:
        return Credentials.from_authorized_user_info(json.loads(oauth_raw))
    if oauth_path:
        return Credentials.from_authorized_user_file(oauth_path)
    if raw:
        info = json.loads(raw)
        return service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
    if path:
        return service_account.Credentials.from_service_account_file(
            path, scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
    raise RuntimeError(
        "A Google service-account or OAuth token environment variable is required"
    )


def _service():
    from googleapiclient.discovery import build

    return build("sheets", "v4", credentials=_credentials(), cache_discovery=False)


def ensure_tabs(service: Any, spreadsheet_id: str) -> None:
    metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    existing = {
        sheet["properties"]["title"] for sheet in metadata.get("sheets", [])
    }
    requests = [
        {"addSheet": {"properties": {"title": title}}}
        for title in TAB_SCHEMAS
        if title not in existing
    ]
    if requests:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body={"requests": requests}
        ).execute()
    for title, headers in TAB_SCHEMAS.items():
        response = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=f"'{title}'!1:1"
        ).execute()
        current = response.get("values", [[]])
        current_headers = current[0] if current and current[0] else []
        if not current_headers:
            service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f"'{title}'!A1",
                valueInputOption="RAW",
                body={"values": [headers]},
            ).execute()
            continue
        missing = [header for header in headers if header not in current_headers]
        if missing:
            start_column = _column_name(len(current_headers) + 1)
            service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f"'{title}'!{start_column}1",
                valueInputOption="RAW",
                body={"values": [missing]},
            ).execute()


def _column_name(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _flatten(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json_dumps(value)
    return value


def merge_existing_row(
    tab: str, headers: list[str], existing_values: list[Any], row: Record
) -> list[Any]:
    current_values = list(existing_values)
    current_values.extend([""] * (len(headers) - len(current_values)))
    merged: list[Any] = []
    for index, header in enumerate(headers):
        current = current_values[index]
        if header in HUMAN_OWNED.get(tab, set()) and current not in ("", None):
            merged.append(current)
        elif header in row:
            merged.append(_flatten(row.get(header)))
        else:
            merged.append(current)
    return merged


def upsert_rows(
    service: Any, spreadsheet_id: str, tab: str, rows: list[Record]
) -> int:
    if not rows:
        return 0
    schema_headers = TAB_SCHEMAS[tab]
    matrix = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"'{tab}'!A1:ZZ"
    ).execute().get("values", [])
    headers = matrix[0] if matrix and matrix[0] else schema_headers
    existing = matrix[1:] if len(matrix) > 1 else []
    id_column = headers.index("id")
    row_by_id = {
        values[id_column]: index + 2
        for index, values in enumerate(existing)
        if len(values) > id_column and values[id_column]
    }
    updates = []
    appends = []
    for row in rows:
        identifier = str(row["id"])
        if identifier in row_by_id:
            existing_values = list(existing[row_by_id[identifier] - 2])
            values = merge_existing_row(tab, headers, existing_values, row)
            updates.append(
                {"range": f"'{tab}'!A{row_by_id[identifier]}", "values": [values]}
            )
        else:
            values = [_flatten(row.get(header)) for header in headers]
            appends.append(values)
    if updates:
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"valueInputOption": "RAW", "data": updates},
        ).execute()
    if appends:
        service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=f"'{tab}'!A:A",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": appends},
        ).execute()
    return len(rows)


def rows_from_run(run: Record) -> dict[str, list[Record]]:
    selected = run.get("primary", []) + run.get("remote_fallback", [])
    companies: dict[str, Record] = {}
    opportunities: list[Record] = []
    outreach_rows: list[Record] = []
    artifacts: list[Record] = []
    for item in selected:
        company_id = f"company_{item['id'].split('_')[-1]}"
        companies[company_id] = {
            "id": company_id,
            "company": item.get("company"),
            "company_url": item.get("company_url"),
            "lane": item.get("lane"),
            "employee_count": item.get("employee_count"),
            "last_seen": run.get("run_date"),
            "confidence": item.get("source_confidence"),
            "source_urls": [item.get("source_url"), item.get("funding_source_url")],
            "status": "qualified_opportunity",
            "next_action": "review_opportunity",
        }
        opportunities.append(
            {
                "id": item["id"],
                "company": item.get("company"),
                "title": item.get("title"),
                "location": item.get("location"),
                "location_class": item.get("location_class"),
                "score": item.get("score"),
                "source": item.get("source"),
                "source_url": item.get("source_url"),
                "apply_url": item.get("apply_url"),
                "resume": item.get("resume"),
                "posted_date": item.get("posted_date"),
                "posted_date_basis": item.get("posted_date_basis"),
                "source_confidence": item.get("source_confidence"),
                "verification_status": item.get("verification_status"),
                "llm_rank": item.get("llm_rank"),
                "llm_fit_score": item.get("llm_fit_score"),
                "llm_relevant": item.get("llm_relevant"),
                "llm_spam": item.get("llm_spam"),
                "llm_rank_reason": item.get("llm_rank_reason"),
                "llm_rank_status": item.get("llm_rank_status"),
                "digest_approved": item.get("digest_approved"),
                "status": "new",
                "last_seen": run.get("run_date"),
            }
        )
        contact = item.get("selected_contact", {})
        draft = item.get("outreach", {})
        outreach_rows.append(
            {
                "id": f"outreach_{item['id']}",
                "opportunity_id": item["id"],
                "company": item.get("company"),
                "contact_name": contact.get("name"),
                "contact_role": contact.get("role"),
                "contact_email": contact.get("email"),
                "contact_status": contact.get("verification_status") or contact.get("status"),
                # draft's own key is "email_subject" -- reading "subject"
                # (neither draft function has ever emitted that key) meant
                # this column was silently blank on every real run.
                "subject": draft.get("email_subject"),
                "claude_prompt": draft.get("claude_prompt"),
                "linkedin_note": draft.get("linkedin_note"),
                "send_status": draft.get("send_status"),
                "mailsuite_status": "not_sent",
                "next_action": "human_review",
                "strategy_id": draft.get("strategy_id"),
            }
        )
        artifacts.append(
            {
                "id": f"artifact_{item['id']}",
                "opportunity_id": item["id"],
                "company": item.get("company"),
                "artifact_status": item.get("artifact_status"),
                "evidence_pack_path": item.get("evidence_pack_path"),
                "artifact_path": item.get("artifact_path"),
                "public_url": "",
                "human_approved": False,
            }
        )
    run_row = {
        "id": run["run_id"],
        "run_kind": run.get("run_kind"),
        "run_date": run.get("run_date"),
        "status": run.get("status"),
        "raw_count": run.get("raw_count"),
        "eligible_count": run.get("eligible_count"),
        "primary_count": len(run.get("primary", [])),
        "remote_count": len(run.get("remote_fallback", [])),
        "digest_primary_count": len(run.get("digest_primary", [])),
        "digest_remote_count": len(run.get("digest_remote_fallback", [])),
        "funding_primary_count": len(run.get("funding_primary", [])),
        "funding_extended_count": len(run.get("funding_extended", [])),
        "completed_at": run.get("completed_at"),
    }
    health = [
        {"id": f"{run['run_id']}_{item['source_id']}", "run_id": run["run_id"], **item}
        for item in run.get("source_health", [])
    ]
    for candidate in run.get("company_candidates", []):
        companies.setdefault(candidate["id"], candidate)
    funding_rows: list[Record] = []
    for event in run.get("funding_primary", []) + run.get("funding_extended", []):
        research = event.get("problem_research") or {}
        funding_rows.append(
            {
                "id": event["funding_event_id"],
                "company": event.get("company"),
                "event_date": event.get("event_date"),
                "funding_window": event.get("funding_window"),
                "headline": event.get("headline"),
                "source_name": event.get("source_name"),
                "source_url": event.get("source_url"),
                "source_confidence": event.get("source_confidence"),
                "verification_status": event.get("verification_status"),
                "problem_hypothesis": research.get("problem_hypothesis"),
                "problem_status": research.get("problem_status"),
                "last_seen": run.get("run_date"),
                "status": "new",
            }
        )
    return {
        "Companies": list(companies.values()),
        "Opportunities": opportunities,
        "Outreach": outreach_rows,
        "Artifacts": artifacts,
        "Runs": [run_row],
        "Source Health": health,
        "Config": [],
        "Funding Signals": funding_rows,
    }


APPLIED_SEND_STATUSES = {"applied", "sent", "sent_manually"}
NO_OUTCOME_VALUES = {"", "none", "no_reply", "no_interview", "pending"}


def _table(matrix: list[list[Any]]) -> list[Record]:
    if not matrix or not matrix[0]:
        return []
    headers = [str(header) for header in matrix[0]]
    return [dict(zip(headers, row)) for row in matrix[1:]]


def summarize_outcomes(outreach_rows: list[Record], opportunity_rows: list[Record]) -> Record:
    """Lifetime application outcomes from the human-owned Outreach columns.

    source_yield has always carried manually_applied/replied/interviewed, and
    nothing ever filled them: build_source_yield read those fields off the
    day's scraped records, which never have them -- they only exist in the
    Sheet, where Daksh records what happened. Without them there is no way to
    learn which sources or which kinds of outreach actually produce replies.
    A row counts as applied when its send_status says so or it has a sent_at.
    """
    source_by_id = {
        str(row.get("id")): str(row.get("source") or "unknown") for row in opportunity_rows
    }
    totals = {"applied": 0, "replied": 0, "interviewed": 0}
    by_source: dict[str, Record] = {}
    for row in outreach_rows:
        status = str(row.get("send_status") or "").strip().casefold()
        reply = str(row.get("reply_outcome") or "").strip().casefold()
        interview = str(row.get("interview_outcome") or "").strip().casefold()
        counts = {
            "applied": int(status in APPLIED_SEND_STATUSES or bool(str(row.get("sent_at") or "").strip())),
            "replied": int(reply not in NO_OUTCOME_VALUES),
            "interviewed": int(interview not in NO_OUTCOME_VALUES),
        }
        if not any(counts.values()):
            continue
        source = source_by_id.get(str(row.get("opportunity_id")), "unknown")
        bucket = by_source.setdefault(source, {"applied": 0, "replied": 0, "interviewed": 0})
        for key, value in counts.items():
            totals[key] += value
            bucket[key] += value
    return {**totals, "by_source": by_source}


def read_outcomes(spreadsheet_id: str | None = None) -> Record:
    """Read the Outreach and Opportunities tabs and summarise outcomes.
    Read-only, with the credential publish_run already uses."""
    spreadsheet_id = spreadsheet_id or os.getenv("INTERNSHIP_SHEET_ID", "")
    if not spreadsheet_id:
        raise RuntimeError("INTERNSHIP_SHEET_ID is required")
    values = _service().spreadsheets().values()

    def read(tab: str) -> list[Record]:
        return _table(
            values.get(spreadsheetId=spreadsheet_id, range=f"'{tab}'!A1:ZZ").execute().get("values", [])
        )

    return summarize_outcomes(read("Outreach"), read("Opportunities"))


def publish_run(run: Record, spreadsheet_id: str | None = None) -> dict[str, int]:
    spreadsheet_id = spreadsheet_id or os.getenv("INTERNSHIP_SHEET_ID", "")
    if not spreadsheet_id:
        raise RuntimeError("INTERNSHIP_SHEET_ID is required")
    service = _service()
    ensure_tabs(service, spreadsheet_id)
    rows = rows_from_run(run)
    return {
        tab: upsert_rows(service, spreadsheet_id, tab, tab_rows)
        for tab, tab_rows in rows.items()
    }


def create_tracking_sheet(title: str) -> dict[str, str]:
    service = _service()
    body = {
        "properties": {"title": title},
        "sheets": [{"properties": {"title": tab}} for tab in TAB_SCHEMAS],
    }
    created = service.spreadsheets().create(body=body, fields="spreadsheetId,spreadsheetUrl").execute()
    spreadsheet_id = str(created["spreadsheetId"])
    ensure_tabs(service, spreadsheet_id)
    return {
        "spreadsheet_id": spreadsheet_id,
        "spreadsheet_url": str(created["spreadsheetUrl"]),
    }
