import { useEffect, useState, type FormEvent } from "react";
import { api, errorText } from "../api";

/** Authenticator app setup: QR code, the key for manual entry, then a code to confirm. */
export function MfaSetup({ onDone, compact }: { onDone: () => void; compact?: boolean }) {
  const [data, setData] = useState<{ secret: string; qr: string } | null>(null);
  const [code, setCode] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api.post<{ secret: string; qr: string }>("/api/auth/mfa/setup/start").then(setData, (e) => setErr(errorText(e)));
  }, []);
  const confirm = async (e: FormEvent) => {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try { await api.post("/api/auth/mfa/setup/confirm", { code }); onDone(); }
    catch (x) { setErr(errorText(x)); setCode(""); }
    finally { setBusy(false); }
  };
  const key = data?.secret.replace(/(.{4})/g, "$1 ").trim();
  return (
    <form onSubmit={confirm} style={{ display: "grid", gap: 12 }}>
      <ol className="small" style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 4 }}>
        <li>Open an authenticator app on your phone, such as Microsoft Authenticator or Google Authenticator.</li>
        <li>Add an account and scan this code. If you can't scan, type the key instead.</li>
        <li>Enter the 6-digit code the app shows for QE Connect.</li>
      </ol>
      <div className="row" style={{ alignItems: "center", gap: 16 }}>
        {data ? <img src={data.qr} alt="QR code for your authenticator app" width={compact ? 150 : 180} height={compact ? 150 : 180}
          style={{ background: "#fff", borderRadius: 8, border: "1px solid var(--line)" }} /> : <div className="muted small">Preparing…</div>}
        {key && <div style={{ minWidth: 0 }}><span className="f">Key</span><code className="mono" style={{ wordBreak: "break-all", fontSize: 14 }}>{key}</code></div>}
      </div>
      <div><label className="f" htmlFor="mfa-new">Code from the app</label>
        <input id="mfa-new" type="text" inputMode="numeric" autoComplete="one-time-code" maxLength={8} value={code}
          onChange={(e) => setCode(e.target.value)} style={{ maxWidth: 200, letterSpacing: ".2em", fontSize: 18 }} /></div>
      {err && <div className="note err" role="alert">{err}</div>}
      <div><button type="submit" className="btn primary" disabled={busy || code.replace(/\D/g, "").length < 6}>Turn on</button></div>
    </form>
  );
}
