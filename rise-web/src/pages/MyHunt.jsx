import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowUpRight,
  BriefcaseBusiness,
  Check,
  Clipboard,
  Cloud,
  FileText,
  LogIn,
  MapPin,
  RefreshCw,
  SearchCheck,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/AuthContext";
import { fetchPersonalHunt, matchesFromPayload } from "@/lib/personalHunt";

function Skeleton() {
  return (
    <div className="mx-auto max-w-6xl animate-pulse px-6 py-16 md:px-10">
      <div className="h-8 w-64 rounded-md bg-secondary" />
      <div className="mt-3 h-4 w-80 rounded bg-secondary" />
      <div className="mt-10 grid gap-4 sm:grid-cols-3">
        {[0, 1, 2].map((item) => <div key={item} className="h-24 rounded-xl bg-secondary" />)}
      </div>
      <div className="mt-6 h-80 rounded-xl bg-secondary" />
    </div>
  );
}

function Message({ icon: Icon, title, body, action }) {
  return (
    <section className="mx-auto flex min-h-[60vh] max-w-xl flex-col items-start justify-center px-6 py-20">
      <div className="flex h-11 w-11 items-center justify-center rounded-full bg-secondary text-foreground">
        <Icon className="h-5 w-5" />
      </div>
      <h1 className="mt-5 text-3xl font-semibold tracking-tight text-foreground">{title}</h1>
      <p className="mt-3 max-w-prose text-base leading-7 text-muted-foreground">{body}</p>
      {action && <div className="mt-7">{action}</div>}
    </section>
  );
}

function Metric({ label, value, detail }) {
  return (
    <div className="rounded-xl border border-border bg-background p-4">
      <div className="text-sm text-muted-foreground">{label}</div>
      <div className="mt-2 text-2xl font-semibold tabular-nums text-foreground">{value}</div>
      {detail && <div className="mt-1 text-xs text-muted-foreground">{detail}</div>}
    </div>
  );
}

function CopyButton({ value, label = "Copy" }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    await navigator.clipboard.writeText(value || "");
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }
  return (
    <button
      type="button"
      onClick={copy}
      disabled={!value}
      className="inline-flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm font-medium text-foreground transition-colors hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-40"
    >
      {copied ? <Check className="h-4 w-4" /> : <Clipboard className="h-4 w-4" />}
      {copied ? "Copied" : label}
    </button>
  );
}

