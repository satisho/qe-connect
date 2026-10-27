import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorText } from "../api";
import { Confirm, Modal, useToast } from "../lib";
import type { Policy, Settings, User } from "../types";

export default function Administration(_: { user: User }) {
  const qc = useQueryClient();
  const toast = useToast();
  const s = useQuery({ queryKey: ["settings"], queryFn: () => api.get<Settings>("/api/settings") });
  const pol = useQuery({ queryKey: ["policy"], queryFn: () => api.get<Policy>("/api/security/policy") });
  const [name, setName] = useState("");
  const [days, setDays] = useState(14);
  const [req, setReq] = useState(false);
  const [idle, setIdle] = useState(30);
  const [sample, setSample] = useState(false);
  const [backup, setBackup] = useState(false);
  const [restore, setRestore] = useState<File | null>(null);
  const [restorePw, setRestorePw] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  useEffect(() => { if (s.data) { setName(s.data.campaign.name); setDays(s.data.campaign.default_due_days); } }, [s.data]);
  useEffect(() => { if (pol.data) { setReq(pol.data.mfa_required); setIdle(pol.data.idle_minutes); } }, [pol.data]);
  const all = () => qc.invalidateQueries();
  const saveCampaign = async () => {
    try { await api.put("/api/settings/campaign", { name, default_due_days: days }); toast("Saved"); all(); } catch (e) { toast(errorText(e), true); }
  };
  const savePolicy = async () => {
    try { await api.put("/api/security/policy", { mfa_required: req, idle_minutes: idle }); toast("Security settings saved"); qc.invalidateQueries({ queryKey: ["policy"] }); }
    catch (e) { toast(errorText(e), true); }
  };
  const loadSample = async () => {
    setSample(false);
    try { await api.post("/api/sample"); toast("Sample data loaded"); all(); } catch (e) { toast(errorText(e), true); }
  };
  const doRestore = async () => {
    if (!restore) return;
    const fd = new FormData();
    fd.append("file", restore);
    if (restorePw) fd.append("password", restorePw);
    try {
      const r = await api.post<{ applications: number; questions: number }>("/api/workspace/import", fd);
      toast(`Restored ${r.applications} applications and ${r.questions} questions`);
      setRestore(null); setRestorePw("");
      if (fileRef.current) fileRef.current.value = "";
      all();
    } catch (e) { toast(errorText(e), true); }
  };
  const missing = pol.data?.users_without_mfa ?? [];
  const dirtyPolicy = pol.data && (req !== pol.data.mfa_required || idle !== pol.data.idle_minutes);
  return (
    <>
      <p className="eyebrow">Admin</p><h1>Administration</h1>
      <div className="panel"><header><h2>Sign-in security</h2></header>
        <div className="fgrid">
          <div className="full"><label className="row" style={{ gap: 8, fontWeight: 600 }}>
            <input className="chk" type="checkbox" checked={req} onChange={(e) => setReq(e.target.checked)} />Require sign-in codes (an authenticator app) for everyone</label>
            <p className="hint">People without an authenticator app are asked to set one up at their next sign-in.
              {missing.length > 0 && <> Not set up yet: {missing.join(", ")}.</>}</p></div>
          <div><label className="f" htmlFor="idle">Sign out after this many minutes without activity</label>
            <input id="idle" type="number" min={0} max={720} value={idle} onChange={(e) => setIdle(Number(e.target.value))} />
            <p className="hint">0 turns this off. Sessions always end after the maximum set on the server (12 hours by default).</p></div>
        </div>
        <div className="row" style={{ marginTop: 12 }}><button type="button" className="btn primary" disabled={!dirtyPolicy} onClick={savePolicy}>Save security settings</button></div>
      </div>
      <div className="panel"><header><h2>Survey</h2></header>
        <div className="fgrid">
          <div><label className="f" htmlFor="cn">Survey name</label><input id="cn" type="text" value={name} onChange={(e) => setName(e.target.value)} />
            <p className="hint">Shown in the portal header and at the top of the respondent's survey.</p></div>
          <div><label className="f" htmlFor="cd">Default days to respond</label><input id="cd" type="number" min={1} max={120} value={days} onChange={(e) => setDays(Number(e.target.value))} />
            <p className="hint">Sets the starting "respond by" date when you send invitations.</p></div>
        </div>
        <div className="row" style={{ marginTop: 12 }}><button type="button" className="btn primary" onClick={saveCampaign}>Save</button></div>
      </div>
      <div className="panel"><header><h2>Backup and restore</h2>
        <p className="small muted" style={{ margin: 0 }}>A backup holds the applications, respondents, questions, lines of business, settings, survey links, responses and sent emails, protected with a password you choose. Team accounts and server secrets aren't included.</p></header>
        <div className="row">
          <button type="button" className="btn" onClick={() => setBackup(true)}>↓ Download backup…</button>
          <label className="btn" htmlFor="restore">Restore from a backup…</label>
          <input id="restore" ref={fileRef} type="file" accept=".qecbackup,.json" className="sr" onChange={(e) => setRestore(e.target.files?.[0] ?? null)} />
        </div>
        <p className="hint">Keep backups somewhere only the assessment team can reach. On a laptop install you can also back up by copying the data folder while QE Connect is stopped.</p>
      </div>
      <div className="panel"><header><h2>Sample data</h2>
        <p className="small muted" style={{ margin: 0 }}>Loads two lines of business, seven applications, the starter question bank and a few example responses, for demos and training.</p></header>
        <button type="button" className="btn" onClick={() => setSample(true)}>Load sample data…</button>
      </div>
      {backup && <BackupModal onClose={() => setBackup(false)} />}
      {sample && <Confirm title="Replace everything with sample data?" action="Load sample data" danger onConfirm={loadSample} onClose={() => setSample(false)}>
        <p>All current applications, questions, lines of business, survey links, responses and sent emails are deleted. Download a backup first if you might need them.</p></Confirm>}
      {restore && <Modal narrow title={`Restore ${restore.name}?`} onClose={() => { setRestore(null); setRestorePw(""); if (fileRef.current) fileRef.current.value = ""; }}
        footer={<><button type="button" className="btn" onClick={() => setRestore(null)}>Cancel</button><button type="button" className="btn danger solid" onClick={doRestore}>Restore backup</button></>}>
        <p style={{ marginTop: 0 }}>Everything currently in QE Connect except team accounts is replaced by the backup. Survey links in the backup start working again.</p>
        {restore.name.endsWith(".qecbackup") && <div><label className="f" htmlFor="rpw">Backup password</label><input id="rpw" type="password" value={restorePw} onChange={(e) => setRestorePw(e.target.value)} autoComplete="off" /></div>}
      </Modal>}
    </>
  );
}

