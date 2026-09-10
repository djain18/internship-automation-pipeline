import test from "node:test";
import assert from "node:assert/strict";
import { matchesFromPayload, isApprovedUser } from "./personalHunt.js";

test("matchesFromPayload labels Bengaluru and remote records", () => {
  const result = matchesFromPayload({
    bengaluru: [{ id: "a" }],
    remote: [{ id: "b" }],
  });
  assert.deepEqual(result.map(({ id, section }) => ({ id, section })), [
    { id: "a", section: "Bengaluru" },
    { id: "b", section: "India remote" },
  ]);
});

test("matchesFromPayload tolerates an empty response", () => {
  assert.deepEqual(matchesFromPayload({}), []);
});

test("isApprovedUser accepts both approved accounts, case and space insensitive", () => {
  assert.equal(isApprovedUser({ email: "dakshinjain187@gmail.com" }), true);
  assert.equal(isApprovedUser({ email: "dakshjainn02@gmail.com" }), true);
  assert.equal(isApprovedUser({ email: "  DakshJainn02@Gmail.com " }), true);
});

test("isApprovedUser rejects other or missing accounts", () => {
  assert.equal(isApprovedUser({ email: "someone@example.com" }), false);
  assert.equal(isApprovedUser({ email: "" }), false);
  assert.equal(isApprovedUser(null), false);
  assert.equal(isApprovedUser(undefined), false);
});

