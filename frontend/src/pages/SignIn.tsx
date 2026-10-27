import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, errorText } from "../api";
import { MfaSetup } from "../components/MfaSetup";
import { Mark } from "../lib";
import type { Pending } from "../types";

export default function SignIn({ needsSetup, version, pending, notice }: { needsSetup: boolean; version: string; pending: Pending | null; notice?: string | null }) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [code, setCode] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const refresh = () => qc.invalidateQueries();

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setErr("");
    if (needsSetup && pw !== pw2) return setErr("The two passwords don't match.");
    setBusy(true);
    try {
      if (needsSetup) await api.post("/api/auth/setup", { name, email, password: pw });
      else await api.post("/api/auth/login", { email, password: pw });
      setPw("");
      await refresh();
    } catch (x) {
      setErr(errorText(x));
    } finally {
      setBusy(false);
    }
  };
  const verify = async (e: FormEvent) => {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try { await api.post("/api/auth/mfa/verify", { code }); await refresh(); }
    catch (x) { setErr(errorText(x)); setCode(""); if ((x as { status?: number }).status === 401 && /timed out/.test(errorText(x))) await refresh(); }
    finally { setBusy(false); }
  };
  const restart = async () => { await api.post("/api/auth/logout"); setErr(""); await refresh(); };

  const brand = <div className="brand"><Mark /><div><b>QE Connect</b><small>BC Ferries · QE Assessment portal</small></div></div>;

  if (pending?.step === "verify") return (
    <div className="auth"><form className="card" onSubmit={verify} noValidate>
      {brand}
      <div><h1 style={{ fontSize: 24 }}>Enter your code</h1><p className="muted" style={{ margin: 0 }}>Open your authenticator app and enter the 6-digit code for QE Connect ({pending.email}).</p></div>
      <div><label className="f" htmlFor="code">Code</label>
        <input id="code" type="text" inputMode="numeric" autoComplete="one-time-code" maxLength={8} autoFocus value={code}
          onChange={(e) => setCode(e.target.value)} style={{ letterSpacing: ".25em", fontSize: 20 }} /></div>
      {err && <div className="note err" role="alert">{err}</div>}
      <button className="btn primary" type="submit" disabled={busy || code.replace(/\D/g, "").length < 6} style={{ justifyContent: "center" }}>Sign in</button>
      <p className="small muted" style={{ margin: 0 }}>Lost your phone? Ask a QE Connect administrator to reset your authenticator. <button type="button" className="btn sm ghost" onClick={restart}>Use another account</button></p>
    </form></div>
  );

  if (pending?.step === "setup") return (
    <div className="auth"><div className="card" style={{ width: "min(520px, 100%)" }}>
      {brand}
      <div><h1 style={{ fontSize: 24 }}>Set up sign-in codes</h1><p className="muted" style={{ margin: 0 }}>Your administrator requires an authenticator app for everyone. It takes about a minute.</p></div>
      <MfaSetup onDone={refresh} />
      <button type="button" className="btn sm ghost" onClick={restart} style={{ justifySelf: "start" }}>Cancel and sign out</button>
    </div></div>
  );

  return (
    <div className="auth">
      <form className="card" onSubmit={submit} noValidate>
        {brand}
        {needsSetup ? (
          <>
            <div><h1 style={{ fontSize: 24 }}>Set up QE Connect</h1>
              <p className="muted" style={{ margin: 0 }}>Create the first administrator account. You can add the rest of the assessment team afterwards.</p></div>
            <div><label className="f" htmlFor="name">Your name</label><input id="name" type="text" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" required /></div>
          </>
        ) : (
          <div><h1 style={{ fontSize: 24 }}>Sign in</h1><p className="muted" style={{ margin: 0 }}>For the QE Assessment team.</p></div>
        )}
        {notice && !needsSetup && <div className="note warn" role="status">{notice}</div>}
        <div><label className="f" htmlFor="email">Work email</label><input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" required /></div>
        <div><label className="f" htmlFor="pw">Password</label><input id="pw" type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete={needsSetup ? "new-password" : "current-password"} required />
          {needsSetup && <p className="hint">At least 10 characters, with upper and lower case letters and a number.</p>}</div>
        {needsSetup && <div><label className="f" htmlFor="pw2">Password again</label><input id="pw2" type="password" value={pw2} onChange={(e) => setPw2(e.target.value)} autoComplete="new-password" required /></div>}
        {err && <div className="note err" role="alert">{err}</div>}
        <button className="btn primary" type="submit" disabled={busy} style={{ justifyContent: "center" }}>{needsSetup ? "Create account and continue" : "Sign in"}</button>
        <p className="small muted" style={{ margin: 0, textAlign: "center" }}>QE Connect {version}</p>
      </form>
    </div>
  );
}
