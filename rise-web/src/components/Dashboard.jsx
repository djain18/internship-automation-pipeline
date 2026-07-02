import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search,
  Bell,
  ChevronDown,
  ChevronRight,
  Home,
  Briefcase,
  MapPin,
  Code2,
  Palette,
  LineChart,
  Megaphone,
  ShieldCheck,
  Plus,
  MoreHorizontal,
  Check,
  X,
  Wallet,
  Users,
  PenTool,
  TrendingUp,
  Scale,
  Package,
  Settings,
  ArrowUpRight,
} from "lucide-react";
import { formatStipend, formatAge } from "@/lib/format";

// Map a cluster name (from api/sheets.py _infer_cluster) to a sidebar icon.
const CLUSTER_ICON = {
  Software: Code2,
  "Data/AI": LineChart,
  Product: Package,
  Design: Palette,
  Marketing: Megaphone,
  Finance: Wallet,
  "Business Dev": TrendingUp,
  HR: Users,
  Content: PenTool,
  Legal: Scale,
  Operations: Settings,
};

function SidebarItem({ icon: Icon, label, active, badge, chevron, onClick, dim }) {
  return (
    <button
      onClick={onClick}
      disabled={!onClick}
      className={`flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-sm transition-colors ${
        active
          ? "bg-secondary font-medium text-foreground"
          : dim
          ? "text-muted-foreground/70"
          : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground"
      } ${onClick ? "cursor-pointer" : "cursor-default"}`}
    >
      <Icon className="h-4 w-4 shrink-0" />
      <span className="flex-1 truncate">{label}</span>
      {badge != null && (
        <span className="rounded-full bg-foreground/10 px-1.5 py-0.5 text-[10px] font-medium text-foreground">
          {badge}
        </span>
      )}
      {chevron && <ChevronRight className="h-3.5 w-3.5" />}
    </button>
  );
}

function StatTile({ label, value, sub, tone }) {
  return (
    <div className="flex-1 basis-0 rounded-xl border border-border bg-background p-4">
      <div className="text-sm text-muted-foreground">{label}</div>
      <div className="mt-1.5 text-2xl font-semibold text-foreground">{value}</div>
      {sub && (
        <div
          className={`mt-1 text-xs font-medium ${
            tone === "red" ? "text-red-500" : "text-green-600"
          }`}
        >
          {sub}
        </div>
      )}
    </div>
  );
}

