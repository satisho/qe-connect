import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, errorText } from "../api";
import { Brand, fmtDate, fmtDateTime, useAccent } from "../lib";
import type { Organization, Question } from "../types";

type Answers = Record<string, string | string[]>;
interface SurveyData {
  application: { name: string; lob: string; team: string; respondent_name: string };
  campaign: string; organization?: Organization; status: string; mode: "core" | "all"; due_at: string | null; completed_at: string | null; reference: string;
  questions: Question[]; answers: Answers; other: Record<string, string>; prefilled: string[];
}
type View = "welcome" | "section" | "review" | "done";

const isOther = (v: unknown) => typeof v === "string" && /^other\b/i.test(v);
const isNone = (v: string) => /^none of/i.test(v);

function shows(q: Question, a: Answers, known: Set<string>) {
  const r = q.rule;
  if (!r || r.kind !== "match" || !r.qid || !known.has(r.qid)) return true;
  const v = a[r.qid];
  if (v == null || v === "" || (Array.isArray(v) && !v.length)) return false;
  const hit = (Array.isArray(v) ? v : [v]).some((x) => (r.match ?? []).includes(String(x).toLowerCase()));
  return r.negate ? !hit : hit;
}
function answered(q: Question, a: Answers, o: Record<string, string>) {
  const v = a[q.qid];
  if (v == null || (typeof v === "string" && !v.trim()) || (Array.isArray(v) && !v.length)) return false;
  const needs = Array.isArray(v) ? v.some(isOther) : isOther(v);
  return !(needs && !(o[q.qid] || "").trim());
}
function problem(q: Question, a: Answers, o: Record<string, string>): string | null {
  const v = a[q.qid];
  if (q.rtype === "number" && v !== undefined && v !== "" && (isNaN(Number(v)) || Number(v) < 0)) return "Enter a whole number, e.g. 12.";
  if (!q.required || answered(q, a, o)) return null;
  if (v && (Array.isArray(v) ? v.some(isOther) : isOther(v))) return 'Tell us what "Other" means here.';
  return q.rtype === "multi" ? "Choose at least one option." : "This question needs an answer.";
}
function sectionParts(s: string) {
  const m = s.match(/^([A-Z]{1,3})[.)]\s*(.*)$/);
  return m ? { id: m[1], name: m[2] } : { id: "", name: s };
}
const COST: Record<Question["rtype"], number> = { single: .4, multi: .6, number: .3, short: .7, long: 1.5 };

