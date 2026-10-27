import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorText } from "../api";
import { Confirm, fmtDateTime, Modal, useToast } from "../lib";
import type { Role, User } from "../types";

const ROLE_HELP: Record<Role, string> = {
  admin: "Everything, including email delivery, team accounts and backups",
  editor: "Set up applications and questions, send surveys, download responses",
  viewer: "Look at the tracker and download responses",
};

export default function Team({ user }: { user: User }) {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({ queryKey: ["users"], queryFn: () => api.get<User[]>("/api/users") });
  const [add, setAdd] = useState(false);
  const [reset, setReset] = useState<User | null>(null);
  const [del, setDel] = useState<User | null>(null);
  const [mfa, setMfa] = useState<User | null>(null);
  const act = async (fn: () => Promise<unknown>, msg: string) => {
    try { await fn(); toast(msg); qc.invalidateQueries({ queryKey: ["users"] }); } catch (e) { toast(errorText(e), true); }
  };
  return (
    <>
      <div className="spread"><div><p className="eyebrow">Admin</p><h1>Team</h1></div><button type="button" className="btn primary" onClick={() => setAdd(true)}>+ Add person</button></div>
      <p className="lede">People on the assessment team who can sign in. Respondents don't need accounts; their survey link is enough.</p>
      <div className="tbl"><table style={{ minWidth: 760 }}>
        <thead><tr><th>Name</th><th>Role</th><th>Sign-in codes</th><th>Last sign-in</th><th>Status</th><th></th></tr></thead>
        <tbody>{(q.data ?? []).map((u) => (
          <tr key={u.id}>
            <td><b>{u.name}</b>{u.id === user.id && <span className="tag info" style={{ marginLeft: 6 }}>You</span>}<span className="sub">{u.email}</span></td>
            <td><select value={u.role} aria-label={`Role for ${u.name}`} style={{ width: "auto" }} onChange={(e) => act(() => api.patch(`/api/users/${u.id}`, { role: e.target.value }), `${u.name} is now ${e.target.value}`)}>
              <option value="admin">Admin</option><option value="editor">Editor</option><option value="viewer">Viewer</option></select>
              <span className="sub">{ROLE_HELP[u.role]}</span></td>
            <td>{u.mfa_enabled ? <span className="tag ok">On</span> : <span className="tag warn">Off</span>}</td>
            <td className="small">{u.last_login_at ? fmtDateTime(u.last_login_at) : <span className="muted">Never</span>}</td>
            <td>{u.active ? <span className="tag ok">Active</span> : <span className="tag">Deactivated</span>}</td>
            <td><div className="acts">
              <button type="button" className="btn sm ghost" onClick={() => setReset(u)}>Reset password</button>
              {u.mfa_enabled && <button type="button" className="btn sm ghost" onClick={() => setMfa(u)}>Reset codes</button>}
              {u.id !== user.id && <button type="button" className="btn sm ghost" onClick={() => act(() => api.patch(`/api/users/${u.id}`, { active: !u.active }), u.active ? `${u.name} deactivated` : `${u.name} activated`)}>{u.active ? "Deactivate" : "Activate"}</button>}
              {u.id !== user.id && <button type="button" className="btn sm ghost danger" onClick={() => setDel(u)}>Remove</button>}
            </div></td>
          </tr>))}</tbody>
      </table></div>
      {add && <UserModal onClose={() => setAdd(false)} onDone={() => { setAdd(false); qc.invalidateQueries({ queryKey: ["users"] }); }} />}
      {reset && <UserModal reset={reset} onClose={() => setReset(null)} onDone={() => setReset(null)} />}
      {mfa && <Confirm title={`Reset sign-in codes for ${mfa.name}?`} action="Reset codes" onClose={() => setMfa(null)}
        onConfirm={() => { act(() => api.patch(`/api/users/${mfa.id}`, { reset_mfa: true }), `Sign-in codes reset for ${mfa.name}`); setMfa(null); }}>
        <p>Use this when someone has lost or replaced their phone. They are signed out, and set up their authenticator app again{mfa.id === user.id ? "" : " the next time they sign in (if codes are required) or from their account menu"}. Check who is asking before you do this.</p></Confirm>}
      {del && <Confirm title={`Remove ${del.name}?`} action="Remove" danger onClose={() => setDel(null)}
        onConfirm={() => { act(() => api.del(`/api/users/${del.id}`), `${del.name} removed`); setDel(null); }}>
        <p>They can no longer sign in. Their past activity stays in the activity log.</p></Confirm>}
    </>
  );
}

function UserModal({ reset, onClose, onDone }: { reset?: User; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("editor");
  const [pw, setPw] = useState("");
  const [err, setErr] = useState("");
  const go = async () => {
    setErr("");
    try {
      if (reset) await api.patch(`/api/users/${reset.id}`, { password: pw });
      else await api.post("/api/users", { name, email, role, password: pw });
      toast(reset ? `Password reset for ${reset.name}. Share it with them securely.` : `${name || email} added. Share the temporary password with them securely.`);
      onDone();
    } catch (e) { setErr(errorText(e)); }
  };
  return (
    <Modal narrow title={reset ? `Reset password for ${reset.name}` : "Add a person"} onClose={onClose} footer={<>
      <button type="button" className="btn" onClick={onClose}>Cancel</button><button type="button" className="btn primary" onClick={go}>{reset ? "Set password" : "Add person"}</button></>}>
      <div style={{ display: "grid", gap: 12 }}>
        {!reset && <>
          <div><label className="f" htmlFor="un">Name</label><input id="un" type="text" value={name} onChange={(e) => setName(e.target.value)} /></div>
          <div><label className="f" htmlFor="ue">Work email</label><input id="ue" type="email" value={email} onChange={(e) => setEmail(e.target.value)} /></div>
          <div><label className="f" htmlFor="ur">Role</label><select id="ur" value={role} onChange={(e) => setRole(e.target.value as Role)}>
            <option value="editor">Editor</option><option value="viewer">Viewer</option><option value="admin">Admin</option></select><p className="hint">{ROLE_HELP[role]}</p></div>
        </>}
        <div><label className="f" htmlFor="up">{reset ? "New password" : "Temporary password"}</label><input id="up" type="text" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="off" />
          <p className="hint">At least 10 characters, with upper and lower case letters and a number. They can change it after signing in.</p></div>
        {err && <div className="note err" role="alert">{err}</div>}
      </div>
    </Modal>
  );
}
