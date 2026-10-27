import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorText } from "../api";
import { Confirm, fillTemplate, fmtDate, fmtDateTime, Link, MailView, Modal, Pill, plural, useToast } from "../lib";
import type { Settings, Status, Tracker, TrackerRow, User } from "../types";

type Filter = "" | "notsent" | "awaiting" | "progress" | "completed";

export default function TrackerPage({ user }: { user: User }) {
  const qc = useQueryClient();
  const toast = useToast();
  const canEdit = user.role !== "viewer";
  const tq = useQuery({ queryKey: ["tracker"], queryFn: () => api.get<Tracker>("/api/tracker"), refetchInterval: 15_000 });
  const [filter, setFilter] = useState<Filter>("");
  const [lob, setLob] = useState("");
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<number[]>([]);
  const [send, setSend] = useState<{ ids: number[]; kind: "Invitation" | "Reminder" } | null>(null);
  const [view, setView] = useState<number | null>(null);
  const [cancel, setCancel] = useState<TrackerRow | null>(null);

  const t = tq.data;
  const rows = useMemo(() => (t?.applications ?? []).filter((a) =>
    (!lob || a.lob === lob) &&
    (!filter || (filter === "awaiting" ? ["sent", "opened", "progress"].includes(a.status) : a.status === filter)) &&
    (!q || `${a.name} ${a.project_id} ${a.respondent_name} ${a.respondent_email} ${a.team}`.toLowerCase().includes(q.toLowerCase()))), [t, lob, filter, q]);
  if (tq.isLoading) return <div className="loading">Loading the tracker…</div>;
  if (!t) return <div className="note err">{errorText(tq.error)}</div>;

  const c = t.counts;
  const awaiting = c.sent + c.opened + c.progress;
  const n = Math.max(1, t.total);
  const lobs = [...new Set(t.applications.map((a) => a.lob).filter(Boolean))].sort();
  const selectable = rows.filter((a) => a.status !== "completed" && a.email_ok);
  const selRows = t.applications.filter((a) => sel.includes(a.id));
  const allOn = selectable.length > 0 && selectable.every((a) => sel.includes(a.id));
  const toggle = (id: number) => setSel((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const stat = (k: Filter, label: string, v: number) => (
    <button type="button" className={`stat ${filter === k ? "on" : ""}`} onClick={() => setFilter(filter === k ? "" : k)} aria-pressed={filter === k}>
      <b>{v}</b><span>{label}</span></button>
  );
  const copyLink = async (a: TrackerRow) => {
    try { await navigator.clipboard.writeText(a.link || ""); toast(`Survey link for ${a.name} copied`); }
    catch { toast("Your browser blocked copying. Open View to see the link.", true); }
  };
  const doCancel = async () => {
    if (!cancel) return;
    try {
      await api.del(`/api/invitations/${cancel.id}`);
      toast(`Survey link for ${cancel.name} cancelled`);
      setCancel(null);
      qc.invalidateQueries({ queryKey: ["tracker"] });
    } catch (e) { toast(errorText(e), true); }
  };
  const sendable = selRows.filter((a) => a.status === "notsent");
  const remindable = selRows.filter((a) => ["sent", "opened", "progress"].includes(a.status));

  return (
    <>
      <div className="spread">
        <div><p className="eyebrow">Tracker</p><h1>Survey responses</h1></div>
        <div className="row">
          <a className={`btn ${c.completed ? "" : "disabled"}`} href={c.completed ? "/api/responses-all/download?fmt=xlsx" : undefined}
            aria-disabled={!c.completed} download>↓ Export completed (Excel)</a>
          <a className="btn ghost" href={c.completed ? "/api/responses-all/download?fmt=csv" : undefined} aria-disabled={!c.completed} download>CSV</a>
        </div>
      </div>
      <p className="lede">Send the survey to the respondent for each application, follow progress, and download each response as soon as it comes back. This page refreshes itself.</p>
      {t.delivery.mode === "sim" && canEdit && (
        <div className="note warn" style={{ margin: "0 0 14px" }}>Email delivery isn't connected yet, so invitations are recorded under Sent emails but not delivered. <Link to="/delivery">Set up email delivery</Link>.</div>
      )}
      <div className="stats">
        {stat("", "Applications", t.total)}{stat("notsent", "Not sent", c.notsent)}{stat("awaiting", "Awaiting response", awaiting)}
        {stat("progress", "In progress", c.progress)}{stat("completed", "Completed", c.completed)}
      </div>
      <div className="meter" role="img" aria-label={`${c.completed} of ${t.total} completed, ${c.progress} in progress`}>
        <i style={{ width: `${(c.completed / n) * 100}%`, background: "var(--ok)" }} />
        <i style={{ width: `${(c.progress / n) * 100}%`, background: "var(--signal)" }} />
        <i style={{ width: `${((c.sent + c.opened) / n) * 100}%`, background: "var(--accent)", opacity: .55 }} />
      </div>
      <div className="toolbar">
        <input type="search" placeholder="Search application, team or respondent" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search" />
        <select value={lob} onChange={(e) => setLob(e.target.value)} aria-label="Filter by line of business">
          <option value="">All lines of business</option>{lobs.map((l) => <option key={l}>{l}</option>)}
        </select>
      </div>
      <div className="tbl">
        <table className="tracker">
          <thead><tr>
            <th>{canEdit && <input className="chk" type="checkbox" aria-label="Select all that can be sent" checked={allOn} disabled={!selectable.length}
              onChange={(e) => setSel(e.target.checked ? selectable.map((a) => a.id) : [])} />}</th>
            <th>Application</th><th>Line of business</th><th>Respondent</th><th>Status</th><th>Progress</th><th>Actions</th>
          </tr></thead>
          <tbody>
            {rows.map((a) => {
              const can = canEdit && a.status !== "completed" && a.email_ok;
              return (
                <tr key={a.id} className={sel.includes(a.id) ? "sel" : ""}>
                  <td>{canEdit && <input className="chk" type="checkbox" checked={sel.includes(a.id)} disabled={!can} onChange={() => toggle(a.id)} aria-label={`Select ${a.name}`} />}</td>
                  <td><b>{a.name}</b><span className="sub mono">{a.project_id || "No project ID"}</span></td>
                  <td>{a.lob || <span className="muted">Not set</span>}</td>
                  <td>{a.respondent_name || (a.email_ok ? "" : <span className="tag warn">No respondent</span>)}<span className="sub">{a.respondent_email}</span></td>
                  <td><Pill s={a.status} />
                    {a.email_failed && <span className="sub bad-t">Email failed. See Sent emails.</span>}
                    {a.reminders > 0 && <span className="sub">{plural(a.reminders, "reminder")}</span>}</td>
                  <td><Progress a={a} /></td>
                  <td><div className="acts">
                    {!a.email_ok && canEdit && <Link to="/applications" className="btn sm ghost">Add respondent</Link>}
                    {a.email_ok && a.status === "notsent" && canEdit && <button type="button" className="btn sm" onClick={() => setSend({ ids: [a.id], kind: "Invitation" })}>Send</button>}
                    {["sent", "opened", "progress"].includes(a.status) && canEdit && <>
                      <button type="button" className="btn sm" onClick={() => setSend({ ids: [a.id], kind: "Reminder" })}>Remind</button>
                      <button type="button" className="btn sm ghost" onClick={() => copyLink(a)} title="Copy the survey link to share it another way">Copy link</button>
                      <button type="button" className="btn sm ghost danger" onClick={() => setCancel(a)} title="Cancel this survey link">Cancel</button>
                    </>}
                    {a.status === "completed" && <>
                      <a className="btn sm primary" href={`/api/responses/${a.id}/download?fmt=xlsx`} download aria-label={`Download response for ${a.name}`}>↓ Download</a>
                      <button type="button" className="btn sm ghost" onClick={() => setView(a.id)}>View</button>
                    </>}
                  </div></td>
                </tr>
              );
            })}
            {!rows.length && <tr><td colSpan={7} className="empty">{t.total ? "No applications match. Clear the search or filters." : <>No applications yet. <Link to="/applications">Add or import them</Link>.</>}</td></tr>}
          </tbody>
        </table>
      </div>
      {canEdit && selRows.length > 0 && (
        <div className="bulk">
          <span>{plural(selRows.length, "application")} selected</span>
          <div className="row">
            <button type="button" className="btn sm ghost" onClick={() => setSel([])}>Clear</button>
            {remindable.length > 0 && <button type="button" className="btn" onClick={() => setSend({ ids: remindable.map((a) => a.id), kind: "Reminder" })}>Remind {remindable.length}</button>}
            {sendable.length > 0 && <button type="button" className="btn primary" onClick={() => setSend({ ids: sendable.map((a) => a.id), kind: "Invitation" })}>Send survey to {sendable.length}</button>}
          </div>
        </div>
      )}
      {send && <SendModal tracker={t} ids={send.ids} kind={send.kind} onClose={() => setSend(null)} onDone={() => { setSend(null); setSel([]); }} />}
      {view !== null && <ResponseModal id={view} canEdit={canEdit} onClose={() => setView(null)} />}
      {cancel && <Confirm title={`Cancel the survey for ${cancel.name}?`} action="Cancel survey link" danger onConfirm={doCancel} onClose={() => setCancel(null)}>
        <p>The link sent to {cancel.respondent_name || cancel.respondent_email} stops working and any answers saved so far are deleted. You can send a new survey afterwards.</p></Confirm>}
    </>
  );
}

function Progress({ a }: { a: TrackerRow }) {
  if (a.status === "completed") return <span className="small">{fmtDate(a.completed_at)}<span className="sub">{a.mode === "all" ? "Full survey" : "Core questions"}</span></span>;
  if (a.status === "opened" || a.status === "progress")
    return <span className="prog"><span className="b"><i style={{ width: `${a.total ? (a.answered / a.total) * 100 : 0}%` }} /></span>{a.answered}/{a.total}</span>;
  if (a.status === "sent") return <span className="small muted">Due {fmtDate(a.due_at)}</span>;
  return null;
}

function SendModal({ tracker, ids, kind, onClose, onDone }: { tracker: Tracker; ids: number[]; kind: "Invitation" | "Reminder"; onClose: () => void; onDone: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => api.get<Settings>("/api/settings") });
  const rows = tracker.applications.filter((a) => ids.includes(a.id));
  const first = rows[0];
  const defDue = new Date(Date.now() + tracker.default_due_days * 864e5).toISOString().slice(0, 10);
  const [due, setDue] = useState(defDue);
  const [busy, setBusy] = useState(false);
  const s = settings.data;
  const d = tracker.delivery;
  const dueDate = kind === "Reminder" && first?.due_at ? new Date(first.due_at) : new Date(`${due}T12:00`);
  const vals = first && s ? {
    first_name: (first.respondent_name || "there").split(" ")[0], name: first.respondent_name, application: first.name,
    project_id: first.project_id, lob: first.lob, team: first.team,
    due_date: dueDate.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" }),
    survey_link: first.link || `${s.delivery.link_base || s.delivery.server.public_url}/s/…`,
  } : null;
  const go = async () => {
    setBusy(true);
    try {
      const r = kind === "Invitation"
        ? await api.post<{ sent: number; skipped: { name: string; reason: string }[] }>("/api/invitations/send", { application_ids: ids, due_date: due })
        : await api.post<{ sent: number; skipped: { name: string; reason: string }[] }>("/api/invitations/remind", { application_ids: ids });
      const what = kind === "Invitation" ? "invitation" : "reminder";
      toast(`${plural(r.sent, what)} ${d.mode === "sim" ? "recorded" : "queued to send"}${r.skipped.length ? `; ${r.skipped.length} skipped` : ""}`);
      qc.invalidateQueries({ queryKey: ["tracker"] });
      qc.invalidateQueries({ queryKey: ["emails"] });
      onDone();
    } catch (e) {
      toast(errorText(e), true);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal eyebrow={kind === "Reminder" ? "Send reminder" : "Send survey"} title={`${kind === "Reminder" ? "Remind" : "Invite"} ${plural(rows.length, "respondent")}`} onClose={onClose}
      footer={<><button type="button" className="btn" onClick={onClose}>Cancel</button>
        <button type="button" className="btn primary" disabled={busy || !rows.length} onClick={go}>Send {plural(rows.length, "email")}</button></>}>
      <div className="row" style={{ alignItems: "flex-end", marginBottom: 14 }}>
        {kind === "Invitation" && <div><label className="f" htmlFor="due">Respond by</label>
          <input id="due" type="date" value={due} min={new Date().toISOString().slice(0, 10)} onChange={(e) => setDue(e.target.value)} style={{ width: 190 }} /></div>}
        <div style={{ flex: 1, minWidth: 220 }}><span className="f">To</span>
          <div className="small">{rows.map((a) => `${a.respondent_name || a.respondent_email} (${a.name})`).join(", ")}</div></div>
      </div>
      {vals && s && <><p className="small muted" style={{ margin: "0 0 6px" }}>Preview{rows.length > 1 ? ` of the email to ${first.respondent_name}` : ""}</p>
        <MailView subject={(kind === "Reminder" ? "Reminder: " : "") + fillTemplate(s.email.subject, vals)} body={fillTemplate(s.email.body, vals)}
          from={`${s.delivery.display_name} <${s.delivery.mailbox}>`} to={`${first.respondent_name} <${first.respondent_email}>`} /></>}
      <div className={`note ${d.mode === "sim" ? "warn" : ""}`}>
        {d.mode === "sim" ? <>Email delivery isn't connected, so {rows.length > 1 ? "these are" : "this is"} recorded under Sent emails only. Copy the survey link from the tracker to share it another way.</>
          : <>Sends through {d.mode === "graph" ? "Microsoft 365" : "the SMTP relay"} as {d.mailbox}, up to {d.rate_per_minute} a minute.{!d.tested && " Email delivery hasn't passed a test yet."}</>}
      </div>
    </Modal>
  );
}

interface ResponseView {
  application: { id: number; name: string; lob: string; respondent_name: string; respondent_email: string };
  status: Status; mode: string; completed_at: string | null;
  sections: { key: string; id: string; name: string; items: { qid: string; text: string; answer: string; required: boolean }[] }[];
}

function ResponseModal({ id, canEdit, onClose }: { id: number; canEdit: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const r = useQuery({ queryKey: ["response", id], queryFn: () => api.get<ResponseView>(`/api/responses/${id}`) });
  const [reopen, setReopen] = useState(false);
  const v = r.data;
  const doReopen = async () => {
    try {
      await api.post(`/api/invitations/${id}/reopen`);
      toast("Response reopened. The respondent can change it with the same link.");
      qc.invalidateQueries({ queryKey: ["tracker"] });
      onClose();
    } catch (e) { toast(errorText(e), true); }
  };
  return (
    <Modal eyebrow="Response" title={v?.application.name ?? "Loading…"} onClose={onClose} footer={<>
      {canEdit && <button type="button" className="btn ghost" onClick={() => setReopen(true)}>Reopen for changes</button>}
      <a className="btn" href={`/api/responses/${id}/download?fmt=csv`} download>CSV</a>
      <a className="btn primary" href={`/api/responses/${id}/download?fmt=xlsx`} download>↓ Download Excel</a></>}>
      {v ? <>
        <p className="small muted" style={{ marginTop: 0 }}>{v.application.respondent_name} · {v.application.lob} · completed {fmtDateTime(v.completed_at)} · {v.mode === "all" ? "full survey" : "core questions"}</p>
        <div className="rlist">
          {v.sections.flatMap((s) => [
            <div key={s.key} className="sh">{s.id ? `${s.id} · ` : ""}{s.name}</div>,
            ...s.items.map((it) => <div key={it.qid}><span className="qid">{it.qid}</span><span>{it.text}</span><span className={`a ${it.answer ? "" : "none"}`}>{it.answer || "Skipped"}</span></div>),
          ])}
        </div>
      </> : <div className="loading">Loading…</div>}
      {reopen && <Confirm title="Reopen this response?" action="Reopen" onConfirm={doReopen} onClose={() => setReopen(false)}>
        <p>The tracker shows it as in progress again, and the respondent can change answers and submit again using the same link. Let them know by email.</p></Confirm>}
    </Modal>
  );
}
