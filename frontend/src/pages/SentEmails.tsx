import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorText } from "../api";
import { fmtDate, fmtDateTime, MailView, useToast } from "../lib";
import type { EmailRow, User } from "../types";

const LABEL: Record<EmailRow["status"], [string, string]> = {
  recorded: ["Recorded only", "sig"], queued: ["Sending…", "info"], sent: ["Sent", "ok"], failed: ["Failed", "warn"],
};

export default function SentEmails({ user }: { user: User }) {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({
    queryKey: ["emails"], queryFn: () => api.get<EmailRow[]>("/api/emails"),
    refetchInterval: (query) => ((query.state.data ?? []).some((e) => e.status === "queued") ? 3000 : 20000),
  });
  const [cur, setCur] = useState<number | null>(null);
  if (q.isLoading) return <div className="loading">Loading…</div>;
  const list = q.data ?? [];
  const e = list.find((x) => x.id === cur) ?? list[0];
  const retry = async (id: number) => {
    try { await api.post(`/api/emails/${id}/retry`); toast("Queued to send again"); qc.invalidateQueries({ queryKey: ["emails"] }); }
    catch (x) { toast(errorText(x), true); }
  };
  return (
    <>
      <p className="eyebrow">Survey</p><h1>Sent emails</h1>
      <p className="lede">Every invitation, reminder and test email, as the respondent receives it, with its delivery status.</p>
      {!list.length ? <div className="panel empty">No emails yet. Select applications on the Tracker and choose Send survey.</div> : (
        <div className="ob">
          <div className="oblist" role="list">
            {list.map((m) => (
              <button type="button" key={m.id} className={e?.id === m.id ? "on" : ""} onClick={() => setCur(m.id)}>
                <span className="t"><b>{m.application || (m.kind === "Test" ? "Test email" : "Removed application")}</b><span className="muted">{fmtDate(m.created_at)}</span></span>
                <span className="s">{m.kind} · {m.to}</span>
                <span><span className={`tag ${LABEL[m.status][1]}`}>{LABEL[m.status][0]}</span></span>
              </button>
            ))}
          </div>
          {e && <div>
            <div className="row" style={{ marginBottom: 10 }}>
              <span className={`tag ${LABEL[e.status][1]}`}>{LABEL[e.status][0]}</span>
              <span className="small muted">{e.status === "sent" ? `Delivered to the mail server ${fmtDateTime(e.sent_at)} via ${e.via === "graph" ? "Microsoft 365" : "SMTP relay"}`
                : e.status === "recorded" ? "Email delivery wasn't connected, so this was recorded but not sent."
                : e.status === "queued" ? "Waiting to send. Emails go out at the per-minute rate set under Email delivery." : ""}</span>
            </div>
            {e.status === "failed" && <div className="note err" style={{ margin: "0 0 12px" }}><b>Couldn't send.</b> {e.error}
              {user.role !== "viewer" && <div style={{ marginTop: 8 }}><button type="button" className="btn sm" onClick={() => retry(e.id)}>Try again</button></div>}</div>}
            <MailView subject={e.subject} body={e.body} from={e.from} to={e.to} at={e.created_at} live />
          </div>}
        </div>
      )}
    </>
  );
}
