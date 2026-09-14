import test from "node:test";
import assert from "node:assert/strict";
import { RESUMES, canApprove, groupDrafts, slotLabel, wordCount } from "./outreach.js";

const draft = (lead_id, status, extra = {}) => ({ lead_id, status, to: "a@b.co", errors: [], ...extra });

test("groupDrafts puts each status in its tab", () => {
  const groups = groupDrafts([
    draft("1", "to_review"),
    draft("2", "needs_address", { to: null }),
    draft("3", "blocked_validation"),
    draft("4", "approved"),
    draft("5", "sent"),
    draft("6", "shadow_sent"),
    draft("7", "send_failed"),
    draft("8", "rejected"),
    draft("9", "sending"),
  ]);
  assert.deepEqual(
    Object.fromEntries(Object.entries(groups).map(([k, v]) => [k, v.map((d) => d.lead_id)])),
    { review: ["1", "2", "3"], approved: ["4", "9"], sent: ["5", "6", "7"], rejected: ["8"] },
  );
});

test("canApprove needs a clean ready draft with an address and no unsaved edits", () => {
  assert.equal(canApprove(draft("1", "to_review"), false), true);
  assert.equal(canApprove(draft("1", "to_review"), true), true); // saved first, then approved
  assert.equal(canApprove(draft("1", "needs_address", { to: null }), false), false);
  assert.equal(canApprove(draft("1", "blocked_validation", { errors: ["x"] }), false), false);
  assert.equal(canApprove(draft("1", "approved"), false), false);
});

test("wordCount matches the server's rule", () => {
  assert.equal(wordCount("I'm writing to you, founder-office team."), 6);
  assert.equal(wordCount(""), 0);
});

test("slotLabel shows IST day and time", () => {
  assert.equal(slotLabel("2026-09-15T10:00:00+05:30"), "Tue 15 Sep, 10:00 IST");
  assert.equal(slotLabel(null), "the next weekday, 10:00 IST");
});

test("RESUMES lists the five allowed attachments", () => {
  assert.equal(RESUMES.length, 5);
  assert.ok(RESUMES.includes("Daksh-Jain-founders_office.pdf"));
});
