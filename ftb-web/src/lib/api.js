// API client — reads from the FastAPI backend.
// Falls back to seed data when the API is unreachable.

const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

async function apiFetch(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  })
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`)
  return res.json()
}

export async function fetchListings() {
  return apiFetch('/api/listings')
}

export async function fetchStats() {
  return apiFetch('/api/stats')
}

export async function submitSubscriber({ email, roles, cities, remote, gradYear }) {
  return apiFetch('/api/subscribe', {
    method: 'POST',
    body: JSON.stringify({ email, roles, cities, remote, gradYear }),
  })
}
