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
