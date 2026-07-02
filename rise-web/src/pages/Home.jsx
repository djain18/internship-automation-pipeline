import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import Hero from "../components/Hero";
import InternshipCard from "../components/InternshipCard";
import EmailAlerts from "../components/EmailAlerts";
import Reveal from "../components/Reveal";

export default function Home({ listings = [], stats, loading, onOpen, onOpenDashboard }) {
  // Listings arrive freshest-first from the API; show the top few as a teaser.
  const teaser = listings.slice(0, 6);

  return (
    <>
      <Hero stats={stats} listings={listings} onOpenDashboard={onOpenDashboard} />

      {/* Freshest roles teaser → full board lives at /internships */}
      <section className="mx-auto w-full max-w-6xl px-6 py-20 md:px-10">
        <Reveal>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <span className="text-sm font-medium uppercase tracking-widest text-muted-foreground">
                Fresh tonight
              </span>
              <h2 className="mt-2 font-display text-4xl tracking-tight text-foreground md:text-5xl">
                The latest verified roles
              </h2>
              <p className="mt-2 max-w-xl text-muted-foreground">
                A peek at tonight's board — every role posted in the last day, scam-checked
                and open to students in India.
              </p>
            </div>
            <Link
              to="/internships"
              className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-foreground px-5 py-2.5 text-sm font-medium text-background transition-transform hover:-translate-y-0.5"
            >
              See all internships
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </Reveal>

        {loading ? (
          <div className="mt-10 text-sm text-muted-foreground">Loading tonight's roles…</div>
        ) : teaser.length > 0 ? (
          <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {teaser.map((l, i) => (
              <Reveal key={l.id} delay={(i % 3) * 0.07} className="h-full">
                <InternshipCard listing={l} onOpen={onOpen} />
              </Reveal>
            ))}
          </div>
        ) : (
          <div className="mt-10 text-sm text-muted-foreground">No roles available right now.</div>
        )}

        <div className="mt-10 text-center sm:hidden">
          <Link
            to="/internships"
            className="inline-flex items-center gap-1.5 text-sm font-medium text-foreground"
          >
            See all internships
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </section>

      <EmailAlerts />
    </>
  );
}
