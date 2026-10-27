import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { fmtDateTime } from "../lib";
import type { SecurityEventRow } from "../types";

const KINDS: [string, string][] = [["", "All events"], ["signin", "Sign-ins"], ["signout", "Sign-outs"], ["session", "Session timeouts"],
  ["mfa", "Sign-in codes"], ["password", "Password changes"], ["user", "Account changes"], ["policy", "Security policy"],
  ["settings", "Email delivery"], ["export", "Downloads and exports"], ["delete", "Deletions"], ["respondent", "Respondent changes"], ["response", "Reopened responses"]];
const LABEL: Record<string, string> = {
  signin: "Sign-in", "signin.password": "Password accepted, code pending", signout: "Sign-out", "session.idle": "Signed out after inactivity",
  "mfa.verify": "Sign-in code", "mfa.setup": "Sign-in code setup", "mfa.enable": "Sign-in codes turned on", "mfa.disable": "Sign-in codes turned off",
  "password.change": "Password changed", "user.create": "Account added", "user.update": "Account changed", "user.delete": "Account removed",
  "policy.change": "Security policy changed", "settings.delivery": "Email delivery changed", "export.response": "Response downloaded",
  "export.responses": "Responses exported", "export.backup": "Backup downloaded", "export.securitylog": "Security log downloaded",
  "delete.application": "Application removed", "delete.applications": "Applications replaced", "delete.questions": "Question bank replaced",
  "delete.lob": "Line of business removed", "delete.surveylink": "Survey link cancelled", "delete.all": "All survey data replaced",
  "respondent.change": "Respondent changed", "response.reopen": "Response reopened",
};
const OUT: Record<string, [string, string]> = { ok: ["OK", "ok"], fail: ["Failed", "warn"], blocked: ["Blocked", "warn"] };

export default function SecurityLog() {
  const [kind, setKind] = useState("");
  const [outcome, setOutcome] = useState("");
  const [q, setQ] = useState("");
  const params = new URLSearchParams();
  if (kind) params.set("kind", kind);
  if (outcome) params.set("outcome", outcome);
  if (q.trim()) params.set("q", q.trim());
  const qs = params.toString();
  const ev = useQuery({ queryKey: ["security", qs], queryFn: () => api.get<SecurityEventRow[]>(`/api/security/events?${qs}`), refetchInterval: 30_000 });
  const fails = (ev.data ?? []).filter((e) => e.outcome !== "ok").length;
  return (
    <>
      <div className="spread"><div><p className="eyebrow">Admin</p><h1>Security log</h1></div>
        <a className="btn" href={`/api/security/events/download?${qs}`} download>↓ Download CSV</a></div>
      <p className="lede">Sign-ins (including failed and blocked attempts), sign-in codes, account and permission changes, downloads, exports and deletions. Kept for as long as the database is kept.</p>
      <div className="toolbar">
        <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Event type">{KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
        <select value={outcome} onChange={(e) => setOutcome(e.target.value)} aria-label="Outcome">
          <option value="">Any outcome</option><option value="ok">OK</option><option value="fail">Failed</option><option value="blocked">Blocked</option></select>
        <input type="search" placeholder="Search person, address or details" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search" />
      </div>
      {fails > 0 && !outcome && <p className="small bad-t" style={{ margin: "0 0 10px" }}>{fails} failed or blocked event{fails > 1 ? "s" : ""} in this list.</p>}
      <div className="tbl"><table style={{ minWidth: 820 }}>
        <thead><tr><th>When</th><th>Event</th><th>Outcome</th><th>Who</th><th>Address</th><th>Details</th></tr></thead>
        <tbody>{(ev.data ?? []).map((e) => (
          <tr key={e.id}><td className="small num" style={{ whiteSpace: "nowrap" }}>{fmtDateTime(e.at)}</td><td>{LABEL[e.kind] ?? e.kind}</td>
            <td><span className={`tag ${OUT[e.outcome]?.[1] ?? ""}`}>{OUT[e.outcome]?.[0] ?? e.outcome}</span></td>
            <td className="small">{e.actor}</td><td className="small mono">{e.ip}</td><td className="small muted">{e.detail}</td></tr>))}
          {!ev.isLoading && !ev.data?.length && <tr><td colSpan={6} className="empty">No events match.</td></tr>}
        </tbody>
      </table></div>
    </>
  );
}
