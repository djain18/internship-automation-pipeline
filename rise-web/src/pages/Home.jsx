import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import Hero from "../components/Hero";
import InternshipCard from "../components/InternshipCard";
import InternshipRow from "../components/InternshipRow";
import HowItWorks from "../components/HowItWorks";
import EmailAlerts from "../components/EmailAlerts";
import FAQ from "../components/FAQ";
import Reveal from "../components/Reveal";

export default function Home({ listings = [], stats, loading, onOpen, onOpenDashboard }) {
  // Listings arrive freshest-first from the API — the very first is the "lead"
  // story, the rest read as a ruled index rather than six duplicate tiles.
  const [lead, ...rest] = listings;
  const index = rest.slice(0, 5);

  return (
    <>
      <Hero stats={stats} listings={listings} onOpenDashboard={onOpenDashboard} />

      {/* Tonight's front page → the full board lives at /internships */}
      <section className="border-t border-border">
        <div className="mx-auto w-full max-w-3xl px-6 py-20 md:px-10">
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
                className="inline-flex shrink-0 items-center gap-1.5 text-sm font-medium text-foreground"
              >
                See all internships
                <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
          </Reveal>

          {loading ? (
            <div className="mt-10 text-sm text-muted-foreground">Loading tonight's roles…</div>
          ) : lead ? (
            <>
              <Reveal delay={0.05} className="mt-10">
                <InternshipCard listing={lead} onOpen={onOpen} featured />
              </Reveal>
              {index.length > 0 && (
                <Reveal delay={0.1} className="mt-2 border-t border-border">
                  {index.map((l) => (
                    <InternshipRow key={l.id} listing={l} onOpen={onOpen} />
                  ))}
                </Reveal>
              )}
            </>
          ) : (
            <div className="mt-10 text-sm text-muted-foreground">No roles available right now.</div>
          )}
        </div>
      </section>

      <HowItWorks stats={stats} />
      <EmailAlerts />
      <FAQ />
    </>
  );
}
