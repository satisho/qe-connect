import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorText } from "../api";
import { ImportBox } from "../components/ImportBox";
import { Modal, plural, useToast } from "../lib";
import type { Question, User } from "../types";

const COLS = ["Q ID", "Section", "Pillar", "Focus area", "Question (as shown to respondent)", "Help text", "Response type",
  "Answer options (one per line)", "Required?", "Priority", "Show-if logic", "Source", "EQA dimension"];
const TYPES: Record<Question["rtype"], string> = { short: "Short text", long: "Long text", single: "Single choice", multi: "Multiple choice", number: "Number" };

export function RuleTag({ q }: { q: Question }) {
  const r = q.rule;
  if (!r) return null;
  if (r.kind === "lobs") return <span className="tag info">Options from LOB list</span>;
  if (r.kind === "bad") return <span className="tag warn" title={q.show_if}>Rule not recognised, always shown</span>;
  return <span className="tag ok" title={q.show_if}>Shown if {r.qid} {r.negate ? "is not" : "is"} {plural(r.values ?? 0, "value")}</span>;
}

export default function Questions({ user }: { user: User }) {
  const qc = useQueryClient();
  const canEdit = user.role !== "viewer";
  const q = useQuery({ queryKey: ["questions"], queryFn: () => api.get<Question[]>("/api/questions") });
  const [edit, setEdit] = useState<Question | null>(null);
  const list = q.data ?? [];
  const sections: { key: string; items: Question[] }[] = [];
  list.forEach((x) => {
    const last = sections[sections.length - 1];
    if (last && last.key === x.section) last.items.push(x);
    else sections.push({ key: x.section, items: [x] });
  });
  const bad = list.filter((x) => x.rule?.kind === "bad").length;
  const refresh = () => { qc.invalidateQueries({ queryKey: ["questions"] }); qc.invalidateQueries({ queryKey: ["lobs"] }); qc.invalidateQueries({ queryKey: ["tracker"] }); };
  return (
    <>
      <div className="spread"><div><p className="eyebrow">Setup</p><h1>Question bank</h1></div>
        <a className="btn" href="/preview" target="_blank" rel="noreferrer">Preview survey ↗</a></div>
      <p className="lede">{plural(list.length, "question")} in {plural(sections.length, "section")}, {list.filter((x) => x.core).length} of them Core.
        {bad > 0 && <b className="bad-t"> {plural(bad, "show-if rule")} could not be read; use Edit to fix {bad > 1 ? "them" : "it"}.</b>}</p>
      {canEdit && <ImportBox url="/api/questions/import" columns={COLS} template="/api/templates/questions.xlsx"
        note="Upload the question bank workbook as it is: every sheet with a Q ID and Question column is read (for example Survey Questions and Additional Survey Questions), and a Lists sheet adds its lines of business. Show-if rules are read in the form Show if B8 is not 'None' or 'Not known'."
        replaceLabel="Replace the question bank" addLabel="Add or update by Q ID"
        replaceWarning="All current questions are replaced. Responses already received keep their answers, matched by Q ID."
        summary={(r) => `${plural(r.imported ?? 0, "question")} imported in ${plural(r.sections ?? 0, "section")}${r.sheets?.length ? ` from ${r.sheets.join(", ")}` : ""}.`}
        onDone={refresh} defaultOpen={!list.length && !q.isLoading} />}
      {q.isLoading ? <div className="loading">Loading…</div> : (
        <div className="tbl"><table style={{ minWidth: 860 }}>
          <thead><tr><th>ID</th><th>Question</th><th>Type</th><th>Required</th><th>Priority</th><th>Rule</th><th></th></tr></thead>
          <tbody>
            {sections.map((s) => [
              <tr className="group" key={s.key}><td colSpan={7}>{s.key}</td></tr>,
              ...s.items.map((x) => (
                <tr key={x.id}>
                  <td className="mono">{x.qid}</td>
                  <td>{x.text}<span className="sub">{[x.pillar, x.focus].filter(Boolean).join(" · ")}{x.options.length ? ` · ${plural(x.options.length, "option")}` : ""}</span></td>
                  <td style={{ whiteSpace: "nowrap" }}>{TYPES[x.rtype]}</td><td>{x.required ? "Yes" : "No"}</td>
                  <td>{x.core ? <span className="tag info">Core</span> : <span className="tag">Optional</span>}</td>
                  <td><RuleTag q={x} /></td>
                  <td>{canEdit && <button type="button" className="btn sm ghost" onClick={() => setEdit(x)}>Edit</button>}</td>
                </tr>
              )),
            ])}
            {!list.length && <tr><td colSpan={7} className="empty">No questions yet. Import the question bank workbook.</td></tr>}
          </tbody>
        </table></div>
      )}
      {edit && <EditQuestion q={edit} onClose={() => setEdit(null)} onDone={() => { setEdit(null); refresh(); }} />}
    </>
  );
}

function EditQuestion({ q, onClose, onDone }: { q: Question; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const [text, setText] = useState(q.text);
  const [help, setHelp] = useState(q.help);
  const [req, setReq] = useState(q.required);
  const [core, setCore] = useState(q.core);
  const [show, setShow] = useState(q.show_if);
  const [opts, setOpts] = useState(q.options.join("\n"));
  const [err, setErr] = useState("");
  const choice = q.rtype === "single" || q.rtype === "multi";
  const go = async () => {
    try {
      await api.patch(`/api/questions/${q.id}`, { text, help, required: req, core, show_if: show, ...(choice ? { options: opts.split("\n") } : {}) });
      toast(`Saved ${q.qid}`);
      onDone();
    } catch (e) { setErr(errorText(e)); }
  };
  return (
    <Modal eyebrow={`${q.qid} · ${TYPES[q.rtype]}`} title="Edit question" onClose={onClose} footer={<>
      <button type="button" className="btn" onClick={onClose}>Cancel</button><button type="button" className="btn primary" onClick={go}>Save</button></>}>
      <div style={{ display: "grid", gap: 12 }}>
        <div><label className="f" htmlFor="qt">Question</label><textarea id="qt" rows={2} value={text} onChange={(e) => setText(e.target.value)} /></div>
        <div><label className="f" htmlFor="qh">Help text</label><input id="qh" type="text" value={help} onChange={(e) => setHelp(e.target.value)} /></div>
        {choice && <div><label className="f" htmlFor="qo">Answer options, one per line</label><textarea id="qo" rows={6} value={opts} onChange={(e) => setOpts(e.target.value)} />
          <p className="hint">An option starting with "Other" asks the respondent to specify. In multiple choice, an option starting with "None of" clears the others.</p></div>}
        <div className="row">
          <label className="row" style={{ gap: 6 }}><input className="chk" type="checkbox" checked={req} onChange={(e) => setReq(e.target.checked)} />Required</label>
          <label className="row" style={{ gap: 6 }}><input className="chk" type="checkbox" checked={core} onChange={(e) => setCore(e.target.checked)} />Core (in the short survey)</label>
        </div>
        <div><label className="f" htmlFor="qs">Show-if rule</label><input id="qs" type="text" value={show} onChange={(e) => setShow(e.target.value)} placeholder="Show if B8 is not 'None' or 'Not known'" />
          <p className="hint">Leave empty to always show. Use: Show if &lt;Q ID&gt; is 'answer' or 'answer', or Show if &lt;Q ID&gt; is not 'answer'. Put each answer in quotes, exactly as it appears in the options.</p></div>
        {err && <div className="note err" role="alert">{err}</div>}
      </div>
    </Modal>
  );
}
