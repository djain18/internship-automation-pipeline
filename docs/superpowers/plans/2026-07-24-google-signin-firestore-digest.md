# Google Sign-In + Firestore-Backed Digest Emails Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A student can sign in with Google on the live site, pick the
fields/cities/grad-year they care about, and automatically receive matching
internships in their inbox every morning — replacing the current
unauthenticated email-capture form entirely.

**Architecture:** Firebase Authentication (Google provider) on the frontend;
on sign-in, the client writes preferences directly to a `users/{uid}`
Firestore document (secured by a schema-validating rule, not just a `uid`
check). The existing 8AM IST `daily_digest` Modal cron swaps its subscriber
source from Resend contacts to a Firestore query via `firebase-admin`, using
a dedicated Modal secret scoped only to that function. Resend keeps doing
only the actual email send.

**Tech Stack:** Firebase JS SDK (client), `firebase-admin` (Python, server),
Firestore, existing Modal/Vercel infra from Project A.

## Global Constraints

- Firebase project already created: project ID `rise-internships-eb6d0`,
  Google sign-in provider enabled, Firestore enabled (production mode,
  no default rules yet — this plan writes the real ones).
- Web app config (public, safe to embed in frontend env vars):
  - `apiKey`: `AIzaSyBZ1zJnO6sD0u2VXrXri3ugTG6pyYeejOw`
  - `authDomain`: `rise-internships-eb6d0.firebaseapp.com`
  - `projectId`: `rise-internships-eb6d0`
  - `storageBucket`: `rise-internships-eb6d0.firebasestorage.app`
  - `messagingSenderId`: `713588841822`
  - `appId`: `1:713588841822:web:8a14ca7329b5830bbb43cf`
- Service-account key file (sensitive — never paste its contents into any
  commit, log, or chat; only the controller reads it, directly into a Modal
  secret): `C:\Users\daksh\Downloads\rise-internships-eb6d0-firebase-adminsdk-fbsvc-911ec6ef7b.json`
- Firebase CLI is installed and authenticated (`dakshhwork18@gmail.com`,
  confirmed access to `rise-internships-eb6d0`).
- `users/{uid}` document shape, exactly:
  `{ email: string, roles: string[], cities: string[], gradYear: string, remote: bool, updatedAt: timestamp }`.
  No other fields. `roles`/`cities` capped at 20 entries each.
- The Firestore security rule must validate this schema, not just
  `request.auth.uid == uid` — a previous design review flagged that a bare
  ownership check would let a malformed doc reach the digest cron's
  per-subscriber loop.
- The Firebase Admin service-account key gets its **own** Modal secret
  (`firebase-admin-key`), attached only to `daily_digest` — never folded into
  `internship-secrets`, which is also attached to the public, unauthenticated
  `run_now` webhook (`modal_app.py`).
- `firebase-admin` is added to the existing heavy pipeline `image` in
  `modal_app.py` (the one `daily_digest` already uses) — **not** a new
  dedicated image. Unlike Project A's public-facing `api_web` (where
  cold-start latency is visitor-facing), `daily_digest` is a scheduled cron
  with no live-traffic latency concern, so a third image variant isn't
  justified here. This is a deliberate simplification versus the design
  spec's suggestion of a dedicated digest-only image.
- No JS test runner exists in `rise-web/` (no vitest/jest configured). Adding
  one is out of scope for this plan — frontend changes are verified manually
  via a real browser (chrome-devtools MCP), matching how Project A verified
  `rise-web` changes. Python changes (the digest script) get real pytest
  unit tests, matching this repo's existing Python test convention.
- Per Project A's established pattern: any command touching live/shared
  infrastructure (`modal deploy`, `vercel env`, `firebase deploy`) is
  confirmed with the user immediately before running, individually.
- Resend contact migration is **not needed**: the live Resend audience was
  confirmed empty (0 contacts, 0 subscribers) during Project A's work — there
  is no existing subscriber base to notify before cutting over.

---

### Task 1: Firebase client SDK, config module, and env vars

**Files:**
- Modify: `rise-web/package.json` (add `firebase` dependency)
- Create: `rise-web/src/lib/firebase.js`
- Modify: root `.env` (user action — add Firebase env vars for local dev,
  read-protected for the agent)
- Modify: Vercel production env vars (controller action, confirm first)

**Interfaces:**
- Produces: `auth` (Firebase Auth instance) and `db` (Firestore instance)
  exported from `rise-web/src/lib/firebase.js`, consumed by Task 2 and
  Task 3.

- [ ] **Step 1: Add the Firebase dependency**

Run (from `rise-web/`): `npm install firebase`

Then open `rise-web/package.json` and confirm a `"firebase": "^..."` line was
added to `dependencies` — note whatever version npm resolved (do not
hand-edit the version).

