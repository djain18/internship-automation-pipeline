// Display + behaviour helpers shared across the board and detail views.

export function formatStipend(stipend) {
  const n = Number(stipend) || 0;
  if (n <= 0) return "Unpaid / Undisclosed";
  if (n >= 100000) return `₹${(n / 100000).toFixed(n % 100000 ? 1 : 0)}L/mo`;
  if (n >= 1000) return `₹${Math.round(n / 1000)}K/mo`;
  return `₹${n}/mo`;
}

export function formatAge(hoursAgo) {
  const h = Number(hoursAgo) || 0;
  if (h < 1) return "Just now";
  if (h < 24) return `${h}h ago`;
  const d = Math.round(h / 24);
  return d === 1 ? "1 day ago" : `${d} days ago`;
}

export function isFresh(hoursAgo) {
  return (Number(hoursAgo) || 99) <= 24;
}

// Where a student actually applies: explicit link → original post → email.
export function openApply(listing) {
  const target =
    listing.applyLink?.trim() ||
    listing.postUrl?.trim() ||
    (listing.contact?.trim() ? `mailto:${listing.contact.trim()}` : "");
  if (!target) return;
  window.open(target, "_blank", "noopener,noreferrer");
}

export function applyLabel(listing) {
  if (listing.applyLink?.trim()) return "Apply now";
  if (listing.postUrl?.trim()) return "Apply via post";
  if (listing.contact?.trim()) return "Email to apply";
  return "View role";
}
