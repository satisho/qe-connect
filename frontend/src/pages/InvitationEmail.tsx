import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorText } from "../api";
import { Confirm, fillTemplate, MailView, useToast } from "../lib";
import type { Settings, Tracker, User } from "../types";

export default function InvitationEmail({ user }: { user: User }) {
  const qc = useQueryClient();
  const toast = useToast();
  const canEdit = user.role !== "viewer";
  const s = useQuery({ queryKey: ["settings"], queryFn: () => api.get<Settings>("/api/settings") });
  const t = useQuery({ queryKey: ["tracker"], queryFn: () => api.get<Tracker>("/api/tracker") });
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [dirty, setDirty] = useState(false);
  const [reset, setReset] = useState(false);
  const ta = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (s.data && !dirty) { setSubject(s.data.email.subject); setBody(s.data.email.body); }
  }, [s.data, dirty]);
  if (!s.data) return <div className="loading">Loading…</div>;
  const sample = t.data?.applications.find((a) => a.email_ok) ?? t.data?.applications[0];
  const base = s.data.delivery.link_base || s.data.delivery.server.public_url;
  const vals = {
    organization: s.data.organization.name || "your organization", team_name: s.data.organization.team_name || "QE Assessment team",
    first_name: (sample?.respondent_name || "Jordan").split(" ")[0], name: sample?.respondent_name || "Jordan Lee",
    application: sample?.name || "Customer portal", project_id: sample?.project_id || "PRJ-1042", lob: sample?.lob || "Customer & Digital Channels",
    team: sample?.team || "", due_date: new Date(Date.now() + s.data.campaign.default_due_days * 864e5).toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" }),
    survey_link: `${base}/s/example-link`,
  };
  const insert = (ph: string) => {
    const el = ta.current;
    if (!el) return;
    const a = el.selectionStart ?? body.length, b = el.selectionEnd ?? a;
    const nb = body.slice(0, a) + ph + body.slice(b);
    setBody(nb);
    setDirty(true);
    requestAnimationFrame(() => { el.focus(); el.selectionStart = el.selectionEnd = a + ph.length; });
  };
  const save = async () => {
    try { await api.put("/api/settings/email", { subject, body }); toast("Invitation email saved"); setDirty(false); qc.invalidateQueries({ queryKey: ["settings"] }); }
    catch (e) { toast(errorText(e), true); }
  };
  const doReset = async () => {
    setReset(false);
    try { await api.post("/api/settings/email/reset"); setDirty(false); await qc.invalidateQueries({ queryKey: ["settings"] }); toast("Default text restored"); }
    catch (e) { toast(errorText(e), true); }
  };
  return (
    <>
      <p className="eyebrow">Setup</p><h1>Invitation email</h1>
      <p className="lede">One message for every invitation; the placeholders fill in for each application. Reminders reuse it with "Reminder:" in front of the subject.</p>
      <div className="mailgrid">
        <div className="panel">
          <label className="f" htmlFor="esub">Subject</label>
          <input id="esub" type="text" value={subject} readOnly={!canEdit} onChange={(e) => { setSubject(e.target.value); setDirty(true); }} />
          <label className="f" htmlFor="ebody" style={{ marginTop: 12 }}>Message</label>
          <textarea id="ebody" ref={ta} rows={18} value={body} readOnly={!canEdit} onChange={(e) => { setBody(e.target.value); setDirty(true); }} />
          {canEdit && <>
            <p className="small muted" style={{ margin: "10px 0 0" }}>Insert a placeholder at the cursor:</p>
            <div className="chips">{s.data.placeholders.map((p) => <button type="button" key={p} onClick={() => insert(p)}>{p}</button>)}</div>
            {!body.includes("{survey_link}") && <div className="note err">Add {"{survey_link}"} so respondents can open the survey.</div>}
            <div className="row" style={{ marginTop: 12 }}>
              <button type="button" className="btn primary" disabled={!dirty} onClick={save}>Save</button>
              {dirty && <button type="button" className="btn" onClick={() => setDirty(false)}>Discard changes</button>}
              <button type="button" className="btn ghost" onClick={() => setReset(true)}>Restore default text</button>
            </div>
          </>}
        </div>
        <div><p className="small muted" style={{ margin: "0 0 8px" }}>Preview for {vals.application}</p>
          <MailView subject={fillTemplate(subject, vals)} body={fillTemplate(body, vals)} from={`${s.data.delivery.display_name} <${s.data.delivery.mailbox}>`}
            to={`${vals.name} <${sample?.respondent_email || "jordan.lee@example.com"}>`} /></div>
      </div>
      {reset && <Confirm title="Restore the default text?" action="Restore default" onConfirm={doReset} onClose={() => setReset(false)}><p>Your subject and message are replaced with QE Connect's original wording.</p></Confirm>}
    </>
  );
}