- [ ] **Step 2: Create the Firebase init module**

Create `rise-web/src/lib/firebase.js`:

```javascript
// Initializes the Firebase app once for the whole site. Config values here
// are public by design (safe to ship in the client bundle) — Firestore
// access is controlled entirely by security rules (see firestore.rules),
// not by keeping these values secret.
import { initializeApp } from "firebase/app";
import { getAuth, GoogleAuthProvider } from "firebase/auth";
import { getFirestore } from "firebase/firestore";

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};

const app = initializeApp(firebaseConfig);

export const auth = getAuth(app);
export const db = getFirestore(app);
export const googleProvider = new GoogleAuthProvider();
```

- [ ] **Step 2 (user action): add local env vars**

Ask the user to add these lines to `rise-web/.env` (create the file if it
doesn't exist — check first with `ls rise-web/.env`; this file is separate
from the root `.env` and is not read-protected the same way, but treat it as
the user's file to edit since it's a Vite env file conventionally
gitignored):

```
VITE_FIREBASE_API_KEY=AIzaSyBZ1zJnO6sD0u2VXrXri3ugTG6pyYeejOw
VITE_FIREBASE_AUTH_DOMAIN=rise-internships-eb6d0.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=rise-internships-eb6d0
VITE_FIREBASE_STORAGE_BUCKET=rise-internships-eb6d0.firebasestorage.app
VITE_FIREBASE_MESSAGING_SENDER_ID=713588841822
VITE_FIREBASE_APP_ID=1:713588841822:web:8a14ca7329b5830bbb43cf
```

- [ ] **Step 3: Verify locally**

Run (from `rise-web/`): `npm run dev`

Open the local dev server URL in a browser and check the browser console —
expect no Firebase initialization errors (e.g. no
`Firebase: Error (auth/invalid-api-key)`). The site should otherwise look
and behave exactly as before (nothing consumes `auth`/`db` yet).

- [ ] **Step 4: Commit**

```bash
git add rise-web/package.json rise-web/package-lock.json rise-web/src/lib/firebase.js
git commit -m "feat: add Firebase client SDK and init module"
```

