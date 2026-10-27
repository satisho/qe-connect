import { useRef, useState } from "react";
import { api, errorText } from "../api";
import { Confirm } from "../lib";

export interface ImportResult {
  added?: number; updated?: number; imported?: number; sections?: number; sheets?: string[];
  created_lobs?: string[]; warnings?: string[];
}

export function ImportBox({ url, columns, note, replaceLabel, addLabel, replaceWarning, template, onDone, summary, defaultOpen }: {
  url: string; columns: string[]; note: string; replaceLabel: string; addLabel?: string; replaceWarning?: string;
  template?: string; onDone: () => void; summary: (r: ImportResult) => string; defaultOpen?: boolean;
}) {
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<{ ok: boolean; title: string; lines: string[] } | null>(null);
  const [confirm, setConfirm] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const run = async (mode: "replace" | "add") => {
    setConfirm(false);
    if (!file && !text.trim()) return setRes({ ok: false, title: "Choose a file or paste some rows first.", lines: [] });
    const fd = new FormData();
    fd.append("mode", mode);
    if (file) fd.append("file", file);
    else fd.append("text", text);
    setBusy(true);
    try {
      const r = await api.post<ImportResult>(url, fd);
      const lines = [...(r.created_lobs?.length ? [`Added to lines of business: ${r.created_lobs.join(", ")}.`] : []), ...(r.warnings ?? [])];
      setRes({ ok: !(r.warnings?.length), title: summary(r), lines });
      setText("");
      setFile(null);
      if (fileRef.current) fileRef.current.value = "";
      onDone();
    } catch (e) {
      setRes({ ok: false, title: errorText(e), lines: [] });
    } finally {
      setBusy(false);
    }
  };
  const copyHeader = async () => {
    try { await navigator.clipboard.writeText(columns.join("\t")); setRes({ ok: true, title: "Header row copied. Paste it into row 1 in Excel.", lines: [] }); }
    catch { setRes({ ok: false, title: "Your browser blocked copying. Type the column names from the list instead.", lines: [] }); }
  };
  return (
    <details className="panel" open={defaultOpen}>
      <summary>↑ Import from Excel</summary>
      <div className="imp">
        <div>
          <label className="f" htmlFor={`file-${url}`}>Upload an Excel workbook (.xlsx) or CSV file</label>
          <input id={`file-${url}`} ref={fileRef} type="file" accept=".xlsx,.xlsm,.csv,.tsv,.txt" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setRes(null); }} />
          <label className="f" htmlFor={`paste-${url}`} style={{ marginTop: 12 }}>…or paste rows copied from Excel, including the header row</label>
          <textarea id={`paste-${url}`} value={text} disabled={!!file} placeholder={columns.join("\t")} onChange={(e) => setText(e.target.value)} />
        </div>
        <div>
          <p className="small muted" style={{ margin: 0 }}>Expected columns. Order doesn't matter; columns are matched by their header names.</p>
          <div className="cols">{columns.map((c) => <code key={c}>{c}</code>)}</div>
          <p className="small muted">{note}</p>
          <div className="row">
            <button type="button" className="btn primary" disabled={busy} onClick={() => (replaceWarning ? setConfirm(true) : run("replace"))}>{replaceLabel}</button>
            {addLabel && <button type="button" className="btn" disabled={busy} onClick={() => run("add")}>{addLabel}</button>}
            {template && <a className="btn ghost" href={template} download>Download template</a>}
            <button type="button" className="btn ghost" onClick={copyHeader}>Copy header row</button>
          </div>
          {res && <div className={`note ${res.ok ? "ok" : "err"}`} role="status"><b>{res.title}</b>{res.lines.length > 0 && <ul>{res.lines.map((l, i) => <li key={i}>{l}</li>)}</ul>}</div>}
        </div>
      </div>
      {confirm && <Confirm title={replaceLabel + "?"} action={replaceLabel} danger onConfirm={() => run("replace")} onClose={() => setConfirm(false)}><p>{replaceWarning}</p></Confirm>}
    </details>
  );
}
