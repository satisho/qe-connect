import { useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorText } from "../api";
import { ImportBox } from "../components/ImportBox";
import { plural, useToast } from "../lib";
import type { Lob, User } from "../types";

export default function Lobs({ user }: { user: User }) {
  const qc = useQueryClient();
  const toast = useToast();
  const canEdit = user.role !== "viewer";
  const q = useQuery({ queryKey: ["lobs"], queryFn: () => api.get<Lob[]>("/api/lobs") });
  const [name, setName] = useState("");
  const [renaming, setRenaming] = useState<number | null>(null);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["lobs"] }); qc.invalidateQueries({ queryKey: ["tracker"] }); qc.invalidateQueries({ queryKey: ["applications"] }); };
  const act = async (fn: () => Promise<unknown>, msg: string) => {
    try { await fn(); toast(msg); refresh(); } catch (e) { toast(errorText(e), true); }
  };
  const add = (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    act(() => api.post("/api/lobs", { name }), `Added ${name}`).then(() => setName(""));
  };
  return (
    <>
      <p className="eyebrow">Setup</p><h1>Lines of business</h1>
      <p className="lede">These are the choices for the line-of-business question in the survey and the filter on the tracker.</p>
      <div className="panel">
        <div className="lobs">
          {(q.data ?? []).map((l) => (
            <div className="lob" key={l.id}>
              {renaming === l.id ? (
                <input type="text" defaultValue={l.name} autoFocus aria-label="New name" style={{ maxWidth: 420 }}
                  onBlur={(e) => { const v = e.target.value.trim(); setRenaming(null); if (v && v !== l.name) act(() => api.patch(`/api/lobs/${l.id}`, { name: v }), "Renamed"); }}
                  onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); if (e.key === "Escape") setRenaming(null); }} />
              ) : <span><b>{l.name}</b> <span className="small muted">{plural(l.applications, "application")}</span></span>}
              {canEdit && <div className="row" style={{ gap: 4 }}>
                <button type="button" className="btn sm ghost" onClick={() => setRenaming(l.id)}>Rename</button>
                <button type="button" className="btn sm ghost danger" disabled={l.applications > 0} title={l.applications ? "Move its applications to another line of business first" : undefined}
                  onClick={() => act(() => api.del(`/api/lobs/${l.id}`), `Removed ${l.name}`)}>Remove</button>
              </div>}
            </div>
          ))}
          {!q.isLoading && !q.data?.length && <div className="empty">No lines of business yet.</div>}
        </div>
        {canEdit && <form className="row" style={{ marginTop: 12 }} onSubmit={add}>
          <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="New line of business" aria-label="New line of business" style={{ flex: 1, minWidth: 200 }} />
          <button type="submit" className="btn primary">Add</button></form>}
      </div>
      {canEdit && <ImportBox url="/api/lobs/import" columns={["Line of Business"]} note="One per row, for example the LOB column from the Lists tab. Names already on the list are skipped."
        replaceLabel="Add to the list" summary={(r) => `${plural(r.created_lobs?.length ?? 0, "line")} of business added.`} onDone={refresh} />}
    </>
  );
}
