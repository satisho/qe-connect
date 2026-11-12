import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import type { Status } from "./types";

/* ---------------- routing (History API, no extra dependency) ---------------- */
export function usePath(): string {
  const [path, setPath] = useState(window.location.pathname);
  useEffect(() => {
    const on = () => setPath(window.location.pathname);
    window.addEventListener("popstate", on);
    window.addEventListener("qec:navigate", on);
    return () => {
      window.removeEventListener("popstate", on);
      window.removeEventListener("qec:navigate", on);
    };
  }, []);
  return path;
}
export function navigate(to: string, replace = false) {
  if (to === window.location.pathname) return;
  if (replace) window.history.replaceState(null, "", to);
  else window.history.pushState(null, "", to);
  window.dispatchEvent(new Event("qec:navigate"));
  window.scrollTo({ top: 0 });
}
export function Link({ to, className, children, ...rest }: { to: string; className?: string; children: ReactNode; [k: string]: unknown }) {
  return (
    <a href={to} className={className} {...rest}
      onClick={(e) => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
        e.preventDefault();
        navigate(to);
      }}>{children}</a>
  );
}

/* ---------------- toast ---------------- */
type ToastState = { text: string; err?: boolean } | null;
const ToastCtx = createContext<(text: string, err?: boolean) => void>(() => {});
export function ToastHost({ children }: { children: ReactNode }) {
  const [t, setT] = useState<ToastState>(null);
  const timer = useRef<number>();
  const show = useCallback((text: string, err = false) => {
    setT({ text, err });
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setT(null), err ? 6000 : 3000);
  }, []);
  return (
    <ToastCtx.Provider value={show}>
      {children}
      <div className={`toast ${t?.err ? "err" : ""}`} role="status" aria-live="polite" hidden={!t}>{t?.text}</div>
    </ToastCtx.Provider>
  );
}
export const useToast = () => useContext(ToastCtx);

/* ---------------- modal ---------------- */
export function Modal({ title, eyebrow, onClose, children, footer, narrow }: {
  title: ReactNode; eyebrow?: ReactNode; onClose: () => void; children: ReactNode; footer?: ReactNode; narrow?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    const first = ref.current?.querySelector<HTMLElement>("input, select, textarea, button.primary, button");
    first?.focus();
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", key);
    return () => { document.removeEventListener("keydown", key); prev?.focus?.(); };
  }, [onClose]);
  return (
    <div className="scrim" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={`modal ${narrow ? "narrow" : ""}`} role="dialog" aria-modal="true" ref={ref}>
        <header>
          <div>{eyebrow && <p className="eyebrow">{eyebrow}</p>}<h2>{title}</h2></div>
          <button type="button" className="x" onClick={onClose} aria-label="Close">×</button>
        </header>
        <div className="mbody">{children}</div>
        {footer && <footer>{footer}</footer>}
      </div>
    </div>
  );
}

export function Confirm({ title, children, action, danger, onConfirm, onClose, busy }: {
  title: string; children: ReactNode; action: string; danger?: boolean; onConfirm: () => void; onClose: () => void; busy?: boolean;
}) {
  return (
    <Modal narrow title={title} onClose={onClose} footer={<>
      <button type="button" className="btn" onClick={onClose}>Cancel</button>
      <button type="button" className={`btn ${danger ? "danger solid" : "primary"}`} disabled={busy} onClick={onConfirm}>{action}</button>
    </>}>{children}</Modal>
  );
}

/* ---------------- formatting ---------------- */
export const fmtDate = (s: string | null | undefined) =>
  s ? new Date(s).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "";
export const fmtDateTime = (s: string | null | undefined) =>
  s ? new Date(s).toLocaleString(undefined, { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }) : "";
export const plural = (n: number, one: string, many = one + "s") => `${n} ${n === 1 ? one : many}`;
export const emailOk = (e: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e.trim());

