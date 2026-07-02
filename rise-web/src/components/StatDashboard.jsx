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
} from "lucide-react";
import { formatStipend } from "@/lib/format";

function SidebarItem({ icon: Icon, label, active, badge, chevron }) {
  return (
    <div
      className={`flex items-center gap-2 rounded-md px-2 py-1.5 ${
        active ? "bg-secondary text-foreground" : "text-muted-foreground"
      }`}
    >
      <Icon className="h-3.5 w-3.5" />
      <span className="flex-1">{label}</span>
      {badge && (
        <span className="rounded-full bg-foreground/10 px-1.5 text-[9px] font-medium text-foreground">
          {badge}
        </span>
      )}
      {chevron && <ChevronRight className="h-3 w-3" />}
    </div>
  );
}

function StatTile({ label, value, sub, tone }) {
  return (
    <div className="flex-1 basis-0 rounded-xl border border-border bg-background p-3">
      <div className="text-muted-foreground">{label}</div>
      <div className="mt-1 text-lg font-semibold text-foreground">{value}</div>
      {sub && (
        <div
          className={`mt-0.5 text-[10px] font-medium ${
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
  // Verified-per-night trend — hand-crafted cubic Bézier area chart.
  return (
    <svg viewBox="0 0 300 80" className="h-20 w-full" preserveAspectRatio="none">
      <defs>
        <linearGradient id="riseArea" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="hsl(var(--accent))" stopOpacity="0.15" />
          <stop offset="100%" stopColor="hsl(var(--accent))" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path
        d="M0,62 C30,58 45,48 75,44 C105,40 120,30 150,28 C180,26 195,34 225,26 C255,18 270,16 300,12 L300,80 L0,80 Z"
        fill="url(#riseArea)"
      />
      <path
        d="M0,62 C30,58 45,48 75,44 C105,40 120,30 150,28 C180,26 195,34 225,26 C255,18 270,16 300,12"
        fill="none"
        stroke="hsl(var(--accent))"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

export default function StatDashboard({ stats, listings = [] }) {
  const verified = stats?.verifiedToday ?? listings.length;
  const spiked = stats?.spikedToday ?? 0;
  const companies = new Set(listings.map((l) => l.org).filter(Boolean)).size;
  const fields = new Set(listings.map((l) => l.cluster).filter(Boolean)).size;
  const recent = listings.slice(0, 4);

  return (
    <div className="select-none pointer-events-none rounded-xl overflow-hidden bg-background text-[11px] text-foreground">
      {/* Top bar */}
      <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
        <div className="flex items-center gap-2">
          <img src="/rise-mark.png" alt="" className="h-3.5 w-auto" />
          <span className="font-semibold">Rise</span>
          <span className="text-muted-foreground">/ tonight's edition</span>
          <ChevronDown className="h-3 w-3 text-muted-foreground" />
        </div>

        <div className="mx-4 flex max-w-xs flex-1 items-center gap-2 rounded-md border border-border bg-secondary/50 px-2.5 py-1.5">
          <Search className="h-3 w-3 text-muted-foreground" />
          <span className="flex-1 text-muted-foreground">Search internships</span>
          <span className="rounded border border-border bg-background px-1 text-[9px] text-muted-foreground">
            ⌘K
          </span>
        </div>

        <div className="flex items-center gap-3">
          <span className="rounded-full bg-accent px-3 py-1.5 text-[10px] font-medium text-accent-foreground">
            Verified
          </span>
          <Bell className="h-3.5 w-3.5 text-muted-foreground" />
          <div className="flex h-6 w-6 items-center justify-center rounded-full bg-accent text-[9px] font-semibold text-accent-foreground">
            JS
          </div>
        </div>
      </div>

      <div className="flex">
        {/* Sidebar */}
        <div className="w-40 shrink-0 space-y-0.5 border-r border-border p-3">
          <SidebarItem icon={Home} label="Tonight" active />
          <SidebarItem icon={Briefcase} label="All roles" badge={String(verified)} />
          <SidebarItem icon={Code2} label="Software" />
          <SidebarItem icon={LineChart} label="Data / AI" />
          <SidebarItem icon={Palette} label="Design" chevron />
          <SidebarItem icon={Megaphone} label="Marketing" />
          <SidebarItem icon={MapPin} label="Locations" chevron />

          <div className="px-2 pb-1 pt-4 text-[9px] font-medium uppercase tracking-wider text-muted-foreground">
            Pipeline
          </div>
          <SidebarItem icon={Search} label="Scraped" />
          <SidebarItem icon={ShieldCheck} label="Scam filter" />
          <SidebarItem icon={Check} label="Verified" />
          <SidebarItem icon={Bell} label="Daily email" />
        </div>

        {/* Main content */}
        <div className="flex-1 bg-secondary/30 p-4">
          <div className="text-sm font-semibold">Welcome back 👋</div>

          {/* Stat tiles */}
          <div className="mt-3 flex gap-3">
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
          <div className="mt-4 flex gap-4">
            <div className="flex-1 basis-0 rounded-xl border border-border bg-background p-4">
              <div className="flex items-center gap-1.5 text-muted-foreground">
                <span>Verified per night</span>
                <Check className="h-3 w-3 text-accent" />
              </div>
              <div className="mt-1 text-xl font-semibold">
                {verified}
                <span className="ml-1 text-xs text-muted-foreground">tonight</span>
              </div>
              <div className="mt-2 flex items-center gap-3 text-[10px]">
                <span className="text-muted-foreground">Last 7 nights</span>
                <span className="font-medium text-green-600">fresh daily</span>
              </div>
              <TrendChart />
            </div>

            <div className="flex-1 basis-0 rounded-xl border border-border bg-background p-4">
              <div className="flex items-center justify-between">
                <span className="font-medium text-foreground">Recent internships</span>
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Plus className="h-3 w-3" />
                  <MoreHorizontal className="h-3 w-3" />
                </div>
              </div>
              <div className="mt-1">
                {recent.map((l) => (
                  <div
                    key={l.id}
                    className="flex items-center justify-between py-2 text-xs"
                  >
                    <div className="min-w-0">
                      <div className="truncate font-medium text-foreground">{l.org}</div>
                      <div className="truncate text-[10px] text-muted-foreground">
                        {l.title}
                      </div>
                    </div>
                    <div className="ml-2 shrink-0 text-right">
                      <div className="text-[10px] text-muted-foreground">{l.location}</div>
                      <div className="font-medium text-foreground">
                        {formatStipend(l.stipend)}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Verified roles table */}
          <div className="mt-4 rounded-xl border border-border bg-background p-4">
            <div className="font-medium text-foreground">Verified roles</div>
            <table className="mt-2 w-full text-left">
              <thead>
                <tr className="text-[10px] text-muted-foreground">
                  <th className="pb-2 font-normal">Company</th>
                  <th className="pb-2 font-normal">Role</th>
                  <th className="pb-2 font-normal">Location</th>
                  <th className="pb-2 font-normal">Status</th>
                </tr>
              </thead>
              <tbody>
                {recent.map((l) => (
                  <tr key={`row-${l.id}`} className="text-xs">
                    <td className="py-1.5 font-medium">{l.org}</td>
                    <td className="py-1.5 text-muted-foreground">{l.title}</td>
                    <td className="py-1.5 text-muted-foreground">{l.location}</td>
                    <td className="py-1.5">
                      <span className="inline-flex items-center gap-1 rounded-full bg-green-100 px-2 py-0.5 text-[9px] font-medium text-green-700">
                        <span className="h-1 w-1 rounded-full bg-green-500" />
                        Verified
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