function BackupModal({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const go = async () => {
    setErr("");
    if (pw !== pw2) return setErr("The passwords don't match.");
    setBusy(true);
    try {
      const res = await fetch("/api/workspace/export", { method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-QEC": "1" }, body: JSON.stringify({ password: pw }) });
      if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "The backup couldn't be made."); }
      const blob = await res.blob();
      const name = /filename="([^"]+)"/.exec(res.headers.get("content-disposition") || "")?.[1] || "QE_Connect_backup.qecbackup";
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
      toast("Backup downloaded. Keep the password somewhere safe; without it the backup can't be restored.");
      onClose();
    } catch (e) { setErr(errorText(e)); }
    finally { setBusy(false); }
  };
  return (
    <Modal narrow title="Download a backup" onClose={onClose} footer={<><button type="button" className="btn" onClick={onClose}>Cancel</button>
      <button type="button" className="btn primary" disabled={busy || !pw} onClick={go}>Download backup</button></>}>
      <div style={{ display: "grid", gap: 12 }}>
        <p style={{ margin: 0 }}>The backup is encrypted with this password. Nobody, including QE Connect, can open it without the password.</p>
        <div><label className="f" htmlFor="bpw">Backup password</label><input id="bpw" type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="new-password" />
          <p className="hint">At least 10 characters, with upper and lower case letters and a number.</p></div>
        <div><label className="f" htmlFor="bpw2">Password again</label><input id="bpw2" type="password" value={pw2} onChange={(e) => setPw2(e.target.value)} autoComplete="new-password" /></div>
        {err && <div className="note err" role="alert">{err}</div>}
      </div>
    </Modal>
  );
}