function TrendChart() {
  return (
    <svg viewBox="0 0 300 80" className="h-24 w-full" preserveAspectRatio="none">
      <defs>
        <linearGradient id="riseAreaFull" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="hsl(var(--accent))" stopOpacity="0.18" />
          <stop offset="100%" stopColor="hsl(var(--accent))" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path
        d="M0,62 C30,58 45,48 75,44 C105,40 120,30 150,28 C180,26 195,34 225,26 C255,18 270,16 300,12 L300,80 L0,80 Z"
        fill="url(#riseAreaFull)"
      />
      <path
        d="M0,62 C30,58 45,48 75,44 C105,40 120,30 150,28 C180,26 195,34 225,26 C255,18 270,16 300,12"
        fill="none"
        stroke="hsl(var(--accent))"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

export default function Dashboard({ open, onClose, stats, listings = [], onOpenListing }) {
  const [activeField, setActiveField] = useState("All");
  const [query, setQuery] = useState("");

  // Lock body scroll + Escape to close while open.
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);

  // Distinct clusters present in the live data, in a stable order.
  const clusters = useMemo(() => {
    const order = Object.keys(CLUSTER_ICON);
    const present = [...new Set(listings.map((l) => l.cluster).filter(Boolean))];
    return present.sort((a, b) => {
      const ia = order.indexOf(a), ib = order.indexOf(b);
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
    });
  }, [listings]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return listings.filter((l) => {
      if (activeField !== "All" && l.cluster !== activeField) return false;
      if (q) {
        const hay = `${l.title} ${l.org} ${(l.tags || []).join(" ")} ${l.location}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [listings, activeField, query]);

  const verified = stats?.verifiedToday ?? listings.length;
  const spiked = stats?.spikedToday ?? 0;
  const companies = new Set(filtered.map((l) => l.org).filter(Boolean)).size;
  const fields = new Set(listings.map((l) => l.cluster).filter(Boolean)).size;
  const recent = filtered.slice(0, 5);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[90] flex items-center justify-center bg-foreground/40 p-3 backdrop-blur-sm sm:p-6"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
        >
          <motion.div
            initial={{ opacity: 0, y: 24, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 24, scale: 0.98 }}
            transition={{ type: "spring", stiffness: 320, damping: 30 }}
            onClick={(e) => e.stopPropagation()}
            className="flex h-full max-h-[860px] w-full max-w-6xl flex-col overflow-hidden rounded-2xl border border-border bg-background shadow-2xl"
          >
            {/* Top bar */}
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <div className="flex items-center gap-2.5">
                <img src="/rise-mark.png" alt="" className="h-5 w-auto" />
                <span className="text-sm font-semibold">Rise</span>
                <span className="text-sm text-muted-foreground">/ tonight's edition</span>
                <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
              </div>

              <div className="mx-4 flex max-w-md flex-1 items-center gap-2 rounded-md border border-border bg-secondary/50 px-3 py-2">
                <Search className="h-4 w-4 text-muted-foreground" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search internships"
                  aria-label="Search internships"
                  className="w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
                />
                <span className="rounded border border-border bg-background px-1.5 text-[10px] text-muted-foreground">
                  esc
                </span>
              </div>

              <div className="flex items-center gap-3">
                <span className="hidden rounded-full bg-accent px-3 py-1.5 text-xs font-medium text-accent-foreground sm:inline-block">
                  Verified
                </span>
                <Bell className="h-4 w-4 text-muted-foreground" />
                <div className="flex h-7 w-7 items-center justify-center rounded-full bg-accent text-[11px] font-semibold text-accent-foreground">
                  JS
                </div>
                <button
                  onClick={onClose}
                  aria-label="Close dashboard"
                  className="ml-1 rounded-md p-1 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
                >
                  <X className="h-4.5 w-4.5" />
                </button>
              </div>
            </div>

            <div className="flex min-h-0 flex-1">
              {/* Sidebar */}
              <div className="hidden w-48 shrink-0 space-y-1 overflow-y-auto border-r border-border p-3 md:block">
                <SidebarItem
                  icon={Home}
                  label="Tonight"
                  active={activeField === "All"}
                  onClick={() => setActiveField("All")}
                />
                <SidebarItem
                  icon={Briefcase}
                  label="All roles"
                  badge={listings.length}
                  active={false}
                  onClick={() => setActiveField("All")}
                />
                {clusters.map((c) => (
                  <SidebarItem
                    key={c}
                    icon={CLUSTER_ICON[c] || Briefcase}
                    label={c}
                    active={activeField === c}
                    onClick={() => setActiveField(c)}
                  />
                ))}

                <div className="px-2.5 pb-1 pt-5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                  Pipeline
                </div>
                <SidebarItem icon={Search} label="Scraped" dim />
                <SidebarItem icon={ShieldCheck} label="Scam filter" dim />
                <SidebarItem icon={Check} label="Verified" dim />
                <SidebarItem icon={Bell} label="Daily email" dim />
              </div>

              {/* Main content */}
              <div className="min-w-0 flex-1 overflow-y-auto bg-secondary/30 p-5">
                <div className="flex items-center justify-between">
                  <div className="text-lg font-semibold">
                    {activeField === "All" ? "Welcome back 👋" : `${activeField} roles`}
                  </div>
                  <div className="text-sm text-muted-foreground">
                    {filtered.length} {filtered.length === 1 ? "role" : "roles"}
                  </div>
                </div>

                {/* Stat tiles */}
                <div className="mt-4 flex flex-wrap gap-3">
                  <StatTile label="Verified tonight" value={verified} sub="live now" />
                  <StatTile label="Companies hiring" value={companies || "—"} />
                  <StatTile label="Fields covered" value={fields || "—"} />
                  <StatTile
                    label="Scams filtered"
                    value={spiked ? `−${spiked}` : "—"}
                    sub="kept out"
                    tone="red"
                  />
                </div>

                {/* Trend + recent */}
                <div className="mt-4 grid gap-4 lg:grid-cols-2">
                  <div className="rounded-xl border border-border bg-background p-4">
                    <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
                      <span>Verified per night</span>
                      <Check className="h-3.5 w-3.5 text-accent" />
                    </div>
                    <div className="mt-1 text-2xl font-semibold">
                      {verified}
                      <span className="ml-1.5 text-sm text-muted-foreground">tonight</span>
                    </div>
                    <div className="mt-2 flex items-center gap-3 text-xs">
                      <span className="text-muted-foreground">Last 7 nights</span>
                      <span className="font-medium text-green-600">fresh daily</span>
                    </div>
                    <TrendChart />
                  </div>

                  <div className="rounded-xl border border-border bg-background p-4">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-foreground">Recent internships</span>
                      <div className="flex items-center gap-2 text-muted-foreground">
                        <Plus className="h-4 w-4" />
                        <MoreHorizontal className="h-4 w-4" />
                      </div>
                    </div>
                    <div className="mt-1">
                      {recent.length === 0 && (
                        <div className="py-6 text-center text-sm text-muted-foreground">
                          No roles match.
                        </div>
                      )}
                      {recent.map((l) => (
                        <button
                          key={l.id}
                          onClick={() => onOpenListing?.(l)}
                          className="group flex w-full items-center justify-between gap-2 rounded-lg px-2 py-2 text-left transition-colors hover:bg-secondary"
                        >
                          <div className="min-w-0">
                            <div className="truncate text-sm font-medium text-foreground">{l.org}</div>
                            <div className="truncate text-xs text-muted-foreground">{l.title}</div>
                          </div>
                          <div className="ml-2 shrink-0 text-right">
                            <div className="text-xs text-muted-foreground">{l.location}</div>
                            <div className="text-sm font-medium text-foreground">
                              {formatStipend(l.stipend)}
                            </div>
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Verified roles table */}
                <div className="mt-4 rounded-xl border border-border bg-background p-4">
                  <div className="text-sm font-medium text-foreground">
                    {activeField === "All" ? "Verified roles" : `Verified ${activeField} roles`}
                  </div>
                  <div className="mt-2 overflow-x-auto">
                    <table className="w-full text-left">
                      <thead>
                        <tr className="border-b border-border text-xs text-muted-foreground">
                          <th className="pb-2 pr-2 font-normal">Company</th>
                          <th className="pb-2 pr-2 font-normal">Role</th>
                          <th className="pb-2 pr-2 font-normal">Location</th>
                          <th className="pb-2 pr-2 font-normal">Posted</th>
                          <th className="pb-2 font-normal">Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filtered.map((l) => (
                          <tr
                            key={`row-${l.id}`}
                            onClick={() => onOpenListing?.(l)}
                            className="cursor-pointer border-b border-border/50 text-sm transition-colors last:border-0 hover:bg-secondary"
                          >
                            <td className="py-2.5 pr-2 font-medium text-foreground">
                              <span className="inline-flex items-center gap-1.5">
                                {l.org}
                                <ArrowUpRight className="h-3 w-3 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
                              </span>
                            </td>
                            <td className="py-2.5 pr-2 text-muted-foreground">{l.title}</td>
                            <td className="py-2.5 pr-2 text-muted-foreground">{l.location}</td>
                            <td className="py-2.5 pr-2 text-muted-foreground">{formatAge(l.hoursAgo)}</td>
                            <td className="py-2.5">
                              <span className="inline-flex items-center gap-1 rounded-full bg-green-100 px-2 py-0.5 text-[11px] font-medium text-green-700">
                                <span className="h-1 w-1 rounded-full bg-green-500" />
                                Verified
                              </span>
                            </td>
                          </tr>
                        ))}
                        {filtered.length === 0 && (
                          <tr>
                            <td colSpan={5} className="py-8 text-center text-sm text-muted-foreground">
                              No roles match your filters.
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