/* ---------------- status pill ---------------- */
export const STATUS: Record<Status, string> = { notsent: "Not sent", sent: "Sent", opened: "Opened", progress: "In progress", completed: "Completed" };
const ICON: Record<Status, ReactNode> = {
  notsent: <svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="5.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeDasharray="2.4 2" /></svg>,
  sent: <svg viewBox="0 0 16 16" aria-hidden="true"><rect x="2" y="3.5" width="12" height="9" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.5" /><path d="M2.5 4.5 8 9l5.5-4.5" fill="none" stroke="currentColor" strokeWidth="1.5" /></svg>,
  opened: <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M1.5 8s2.4-4.5 6.5-4.5S14.5 8 14.5 8 12.1 12.5 8 12.5 1.5 8 1.5 8z" fill="none" stroke="currentColor" strokeWidth="1.5" /><circle cx="8" cy="8" r="2" fill="currentColor" /></svg>,
  progress: <svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" strokeWidth="1.5" opacity=".35" /><path d="M8 2a6 6 0 0 1 6 6H8z" fill="currentColor" /></svg>,
  completed: <svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="7" fill="currentColor" /><path d="M4.8 8.2 7 10.4l4.3-4.6" fill="none" stroke="var(--ok-soft)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>,
};
export const Pill = ({ s }: { s: Status }) => <span className={`st ${s}`}>{ICON[s]}{STATUS[s]}</span>;

/* QE Connect mark: three linked people/nodes (a community of practice), coloured by the organization's accent. */
export const Mark = () => (
  <svg className="mark" viewBox="0 0 34 34" aria-hidden="true">
    <rect width="34" height="34" rx="8" fill="var(--accent)" />
    <path d="M11 22.5L17 11l6 11.5z" fill="none" stroke="var(--accent-ink)" strokeWidth="1.8" strokeLinejoin="round" opacity=".85" />
    <circle cx="17" cy="11" r="3.4" fill="var(--signal)" />
    <circle cx="11" cy="22.5" r="3.4" fill="var(--accent-ink)" />
    <circle cx="23" cy="22.5" r="3.4" fill="var(--accent-ink)" />
  </svg>
);

/* Product name stays "QE Connect"; the line under it names the client organization when one is set. */
export function Brand({ org, sub }: { org?: { name: string } | null; sub: string }) {
  const name = org?.name?.trim();
  return <div className="brand"><Mark /><div><b>QE Connect</b><small>{name ? `${name} · ${sub}` : sub}</small></div></div>;
}

/* Applies the organization's accent colour (a #RRGGBB value) to the whole interface. */
export function useAccent(accent?: string | null) {
  useEffect(() => {
    const root = document.documentElement;
    if (accent && /^#[0-9a-f]{6}$/i.test(accent)) {
      const n = parseInt(accent.slice(1), 16);
      const lin = (c: number) => { const s = c / 255; return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4; };
      const lum = 0.2126 * lin(n >> 16) + 0.7152 * lin((n >> 8) & 255) + 0.0722 * lin(n & 255);
      root.style.setProperty("--brand", accent);
      root.style.setProperty("--brand-ink", lum > 0.36 ? "#0B1A22" : "#FFFFFF");
      root.dataset.brand = "1";
    } else {
      root.style.removeProperty("--brand");
      root.style.removeProperty("--brand-ink");
      delete root.dataset.brand;
    }
  }, [accent]);
}

/* ---------------- email preview (mirrors the server's template filling) ---------------- */
export function fillTemplate(tpl: string, v: Record<string, string>) {
  return tpl.replace(/\{(\w+)\}/g, (m, k) => (k in v ? v[k] : m));
}
export function MailView({ subject, body, from, to, at, live }: { subject: string; body: string; from: string; to: string; at?: string | null; live?: boolean }) {
  const paras = body.split(/\n{2,}/);
  const LINK = /(https?:\/\/[^\s<]+\/s\/[A-Za-z0-9_-]+)/;
  return (
    <div className="mail">
      <div className="mh"><b>{subject}</b><span>From: {from}</span><span>To: {to}</span>{at && <span>{fmtDateTime(at)}</span>}</div>
      <div className="mb">
        {paras.map((p, i) => {
          const parts = p.split(LINK);
          return (
            <p key={i}>
              {parts.map((part, j) => LINK.test(part)
                ? <span key={j}><br /><a className="cta" href={live ? part.replace(/^https?:\/\/[^/]+/, "") : undefined}
                    target={live ? "_blank" : undefined} rel="noreferrer">Start the survey</a><br /><span className="lnk">{part}</span></span>
                : part.split("\n").map((line, k, arr) => <span key={`${j}-${k}`}>{line}{k < arr.length - 1 && <br />}</span>))}
            </p>
          );
        })}
      </div>
    </div>
  );
}
