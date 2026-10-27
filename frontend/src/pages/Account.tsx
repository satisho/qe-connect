import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorText } from "../api";
import { MfaSetup } from "../components/MfaSetup";
import { Modal, useToast } from "../lib";
import type { AuthState, User } from "../types";

export function AccountModal({ user, onClose }: { user: User; onClose: () => void }) {
  const toast = useToast();
  const qc = useQueryClient();
  const auth = useQuery({ queryKey: ["auth"], queryFn: () => api.get<AuthState>("/api/auth/state") });
  const [cur, setCur] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [err, setErr] = useState("");
  const [setup, setSetup] = useState(false);
  const [offPw, setOffPw] = useState("");
  const [offErr, setOffErr] = useState("");
  const save = async () => {
    setErr("");
    if (pw !== pw2) return setErr("The new passwords don't match.");
    try {
      await api.post("/api/auth/password", { current: cur, new: pw });
      toast("Password changed. Other sign-ins were signed out.");
      setCur(""); setPw(""); setPw2("");
    } catch (e) { setErr(errorText(e)); }
  };
  const turnOff = async () => {
    setOffErr("");
    try { await api.post("/api/auth/mfa/disable", { password: offPw }); setOffPw(""); toast("Sign-in codes turned off"); qc.invalidateQueries({ queryKey: ["auth"] }); }
    catch (e) { setOffErr(errorText(e)); }
  };
  const mfaOn = auth.data?.user?.mfa_enabled ?? user.mfa_enabled;
  const required = auth.data?.mfa_required;
  return (
    <Modal title="Password and sign-in codes" onClose={onClose}>
      <div style={{ display: "grid", gap: 18 }}>
        <section className="panel" style={{ margin: 0 }}>
          <header><h2>Sign-in codes</h2><p className="small muted" style={{ margin: 0 }}>A code from an authenticator app on your phone, asked for after your password.</p></header>
          {mfaOn ? <>
            <p style={{ margin: "0 0 10px" }}><span className="tag ok">On</span> Your account asks for a code at every sign-in.</p>
            {required ? <p className="small muted" style={{ margin: 0 }}>Your administrator requires sign-in codes for everyone, so they can't be turned off.</p> : (
              <div className="row" style={{ alignItems: "flex-end" }}>
                <div><label className="f" htmlFor="offpw">Your password, to turn codes off</label><input id="offpw" type="password" value={offPw} onChange={(e) => setOffPw(e.target.value)} autoComplete="current-password" /></div>
                <button type="button" className="btn danger" disabled={!offPw} onClick={turnOff}>Turn off</button>
              </div>)}
            {offErr && <div className="note err" role="alert">{offErr}</div>}
          </> : setup ? <MfaSetup compact onDone={() => { setSetup(false); toast("Sign-in codes are on"); qc.invalidateQueries({ queryKey: ["auth"] }); }} /> : <>
            <p style={{ margin: "0 0 10px" }}><span className="tag warn">Off</span> Anyone with your password can sign in as you.</p>
            <button type="button" className="btn primary" onClick={() => setSetup(true)}>Set up an authenticator app</button>
          </>}
        </section>
        <section className="panel" style={{ margin: 0 }}>
          <header><h2>Change password</h2></header>
          <div style={{ display: "grid", gap: 12 }}>
            <div><label className="f" htmlFor="cur">Current password</label><input id="cur" type="password" value={cur} onChange={(e) => setCur(e.target.value)} autoComplete="current-password" /></div>
            <div><label className="f" htmlFor="npw">New password</label><input id="npw" type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="new-password" />
              <p className="hint">At least 10 characters, with upper and lower case letters and a number.</p></div>
            <div><label className="f" htmlFor="npw2">New password again</label><input id="npw2" type="password" value={pw2} onChange={(e) => setPw2(e.target.value)} autoComplete="new-password" /></div>
            {err && <div className="note err" role="alert">{err}</div>}
            <div><button type="button" className="btn primary" disabled={!cur || !pw} onClick={save}>Change password</button></div>
          </div>
        </section>
      </div>
    </Modal>
  );
}
