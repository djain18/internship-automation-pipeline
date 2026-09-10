import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Check, Loader2 } from "lucide-react";
import { doc, getDoc, setDoc, serverTimestamp } from "firebase/firestore";
import { Button } from "@/components/ui/button";
import { db } from "@/lib/firebase";
import { useAuth } from "@/lib/AuthContext";
import Reveal from "./Reveal";

const FIELDS = [
  "Software", "Data/AI", "AI Automation", "Design", "Product", "Marketing",
  "Finance", "Business Dev", "Founder's Office", "Forward Deployed",
  "HR", "Content", "Operations",
];
const CITIES = ["Bangalore", "Mumbai", "Delhi NCR", "Hyderabad", "Pune", "Chennai", "Remote"];
const GRAD_YEARS = ["2026", "2027", "2028", "2029"];

// A quiet, static preview of what the email actually looks like — replaces a
// decorative color panel with the one thing that's genuinely persuasive here.
function EditionPreview() {
  return (
    <div className="rounded-lg border border-ink-foreground/15 bg-ink-foreground/[0.03] p-6">
      <div className="flex items-center justify-between border-b border-ink-foreground/15 pb-4">
        <span className="font-display text-xl italic tracking-tight text-ink-foreground">Rise</span>
        <span className="text-xs uppercase tracking-widest text-ink-foreground/50">
          Tonight's edition
        </span>
      </div>
      <div className="mt-4 space-y-4">
        {[
          { role: "Frontend Developer Intern", org: "Razorpay · Bangalore", pay: "₹40K/mo" },
          { role: "Product Management Intern", org: "Groww · Bangalore", pay: "₹45K/mo" },
        ].map((r) => (
          <div key={r.role} className="flex items-start justify-between gap-4 border-b border-ink-foreground/10 pb-4 last:border-b-0 last:pb-0">
            <div className="min-w-0">
              <div className="truncate text-sm font-medium text-ink-foreground">{r.role}</div>
              <div className="mt-0.5 text-xs text-ink-foreground/50">{r.org}</div>
            </div>
            <div className="shrink-0 text-xs tabular-nums text-ink-foreground/70">{r.pay}</div>
          </div>
        ))}
      </div>
      <p className="mt-4 text-xs leading-relaxed text-ink-foreground/40">
        One email each day, matched to the fields and city selected below.
      </p>
    </div>
  );
}

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
    <section id="alerts" className="relative scroll-mt-20 overflow-hidden border-t border-border bg-ink text-ink-foreground">
      {/* The same treeline from the hero, now at night — a glimpse, not a repeat. */}
      <div
        className="pointer-events-none absolute inset-x-0 bottom-0 h-2/3 bg-cover bg-[position:right_bottom]"
        style={{
          backgroundImage: "url(/hero-still.jpeg)",
          filter: "grayscale(0.5) brightness(0.55) contrast(1.05)",
          maskImage: "linear-gradient(to top, black, transparent), linear-gradient(to left, black 15%, transparent 65%)",
          maskComposite: "intersect",
          WebkitMaskImage:
            "linear-gradient(to top, black, transparent), linear-gradient(to left, black 15%, transparent 65%)",
          WebkitMaskComposite: "source-in",
        }}
      />
      <div className="relative mx-auto max-w-5xl px-6 py-20 md:px-10">
        <Reveal className="grid gap-12 md:grid-cols-[1.2fr_1fr] md:gap-16">
          <div>
            {status === "done" ? (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
              >
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-accent text-accent-foreground">
                  <Check className="h-5 w-5" />
                </div>
                <h2 className="mt-5 font-display text-4xl tracking-tight text-ink-foreground md:text-5xl">
                  Preferences saved
                </h2>
                <p className="mt-3 max-w-md text-ink-foreground/60">
                  The first email will arrive tomorrow morning with the newest roles in{" "}
                  {roles.length ? roles.join(", ") : "the selected fields"}. Sign in at any time
                  to update these preferences.
                </p>
              </motion.div>
            ) : !user ? (
              <>
                <h2 className="font-display text-4xl tracking-tight text-ink-foreground md:text-5xl">
                  Receive the daily edition by email
                </h2>
                <p className="mt-3 max-w-md text-ink-foreground/60">
                  Sign in with Google, select fields and a city, and receive one short email
                  each day with internships matched to those preferences. Free, with no
                  spam, and unsubscribe at any time.
                </p>
                <div className="mt-8">
                  <Button
                    onClick={handleSignIn}
                    disabled={signingIn}
                    className="rounded-full bg-ink-foreground px-7 py-6 text-sm font-medium text-ink hover:bg-ink-foreground/90"
                  >
                    {signingIn ? <Loader2 className="h-4 w-4 animate-spin" /> : "Continue with Google"}
                  </Button>
                  {signInError && (
                    <p className="mt-3 text-sm text-red-400">
                      Sign-in was not completed. Please try again.
                    </p>
                  )}
                </div>
              </>
            ) : (
              <>
                <h2 className="font-display text-4xl tracking-tight text-ink-foreground md:text-5xl">
                  Receive the daily edition by email
                </h2>
                <p className="mt-3 text-ink-foreground/60">
                  Signed in as {user.email}. Select fields and a city below.
                </p>

                <form onSubmit={onSubmit} className="mt-8 space-y-6">
                  <div>
                    <label className="mb-2 block text-sm font-medium text-ink-foreground">
                      Fields of interest
                    </label>
                    <div className="flex flex-wrap gap-2">
                      {FIELDS.map((f) => (
                        <button
                          type="button"
                          key={f}
                          onClick={() => toggle(f)}
                          className={`rounded-full px-3.5 py-1.5 text-sm transition-colors ${
                            roles.includes(f)
                              ? "bg-ink-foreground text-ink"
                              : "border border-ink-foreground/20 text-ink-foreground/60 hover:text-ink-foreground"
                          }`}
                        >
                          {f}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="grid gap-4 sm:grid-cols-2">
                    <div>
                      <label htmlFor="alert-city" className="mb-2 block text-sm font-medium text-ink-foreground">City</label>
                      <select
                        id="alert-city"
                        value={city}
                        onChange={(e) => setCity(e.target.value)}
                        className="w-full rounded-md border border-ink-foreground/20 bg-transparent px-4 py-3 text-sm text-ink-foreground outline-none focus:ring-2 focus:ring-ink-foreground/30"
                      >
                        {CITIES.map((c) => (
                          <option key={c} value={c} className="text-foreground">
                            {c}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label htmlFor="alert-grad" className="mb-2 block text-sm font-medium text-ink-foreground">
                        Graduating in
                      </label>
                      <select
                        id="alert-grad"
                        value={gradYear}
                        onChange={(e) => setGradYear(e.target.value)}
                        className="w-full rounded-md border border-ink-foreground/20 bg-transparent px-4 py-3 text-sm text-ink-foreground outline-none focus:ring-2 focus:ring-ink-foreground/30"
                      >
                        {GRAD_YEARS.map((y) => (
                          <option key={y} value={y} className="text-foreground">
                            {y}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <Button
                    type="submit"
                    disabled={status === "loading"}
                    className="rounded-full bg-ink-foreground px-7 py-6 text-sm font-medium text-ink hover:bg-ink-foreground/90"
                  >
                    {status === "loading" ? <Loader2 className="h-4 w-4 animate-spin" /> : "Save preferences"}
                  </Button>

                  {status === "error" && (
                    <p className="text-sm text-red-400">
                      Preferences could not be saved. Please try again.
                    </p>
                  )}
                </form>
              </>
            )}
          </div>

          <div className="hidden md:block">
            <EditionPreview />
          </div>
        </Reveal>
      </div>
    </section>
  );
}
