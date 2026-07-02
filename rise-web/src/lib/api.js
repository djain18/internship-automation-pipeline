// Thin client for the existing FastAPI backend (api/main.py).
// Falls back to local seed data so the site never renders blank.

import { SEED_LISTINGS, SEED_STATS } from "./seed";

const BASE = (import.meta.env.VITE_API_BASE || "").replace(/\/$/, "");

async function getJSON(path, { signal, timeout = 8000 } = {}) {
  if (!BASE) throw new Error("VITE_API_BASE not set");
  const ctrl = new AbortController();
  // Forward an external abort (e.g. React effect cleanup) to our controller.
  const onAbort = () => ctrl.abort();
  if (signal) signal.addEventListener("abort", onAbort, { once: true });
  const t = setTimeout(() => ctrl.abort(), timeout);
  try {
    const res = await fetch(`${BASE}${path}`, { signal: ctrl.signal });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } finally {
    clearTimeout(t);
    if (signal) signal.removeEventListener("abort", onAbort);
  }
}

export async function fetchListings(signal) {
  try {
    const data = await getJSON("/api/listings", { signal });
    if (Array.isArray(data) && data.length) return data;
    return SEED_LISTINGS;
  } catch (e) {
    // Don't mask an aborted request (StrictMode/unmount) as a seed fallback —
    // let the caller ignore it so the live result from the surviving run wins.
    if (e?.name === "AbortError") throw e;
    return SEED_LISTINGS;
  }
}

export async function fetchStats(signal) {
  try {
    const data = await getJSON("/api/stats", { signal });
    return data && typeof data === "object" ? data : SEED_STATS;
  } catch (e) {
    if (e?.name === "AbortError") throw e;
    return SEED_STATS;
  }
}

export async function subscribe(payload) {
  if (!BASE) {
    // No backend configured — pretend success in local/demo mode.
    return { status: "ok", demo: true };
  }
  const res = await fetch(`${BASE}/api/subscribe`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
