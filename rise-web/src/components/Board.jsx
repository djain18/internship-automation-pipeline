import { useMemo, useState } from "react";
import { Search, SlidersHorizontal } from "lucide-react";
import InternshipCard from "./InternshipCard";
import Reveal from "./Reveal";

const TYPES = ["Remote", "Hybrid", "Onsite"];
const SORTS = [
  { id: "fresh", label: "Freshest" },
  { id: "stipend", label: "Highest stipend" },
  { id: "score", label: "Best match" },
];

function uniq(arr) {
  return [...new Set(arr.filter(Boolean))];
}

export default function Board({ listings = [], loading, onOpen }) {
  const [query, setQuery] = useState("");
  const [field, setField] = useState("All");
  const [location, setLocation] = useState("All");
  const [type, setType] = useState(null);
  const [sort, setSort] = useState("fresh");

  const fields = useMemo(
    () => ["All", ...uniq(listings.map((l) => l.cluster)).sort()],
    [listings]
  );
  const locations = useMemo(
    () => ["All", ...uniq(listings.map((l) => l.location)).sort()],
    [listings]
  );

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    let out = listings.filter((l) => {
      if (field !== "All" && l.cluster !== field) return false;
      if (location !== "All" && l.location !== location) return false;
      if (type && l.type !== type) return false;
      if (q) {
        const hay = `${l.title} ${l.org} ${(l.tags || []).join(" ")}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
    out = [...out].sort((a, b) => {
      if (sort === "stipend") return (b.stipend || 0) - (a.stipend || 0);
      if (sort === "score") return (b.score || 0) - (a.score || 0);
      return (a.hoursAgo || 0) - (b.hoursAgo || 0); // freshest
    });
    return out;
  }, [listings, query, field, location, type, sort]);

  return (
    <section id="board" className="mx-auto w-full max-w-6xl scroll-mt-20 px-6 py-20 md:px-10">
      <Reveal>
        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <h2 className="font-display text-4xl tracking-tight text-foreground md:text-5xl">
              Tonight's board
            </h2>
            <p className="mt-2 max-w-xl text-muted-foreground">
              Every role here was posted in the last day, checked for scams, and confirmed
              open to students in India.
            </p>
          </div>
          <div className="text-sm text-muted-foreground">
            {loading ? "Loading…" : `${results.length} internships`}
          </div>
        </div>
      </Reveal>

      {/* Controls */}
      <div className="mt-8 space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row">
          <div className="flex flex-1 items-center gap-2 rounded-full border border-border bg-background px-4 py-2.5">
            <Search className="h-4 w-4 text-muted-foreground" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search role, company, or skill…"
              aria-label="Search internships"
              className="w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
            />
          </div>
          <div className="flex items-center gap-2">
            <select
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              aria-label="Filter by location"
              className="rounded-full border border-border bg-background px-4 py-2.5 text-sm text-foreground outline-none"
            >
              {locations.map((l) => (
                <option key={l} value={l}>
                  {l === "All" ? "All locations" : l}
                </option>
              ))}
            </select>
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value)}
              aria-label="Sort internships"
              className="rounded-full border border-border bg-background px-4 py-2.5 text-sm text-foreground outline-none"
            >
              {SORTS.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Field chips + type toggle */}
        <div className="flex flex-wrap items-center gap-2">
          {fields.map((f) => (
            <button
              key={f}
              onClick={() => setField(f)}
              className={`rounded-full px-3.5 py-1.5 text-sm transition-colors ${
                field === f
                  ? "bg-foreground text-background"
                  : "border border-border bg-background text-muted-foreground hover:text-foreground"
              }`}
            >
              {f}
            </button>
          ))}
          <span className="mx-1 hidden h-5 w-px bg-border sm:inline-block" />
          <SlidersHorizontal className="hidden h-4 w-4 text-muted-foreground sm:inline-block" />
          {TYPES.map((t) => (
            <button
              key={t}
              onClick={() => setType(type === t ? null : t)}
              className={`rounded-full px-3 py-1.5 text-sm transition-colors ${
                type === t
                  ? "bg-accent text-accent-foreground"
                  : "border border-border bg-background text-muted-foreground hover:text-foreground"
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      {/* Grid */}
      {results.length > 0 ? (
        <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {results.map((l, i) => (
            <Reveal key={l.id} delay={(i % 3) * 0.07} className="h-full">
              <InternshipCard listing={l} onOpen={onOpen} />
            </Reveal>
          ))}
        </div>
      ) : (
        <div className="mt-16 rounded-2xl border border-dashed border-border py-20 text-center">
          <p className="font-display text-2xl text-foreground">No matches</p>
          <p className="mt-2 text-sm text-muted-foreground">
            Try clearing a filter or searching a different field.
          </p>
        </div>
      )}
    </section>
  );
}
