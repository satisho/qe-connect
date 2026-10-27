export type Role = "admin" | "editor" | "viewer";
export type Status = "notsent" | "sent" | "opened" | "progress" | "completed";

export interface User { id: number; email: string; name: string; role: Role; active: boolean; mfa_enabled: boolean; last_login_at: string | null }
export interface Pending { step: "verify" | "setup"; email: string }
export interface AuthState {
  needs_setup: boolean; user: User | null; pending: Pending | null; version: string; campaign: string;
  mfa_required: boolean; notice: string | null;
}
export interface SecurityEventRow { id: number; at: string; kind: string; outcome: "ok" | "fail" | "blocked"; actor: string; ip: string; detail: string }
export interface Policy { mfa_required: boolean; idle_minutes: number; users_without_mfa: string[] }

export interface Lob { id: number; name: string; position: number; applications: number }
export interface App {
  id: number; name: string; project_id: string; lob_id: number | null; lob: string; team: string;
  respondent_name: string; respondent_email: string; status: Status;
}
export interface Rule { kind: "lobs" | "bad" | "match"; qid?: string; negate?: boolean; values?: number; match?: string[] }
export interface Question {
  id: number; qid: string; position: number; section: string; pillar: string; focus: string; text: string; help: string;
  rtype: "short" | "long" | "single" | "multi" | "number"; options: string[]; required: boolean; core: boolean;
  show_if: string; source: string; dimension: string; rule: Rule | null;
}
export interface TrackerRow {
  id: number; name: string; project_id: string; lob: string; lob_id: number | null; team: string;
  respondent_name: string; respondent_email: string; email_ok: boolean; status: Status; answered: number; total: number;
  mode: "core" | "all" | null; due_at: string | null; sent_at: string | null; opened_at: string | null;
  completed_at: string | null; reminders: number; email_failed: boolean; link?: string;
}
export interface Tracker {
  applications: TrackerRow[]; counts: Record<Status, number>; total: number; default_due_days: number;
  delivery: { mode: "sim" | "graph" | "smtp"; mailbox: string; tested: boolean; rate_per_minute: number };
}
export interface EmailRow {
  id: number; application_id: number | null; application: string; kind: string; to: string; from: string;
  subject: string; body: string; status: "queued" | "sent" | "recorded" | "failed"; via: string; error: string;
  created_at: string; sent_at: string | null;
}
export interface Delivery {
  mode: "sim" | "graph" | "smtp"; tenant: string; client: string; auth_type: "secret" | "cert"; cert_thumbprint: string;
  save_sent: boolean; host: string; port: number; security: "starttls" | "tls" | "none"; smtp_auth: "none" | "login";
  username: string; mailbox: string; display_name: string; reply_to: string; rate_per_minute: number; link_base: string;
  tested: { ok: boolean; at: string; mode: string; steps: { ok: boolean; text: string }[] } | null;
  server: { client_secret_set: boolean; smtp_password_set: boolean; cert_path_set: boolean; public_url: string };
  problems: string[];
}
export interface Settings {
  campaign: { name: string; default_due_days: number };
  email: { subject: string; body: string };
  delivery: Delivery;
  placeholders: string[];
}
export interface ActivityRow { id: number; at: string; actor: string; action: string; detail: string }