(Do not commit `rise-web/.env` — it should already be gitignored the same
way the root `.env` is; confirm with `git status` that it's not staged.)

---

### Task 2: Auth context + Navbar sign-in state

**Files:**
- Create: `rise-web/src/lib/AuthContext.jsx`
- Modify: `rise-web/src/main.jsx`
- Modify: `rise-web/src/components/Navbar.jsx`

**Interfaces:**
- Consumes: `auth`, `googleProvider` from `rise-web/src/lib/firebase.js`
  (Task 1).
- Produces: `useAuth()` hook returning
  `{ user, loading, signInWithGoogle, signOutUser }`, consumed by Task 3 and
  by `Navbar.jsx`. `user` is `null` when signed out, else the Firebase
  `User` object (`user.uid`, `user.email`, `user.displayName`,
  `user.photoURL`).

- [ ] **Step 1: Create the auth context**

Create `rise-web/src/lib/AuthContext.jsx`:

```javascript
import { createContext, useContext, useEffect, useState } from "react";
import {
  onAuthStateChanged,
  signInWithPopup,
  signOut,
} from "firebase/auth";
import { auth, googleProvider } from "./firebase";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (firebaseUser) => {
      setUser(firebaseUser);
      setLoading(false);
    });
    return unsubscribe;
  }, []);

  async function signInWithGoogle() {
    await signInWithPopup(auth, googleProvider);
  }

  async function signOutUser() {
    await signOut(auth);
  }

  return (
    <AuthContext.Provider value={{ user, loading, signInWithGoogle, signOutUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
```

- [ ] **Step 2: Wrap the app in the provider**

In `rise-web/src/main.jsx`, add the import and wrap `<App />`:

```javascript
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { AuthProvider } from "./lib/AuthContext.jsx";
import App from "./App.jsx";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>
);
```

- [ ] **Step 3: Update the Navbar**

Replace `rise-web/src/components/Navbar.jsx` in full:

```javascript
import { Link, NavLink, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/AuthContext";

const links = [
  { label: "Internships", to: "/internships" },
  { label: "How it works", to: "/how-it-works" },
  { label: "FAQ", to: "/faq" },
];

export default function Navbar() {
  const navigate = useNavigate();
  const { user, loading, signInWithGoogle, signOutUser } = useAuth();

  return (
    <header className="sticky top-0 z-50 border-b border-border/60 bg-background/80 backdrop-blur-md">
      <nav className="mx-auto flex max-w-6xl items-center justify-between px-6 md:px-10 py-4 font-body">
        <Link to="/" aria-label="Rise — home" className="flex items-center">
          <img src="/rise-logo.png" alt="Rise" className="h-7 w-auto" />
        </Link>

        <div className="hidden md:flex items-center gap-8">
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              className={({ isActive }) =>
                `text-sm transition-colors ${
                  isActive ? "text-foreground font-medium" : "text-muted-foreground hover:text-foreground"
                }`
              }
            >
              {link.label}
            </NavLink>
          ))}
        </div>

        {loading ? null : user ? (
          <div className="flex items-center gap-3">
            {user.photoURL && (
              <img
                src={user.photoURL}
                alt={user.displayName || user.email}
                className="h-8 w-8 rounded-full"
                referrerPolicy="no-referrer"
              />
            )}
            <button
              onClick={signOutUser}
              className="text-sm text-muted-foreground hover:text-foreground"
            >
              Sign out
            </button>
          </div>
        ) : (
          <Button
            onClick={() => navigate("/#alerts")}
            className="rounded-full px-5 text-sm font-medium"
          >
            Get daily alerts
          </Button>
        )}
      </nav>
    </header>
  );
}
```

Signed-out users still see the existing "Get daily alerts" button (which
scrolls to the `#alerts` section, now the sign-in form built in Task 3) —
only the signed-in state is new.

- [ ] **Step 4: Verify locally**

Run (from `rise-web/`): `npm run dev`. Load the site — it should render
identically to before (no user signed in yet, so the Navbar's signed-out
branch renders, unchanged from the prior markup).

- [ ] **Step 5: Commit**

```bash
git add rise-web/src/lib/AuthContext.jsx rise-web/src/main.jsx rise-web/src/components/Navbar.jsx
git commit -m "feat: add Firebase auth context and Navbar sign-in state"
```

---

### Task 3: Replace EmailAlerts.jsx with Google Sign-In + Firestore preferences

**Files:**
- Modify: `rise-web/src/components/EmailAlerts.jsx` (full rewrite)

**Interfaces:**
- Consumes: `useAuth()` (Task 2), `db` from `rise-web/src/lib/firebase.js`
  (Task 1).
- Produces: writes to `users/{uid}` in Firestore — the shape Task 6's rules
  validate and Task 7's digest script reads.

- [ ] **Step 1: Rewrite the component**

Replace `rise-web/src/components/EmailAlerts.jsx` in full:

```javascript
import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Check, Loader2 } from "lucide-react";
import { doc, getDoc, setDoc, serverTimestamp } from "firebase/firestore";
import { Button } from "@/components/ui/button";
import { db } from "@/lib/firebase";
import { useAuth } from "@/lib/AuthContext";
import Reveal from "./Reveal";

const FIELDS = [
  "Software", "Data/AI", "Design", "Product", "Marketing",
  "Finance", "Business Dev", "HR", "Content", "Operations",
];
const CITIES = ["Bangalore", "Mumbai", "Delhi NCR", "Hyderabad", "Pune", "Chennai", "Remote"];
const GRAD_YEARS = ["2026", "2027", "2028", "2029"];

export default function EmailAlerts() {
  const { user, signInWithGoogle } = useAuth();
  const [roles, setRoles] = useState([]);
  const [city, setCity] = useState("Bangalore");
  const [gradYear, setGradYear] = useState("2027");
  const [status, setStatus] = useState("idle"); // idle | loading | done | error
  const [signingIn, setSigningIn] = useState(false);
  const [signInError, setSignInError] = useState(false);

  // Prefill from the user's existing saved preferences, if any.
  useEffect(() => {
    if (!user) return;
    getDoc(doc(db, "users", user.uid)).then((snap) => {
      if (!snap.exists()) return;
      const data = snap.data();
      if (Array.isArray(data.roles)) setRoles(data.roles);
      if (Array.isArray(data.cities) && data.cities[0]) setCity(data.cities[0]);
      if (data.gradYear) setGradYear(data.gradYear);
    });
  }, [user]);

  const toggle = (f) =>
    setRoles((r) => (r.includes(f) ? r.filter((x) => x !== f) : [...r, f]));

  async function handleSignIn() {
    setSigningIn(true);
    setSignInError(false);
    try {
      await signInWithGoogle();
    } catch (err) {
      // auth/popup-closed-by-user is a normal cancel, not a failure worth
      // surfacing; anything else (e.g. popup blocked, network error) gets
      // an inline message so sign-in failure is visible, not silent.
      if (err?.code !== "auth/popup-closed-by-user") {
        setSignInError(true);
      }
    } finally {
      setSigningIn(false);
    }
  }

  async function onSubmit(e) {
    e.preventDefault();
    if (!user) return;
    setStatus("loading");
    try {
      await setDoc(doc(db, "users", user.uid), {
        email: user.email,
        roles,
        cities: [city],
        remote: city === "Remote",
        gradYear,
        updatedAt: serverTimestamp(),
      });
      setStatus("done");
    } catch {
      setStatus("error");
    }
  }

  return (
    <section id="alerts" className="scroll-mt-20 border-t border-border bg-secondary/30">
      <div className="mx-auto max-w-4xl px-6 py-20 md:px-10">
        <Reveal
          className="overflow-hidden rounded-3xl border border-border bg-background p-8 shadow-dashboard md:p-12"
        >
          {status === "done" ? (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex flex-col items-center py-8 text-center"
            >
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-accent text-accent-foreground">
                <Check className="h-6 w-6" />
              </div>
              <h3 className="mt-5 font-display text-3xl tracking-tight text-foreground">
                You're on the list
              </h3>
              <p className="mt-2 max-w-md text-muted-foreground">
                Tomorrow morning you'll get your first edition — the freshest roles in{" "}
                {roles.length ? roles.join(", ") : "your fields"}. Sign back in anytime to update
                your preferences.
              </p>
            </motion.div>
          ) : !user ? (
            <>
              <div className="max-w-xl">
                <h2 className="font-display text-4xl tracking-tight text-foreground md:text-5xl">
                  Get the edition in your inbox
                </h2>
                <p className="mt-3 text-muted-foreground">
                  Sign in with Google, pick your fields and city, and get one short email a day
                  with the freshest internships matched to you. Free, no spam, unsubscribe anytime.
                </p>
              </div>
              <div className="mt-8">
                <Button
                  onClick={handleSignIn}
                  disabled={signingIn}
                  className="rounded-full px-7 py-6 text-sm font-medium"
                >
                  {signingIn ? <Loader2 className="h-4 w-4 animate-spin" /> : "Continue with Google"}
                </Button>
                {signInError && (
                  <p className="mt-3 text-sm text-red-500">
                    Sign-in didn't go through — please try again.
                  </p>
                )}
              </div>
            </>
          ) : (
            <>
              <div className="max-w-xl">
                <h2 className="font-display text-4xl tracking-tight text-foreground md:text-5xl">
                  Get the edition in your inbox
                </h2>
                <p className="mt-3 text-muted-foreground">
                  Signed in as {user.email}. Pick your fields and city below.
                </p>
              </div>

              <form onSubmit={onSubmit} className="mt-8 space-y-6">
                <div>
                  <label className="mb-2 block text-sm font-medium text-foreground">
                    Fields you care about
                  </label>
                  <div className="flex flex-wrap gap-2">
                    {FIELDS.map((f) => (
                      <button
                        type="button"
                        key={f}
                        onClick={() => toggle(f)}
                        className={`rounded-full px-3.5 py-1.5 text-sm transition-colors ${
                          roles.includes(f)
                            ? "bg-foreground text-background"
                            : "border border-border bg-background text-muted-foreground hover:text-foreground"
                        }`}
                      >
                        {f}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <label htmlFor="alert-city" className="mb-2 block text-sm font-medium text-foreground">City</label>
                    <select
                      id="alert-city"
                      value={city}
                      onChange={(e) => setCity(e.target.value)}
                      className="w-full rounded-xl border border-border bg-background px-4 py-3 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring"
                    >
                      {CITIES.map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label htmlFor="alert-grad" className="mb-2 block text-sm font-medium text-foreground">
                      Graduating in
                    </label>
                    <select
                      id="alert-grad"
                      value={gradYear}
                      onChange={(e) => setGradYear(e.target.value)}
                      className="w-full rounded-xl border border-border bg-background px-4 py-3 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring"
                    >
                      {GRAD_YEARS.map((y) => (
                        <option key={y} value={y}>
                          {y}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <Button
                  type="submit"
                  disabled={status === "loading"}
                  className="rounded-full px-7 py-6 text-sm font-medium"
                >
                  {status === "loading" ? <Loader2 className="h-4 w-4 animate-spin" /> : "Save preferences"}
                </Button>

                {status === "error" && (
                  <p className="text-sm text-red-500">
                    Something went wrong saving your preferences — please try again.
                  </p>
                )}
              </form>
            </>
          )}
        </Reveal>
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Verify locally**

Run (from `rise-web/`): `npm run dev`. Scroll to the alerts section — expect
a "Continue with Google" button (signed out) and the existing card styling
preserved. Full sign-in verification (real popup, real Firestore write)
happens in Task 8 against the deployed site, since Google OAuth popups
require an authorized domain (localhost is authorized by default by
Firebase for testing, so this can also be checked now if convenient — not
required at this step).

- [ ] **Step 3: Commit**

```bash
git add rise-web/src/components/EmailAlerts.jsx
git commit -m "feat: replace email-capture form with Google Sign-In + Firestore preferences"
```

---

### Task 4: Firestore security rules

**Files:**
- Create: `firestore.rules` (repo root)
- Create: `firebase.json` (repo root)
- Create: `.firebaserc` (repo root)

**Interfaces:**
- Produces: the deployed Firestore rule set that Task 3's client writes and
  Task 7's Admin SDK reads operate under (Admin SDK bypasses these rules
  entirely — they only gate the client write from Task 3).

- [ ] **Step 1: Create the Firebase project config files**

Create `.firebaserc`:

```json
{
  "projects": {
    "default": "rise-internships-eb6d0"
  }
}
```

Create `firebase.json`:

```json
{
  "firestore": {
    "rules": "firestore.rules"
  }
}
```

- [ ] **Step 2: Write the security rules**

Create `firestore.rules`:

```
rules_version = '2';

service cloud.firestore {
  match /databases/{database}/documents {
    match /users/{uid} {
      // Only the signed-in owner may read or write their own doc — the
      // digest cron uses the Admin SDK, which bypasses these rules
      // entirely, so it never needs client read access here.
      allow read: if request.auth != null && request.auth.uid == uid;

      allow write: if request.auth != null
        && request.auth.uid == uid
        && request.resource.data.keys().hasOnly(
             ['email', 'roles', 'cities', 'gradYear', 'remote', 'updatedAt']
           )
        && request.resource.data.email is string
        && request.resource.data.email.size() < 200
        && request.resource.data.roles is list
        && request.resource.data.roles.size() <= 20
        && request.resource.data.cities is list
        && request.resource.data.cities.size() <= 20
        && request.resource.data.gradYear is string
        && request.resource.data.gradYear.size() < 20
        && request.resource.data.remote is bool
        && request.resource.data.updatedAt is timestamp;
    }
  }
}
```

- [ ] **Step 3: Deploy the rules**

Confirm with the user before running (this is a live change to the Firebase
project's security configuration):

Run (from repo root): `firebase deploy --only firestore:rules`
Expected: `✔  Deploy complete!` and a link to the rules in the Firebase
console.

- [ ] **Step 4: Verify in the console**

Open the Firebase console → Firestore Database → **Rules** tab and confirm
the deployed rule text matches what was written in Step 2.

- [ ] **Step 5: Commit**

```bash
git add .firebaserc firebase.json firestore.rules
git commit -m "feat: add Firestore security rules for users/{uid} preferences"
```

---

### Task 5: Remove the dead email-capture backend path

`EmailAlerts.jsx` no longer calls the backend at all (Task 3 writes directly
to Firestore) — the `/api/subscribe` route and its Resend-contact-upsert
logic are now dead code. Removing dead code rather than leaving it half-used
avoids two parallel, silently-diverging subscriber systems.

**Files:**
- Modify: `api/main.py` (remove the subscribe route and its model)
- Delete: `api/email_service.py`
- Modify: `rise-web/src/lib/api.js` (remove `subscribe()`)

**Interfaces:**
- No interfaces produced — this task only removes code nothing else in the
  codebase will call after Task 3 ships.

- [ ] **Step 1: Remove the route from api/main.py**

In `api/main.py`, remove:
- The `import email_service` line.
- The `SubscribePayload` class.
- The entire `@app.post("/api/subscribe", ...)` function.
- Change `from pydantic import BaseModel, EmailStr` to `from pydantic import BaseModel` (only `SubscribePayload` used `EmailStr`; leave `BaseModel` if anything else in the file still uses it — check before removing `BaseModel` too, since currently `SubscribePayload` was its only user, so after removing that class, remove the whole `from pydantic import ...` line entirely if `BaseModel` is now unused).

The result should leave `/api/listings`, `/api/stats`, and `/health` exactly
as they are today, with no import or route referencing subscriptions.

- [ ] **Step 2: Delete the now-unused email service module**

```bash
git rm api/email_service.py
```

- [ ] **Step 3: Remove the frontend subscribe() call**

In `rise-web/src/lib/api.js`, remove the `subscribe()` function entirely
(the `fetchListings`/`fetchStats` functions and the `getJSON` helper are
untouched — they're still used by the rest of the site).

- [ ] **Step 4: Verify**

Run: `pytest tests/ -v` — expect all tests still passing (none of the
removed code has direct test coverage, but this confirms nothing else in the
Python codebase imports `email_service`).

Run: `grep -rn "email_service\|subscribe" api/ rise-web/src/` — expect no
remaining references (aside from this plan/commit history).

- [ ] **Step 5: Commit**

```bash
git add api/main.py rise-web/src/lib/api.js
git rm api/email_service.py
git commit -m "refactor: remove dead /api/subscribe path (Firestore is now the single preferences store)"
```

---

### Task 6: Backend Firestore access — dependency, secret, and digest script rewrite

**Files:**
- Modify: `modal_app.py` (add `firebase-admin` to the pipeline image, add the
  `firebase-admin-key` secret to `daily_digest`)
- Modify: `requirements.txt` (root — add `firebase-admin` for local dev
  parity)
- Modify: `execution/send_daily_digest.py` (swap `fetch_contacts()`/`_prefs()`
  for Firestore; add per-user fault isolation)
- Create: `tests/test_digest_matching.py`

**Interfaces:**
- Consumes: the `firebase-admin-key` Modal secret (this task's Step 3).
- Produces: `execution/send_daily_digest.py`'s `main()` now reads
  subscribers from Firestore instead of Resend contacts — no other function
  signatures in that file change (`match_for(contact, listings)` still
  takes a plain dict-like `contact` and returns the same list shape;
  `build_html`/`send` are untouched).

- [ ] **Step 1: Write the failing test for the updated `_prefs()` shape**

Add to a new file `tests/test_digest_matching.py`:

```python
"""Unit tests for send_daily_digest.py's subscriber-matching logic, updated
for Firestore's native-list field shape (roles/cities are real lists, not
Resend's comma-joined strings)."""

import send_daily_digest as digest


class TestPrefs:
    def test_list_shaped_roles_and_cities(self):
        contact = {"roles": ["Software", "Data/AI"], "cities": ["Bangalore"]}
        roles, cities = digest._prefs(contact)
        assert roles == ["software", "data/ai"]
        assert cities == ["bangalore"]

    def test_missing_fields_default_empty(self):
        roles, cities = digest._prefs({})
        assert roles == []
        assert cities == []

    def test_non_list_fields_do_not_crash(self):
        # A malformed doc (e.g. written by a buggy client before the
        # Firestore rule validation existed) must not crash matching.
        roles, cities = digest._prefs({"roles": "not-a-list", "cities": None})
        assert roles == []
        assert cities == []


class TestMatchFor:
    def _listings(self):
        return [
            {"cluster": "Software", "title": "Backend Intern", "location": "Bangalore", "hoursAgo": 2},
            {"cluster": "Marketing", "title": "SEO Intern", "location": "Mumbai", "hoursAgo": 5},
        ]

    def test_matches_by_role_and_city(self):
        contact = {"roles": ["Software"], "cities": ["Bangalore"]}
        picks = digest.match_for(contact, self._listings())
        assert len(picks) == 1
        assert picks[0]["title"] == "Backend Intern"

    def test_no_prefs_returns_freshest(self):
        picks = digest.match_for({}, self._listings())
        assert len(picks) == 2

    def test_malformed_doc_falls_back_to_freshest_not_crash(self):
        contact = {"roles": "not-a-list", "cities": 12345}
        picks = digest.match_for(contact, self._listings())
        assert len(picks) == 2
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `pytest tests/test_digest_matching.py -v`
Expected: `test_non_list_fields_do_not_crash` and
`test_malformed_doc_falls_back_to_freshest_not_crash` FAIL (current
`_prefs()` does `str(data.get("roles", "")).split(",")`, which on a list
input produces garbage like `"['Software', 'Data/AI']"` split on commas,
not a crash but wrong output — and on `None`/non-string input inside
`match_for`'s `hay_role`/`hay_city` checks, the string-shaped assumption
breaks). The other tests may already coincidentally pass or fail depending
on current behavior — the point is confirming the new shape isn't yet
correctly handled.

- [ ] **Step 3: Rewrite `_prefs()` and `fetch_contacts()` in `execution/send_daily_digest.py`**

First, add `tempfile` to the existing top-of-file imports (currently
`import os`, `import html`, `import logging`, then `import requests`) — add
`import tempfile` alongside them, since the rewritten `fetch_contacts()`
below needs it.

Then replace the `fetch_contacts()` function (currently reading from Resend)
with a Firestore-backed version, and update `_prefs()` for the list-shaped
fields. Replace these two functions:

```python
def fetch_contacts() -> list[dict]:
    """Read all subscriber preference docs from Firestore's users/ collection."""
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
    except ImportError:
        log.error("firebase-admin not installed — cannot fetch subscribers.")
        return []

    if not firebase_admin._apps:
        cred_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "")
        if not cred_json:
            log.warning("FIREBASE_SERVICE_ACCOUNT_JSON not set — skipping (dry run).")
            return []
        # tempfile.gettempdir(), not a hardcoded "/tmp" — this runs both in
        # Modal (Linux) and locally (Windows, during manual verification).
        cred_path = os.path.join(tempfile.gettempdir(), "firebase-admin-key.json")
        with open(cred_path, "w", encoding="utf-8") as f:
            f.write(cred_json)
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)

    db = firestore.client()
    try:
        docs = db.collection("users").stream()
        return [doc.to_dict() for doc in docs]
    except Exception as e:
        log.error("Could not fetch Firestore subscribers: %s", e)
        return []


def _prefs(contact: dict) -> tuple[list[str], list[str]]:
    """Best-effort read of a subscriber's saved role/city preferences.
    Firestore stores roles/cities as real lists (unlike Resend's
    comma-joined custom fields) — tolerate a malformed doc rather than
    crash, since one bad record must not kill the whole digest run."""
    raw_roles = contact.get("roles")
    raw_cities = contact.get("cities")
    roles = [r.strip().lower() for r in raw_roles if isinstance(r, str) and r.strip()] if isinstance(raw_roles, list) else []
    cities = [c.strip().lower() for c in raw_cities if isinstance(c, str) and c.strip()] if isinstance(raw_cities, list) else []
    return roles, cities
```

Remove the old `RESEND_AUDIENCE` constant's usage in `fetch_contacts()`
(the `RESEND_AUDIENCE`/`RESEND_API_KEY` module-level constants stay — `send()`
still uses `RESEND_API_KEY` to actually send mail).

- [ ] **Step 4: Add per-user fault isolation to `main()`**

In `execution/send_daily_digest.py`'s `main()`, the subscriber loop currently
reads:

```python
    sent = 0
    for c in contacts:
        email = c.get("email")
        if not email:
            continue
        picks = match_for(c, listings)
        if not picks:
            continue
        name = (c.get("first_name") or "").strip()
        if send(email, build_html(name, picks), len(picks)):
            sent += 1
```

Replace it with a version where one bad record can't kill the whole run:

```python
    sent = 0
    for c in contacts:
        try:
            email = c.get("email")
            if not email:
                continue
            picks = match_for(c, listings)
            if not picks:
                continue
            name = (c.get("first_name") or "").strip()
            if send(email, build_html(name, picks), len(picks)):
                sent += 1
        except Exception as e:
            log.error("Skipping subscriber %s due to error: %s", c.get("email", "<unknown>"), e)
            continue
```

- [ ] **Step 5: Run the tests again to confirm they pass**

Run: `pytest tests/test_digest_matching.py -v`
Expected: all PASS.

Run: `pytest tests/ -v`
Expected: full suite passes (no regressions in existing tests).

- [ ] **Step 6: Add `firebase-admin` to the pipeline's dependencies**

In `modal_app.py`, add `"firebase-admin"` to the existing heavy `image`'s
`pip_install(...)` call (the same `image` variable `daily_digest` already
uses — do not create a new image, per Global Constraints).

In root `requirements.txt`, add a new line: `firebase-admin>=6.0.0` (matches
this file's existing loose `>=` pin style).

- [ ] **Step 7: Add the dedicated Modal secret to `daily_digest`**

In `modal_app.py`, find the `daily_digest` function's decorator:

```python
@app.function(
    image=image,
    secrets=[
        modal.Secret.from_name("internship-secrets"),
    ],
    timeout=900,
)
def daily_digest():
```

Change it to also include the new, separately-scoped secret:

```python
@app.function(
    image=image,
    secrets=[
        modal.Secret.from_name("internship-secrets"),
        modal.Secret.from_name("firebase-admin-key"),
    ],
    timeout=900,
)
def daily_digest():
```

Do **not** add `firebase-admin-key` to any other function (especially not
`run_now`, the public webhook) — this is the whole point of scoping it
separately.

- [ ] **Step 8: Create the Modal secret from the service-account key file**

Confirm with the user before running (creates a live, sensitive Modal
secret). The controller runs this directly — never delegate this step to a
subagent, since the file's content would then appear in that subagent's
context/transcript:

```bash
modal secret create firebase-admin-key FIREBASE_SERVICE_ACCOUNT_JSON="$(cat 'C:\Users\daksh\Downloads\rise-internships-eb6d0-firebase-adminsdk-fbsvc-911ec6ef7b.json')" --force
```

Expected: `Created a new secret 'firebase-admin-key' with the keys
'FIREBASE_SERVICE_ACCOUNT_JSON'` — confirm only the key *name* is printed,
never the value.

- [ ] **Step 9: Verify the file parses**

Run: `python -c "import ast; ast.parse(open('modal_app.py', encoding='utf-8').read())"`
Expected: no output (no syntax errors).

- [ ] **Step 10: Commit**

```bash
git add modal_app.py requirements.txt execution/send_daily_digest.py tests/test_digest_matching.py
git commit -m "feat: read digest subscribers from Firestore instead of Resend contacts"
```

---

### Task 7: Deploy and verify end-to-end

**Files:** none (operational task)

**Interfaces:**
- Consumes: everything from Tasks 1–6.

- [ ] **Step 1: Add Firebase env vars to Vercel**

Confirm with the user before running each (live production config change):

```bash
cd rise-web
vercel env add VITE_FIREBASE_API_KEY production
vercel env add VITE_FIREBASE_AUTH_DOMAIN production
vercel env add VITE_FIREBASE_PROJECT_ID production
vercel env add VITE_FIREBASE_STORAGE_BUCKET production
vercel env add VITE_FIREBASE_MESSAGING_SENDER_ID production
vercel env add VITE_FIREBASE_APP_ID production
```

(Use the exact values from Global Constraints when prompted for each.)

- [ ] **Step 2: Redeploy rise-web**

Confirm with the user before running:

```bash
vercel --prod
```

- [ ] **Step 3: Authorize the production domain for Google Sign-In**

In the Firebase console → Authentication → Settings → **Authorized
domains**, confirm `rise-web-kappa.vercel.app` (or the current production
domain) is listed. If not, add it — Google Sign-In's popup will otherwise
fail with `auth/unauthorized-domain` on the live site even though it works
on `localhost`.

- [ ] **Step 4: Redeploy the Modal app**

Confirm with the user before running:

```bash
MODAL_PROFILE=dakshinjain187 modal deploy modal_app.py
```

- [ ] **Step 5: Verify sign-in and Firestore write on the live site**

Using a real browser (chrome-devtools MCP or manual): navigate to the
production site, click "Continue with Google," complete the popup sign-in,
select fields/city/grad year, click "Save preferences," and confirm the
success state renders ("You're on the list").

Then check the Firebase console → Firestore Database → Data tab → `users`
collection → confirm a document exists keyed by the signed-in user's UID,
with the exact fields saved.

- [ ] **Step 6: Verify the digest script end-to-end**

Run locally (reads the live Firestore project via the same service-account
key, and the live Modal-hosted API for listings):

```bash
FIREBASE_SERVICE_ACCOUNT_JSON="$(cat 'C:\Users\daksh\Downloads\rise-internships-eb6d0-firebase-adminsdk-fbsvc-911ec6ef7b.json')" python execution/send_daily_digest.py
```

Expected: logs show at least one Firestore subscriber fetched (the test
account from Step 5), and — if `RESEND_API_KEY` is set — an actual digest
email sent to that account's address; without it, a dry-run log of the
matched listings for that subscriber.

- [ ] **Step 7: No commit for this task** — purely operational (env vars,
deploys, and a manual verification pass).

---

### Task 8: Update CLAUDE.md's architecture note

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:** none.

- [ ] **Step 1: Update the architecture description**

In `CLAUDE.md`, find the line:

> The Sheet is the **only** coupling between the two.

Change the surrounding paragraph to note the new second coupling point.
Replace:

```
The Sheet is the **only** coupling between the two systems. They share `GOOGLE_SHEET_ID`; the pipeline writes via OAuth (`credentials.json`/`token.json`), the API reads via a public API key (sheet must be "anyone with link can view").
```

with:

```
The Sheet is the primary coupling between the two systems, and Firestore is a second, narrower one: `rise-web` writes signed-in users' digest preferences directly to a `users/{uid}` Firestore collection (Firebase Auth + Firestore security rules), and the pipeline-side `daily_digest` cron (via `firebase-admin`, a separately-scoped Modal secret) reads that same collection to personalize each subscriber's email. They share `GOOGLE_SHEET_ID`; the pipeline writes via OAuth (`credentials.json`/`token.json`), the API reads via Google's keyless CSV export (the sheet must be "anyone with link can view").
```

(Note: this also corrects a pre-existing inaccuracy — `api/sheets.py` reads
via a keyless CSV export, not `GOOGLE_API_KEY`, which is unused.)

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: note Firestore as a second coupling point between pipeline and website"
```

---

## Definition of done for this plan

- `pytest tests/ -v` passes in full, including the new
  `tests/test_digest_matching.py`.
- A real Google sign-in on the live production site successfully creates a
  `users/{uid}` Firestore document with the expected fields.
- `execution/send_daily_digest.py`, run against the live Firestore project,
  fetches at least one real subscriber and correctly matches/sends (or
  dry-run logs) their digest.
- The old `/api/subscribe` route, `api/email_service.py`, and the frontend
  `subscribe()` call no longer exist anywhere in the codebase.
- `CLAUDE.md`'s architecture section accurately describes both coupling
  points.
