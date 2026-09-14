import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, ArrowLeft, ArrowUpRight, Check, LogIn, Mail, Send, ShieldCheck, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/AuthContext";
import {
  RESUMES,
  approveDraft,
  canApprove,
  fetchDrafts,
  groupDrafts,
  rejectDraft,
  saveDraft,
  slotLabel,
  wordCount,
} from "@/lib/outreach";

const STATE_LABEL = {
  to_review: "Ready to approve",
  needs_address: "Needs an address",
  blocked_validation: "Fix before approving",
  approved: "Approved",
  sending: "Sending",
  sent: "Sent",
  shadow_sent: "Shadow copy sent to you",
  send_failed: "Send failed",
  rejected: "Rejected",
};

const field =
  "w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

function Notice({ icon: Icon, title, body, action }) {
  return (
    <section className="mx-auto flex min-h-[60vh] max-w-xl flex-col items-start justify-center px-6 py-20">
      <div className="flex h-11 w-11 items-center justify-center rounded-full bg-secondary text-foreground"><Icon className="h-5 w-5" /></div>
      <h1 className="mt-5 text-3xl font-semibold tracking-tight text-foreground">{title}</h1>
      <p className="mt-3 max-w-prose text-base leading-7 text-muted-foreground">{body}</p>
      {action && <div className="mt-7">{action}</div>}
    </section>
  );
}

function DraftCard({ item, edits, onEdit, selected, onSelect, onSave, onReject, onUnapprove, busy }) {
  const value = { ...item, ...edits };
  const dirty = Object.keys(edits).length > 0;
  const editable = ["to_review", "needs_address", "blocked_validation", "approved", "rejected", "send_failed"].includes(item.status);
  const approvable = canApprove(value, dirty) && !(dirty && !value.to);
  const words = wordCount(value.body);
  const id = `draft-${item.lead_id}`;
  return (
    <article className="rounded-xl border border-border bg-background p-5 md:p-6" aria-labelledby={`${id}-title`}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          {item.status in { to_review: 1, needs_address: 1, blocked_validation: 1 } && (
            <input
              type="checkbox"
              aria-label={`Select ${item.company} to approve`}
              className="mt-1.5 h-4 w-4 accent-[hsl(var(--accent))]"
              checked={selected}
              disabled={!approvable || busy}
              onChange={(event) => onSelect(event.target.checked)}
            />
          )}
          <div>
            <h2 id={`${id}-title`} className="text-lg font-semibold text-foreground">{item.company}</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {item.title}{item.kimi_fit != null ? ` · Kimi fit ${item.kimi_fit}` : ""} · {STATE_LABEL[item.status] || item.status}
            </p>
          </div>
        </div>
        {item.source_url && (
          <a href={item.source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-sm font-medium text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            Listing <ArrowUpRight className="h-4 w-4" />
          </a>
        )}
      </div>

      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <label className="block text-sm">
          <span className="text-xs text-muted-foreground">To</span>
          <input className={`${field} mt-1`} type="email" value={value.to || ""} placeholder="Add a public address" disabled={!editable || busy}
            onChange={(event) => onEdit({ to: event.target.value })} />
          <span className="mt-1 block text-xs text-muted-foreground">
            {edits.to !== undefined ? "Entered by you" : value.to_source === "entered_by_daksh" ? "Entered by you" : value.to_source
              ? <a href={value.to_source} target="_blank" rel="noreferrer" className="text-accent">Where it was published</a> : "No public address found"}
          </span>
        </label>
        <label className="block text-sm">
          <span className="text-xs text-muted-foreground">Attachment</span>
          <select className={`${field} mt-1`} value={value.attachment || ""} disabled={!editable || busy} onChange={(event) => onEdit({ attachment: event.target.value })}>
            {RESUMES.map((name) => <option key={name} value={name}>{name}</option>)}
          </select>
        </label>
      </div>

      <label className="mt-4 block text-sm">
        <span className="text-xs text-muted-foreground">Subject{item.listing_subject ? ` (the listing asks for "${item.listing_subject}")` : ""}</span>
        <input className={`${field} mt-1`} value={value.subject || ""} disabled={!editable || busy} onChange={(event) => onEdit({ subject: event.target.value })} />
      </label>
      <label className="mt-4 block text-sm">
        <span className="flex justify-between text-xs text-muted-foreground"><span>Email</span><span className={words < 80 || words > 150 ? "text-[hsl(var(--accent-warm))]" : ""}>{words} words · aim for 80–150</span></span>
        <textarea className={`${field} mt-1 min-h-[180px] leading-6`} value={value.body || ""} disabled={!editable || busy} onChange={(event) => onEdit({ body: event.target.value })} />
      </label>

      {(item.errors || []).length > 0 && !dirty && (
        <div className="mt-4 flex items-start gap-2 rounded-lg bg-secondary/70 p-3 text-sm">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-[hsl(var(--accent-warm))]" />
          <span>Checks: {item.errors.join(", ")}</span>
        </div>
      )}
      {item.send_error && <p className="mt-3 text-sm text-[hsl(var(--accent-warm))]">{item.send_error}</p>}
      {item.slot && item.status === "approved" && <p className="mt-3 text-sm text-muted-foreground">Sends {slotLabel(item.slot)}.</p>}
      {item.sent_at && <p className="mt-3 text-sm text-muted-foreground">Sent {new Date(item.sent_at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })} · Gmail {item.message_id}</p>}

      {item.follow_up && (
        <details className="mt-4 text-sm">
          <summary className="cursor-pointer text-muted-foreground">Day-3 follow-up and LinkedIn note</summary>
          <p className="mt-2 whitespace-pre-wrap leading-6">{item.follow_up}</p>
          {item.linkedin_note && <p className="mt-2 whitespace-pre-wrap leading-6 text-muted-foreground">{item.linkedin_note}</p>}
        </details>
      )}

      {editable && (
        <div className="mt-5 flex flex-wrap gap-2">
          {dirty && <Button size="sm" onClick={onSave} disabled={busy}>Save changes</Button>}
          {item.status === "approved" && <Button size="sm" variant="outline" onClick={onUnapprove} disabled={busy}>Move back to review</Button>}
          {item.status !== "rejected" && item.status !== "approved" && (
            <Button size="sm" variant="outline" onClick={onReject} disabled={busy}><X className="mr-1 h-4 w-4" /> Reject</Button>
          )}
        </div>
      )}
    </article>
  );
}

