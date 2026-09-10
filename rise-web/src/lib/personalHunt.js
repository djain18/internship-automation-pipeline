const DEFAULT_PERSONAL_API =
  "https://dakshinjain187--daksh-internship-hunt-personal-api.modal.run";

// Mirrors PERSONAL_APPROVED_EMAILS in personal_hunt/execution/private_api.py.
// Client-side use is presentation only — the API is the actual gate.
export const APPROVED_EMAILS = [
  "dakshinjain187@gmail.com",
  "dakshjainn02@gmail.com",
];

export function personalApiBase() {
  return (import.meta.env.VITE_PERSONAL_API_BASE || DEFAULT_PERSONAL_API).replace(/\/$/, "");
}

export function isApprovedUser(user) {
  const email = (user?.email || "").trim().toLowerCase();
  return Boolean(email) && APPROVED_EMAILS.includes(email);
}

export function matchesFromPayload(payload) {
  return [
    ...(payload?.bengaluru || []).map((item) => ({ ...item, section: "Bengaluru" })),
    ...(payload?.remote || []).map((item) => ({ ...item, section: "India remote" })),
  ];
}

export async function fetchPersonalHunt(user, signal) {
  const token = await user.getIdToken();
  const response = await fetch(`${personalApiBase()}/api/personal/latest`, {
    signal,
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok) {
    const error = new Error(body?.detail || "Your private hunt could not be loaded.");
    error.status = response.status;
    throw error;
  }
  return body;
}