function MatchDetail({ item }) {
  if (!item) return null;
  const outreach = item.outreach || {};
  const contact = item.selected_contact || {};
  const research = item.research || {};
  const evidence = research.evidence_ledger || research.evidence || [];
  return (
    <article className="min-w-0 rounded-xl border border-border bg-background p-5 md:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-sm font-medium text-accent">{item.section}</div>
          <h2 className="mt-1 text-2xl font-semibold tracking-tight text-foreground">{item.title}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{item.company} · {item.location}</p>
        </div>
        <div className="flex gap-2">
          <a href={item.source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm font-medium hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            Source <ArrowUpRight className="h-4 w-4" />
          </a>
          <a href={item.apply_url || item.source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 rounded-md bg-accent px-3 py-2 text-sm font-semibold text-accent-foreground hover:bg-accent/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            Apply <ArrowUpRight className="h-4 w-4" />
          </a>
        </div>
      </div>

      <dl className="mt-6 grid gap-4 border-y border-border py-5 sm:grid-cols-3">
        <div><dt className="text-xs text-muted-foreground">Deterministic score</dt><dd className="mt-1 font-semibold">{item.score ?? "—"}/100</dd></div>
        <div><dt className="text-xs text-muted-foreground">Kimi fit</dt><dd className="mt-1 font-semibold">{item.llm_fit_score ?? "—"}/100</dd></div>
        <div><dt className="text-xs text-muted-foreground">Recommended resume</dt><dd className="mt-1 break-words text-sm font-medium">{item.resume || "Master"}</dd></div>
      </dl>

      <section className="mt-6">
        <h3 className="text-sm font-semibold">Why it made the shortlist</h3>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">{item.llm_rank_reason || "The role passed the deterministic and model gates."}</p>
      </section>

      {evidence.length > 0 && (
        <section className="mt-6">
          <h3 className="text-sm font-semibold">Evidence</h3>
          <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
            {evidence.slice(0, 5).map((entry, index) => (
              <li key={`${entry.url || "evidence"}-${index}`} className="rounded-lg bg-secondary/70 p-3">
                <span className="font-medium text-foreground">{entry.type || "Observation"}: </span>
                {entry.observation || entry.claim || entry.inference || entry.uncertainty}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="mt-6">
        <h3 className="text-sm font-semibold">Contact</h3>
        {contact.email ? (
          <div className="mt-3 flex flex-wrap items-start justify-between gap-3 rounded-lg border border-border p-4 text-sm">
            <div className="min-w-0">
              <div className="break-all font-medium text-foreground">{contact.name ? `${contact.name} · ` : ""}{contact.email}</div>
              <div className="mt-1 text-xs text-muted-foreground">
                {contact.role || "Published address"} · {contact.confidence || "unrated"} confidence
                {contact.source_url && (<> · <a href={contact.source_url} target="_blank" rel="noreferrer" className="text-accent">where it was published</a></>)}
              </div>
            </div>
            <CopyButton value={contact.email} label="Copy email" />
          </div>
        ) : (
          <p className="mt-2 text-sm text-muted-foreground">No public address found. The prompt below asks Claude Code to find the founder or hiring lead's public channel, with its source.</p>
        )}
      </section>

      <section className="mt-6">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-sm font-semibold">
            {outreach.send_status === "research_first_needs_human_review" ? "Research-first prompt for Claude Code" : "Email prompt for Claude Code"}
          </h3>
          <CopyButton value={outreach.claude_prompt} label="Copy prompt" />
        </div>
        <pre className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap rounded-lg bg-secondary/70 p-4 text-xs leading-5 text-muted-foreground">{outreach.claude_prompt || "No prompt was produced for this match."}</pre>
        {outreach.linkedin_note && (
          <div className="mt-3 flex items-start justify-between gap-3 rounded-lg border border-border p-4">
            <p className="text-sm leading-6 text-muted-foreground">{outreach.linkedin_note}</p>
            <CopyButton value={outreach.linkedin_note} label="Copy note" />
          </div>
        )}
      </section>
    </article>
  );
}

export default function MyHunt() {
  const { user, loading: authLoading, signInWithGoogle } = useAuth();
  const [payload, setPayload] = useState(null);
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("matches");
  const [selectedId, setSelectedId] = useState(null);

  useEffect(() => {
    const previousTitle = document.title;
    document.title = "My internship hunt · Rise";
    let robots = document.querySelector('meta[name="robots"]');
    const created = !robots;
    if (!robots) {
      robots = document.createElement("meta");
      robots.name = "robots";
      document.head.appendChild(robots);
    }
    const previousRobots = robots.content;
    robots.content = "noindex,nofollow,noarchive";
    return () => {
      document.title = previousTitle;
      if (created) robots.remove(); else robots.content = previousRobots;
    };
  }, []);

  useEffect(() => {
    if (!user) return;
    const controller = new AbortController();
    setStatus("loading");
    setError(null);
    fetchPersonalHunt(user, controller.signal)
      .then((data) => {
        setPayload(data);
        const first = matchesFromPayload(data)[0];
        setSelectedId(first?.id || null);
        setStatus("ready");
      })
      .catch((err) => {
        if (err.name === "AbortError") return;
        setError(err);
        setStatus(err.status === 403 ? "denied" : "error");
      });
    return () => controller.abort();
  }, [user]);

  const matches = useMemo(() => matchesFromPayload(payload), [payload]);
  const selected = matches.find((item) => item.id === selectedId) || matches[0];
  const funding = [...(payload?.funding?.primary || []), ...(payload?.funding?.extended || [])];
  const needsVerification = payload?.needsVerification || [];
  const failedSources = (payload?.sourceHealth || []).filter((item) => item.status === "failed");

  if (authLoading) return <Skeleton />;
  if (!user) {
    return <Message icon={LogIn} title="Sign in to open your hunt" body="This workspace contains private internship research, evidence, and manual outreach drafts." action={<Button onClick={signInWithGoogle} className="rounded-full px-5">Continue with Google</Button>} />;
  }
  if (status === "loading" || status === "idle") return <Skeleton />;
  if (status === "denied") return <Message icon={ShieldCheck} title="Private access only" body="This Google account does not have access to Daksh’s personal internship hunt. Sign in with the approved account." />;
  if (status === "error") return <Message icon={AlertTriangle} title="The latest hunt is unavailable" body={error?.message || "The private service could not load a verified live run. No fallback data was shown."} />;

  return (
    <div className="border-t border-border bg-secondary/30">
      <div className="mx-auto max-w-6xl px-6 py-12 md:px-10 md:py-16">
        <header className="flex flex-wrap items-end justify-between gap-5">
          <div>
            <div className="flex items-center gap-2 text-sm font-medium text-accent"><ShieldCheck className="h-4 w-4" /> Private workspace</div>
            <h1 className="mt-3 text-4xl font-semibold tracking-tight text-foreground">My internship hunt</h1>
            <p className="mt-3 max-w-2xl text-base leading-7 text-muted-foreground">High-fit opportunities, source-backed company research, and drafts ready for your manual review.</p>
          </div>
          <div className="text-sm text-muted-foreground">Run {payload.run?.date} · {payload.run?.status}</div>
        </header>

        <section className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4" aria-label="Run summary">
          <Metric label="New matches" value={matches.length} detail={`${payload.bengaluru?.length || 0} Bengaluru · ${payload.remote?.length || 0} remote`} />
          <Metric label="Eligible before Kimi" value={payload.run?.eligibleCount || 0} detail={`${payload.withheldCount || 0} withheld after review`} />
          <Metric label="Funding signals" value={funding.length} detail="Last 30 days maximum" />
          <Metric label="Apify this month" value={`$${Number(payload.apify?.month_spend_usd || 0).toFixed(2)}`} detail="$5.00 hard stop" />
        </section>

        {payload.run?.digestUsable === false && (
          <div className="mt-5 flex items-start gap-3 rounded-xl border border-border bg-background p-4 text-sm">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-[hsl(var(--accent-warm))]" />
            <div><div className="font-medium">Kimi scoring failed on this run</div><div className="mt-1 text-muted-foreground">No internship could be approved, so Matches is empty for that reason, not because nothing was found. Funding, verification leads and source health below are unaffected.</div></div>
          </div>
        )}

        {failedSources.length > 0 && (
          <div className="mt-5 flex items-start gap-3 rounded-xl border border-border bg-background p-4 text-sm">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-[hsl(var(--accent-warm))]" />
            <div><div className="font-medium">Some sources need attention</div><div className="mt-1 text-muted-foreground">{failedSources.map((item) => item.source_id).join(", ")}. The run kept an audit trail and did not invent replacement records.</div></div>
          </div>
        )}

        <div className="mt-8 flex gap-1 rounded-lg border border-border bg-background p-1" role="tablist" aria-label="Personal hunt sections">
          {[["matches", "Matches", BriefcaseBusiness], ["funding", "Funding", Sparkles], ["verify", `Verify${needsVerification.length ? ` (${needsVerification.length})` : ""}`, ShieldCheck], ["pipeline", "Pipeline", SearchCheck]].map(([value, label, Icon]) => (
            <button key={value} role="tab" aria-selected={tab === value} onClick={() => setTab(value)} className={`inline-flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${tab === value ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground"}`}>
              <Icon className="h-4 w-4" /> {label}
            </button>
          ))}
        </div>

        {tab === "matches" && (matches.length ? (
          <div className="mt-5 grid items-start gap-5 lg:grid-cols-[320px_minmax(0,1fr)]">
            <div className="overflow-hidden rounded-xl border border-border bg-background">
              {matches.map((item) => (
                <button key={item.id} onClick={() => setSelectedId(item.id)} className={`w-full border-b border-border px-4 py-4 text-left transition-colors last:border-b-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring ${selected?.id === item.id ? "bg-secondary" : "hover:bg-secondary/60"}`}>
                  <div className="text-xs font-medium text-accent">{item.section}</div>
                  <div className="mt-1 text-sm font-semibold text-foreground">{item.title}</div>
                  <div className="mt-1 text-xs text-muted-foreground">{item.company}</div>
                  <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground"><span className="inline-flex items-center gap-1"><MapPin className="h-3 w-3" />{item.location}</span><span>{item.llm_fit_score ?? "—"}/100</span></div>
                </button>
              ))}
            </div>
            <MatchDetail item={selected} />
          </div>
        ) : <Message icon={Cloud} title="No match cleared every gate" body="The pipeline stayed honest and did not pad today’s edition. Source health and withheld records remain available in the audit trail." />)}

        {tab === "funding" && (
          <div className="mt-5 divide-y divide-border overflow-hidden rounded-xl border border-border bg-background">
            {funding.length ? funding.map((event) => (
              <article key={event.funding_event_id || event.id} className="p-5 md:p-6">
                <div className="flex flex-wrap items-start justify-between gap-4"><div><h2 className="text-lg font-semibold">{event.company}</h2><p className="mt-1 text-sm text-muted-foreground">{event.headline}</p></div><a href={event.source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 text-sm font-medium text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">Source <ArrowUpRight className="h-4 w-4" /></a></div>
                {event.problem_research?.problem_hypothesis && <div className="mt-4 rounded-lg bg-secondary/70 p-4 text-sm leading-6"><span className="font-medium">Inference to validate: </span><span className="text-muted-foreground">{event.problem_research.problem_hypothesis}</span></div>}
              </article>
            )) : <div className="p-8 text-sm text-muted-foreground">No current funding signal passed the dated evidence gate.</div>}
          </div>
        )}

        {tab === "verify" && (
          <div className="mt-5 overflow-hidden rounded-xl border border-border bg-background">
            <div className="border-b border-border bg-secondary/40 px-5 py-4 text-sm">
              <div className="font-medium">Unverified LinkedIn leads</div>
              <div className="mt-1 text-muted-foreground">These cleared every other filter but link to LinkedIn, which this pipeline is not permitted to open. They are machine-collected unverified leads, not approved matches, and they are not counted in the numbers above. Open each one yourself before acting on it.</div>
            </div>
            {needsVerification.length ? needsVerification.map((item) => (
              <article key={item.id} className="flex flex-wrap items-start justify-between gap-4 border-b border-border px-5 py-4 text-sm last:border-b-0">
                <div>
                  <div className="font-semibold text-foreground">{item.title}</div>
                  <div className="mt-1 text-xs text-muted-foreground">{item.company}</div>
                  <div className="mt-2 flex items-center gap-3 text-xs text-muted-foreground"><span className="inline-flex items-center gap-1"><MapPin className="h-3 w-3" />{item.location}</span><span>Posted {item.posted_date}</span></div>
                </div>
                <a href={item.apply_url || item.source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 text-sm font-medium text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">Verify <ArrowUpRight className="h-4 w-4" /></a>
              </article>
            )) : <div className="p-8 text-sm text-muted-foreground">Nothing is waiting on manual verification.</div>}
          </div>
        )}

        {tab === "pipeline" && (
          <div className="mt-5 overflow-hidden rounded-xl border border-border bg-background">
            <div className="grid grid-cols-[1fr_auto_auto] gap-4 border-b border-border px-5 py-3 text-xs font-medium text-muted-foreground"><span>Source</span><span>Records</span><span>Status</span></div>
            {(payload.sourceHealth || []).map((source, index) => (
              <div key={`${source.source_id}-${index}`} className="grid grid-cols-[1fr_auto_auto] items-center gap-4 border-b border-border px-5 py-4 text-sm last:border-b-0"><div><div className="font-medium">{source.source_id}</div>{source.human_action && <div className="mt-1 text-xs text-muted-foreground">{source.human_action}</div>}</div><span className="tabular-nums text-muted-foreground">{source.record_count || 0}</span><span className="rounded-full bg-secondary px-2 py-1 text-xs font-medium">{source.status}</span></div>
            ))}
          </div>
        )}

        <footer className="mt-8 flex items-center gap-2 text-xs text-muted-foreground"><RefreshCw className="h-3.5 w-3.5" /> Completed {payload.run?.completedAt || "recently"}. Applications and outreach are always manual.</footer>
      </div>
    </div>
  );
}

