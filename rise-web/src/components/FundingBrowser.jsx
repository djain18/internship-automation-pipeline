import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, Check, Clipboard, MapPin } from "lucide-react";
import { useAuth } from "@/lib/AuthContext";
import { RESUMES, fillEmailPrompt, slotLabel, wordCount, writeOwnDraft } from "@/lib/outreach";

const STATUS_LABEL = {
  to_review: "Draft to review",
  needs_address: "Draft needs an address",
  blocked_validation: "Draft fails checks",
  approved: "Approved",
  sending: "Sending",
  sent: "Sent",
  shadow_sent: "Sent (shadow)",
  send_failed: "Send failed",
  rejected: "Rejected",
};

const WHY_NOT_RESEARCHED = {
  no_company_site: "No company website could be verified, so there is nothing to research yet.",
};

function Copy({ value, label }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    await navigator.clipboard.writeText(value || "");
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }
  return (
    <button type="button" onClick={copy} disabled={!value} className="inline-flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm font-medium text-foreground transition-colors hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-40">
      {copied ? <Check className="h-4 w-4" /> : <Clipboard className="h-4 w-4" />}
      {copied ? "Copied" : label}
    </button>
  );
}

function raiseText(event) {
  return [event.amount, event.round_type].filter(Boolean).join(" · ") || "Undisclosed round";
}

function cityLabel(event) {
  const city = event.location_evidence?.city;
  return city ? city[0].toUpperCase() + city.slice(1) : "";
}

function OwnDraftForm({ event, draftStatus }) {
  const { user } = useAuth();
  const contact = event.selected_contact || {};
  const [form, setForm] = useState({
    to: contact.email || "",
    subject: "",
    body: "",
    attachment: "Daksh-Jain-founders_office.pdf",
  });
  const [state, setState] = useState({ status: "idle", message: "" });
  const locked = draftStatus && !["to_review", "needs_address", "blocked_validation", "rejected"].includes(draftStatus.status);

  async function submit(e) {
    e.preventDefault();
    setState({ status: "saving", message: "" });
    try {
      const saved = await writeOwnDraft(user, {
        lead_id: event.funding_event_id,
        company: event.company,
        source_url: event.source_url,
        to: form.to,
        to_source: form.to && form.to === contact.email ? contact.source_url || "" : "",
        subject: form.subject,
        body: form.body,
        attachment: form.attachment,
      });
      setState({
        status: "saved",
        message: saved.errors?.length ? `Saved, but it fails: ${saved.errors.join(", ")}. Fix it in the Outbox.` : "Saved to the Outbox for your review.",
      });
    } catch (err) {
      setState({ status: "error", message: err.message });
    }
  }

  if (locked) {
    return <p className="mt-3 text-sm text-muted-foreground">{STATUS_LABEL[draftStatus.status]}{draftStatus.slot ? `, sends ${slotLabel(draftStatus.slot)}` : ""}. This company is not drafted twice.</p>;
  }
  const field = "mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";
  return (
    <form onSubmit={submit} className="mt-3 space-y-3">
      <label className="block text-xs text-muted-foreground">To
        <input type="email" value={form.to} onChange={(e) => setForm({ ...form, to: e.target.value })} className={field} placeholder="founder@company.com" />
      </label>
      <label className="block text-xs text-muted-foreground">Subject
        <input value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })} className={field} required />
      </label>
      <label className="block text-xs text-muted-foreground">Body ({wordCount(form.body)} words, 80-150)
        <textarea value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} rows={10} className={field} required />
      </label>
      <label className="block text-xs text-muted-foreground">Resume
        <select value={form.attachment} onChange={(e) => setForm({ ...form, attachment: e.target.value })} className={field}>
          {RESUMES.map((name) => <option key={name}>{name}</option>)}
        </select>
      </label>
      <div className="flex flex-wrap items-center gap-3">
        <button type="submit" disabled={state.status === "saving"} className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-foreground hover:bg-accent/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50">
          {state.status === "saving" ? "Saving" : "Save to Outbox"}
        </button>
        {state.message && <span role="status" className="text-sm text-muted-foreground">{state.message} {state.status === "saved" && <Link to="/my-hunt/outbox" className="text-accent">Open Outbox</Link>}</span>}
      </div>
    </form>
  );
}