export default function Outbox() {
  const { user, loading: authLoading, signInWithGoogle } = useAuth();
  const [payload, setPayload] = useState(null);
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("review");
  const [edits, setEdits] = useState({});
  const [selected, setSelected] = useState({});
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState("");

  useEffect(() => {
    const previous = document.title;
    document.title = "Outbox · Rise";
    return () => { document.title = previous; };
  }, []);

  const load = useCallback(async () => {
    if (!user) return;
    setStatus((current) => (current === "ready" ? current : "loading"));
    try {
      setPayload(await fetchDrafts(user));
      setStatus("ready");
    } catch (err) {
      setError(err);
      setStatus(err.status === 403 ? "denied" : "error");
    }
  }, [user]);

  useEffect(() => { load(); }, [load]);

  const groups = useMemo(() => groupDrafts(payload?.drafts), [payload]);
  const chosen = groups.review.filter((item) => selected[item.lead_id]);

  async function run(action, message) {
    setBusy(true);
    setFlash("");
    try {
      await action();
      setFlash(message);
    } catch (err) {
      setFlash(err.message);
    } finally {
      await load();
      setBusy(false);
    }
  }

  const edit = (id, change) => setEdits((current) => ({ ...current, [id]: { ...(current[id] || {}), ...change } }));
  const clearEdits = (ids) => setEdits((current) => Object.fromEntries(Object.entries(current).filter(([key]) => !ids.includes(key))));

  function approveSelected() {
    const ids = chosen.map((item) => item.lead_id);
    run(async () => {
      for (const id of ids) {
        if (edits[id]) await saveDraft(user, id, edits[id]);
        await approveDraft(user, id);
      }
      clearEdits(ids);
      setSelected({});
    }, `${ids.length} approved. They send ${slotLabel(payload?.nextSlot)}.`);
  }

  if (authLoading || status === "idle" || status === "loading") return <div className="min-h-[60vh] animate-pulse bg-secondary/30" />;
  if (!user) return <Notice icon={LogIn} title="Sign in to open your outbox" body="Drafted cold emails wait here for your approval." action={<Button onClick={signInWithGoogle} className="rounded-full px-5">Continue with Google</Button>} />;
  if (status === "denied") return <Notice icon={ShieldCheck} title="Private access only" body="This Google account cannot open Daksh's outbox." />;
  if (status === "error") return <Notice icon={AlertTriangle} title="The outbox is unavailable" body={error?.message || "Drafts could not be loaded. Nothing was sent."} />;

  const tabs = [["review", "To review"], ["approved", "Approved"], ["sent", "Sent"], ["rejected", "Rejected"]];
  const list = groups[tab];

  return (
    <div className="border-t border-border bg-secondary/30">
      <div className="mx-auto max-w-4xl px-6 pb-32 pt-12 md:px-10 md:pt-16">
        <Link to="/my-hunt" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="h-4 w-4" /> My hunt</Link>
        <header className="mt-4">
          <div className="flex items-center gap-2 text-sm font-medium text-accent"><Mail className="h-4 w-4" /> Outbox</div>
          <h1 className="mt-3 text-4xl font-semibold tracking-tight text-foreground">Emails to approve</h1>
          <p className="mt-3 max-w-2xl text-base leading-7 text-muted-foreground">
            Approve by 09:00 IST and they send {slotLabel(payload?.nextSlot)} from dakshjainn02@gmail.com with the chosen resume. Editing an approved email moves it back here. Nothing is sent without your approval.
          </p>
        </header>

        {flash && <div role="status" className="mt-6 rounded-lg border border-border bg-background p-3 text-sm">{flash}</div>}

        <div className="mt-8 flex flex-wrap gap-1 rounded-lg border border-border bg-background p-1" role="tablist" aria-label="Outbox sections">
          {tabs.map(([value, label]) => (
            <button key={value} role="tab" aria-selected={tab === value} onClick={() => setTab(value)}
              className={`rounded-md px-4 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${tab === value ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground"}`}>
              {label} ({groups[value].length})
            </button>
          ))}
        </div>

        <div className="mt-5 space-y-4">
          {list.length ? list.map((item) => (
            <DraftCard
              key={item.lead_id}
              item={item}
              edits={edits[item.lead_id] || {}}
              busy={busy}
              selected={Boolean(selected[item.lead_id])}
              onSelect={(checked) => setSelected((current) => ({ ...current, [item.lead_id]: checked }))}
              onEdit={(change) => edit(item.lead_id, change)}
              onSave={() => run(async () => { await saveDraft(user, item.lead_id, edits[item.lead_id]); clearEdits([item.lead_id]); }, "Saved. Checks ran again.")}
              onReject={() => run(() => rejectDraft(user, item.lead_id), `${item.company} rejected.`)}
              onUnapprove={() => run(() => saveDraft(user, item.lead_id, { subject: item.subject }), `${item.company} moved back to review.`)}
            />
          )) : (
            <div className="rounded-xl border border-border bg-background p-8 text-sm text-muted-foreground">
              {tab === "review" ? "No drafts are waiting. Tonight's drafts arrive with the 21:00 email." : "Nothing here yet."}
            </div>
          )}
        </div>
      </div>

      {tab === "review" && groups.review.length > 0 && (
        <div className="fixed inset-x-0 bottom-0 border-t border-border bg-background/95 backdrop-blur">
          <div className="mx-auto flex max-w-4xl flex-wrap items-center justify-between gap-3 px-6 py-3 md:px-10">
            <span className="text-sm text-muted-foreground">{chosen.length} selected · sends {slotLabel(payload?.nextSlot)}</span>
            <Button onClick={approveSelected} disabled={!chosen.length || busy} className="rounded-full px-5">
              {busy ? <Check className="mr-2 h-4 w-4" /> : <Send className="mr-2 h-4 w-4" />} Approve {chosen.length || ""} selected
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
