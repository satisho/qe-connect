import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorText } from "../api";
import { ImportBox } from "../components/ImportBox";
import { Confirm, emailOk, Modal, Pill, plural, useToast } from "../lib";
import type { App, Lob, User } from "../types";

const COLS = ["Application", "Project ID", "Line of Business", "Delivery team / ART", "Respondent name", "Respondent email"];
type Field = "name" | "project_id" | "team" | "respondent_name" | "respondent_email";

export default function Applications({ user }: { user: User }) {
  const qc = useQueryClient();
  const toast = useToast();
  const canEdit = user.role !== "viewer";
  const apps = useQuery({ queryKey: ["applications"], queryFn: () => api.get<App[]>("/api/applications") });
  const lobs = useQuery({ queryKey: ["lobs"], queryFn: () => api.get<Lob[]>("/api/lobs") });
  const [del, setDel] = useState<App | null>(null);
  const [adding, setAdding] = useState(false);
  const refresh = () => ["applications", "tracker", "lobs"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));

  const save = async (a: App, patch: Partial<App>) => {
    try { await api.patch(`/api/applications/${a.id}`, patch); refresh(); toast(`Saved ${a.name}`); }
    catch (e) { toast(errorText(e), true); refresh(); }
  };
  const remove = async () => {
    if (!del) return;
    try { await api.del(`/api/applications/${del.id}`); toast(`Removed ${del.name}`); setDel(null); refresh(); }
    catch (e) { toast(errorText(e), true); }
  };
  const list = apps.data ?? [];
  const cell = (a: App, f: Field, label: string, type = "text") => (
    <input type={type} defaultValue={a[f]} key={`${a.id}-${f}-${a[f]}`} aria-label={`${label} for ${a.name}`} readOnly={!canEdit}
      className={f === "respondent_email" && a[f] && !emailOk(a[f]) ? "bad" : ""}
      placeholder={f === "respondent_email" ? "name@bcferries.com" : ""}
      onBlur={(e) => { const v = e.target.value.trim(); if (canEdit && v !== a[f]) save(a, { [f]: v }); }}
      onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
  );

  return (
    <>
      <div className="spread"><div><p className="eyebrow">Setup</p><h1>Applications &amp; respondents</h1></div>
        {canEdit && <button type="button" className="btn primary" onClick={() => setAdding(true)}>+ Add application</button>}</div>
      <p className="lede">Each application gets one survey, sent to the respondent named here. Changes save when you leave a field.</p>
      {canEdit && <ImportBox url="/api/applications/import" columns={COLS} template="/api/templates/applications.xlsx"
        note="Rows that match an existing application (same name and project ID) update it and keep its survey. Unknown lines of business are added to the list."
        replaceLabel="Replace all applications" addLabel="Add or update"
        replaceWarning="Every current application is removed, along with its survey link and any response already received. Download the completed responses first if you need them."
        summary={(r) => `${plural(r.added ?? 0, "application")} added, ${r.updated ?? 0} updated.`} onDone={refresh} defaultOpen={!list.length && !apps.isLoading} />}
      {apps.isLoading ? <div className="loading">Loading…</div> : (
        <div className="tbl">
          <table className="edit">
            <thead><tr><th>Application</th><th>Project ID</th><th>Line of business</th><th>Delivery team / ART</th><th>Respondent</th><th>Respondent email</th><th>Survey</th><th></th></tr></thead>
            <tbody>
              {list.map((a) => (
                <tr key={a.id}>
                  <td>{cell(a, "name", "Application")}</td>
                  <td style={{ width: 120 }}>{cell(a, "project_id", "Project ID")}</td>
                  <td><select value={a.lob_id ?? ""} disabled={!canEdit} aria-label={`Line of business for ${a.name}`}
                    onChange={(e) => save(a, { lob_id: e.target.value ? Number(e.target.value) : null })}>
                    <option value="">Not set</option>{(lobs.data ?? []).map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}</select></td>
                  <td>{cell(a, "team", "Delivery team")}</td>
                  <td>{cell(a, "respondent_name", "Respondent name")}</td>
                  <td>{cell(a, "respondent_email", "Respondent email", "email")}</td>
                  <td><Pill s={a.status} /></td>
                  <td>{canEdit && <button type="button" className="btn sm ghost danger" onClick={() => setDel(a)} aria-label={`Remove ${a.name}`}>Remove</button>}</td>
                </tr>
              ))}
              {!list.length && <tr><td colSpan={8} className="empty">No applications yet. Import them from Excel or add them one at a time.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
      {del && <Confirm title={`Remove ${del.name}?`} action="Remove application" danger onConfirm={remove} onClose={() => setDel(null)}>
        <p>{del.status === "completed" ? "Its completed response is deleted too. Download it from the Tracker first if you need it."
          : del.status !== "notsent" ? "Its survey link stops working and any answers saved so far are deleted." : "It hasn't been sent a survey yet."}</p></Confirm>}
      {adding && <AddApp lobs={lobs.data ?? []} onClose={() => setAdding(false)} onDone={() => { setAdding(false); refresh(); }} />}
    </>
  );
}

function AddApp({ lobs, onClose, onDone }: { lobs: Lob[]; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const [f, setF] = useState({ name: "", project_id: "", lob_id: String(lobs[0]?.id ?? ""), team: "", respondent_name: "", respondent_email: "" });
  const [err, setErr] = useState("");
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const go = async () => {
    setErr("");
    if (f.respondent_email && !emailOk(f.respondent_email)) return setErr("The respondent email doesn't look right.");
    try {
      await api.post("/api/applications", { ...f, lob_id: f.lob_id === "" ? null : Number(f.lob_id) });
      toast(`Added ${f.name}`);
      onDone();
    } catch (e) { setErr(errorText(e)); }
  };
  return (
    <Modal title="Add an application" onClose={onClose} footer={<><button type="button" className="btn" onClick={onClose}>Cancel</button>
      <button type="button" className="btn primary" onClick={go} disabled={!f.name.trim()}>Add application</button></>}>
      <div className="fgrid">
        <div><label className="f" htmlFor="na">Application</label><input id="na" type="text" value={f.name} onChange={set("name")} /></div>
        <div><label className="f" htmlFor="np">Project ID (optional)</label><input id="np" type="text" value={f.project_id} onChange={set("project_id")} /></div>
        <div><label className="f" htmlFor="nl">Line of business</label><select id="nl" value={f.lob_id} onChange={set("lob_id")}>
          <option value="">Not set</option>{lobs.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}</select></div>
        <div><label className="f" htmlFor="nt">Delivery team / ART</label><input id="nt" type="text" value={f.team} onChange={set("team")} /></div>
        <div><label className="f" htmlFor="nr">Respondent name</label><input id="nr" type="text" value={f.respondent_name} onChange={set("respondent_name")} /></div>
        <div><label className="f" htmlFor="ne">Respondent email</label><input id="ne" type="email" value={f.respondent_email} onChange={set("respondent_email")} placeholder="name@bcferries.com" /></div>
      </div>
      {err && <div className="note err" role="alert">{err}</div>}
    </Modal>
  );
}
