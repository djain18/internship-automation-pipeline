import { personalApiBase } from "./personalHunt.js";

// Mirrors RESUME_ATTACHMENTS in personal_hunt/execution/check_draft.py.
export const RESUMES = [
  "Daksh-Jain-founders_office.pdf",
  "Daksh-Jain-ai_automation.pdf",
  "Daksh-Jain-gtm.pdf",
  "Daksh-Jain-ops.pdf",
  "Daksh-Jain-Master.pdf",
];

const TAB_OF = {
  to_review: "review",
  needs_address: "review",
  blocked_validation: "review",
  approved: "approved",
  sending: "approved",
  sent: "sent",
  shadow_sent: "sent",
  send_failed: "sent",
  rejected: "rejected",
};

export function groupDrafts(drafts) {
  const groups = { review: [], approved: [], sent: [], rejected: [] };
  for (const item of drafts || []) groups[TAB_OF[item.status] || "review"].push(item);
  return groups;
}

// Unsaved edits are saved before approving, so they do not block the checkbox;
// the server re-checks everything on save and on approve.
export function canApprove(item, _dirty) {
  return item.status === "to_review" && Boolean(item.to) && !(item.errors || []).length;
}

// Same token rule as check_draft.py: [\w'’-]+
export function wordCount(text) {
  return (String(text || "").match(/[\p{L}\p{N}_'’-]+/gu) || []).length;
}

export function slotLabel(slot) {
  if (!slot) return "the next weekday, 10:00 IST";
  const date = new Date(slot);
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Kolkata",
    weekday: "short",
    day: "numeric",
    month: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const get = (type) => parts.find((part) => part.type === type)?.value;
  // Fixed month names: locales disagree ("Sep" vs "Sept"); the email uses "Sep".
  const month = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][Number(get("month")) - 1];
  return `${get("weekday")} ${Number(get("day"))} ${month}, ${get("hour")}:${get("minute")} IST`;
}

async function call(user, path, { method = "GET", body } = {}) {
  const token = await user.getIdToken();
  const response = await fetch(`${personalApiBase()}${path}`, {
    method,
    headers: { Authorization: `Bearer ${token}`, ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const error = new Error(payload?.detail || "The outbox could not be updated.");
    error.status = response.status;
    throw error;
  }
  return payload;
}

export const fetchDrafts = (user) => call(user, "/api/outreach/drafts");
export const saveDraft = (user, id, changes) =>
  call(user, `/api/outreach/drafts/${encodeURIComponent(id)}`, { method: "PATCH", body: changes });
export const approveDraft = (user, id) =>
  call(user, `/api/outreach/drafts/${encodeURIComponent(id)}/approve`, { method: "POST" });
export const rejectDraft = (user, id) =>
  call(user, `/api/outreach/drafts/${encodeURIComponent(id)}/reject`, { method: "POST" });
