import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { fmtDateTime } from "../lib";
import type { ActivityRow } from "../types";

const LABELS: Record<string, string> = {
  "user.setup": "Set up QE Connect", "user.login": "Signed in", "user.password": "Changed password", "user.mfa": "Set up sign-in codes", "user.create": "Added a team member",
  "user.update": "Updated a team member", "user.delete": "Removed a team member", "lob.add": "Added a line of business",
  "lob.rename": "Renamed a line of business", "lob.delete": "Removed a line of business", "lob.import": "Imported lines of business",
  "app.add": "Added an application", "app.respondent": "Changed a respondent", "app.delete": "Removed an application",
  "app.import": "Imported applications", "question.update": "Edited a question", "question.import": "Imported questions",
  "settings.organization": "Changed the organization details", "settings.campaign": "Renamed the survey", "settings.email": "Changed the invitation email", "settings.delivery": "Changed email delivery",
  "mail.test": "Sent a test email", "invite.send": "Sent invitations", "invite.remind": "Sent reminders", "invite.reopen": "Reopened a response",
  "invite.withdraw": "Cancelled a survey link", "survey.open": "Respondent opened the survey", "survey.submit": "Respondent submitted",
  "response.download": "Downloaded a response", "response.export": "Exported responses", "email.retry": "Retried an email",
  "sample.load": "Loaded sample data", "workspace.export": "Downloaded a backup", "workspace.import": "Restored a backup",
};

export default function Activity() {
  const q = useQuery({ queryKey: ["activity"], queryFn: () => api.get<ActivityRow[]>("/api/activity"), refetchInterval: 30_000 });
  return (
    <>
      <p className="eyebrow">Admin</p><h1>Activity</h1>
      <p className="lede">The latest 200 changes, sends, sign-ins and survey submissions.</p>
      <div className="tbl"><table style={{ minWidth: 720 }}>
        <thead><tr><th>When</th><th>Who</th><th>What</th><th>Details</th></tr></thead>
        <tbody>{(q.data ?? []).map((r) => (
          <tr key={r.id}><td className="small num" style={{ whiteSpace: "nowrap" }}>{fmtDateTime(r.at)}</td><td className="small">{r.actor}</td>
            <td>{LABELS[r.action] ?? r.action}</td><td className="small muted">{r.detail}</td></tr>))}
          {!q.isLoading && !q.data?.length && <tr><td colSpan={4} className="empty">Nothing yet.</td></tr>}
        </tbody>
      </table></div>
    </>
  );
}