function FundingDetail({ event, draftStatus }) {
  const [link, setLink] = useState("");
  const [summary, setSummary] = useState("");
  if (!event) return null;
  const deep = event.deep_problem_research || {};
  const signals = deep.observed_signals || [];
  const brief = event.prompt_generation?.prompt_text || "";
  const emailPrompt = event.outreach?.email_prompt || "";
  const contact = event.selected_contact || {};
  const field = "mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";
  return (
    <article className="min-w-0 rounded-xl border border-border bg-background p-5 md:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="text-2xl font-semibold tracking-tight">{event.company}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{raiseText(event)} · {event.event_date}{event.sector ? ` · ${event.sector}` : ""}</p>
          {event.location_evidence?.observation && <p className="mt-2 text-xs text-muted-foreground">Office: “{event.location_evidence.observation}” <a href={event.location_evidence.url} target="_blank" rel="noreferrer" className="text-accent">source</a></p>}
        </div>
        <div className="flex flex-wrap gap-2">
          {(event.corroborating_urls || [event.source_url]).map((url, index) => (
            <a key={url} href={url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 rounded-md border border-border px-3 py-2 text-sm hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">Source {index + 1} <ArrowUpRight className="h-4 w-4" /></a>
          ))}
          {event.company_url && <a href={event.company_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 rounded-md border border-border px-3 py-2 text-sm hover:bg-secondary">Website <ArrowUpRight className="h-4 w-4" /></a>}
        </div>
      </div>

      {!brief ? (
        <p className="mt-6 rounded-lg bg-secondary/70 p-4 text-sm text-muted-foreground">
          {event.research_status === "researched"
            ? "Researched, but the public evidence did not support a specific problem. No prompt was written rather than guessing."
            : WHY_NOT_RESEARCHED[event.research_status] || "Not researched yet. Each run researches the next 5 companies, Bengaluru and Chennai first."}
        </p>
      ) : (
        <>
          <section className="mt-6">
            <h3 className="text-sm font-semibold">What the sources say</h3>
            <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
              {signals.map((signal, index) => (
                <li key={`${signal.url}-${index}`} className="rounded-lg bg-secondary/70 p-3">“{signal.text}” <a href={signal.url} target="_blank" rel="noreferrer" className="text-accent">source</a></li>
              ))}
            </ul>
            <p className="mt-3 text-sm leading-6"><span className="font-medium">Inference to check: </span><span className="text-muted-foreground">{deep.problem_hypothesis}</span></p>
          </section>

          <section className="mt-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h3 className="text-sm font-semibold">Step 1 · Research brief for Claude Code</h3>
              <Copy value={brief} label="Copy research brief" />
            </div>
            <p className="mt-2 text-sm text-muted-foreground">Claude reads the sources, proposes three prototypes, you pick one and build it.</p>
          </section>

          <section className="mt-6">
            <h3 className="text-sm font-semibold">Step 2 · Email prompt</h3>
            <label className="mt-3 block text-xs text-muted-foreground">Prototype link
              <input type="url" value={link} onChange={(e) => setLink(e.target.value)} className={field} placeholder="https://your-prototype.vercel.app" />
            </label>
            <label className="mt-3 block text-xs text-muted-foreground">What it does (the WHAT_IT_DOES line)
              <input value={summary} onChange={(e) => setSummary(e.target.value)} className={field} />
            </label>
            <div className="mt-3"><Copy value={link && summary ? fillEmailPrompt(emailPrompt, link, summary) : ""} label="Copy email prompt" /></div>
            {contact.email && <p className="mt-2 text-xs text-muted-foreground">Contact: {contact.name ? `${contact.name} · ` : ""}{contact.email}{contact.source_url && <> · <a href={contact.source_url} target="_blank" rel="noreferrer" className="text-accent">where published</a></>}</p>}
          </section>

          <section className="mt-6 border-t border-border pt-5">
            <h3 className="text-sm font-semibold">Step 3 · Write my own draft</h3>
            <OwnDraftForm key={event.funding_event_id} event={event} draftStatus={draftStatus} />
          </section>
        </>
      )}
    </article>
  );
}

export default function FundingBrowser({ events, drafts = {} }) {
  const [selectedId, setSelectedId] = useState(null);
  const selected = events.find((event) => event.funding_event_id === selectedId) || events[0];
  return (
    <div className="mt-5 grid items-start gap-5 lg:grid-cols-[320px_minmax(0,1fr)]">
      <div className="overflow-hidden rounded-xl border border-border bg-background">
        {events.map((event) => {
          const draft = drafts[event.funding_event_id];
          return (
            <button key={event.funding_event_id} onClick={() => setSelectedId(event.funding_event_id)} className={`w-full border-b border-border px-4 py-4 text-left transition-colors last:border-b-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring ${selected?.funding_event_id === event.funding_event_id ? "bg-secondary" : "hover:bg-secondary/60"}`}>
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-semibold text-foreground">{event.company}</span>
                {event.prompt_generation?.prompt_text && <span className="rounded-full bg-accent/10 px-2 py-0.5 text-xs font-medium text-accent">Problem found</span>}
              </div>
              <div className="mt-1 text-xs text-muted-foreground">{raiseText(event)} · {event.age_days ?? "?"}d ago</div>
              <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                {cityLabel(event) && <span className="inline-flex items-center gap-1"><MapPin className="h-3 w-3" />{cityLabel(event)}</span>}
                {draft && <span className="rounded-full bg-secondary px-2 py-0.5 font-medium">{STATUS_LABEL[draft.status] || draft.status}</span>}
              </div>
            </button>
          );
        })}
      </div>
      <FundingDetail key={selected?.funding_event_id} event={selected} draftStatus={drafts[selected?.funding_event_id]} />
    </div>
  );
}
