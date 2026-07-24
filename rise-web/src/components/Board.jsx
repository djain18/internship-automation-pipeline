import { useMemo, useState } from "react";
import { Search, SlidersHorizontal, LayoutGrid, List as ListIcon } from "lucide-react";
import InternshipCard from "./InternshipCard";
import InternshipRow from "./InternshipRow";
import Reveal from "./Reveal";

const TYPES = ["Onsite", "Hybrid", "Remote"];
const SORTS = [
  { id: "fresh", label: "Freshest" },
  { id: "stipend", label: "Highest stipend" },
  { id: "score", label: "Best match" },
];

const selectClass =
  "rounded-md border border-border bg-background px-3.5 py-2 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring";

function uniq(arr) {
  return [...new Set(arr.filter(Boolean))];
}

export default function Board({ listings = [], loading, onOpen }) {
  const [query, setQuery] = useState("");
  const [field, setField] = useState("All");
  const [location, setLocation] = useState("All");
  const [type, setType] = useState(null);
  const [sort, setSort] = useState("fresh");
  const [view, setView] = useState("list");
  const [filtersOpen, setFiltersOpen] = useState(false);

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

  const activeFilterCount = (field !== "All" ? 1 : 0) + (location !== "All" ? 1 : 0) + (type ? 1 : 0);

  return (
    <section id="board" className="mx-auto w-full max-w-6xl px-6 pb-20 pt-6 md:px-10">
      <Reveal>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="font-display text-3xl tracking-tight text-foreground md:text-4xl">
            Tonight's board
          </h1>
          <span className="text-sm tabular-nums text-muted-foreground">
            {loading ? "Loading…" : `${results.length} internships`}
          </span>
        </div>
      </Reveal>

      {/* Toolbar */}
      <div className="mt-5 flex flex-col gap-3 border-y border-border py-4 sm:flex-row sm:items-center">
        <div className="flex flex-1 items-center gap-2 rounded-md border border-border bg-background px-3.5 py-2">
          <Search className="h-4 w-4 shrink-0 text-muted-foreground" />
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
            value={sort}
            onChange={(e) => setSort(e.target.value)}
            aria-label="Sort internships"
            className={selectClass}
          >
            {SORTS.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>

          <div className="flex items-center rounded-md border border-border p-0.5">
            <button
              type="button"
              onClick={() => setView("list")}
              aria-label="List view"
              aria-pressed={view === "list"}
              className={`flex h-8 w-8 items-center justify-center rounded ${
                view === "list" ? "bg-foreground text-background" : "text-muted-foreground"
              }`}
            >
              <ListIcon className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => setView("grid")}
              aria-label="Grid view"
              aria-pressed={view === "grid"}
              className={`flex h-8 w-8 items-center justify-center rounded ${
                view === "grid" ? "bg-foreground text-background" : "text-muted-foreground"
              }`}
            >
              <LayoutGrid className="h-4 w-4" />
            </button>
          </div>

          <button
            type="button"
            onClick={() => setFiltersOpen((o) => !o)}
            className="flex items-center gap-1.5 rounded-md border border-border px-3.5 py-2 text-sm text-foreground md:hidden"
          >
            <SlidersHorizontal className="h-4 w-4" />
            Filters
            {activeFilterCount > 0 && <span className="tabular-nums">({activeFilterCount})</span>}
          </button>
        </div>
      </div>

      {/* Filters — two clearly separate axes: field, then mode + location */}
      <div className={`${filtersOpen ? "block" : "hidden"} mt-4 space-y-4 md:block`}>
        <div>
          <div className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Field
          </div>
          <div className="flex flex-wrap gap-2">
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
          </div>
        </div>

        <div className="flex flex-wrap items-end gap-6">
          <div>
            <div className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Work mode
            </div>
            <div className="inline-flex items-center rounded-md border border-border p-0.5">
              <button
                onClick={() => setType(null)}
                className={`rounded px-3 py-1.5 text-sm transition-colors ${
                  !type ? "bg-foreground text-background" : "text-muted-foreground hover:text-foreground"
                }`}
              >
                All
              </button>
              {TYPES.map((t) => (
                <button
                  key={t}
                  onClick={() => setType(t)}
                  className={`rounded px-3 py-1.5 text-sm transition-colors ${
                    type === t ? "bg-foreground text-background" : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          <div>
            <div className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Location
            </div>
            <select
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              aria-label="Filter by location"
              className={selectClass}
            >
              {locations.map((l) => (
                <option key={l} value={l}>
                  {l === "All" ? "All locations" : l}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Results */}
      {results.length > 0 ? (
        view === "list" ? (
          <div className="mt-8 border-t border-border">
            {results.map((l) => (
              <InternshipRow key={l.id} listing={l} onOpen={onOpen} />
            ))}
          </div>
        ) : (
          <div className="mt-8 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {results.map((l, i) => (
              <Reveal key={l.id} delay={(i % 3) * 0.05} className="h-full">
                <InternshipCard listing={l} onOpen={onOpen} />
              </Reveal>
            ))}
          </div>
        )
      ) : (
        <div className="mt-16 border border-dashed border-border py-20 text-center">
          <p className="font-display text-2xl text-foreground">No matches</p>
          <p className="mt-2 text-sm text-muted-foreground">
            Try clearing a filter or searching a different field.
          </p>
        </div>
      )}
    </section>
  );
}
