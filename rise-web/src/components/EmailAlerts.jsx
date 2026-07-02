import { useState } from "react";
import { motion } from "framer-motion";
import { Check, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { subscribe } from "@/lib/api";
import Reveal from "./Reveal";

const FIELDS = [
  "Software", "Data/AI", "Design", "Product", "Marketing",
  "Finance", "Business Dev", "HR", "Content", "Operations",
];
const CITIES = ["Bangalore", "Mumbai", "Delhi NCR", "Hyderabad", "Pune", "Chennai", "Remote"];
const GRAD_YEARS = ["2026", "2027", "2028", "2029"];

export default function EmailAlerts() {
  const [email, setEmail] = useState("");
  const [roles, setRoles] = useState([]);
  const [city, setCity] = useState("Bangalore");
  const [gradYear, setGradYear] = useState("2027");
  const [status, setStatus] = useState("idle"); // idle | loading | done | error

  const toggle = (f) =>
    setRoles((r) => (r.includes(f) ? r.filter((x) => x !== f) : [...r, f]));

  async function onSubmit(e) {
    e.preventDefault();
    if (!email.trim()) return;
    setStatus("loading");
    try {
      await subscribe({
        email: email.trim(),
        roles,
        cities: [city],
        remote: city === "Remote",
        gradYear,
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
                {roles.length ? roles.join(", ") : "your fields"}. One click unsubscribes, any time.
              </p>
            </motion.div>
          ) : (
            <>
              <div className="max-w-xl">
                <h2 className="font-display text-4xl tracking-tight text-foreground md:text-5xl">
                  Get the edition in your inbox
                </h2>
                <p className="mt-3 text-muted-foreground">
                  One short email a day with the freshest internships matched to your fields
                  and city. Free, no spam, unsubscribe anytime.
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

                <div className="flex flex-col gap-3 sm:flex-row">
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@college.edu"
                    aria-label="Your email address"
                    className="flex-1 rounded-full border border-border bg-background px-5 py-3 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring"
                  />
                  <Button
                    type="submit"
                    disabled={status === "loading"}
                    className="rounded-full px-7 py-6 text-sm font-medium"
                  >
                    {status === "loading" ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      "Subscribe free"
                    )}
                  </Button>
                </div>

                {status === "error" && (
                  <p className="text-sm text-red-500">
                    Something went wrong — please check your email and try again.
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