export default function Survey({ token, preview }: { token?: string; preview?: boolean }) {
  const [data, setData] = useState<SurveyData | null>(null);
  const [loadErr, setLoadErr] = useState("");
  const [answers, setAnswers] = useState<Answers>({});
  const [other, setOther] = useState<Record<string, string>>({});
  const [mode, setMode] = useState<"core" | "all">("core");
  const [view, setView] = useState<View>("welcome");
  const [sec, setSec] = useState(0);
  const [tried, setTried] = useState<Set<string>>(new Set());
  const [serverProblems, setServerProblems] = useState<Record<string, string>>({});
  const [save, setSave] = useState<{ state: "idle" | "saving" | "saved" | "error"; at?: string }>({ state: "idle" });
  const [busy, setBusy] = useState(false);
  const [revealed, setRevealed] = useState<Set<string>>(new Set());
  const timer = useRef<number>();
  const pending = useRef(false);
  const latest = useRef({ answers, other, mode });
  latest.current = { answers, other, mode };
  useAccent(data?.organization?.accent);

  useEffect(() => {
    (async () => {
      try {
        let d: SurveyData;
        if (preview) {
          const p = await api.get<{ questions: Question[] }>("/api/survey-preview");
          const st = await api.get<{ campaign: string; organization: Organization }>("/api/auth/state");
          d = { application: { name: "Example application", lob: "", team: "", respondent_name: "Preview" }, campaign: st.campaign, organization: st.organization, status: "opened",
            mode: "core", due_at: null, completed_at: null, reference: "PREVIEW", questions: p.questions, answers: {}, other: {}, prefilled: [] };
        } else d = await api.get<SurveyData>(`/api/s/${encodeURIComponent(token!)}`);
        setData(d);
        setAnswers(d.answers || {});
        setOther(d.other || {});
        setMode(d.mode || "core");
        if (d.status === "completed") setView("done");
        document.title = `${d.application.name} · QE Connect survey`;
      } catch (e) {
        setLoadErr(errorText(e));
      }
    })();
  }, [token, preview]);

  const flush = useCallback(async () => {
    window.clearTimeout(timer.current);
    if (preview || !pending.current) return true;
    pending.current = false;
    setSave({ state: "saving" });
    try {
      const r = await api.put<{ saved_at: string }>(`/api/s/${encodeURIComponent(token!)}`, latest.current);
      setSave({ state: "saved", at: r.saved_at });
      return true;
    } catch (e) {
      pending.current = true;
      setSave({ state: "error" });
      if (e instanceof ApiError && e.status === 409) window.location.reload();
      return false;
    }
  }, [preview, token]);
  const changed = () => {
    pending.current = true;
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(flush, 900);
  };
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => { if (pending.current) { flush(); e.preventDefault(); } };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [flush]);

  const qs = data?.questions ?? [];
  const known = useMemo(() => new Set(qs.map((q) => q.qid)), [qs]);
  const vis = useMemo(() => qs.filter((q) => (mode === "all" || q.core) && shows(q, answers, known)), [qs, mode, answers, known]);
  const sections = useMemo(() => {
    const out: { key: string; id: string; name: string; items: Question[] }[] = [];
    vis.forEach((q) => {
      const last = out[out.length - 1];
      if (last && last.key === q.section) last.items.push(q);
      else out.push({ key: q.section, ...sectionParts(q.section), items: [q] });
    });
    return out;
  }, [vis]);

  if (loadErr) return <Frame><div className="done"><p className="eyebrow">Survey link</p><h1>This link isn't working</h1><p className="lede">{loadErr}</p></div></Frame>;
  if (!data) return <div className="loading">Opening your survey…</div>;

  const done = vis.filter((q) => answered(q, answers, other)).length;
  const pct = vis.length ? Math.round((done / vis.length) * 100) : 0;
  const cur = sections[Math.min(sec, sections.length - 1)];
  const go = async (v: View, s = 0) => { await flush(); setView(v); setSec(s); window.scrollTo({ top: 0 }); };

  const setAnswer = (q: Question, v: string | string[]) => {
    const before = new Set(vis.map((x) => x.qid));
    const next = { ...answers, [q.qid]: v };
    setAnswers(next);
    setServerProblems((p) => { const n = { ...p }; delete n[q.qid]; return n; });
    const after = qs.filter((x) => (mode === "all" || x.core) && shows(x, next, known)).map((x) => x.qid).filter((id) => !before.has(id));
    if (after.length) setRevealed(new Set(after));
    changed();
  };
  const msgFor = (q: Question) => serverProblems[q.qid] || (cur && tried.has(cur.key) ? problem(q, answers, other) : null);

  const next = async () => {
    if (!cur) return;
    setTried((t) => new Set(t).add(cur.key));
    const bad = cur.items.filter((q) => problem(q, answers, other));
    if (bad.length) {
      document.getElementById(`card-${bad[0].qid}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    if (sec < sections.length - 1) go("section", sec + 1);
    else go("review");
  };
  const submit = async () => {
    const bad = vis.filter((q) => problem(q, answers, other));
    if (bad.length) {
      setTried(new Set(sections.map((s) => s.key)));
      go("section", sections.findIndex((s) => s.items.includes(bad[0])));
      return;
    }
    if (preview) { setView("done"); return; }
    setBusy(true);
    try {
      window.clearTimeout(timer.current);
      pending.current = false;
      const d = await api.post<SurveyData>(`/api/s/${encodeURIComponent(token!)}/submit`, { answers, other, mode });
      setData(d);
      setView("done");
      window.scrollTo({ top: 0 });
    } catch (e) {
      if (e instanceof ApiError && e.status === 422 && (e.data as any)?.problems) {
        const probs: { qid: string; message: string }[] = (e.data as any).problems;
        setServerProblems(Object.fromEntries(probs.map((p) => [p.qid, p.message])));
        setTried(new Set(sections.map((s) => s.key)));
        go("section", Math.max(0, sections.findIndex((s) => s.items.some((q) => q.qid === probs[0].qid))));
      } else setSave({ state: "error" });
    } finally { setBusy(false); }
  };

  const saveBadge = preview ? <span className="saved">Preview: answers aren't recorded</span>
    : view === "done" ? null
    : save.state === "error" ? <span className="saved bad"><i />Couldn't save. Check your connection; we'll keep trying.</span>
    : save.state === "saving" ? <span className="saved"><i />Saving…</span>
    : save.state === "saved" ? <span className="saved"><i />Saved {fmtDateTime(save.at)}</span>
    : <span className="saved"><i />Your answers save as you go</span>;

  const team = data.organization?.team_name || "QE Assessment team";
  const header = (
    <>
      {preview && <div className="banner"><div className="wrap"><span>Preview of the survey as respondents see it. Answers aren't recorded.</span>
        <button type="button" className="btn sm" onClick={() => window.close()}>Close preview</button></div></div>}
      <header className="top"><div className="wrap"><Brand org={data.organization} sub={data.campaign} />{saveBadge}</div></header>
    </>
  );

  if (view === "welcome") {
    const stat = (m: "core" | "all") => {
      const list = qs.filter((q) => m === "all" || q.core);
      return { n: list.length, mins: Math.round(list.reduce((s, q) => s + COST[q.rtype], 0) + 1) };
    };
    const c = stat("core"), a = stat("all");
    const started = Object.keys(answers).length > (data.prefilled?.length ?? 0);
    return (
      <>{header}<div className="wrap rs" style={{ paddingBlock: "28px 56px" }}><main style={{ maxWidth: 780 }}>
        <p className="eyebrow">You're invited</p>
        <h1>Tell us how quality works on {data.application.name}</h1>
        <p className="lede">The {team} is building a picture of testing and quality practice across {data.organization?.name || "your organization's"} applications. There are no right or wrong answers, and "Not sure" is always fine.</p>
        <dl className="invite kv">
          <div><dt>Application</dt><dd>{data.application.name}</dd></div>
          {data.application.lob && <div><dt>Line of business</dt><dd>{data.application.lob}</dd></div>}
          <div><dt>Please respond by</dt><dd>{data.due_at ? fmtDate(data.due_at) : "No date set"}</dd></div>
          <div><dt>Your progress</dt><dd>{started ? "Saved, pick up where you left off" : "Not started"}</dd></div>
        </dl>
        <h2>How much time do you have?</h2>
        <div className="modes" role="radiogroup" aria-label="Survey length">
          {([["core", "Core questions", "The questions the assessment needs most.", `${c.n} questions`, c.mins],
            ["all", "Full survey", "Adds optional questions on capacity, onboarding and shared practice.", `up to ${a.n} questions`, a.mins]] as const).map(([m, t, d, n, mins]) => (
            <label key={m} className={`mode ${mode === m ? "on" : ""}`}>
              <input type="radio" name="mode" checked={mode === m} onChange={() => { setMode(m); changed(); }} />
              <b>{t}</b><small>{d}</small><span className="meta"><span>{n}</span><span>about {mins} min</span></span>
            </label>))}
        </div>
        {data.prefilled?.length > 0 && <p className="small muted" style={{ margin: "0 0 18px" }}>We've filled in what we already know about the application. You can change any of it.</p>}
        <button type="button" className="btn primary" onClick={() => go("section", 0)}>{started ? "Continue survey" : "Start survey"} →</button>
      </main></div></>
    );
  }

  if (view === "done") {
    return (
      <>{header}<div className="wrap rs" style={{ paddingBlock: "28px 56px" }}><div className="done">
        <p className="eyebrow">{preview ? "Preview finished" : "Submitted"}</p>
        <h1>{preview ? "That's the end of the survey" : "Thank you. Your response is in."}</h1>
        {preview ? <p className="lede">In a real survey, the response now appears as completed on the tracker.</p> : <>
          <p className="lede" style={{ marginBottom: 6 }}>The {team} now has your answers for <b>{data.application.name}</b>{data.completed_at ? ` (submitted ${fmtDateTime(data.completed_at)})` : ""}. Your reference:</p>
          <span className="ref">{data.reference}</span>
          <p className="help">Need to change something? Reply to the invitation email and the team can reopen your survey.</p></>}
      </div></div></>
    );
  }

  const rail = (
    <aside className="rail" aria-label="Survey sections"><h3>Your route</h3>
      <ol className="stops">
        {sections.map((s, i) => {
          const d = s.items.filter((q) => answered(q, answers, other)).length;
          const here = view === "section" && sec === i;
          const ok = !here && d > 0 && s.items.every((q) => !problem(q, answers, other));
          return <li key={s.key} className={`stop ${here ? "here" : ""} ${ok ? "done" : ""}`}><button type="button" onClick={() => go("section", i)} aria-current={here ? "step" : undefined}>
            <span className="dot" /><span><span className="lbl">{s.id && <em>{s.id}</em>}{s.name}</span><br /><span className="cnt">{d} of {s.items.length} answered</span></span></button></li>;
        })}
        <li className={`stop ${view === "review" ? "here" : ""}`}><button type="button" onClick={() => go("review")}><span className="dot" /><span><span className="lbl">Review &amp; submit</span><br /><span className="cnt">Check, then send</span></span></button></li>
      </ol>
    </aside>
  );
  const strip = (label: string) => <div className="strip"><div className="bar"><span style={{ width: `${pct}%` }} /></div><p><span>{label}</span><span>{pct}%</span></p></div>;

  if (view === "review" || !cur) {
    const missing = vis.filter((q) => problem(q, answers, other)).length;
    return (
      <>{header}<div className="wrap rs rshell">{rail}<main>
        {strip("Review & submit")}
        <p className="eyebrow">Last stop</p><h1>Review your answers</h1>
        <p className="lede">{missing ? `${missing} required question${missing > 1 ? "s still need" : " still needs"} an answer.` : "Everything required is answered. When you submit, your response goes straight to the QE Assessment team."}</p>
        {sections.map((s, i) => (
          <div className="rlist" key={s.key} style={{ marginBottom: 14 }}>
            <div className="sh"><span>{s.id && `${s.id} · `}{s.name}</span><button type="button" className="btn sm" onClick={() => go("section", i)}>Edit</button></div>
            {s.items.map((q) => {
              const has = answered(q, answers, other);
              const v = answers[q.qid];
              const text = has ? (Array.isArray(v) ? v : [v]).map((x) => (isOther(x) ? `Other: ${other[q.qid]}` : x)).join(", ") : q.required ? "Needs an answer" : "Skipped";
              return <div key={q.qid}><span className="qid">{q.qid}</span><span>{q.text}</span><span className={`a ${has ? "" : q.required ? "miss" : "none"}`}>{text}</span></div>;
            })}
          </div>
        ))}
        <div className="fnav"><button type="button" className="btn ghost" onClick={() => go("section", sections.length - 1)}>← Back</button>
          <button type="button" className="btn primary" disabled={busy} onClick={submit}>{preview ? "Finish preview" : busy ? "Submitting…" : "Submit response"}</button></div>
      </main></div></>
    );
  }

  return (
    <>{header}<div className="wrap rs rshell">{rail}<main>
      {strip(`Section ${sec + 1} of ${sections.length} · ${cur.name}`)}
      {cur.id && <p className="eyebrow">Section {cur.id}</p>}<h1>{cur.name}</h1>
      <div className="qs">{cur.items.map((q) => (
        <Field key={q.qid} q={q} value={answers[q.qid]} other={other[q.qid] ?? ""} msg={msgFor(q)} reveal={revealed.has(q.qid)}
          known={!preview && data.prefilled?.includes(q.qid)}
          onChange={(v) => setAnswer(q, v)} onOther={(t) => { setOther({ ...other, [q.qid]: t }); changed(); }} />))}
      </div>
      <div className="fnav">
        <button type="button" className="btn ghost" onClick={() => (sec ? go("section", sec - 1) : go("welcome"))}>← {sec ? "Back" : "Survey intro"}</button>
        <button type="button" className="btn primary" onClick={next}>{sec === sections.length - 1 ? "Review answers" : `Next: ${sections[sec + 1].name}`} →</button>
      </div>
    </main></div></>
  );
}

function Frame({ children }: { children: React.ReactNode }) {
  return <><header className="top"><div className="wrap"><Brand sub="QE Assessment survey" /></div></header>
    <div className="wrap rs" style={{ paddingBlock: "28px 56px" }}>{children}</div></>;
}

function Field({ q, value, other, msg, reveal, known, onChange, onOther }: {
  q: Question; value: string | string[] | undefined; other: string; msg: string | null; reveal: boolean; known: boolean;
  onChange: (v: string | string[]) => void; onOther: (t: string) => void;
}) {
  const lab = `lab-${q.qid}`;
  const sel = q.rtype === "multi" ? ((value as string[]) ?? []) : [value as string];
  const toggle = (o: string, on: boolean) => {
    let curr = ((value as string[]) ?? []).slice();
    if (on) curr = isNone(o) ? [o] : [...curr.filter((x) => !isNone(x)), o];
    else curr = curr.filter((x) => x !== o);
    onChange(q.options.filter((x) => curr.includes(x)));
  };
  return (
    <div className={`q ${msg ? "err" : ""} ${reveal ? "reveal" : ""}`} id={`card-${q.qid}`}>
      <div className="qhead"><span className="qid">{q.qid}</span><span className="small muted">{q.focus}</span></div>
      {q.rule?.kind === "match" && <p className="because">↳ Shown because of your answer to {q.rule.qid}.</p>}
      {known && <p className="known">✓ Filled in from the assessment team's records. Change it if it's wrong.</p>}
      <p className="qtext" id={lab}>{q.text}{q.required ? <span className="req" aria-label="required">*</span> : <span className="opt-tag">Optional</span>}</p>
      {q.help && <p className="help">{q.help}</p>}
      {q.rtype === "short" && <input type="text" aria-labelledby={lab} value={(value as string) ?? ""} onChange={(e) => onChange(e.target.value)} />}
      {q.rtype === "long" && <textarea aria-labelledby={lab} value={(value as string) ?? ""} onChange={(e) => onChange(e.target.value)} />}
      {q.rtype === "number" && <input type="number" inputMode="numeric" min={0} step={1} aria-labelledby={lab} value={(value as string) ?? ""} onChange={(e) => onChange(e.target.value)} />}
      {(q.rtype === "single" || q.rtype === "multi") && <>
        <div className={`choices ${q.options.length > 5 ? "two" : ""}`} role={q.rtype === "multi" ? "group" : "radiogroup"} aria-labelledby={lab}>
          {q.options.map((o) => {
            const on = sel.includes(o);
            return <label key={o} className={`choice ${on ? "on" : ""}`}>
              <input type={q.rtype === "multi" ? "checkbox" : "radio"} name={`r-${q.qid}`} checked={on}
                onChange={(e) => (q.rtype === "multi" ? toggle(o, e.target.checked) : onChange(o))} /><span>{o}</span></label>;
          })}
        </div>
        {sel.some(isOther) && <input type="text" aria-label="Please specify" placeholder="Please specify" value={other} onChange={(e) => onOther(e.target.value)} autoFocus />}
      </>}
      {msg && <p className="msg">{msg}</p>}
    </div>
  );
}
