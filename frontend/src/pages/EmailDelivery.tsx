import { useEffect, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorText } from "../api";
import { fmtDateTime, useToast } from "../lib";
import type { Delivery, Settings, User } from "../types";

type Form = Omit<Delivery, "tested" | "server" | "problems">;

export default function EmailDelivery({ user }: { user: User }) {
  const qc = useQueryClient();
  const toast = useToast();
  const admin = user.role === "admin";
  const s = useQuery({ queryKey: ["settings"], queryFn: () => api.get<Settings>("/api/settings") });
  const [f, setF] = useState<Form | null>(null);
  const [dirty, setDirty] = useState(false);
  const [to, setTo] = useState(user.email);
  const [busy, setBusy] = useState(false);
  const d = s.data?.delivery;
  useEffect(() => {
    if (d && !dirty) {
      const { tested: _t, server: _s, problems: _p, ...rest } = d;
      setF(rest);
    }
  }, [d, dirty]);
  if (!d || !f) return <div className="loading">Loading…</div>;
  const set = <K extends keyof Form>(k: K, v: Form[K]) => { setF({ ...f, [k]: v }); setDirty(true); };
  const save = async () => {
    try { await api.put("/api/settings/delivery", f); setDirty(false); await qc.invalidateQueries({ queryKey: ["settings"] }); qc.invalidateQueries({ queryKey: ["tracker"] }); toast("Email delivery saved"); return true; }
    catch (e) { toast(errorText(e), true); return false; }
  };
  const test = async () => {
    if (dirty && !(await save())) return;
    setBusy(true);
    try { await api.post("/api/settings/delivery/test", { to }); await qc.invalidateQueries({ queryKey: ["settings"] }); qc.invalidateQueries({ queryKey: ["emails"] }); }
    catch (e) { toast(errorText(e), true); }
    finally { setBusy(false); }
  };
  const fld = (k: keyof Form, label: string, o: { type?: string; ph?: string; hint?: ReactNode; full?: boolean } = {}) => (
    <div className={o.full ? "full" : ""}>
      <label className="f" htmlFor={`d-${k}`}>{label}</label>
      <input id={`d-${k}`} type={o.type || "text"} value={String(f[k] ?? "")} placeholder={o.ph} readOnly={!admin}
        onChange={(e) => set(k, (o.type === "number" ? Number(e.target.value) : e.target.value) as never)} />
      {o.hint && <p className="hint">{o.hint}</p>}
    </div>
  );
  const seg = <K extends keyof Form>(k: K, opts: [Form[K], string][]) => (
    <div className="seg" role="radiogroup">{opts.map(([v, l]) => (
      <label key={String(v)} className={f[k] === v ? "on" : ""}><input type="radio" name={`d-${String(k)}`} checked={f[k] === v} disabled={!admin} onChange={() => set(k, v)} />{l}</label>))}</div>
  );
  const route = (v: Form["mode"], title: string, desc: string, tag?: ReactNode) => (
    <label className={`route ${f.mode === v ? "on" : ""}`}>
      <input type="radio" name="d-mode" checked={f.mode === v} disabled={!admin} onChange={() => set("mode", v)} />
      <b>{title}{tag}</b><small>{desc}</small>
    </label>
  );
  const srv = d.server;
  const envFlag = (ok: boolean, name: string) => ok
    ? <span className="tag ok">Set on the server</span>
    : <span className="tag warn">Not set: add {name} to the .env file and restart</span>;
  const t = d.tested;

  return (
    <>
      <p className="eyebrow">Setup</p><h1>Email delivery</h1>
      <p className="lede">How QE Connect sends invitations and reminders from inside your organization. Your IT team supplies these details. {!admin && "Only administrators can change them."}</p>
      <div className="routes" role="radiogroup" aria-label="Delivery method">
        {route("graph", "Microsoft 365 (Graph)", "Sends from your organization's mailbox through Microsoft Graph. No SMTP needed.", <span className="tag info">Recommended</span>)}
        {route("smtp", "SMTP relay", "Sends through your Exchange server or an Exchange Online relay connector.")}
        {route("sim", "Not connected", "Emails are recorded under Sent emails only. Use this for demos and dry runs.")}
      </div>
      {f.mode === "graph" && <div className="panel"><header><h2>Microsoft 365 connection</h2><p className="small muted" style={{ margin: 0 }}>From the app registration your IT creates in Microsoft Entra ID.</p></header>
        <div className="fgrid">
          {fld("tenant", "Directory (tenant) ID", { ph: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" })}
          {fld("client", "Application (client) ID", { ph: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" })}
          <div className="full"><span className="f">Sign-in method</span>{seg("auth_type", [["cert", "Certificate (recommended)"], ["secret", "Client secret"]])}</div>
          {f.auth_type === "secret"
            ? <div className="full"><span className="f">Client secret</span>{envFlag(srv.client_secret_set, "QEC_MAIL_CLIENT_SECRET")}
                <p className="hint">Secrets stay on the server, never in the portal or the database.</p></div>
            : <>{fld("cert_thumbprint", "Certificate thumbprint", { ph: "e.g. 3F2A…9B1C" })}
                <div><span className="f">Certificate private key</span>{envFlag(srv.cert_path_set, "QEC_MAIL_CERT_PATH")}</div></>}
          <div className="full"><label className="row" style={{ gap: 8, fontWeight: 550 }}><input className="chk" type="checkbox" checked={f.save_sent} disabled={!admin} onChange={(e) => set("save_sent", e.target.checked)} />Keep a copy in the mailbox's Sent Items</label></div>
        </div></div>}
      {f.mode === "smtp" && <div className="panel"><header><h2>SMTP relay</h2><p className="small muted" style={{ margin: 0 }}>An Exchange receive connector (on-premises) or an Exchange Online relay connector that accepts mail from the QE Connect server.</p></header>
        <div className="fgrid">
          {fld("host", "Server", { ph: "smtp.example.local or example-com.mail.protection.outlook.com" })}
          {fld("port", "Port", { type: "number", ph: "587", hint: "Usually 25 for a relay connector, 587 with sign-in." })}
          <div className="full"><span className="f">Encryption</span>{seg("security", [["starttls", "STARTTLS"], ["tls", "TLS (SMTPS)"], ["none", "None (internal only)"]])}</div>
          <div className="full"><span className="f">Authentication</span>{seg("smtp_auth", [["none", "None, server IP is allow-listed"], ["login", "Username and password"]])}</div>
          {f.smtp_auth === "login" && <>{fld("username", "Username", { ph: "svc-qe-connect@example.com" })}
            <div><span className="f">Password</span>{envFlag(srv.smtp_password_set, "QEC_SMTP_PASSWORD")}</div></>}
        </div>
        {f.smtp_auth === "login" && /office365|outlook/i.test(f.host) && <div className="note warn">Microsoft is retiring basic username-and-password sign-in for SMTP in Exchange Online. Prefer Microsoft 365 (Graph) or an IP-based relay connector.</div>}
      </div>}
      {f.mode !== "sim" && <div className="panel"><header><h2>Sender</h2></header>
        <div className="fgrid">
          {fld("mailbox", "Send from mailbox", { type: "email", ph: "qe-connect@example.com", hint: "A shared mailbox works well, so replies reach the whole team." })}
          {fld("display_name", "Display name", { ph: "QE Connect", hint: f.mode === "graph" ? "Microsoft 365 shows the mailbox's own display name." : undefined })}
          {fld("reply_to", "Reply-to (optional)", { type: "email", ph: "qe-assessment-team@example.com" })}
          {fld("rate_per_minute", "Most emails per minute", { type: "number", hint: "Exchange Online accepts about 30 messages a minute per mailbox." })}
        </div></div>}
      <div className="panel"><header><h2>Survey links</h2></header>
        <div className="fgrid">{fld("link_base", "Survey link address", { full: true, ph: srv.public_url,
          hint: <>The address respondents open from the email. It must be reachable from their computers and phones (your network or VPN). Leave empty to use {srv.public_url} from the server settings.</> })}</div></div>
      {admin && (dirty ? <div className="sticky-save"><button type="button" className="btn" onClick={() => setDirty(false)}>Discard</button><button type="button" className="btn primary" onClick={save}>Save email delivery</button></div> : null)}

      {admin && <div className="panel"><header><h2>Send a test email</h2><p className="small muted" style={{ margin: 0 }}>Checks the settings and sends one message. Invitations can go out once this passes.</p></header>
        <div className="row"><input type="email" value={to} onChange={(e) => setTo(e.target.value)} aria-label="Test recipient" style={{ flex: 1, minWidth: 220 }} />
          <button type="button" className="btn primary" disabled={busy} onClick={test}>{busy ? "Sending…" : dirty ? "Save and send test" : "Send test"}</button></div>
        {t && <><ul className="steps">{t.steps.map((x, i) => <li key={i} className={x.ok ? "ok" : "bad"}><span className="ic">{x.ok ? "✓" : "!"}</span><span>{x.text}</span></li>)}</ul>
          <p className="hint">{t.ok ? `Passed ${fmtDateTime(t.at)}.` : "Fix the items marked ! and test again."}</p></>}
        {!t && d.problems.length > 0 && f.mode !== "sim" && <div className="note warn"><b>Still needed:</b><ul>{d.problems.map((p) => <li key={p}>{p}</li>)}</ul></div>}
      </div>}

      <details className="panel"><summary>What to ask your IT team for</summary>
        <ul className="ask">
          {f.mode === "smtp" ? <>
            <li>An SMTP relay (receive connector) that accepts mail from the QE Connect server's IP address, with its host name and port.</li>
            <li>Permission for that relay to send as the QE Connect mailbox.</li></> : <>
            <li>A Microsoft Entra ID app registration with the Mail.Send application permission and admin consent.</li>
            <li>An application access policy (or RBAC for Applications scope) that limits the app to the QE Connect mailbox only, so it cannot send as anyone else.</li>
            <li>A certificate (preferred) or client secret for the app, with its expiry date.</li></>}
          <li>A shared mailbox such as qe-connect@example.com, with the assessment team as members so they see replies.</li>
          <li>An internal web address (DNS name and certificate) for the survey links.</li>
          <li>Outbound access from the QE Connect server to {f.mode === "smtp" ? "the relay host and port" : "graph.microsoft.com and login.microsoftonline.com on port 443"}.</li>
        </ul></details>
    </>
  );
}
