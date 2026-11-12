import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import { Brand, Link, navigate, useAccent, usePath } from "./lib";
import type { AuthState, Organization, Settings, Tracker, User } from "./types";
import SignIn from "./pages/SignIn";
import TrackerPage from "./pages/Tracker";
import SentEmails from "./pages/SentEmails";
import Applications from "./pages/Applications";
import Questions from "./pages/Questions";
import Lobs from "./pages/Lobs";
import InvitationEmail from "./pages/InvitationEmail";
import EmailDelivery from "./pages/EmailDelivery";
import Team from "./pages/Team";
import Activity from "./pages/Activity";
import Administration from "./pages/Administration";
import SecurityLog from "./pages/SecurityLog";
import { AccountModal } from "./pages/Account";
import Survey from "./survey/Survey";

const PAGES: Record<string, { el: (u: User) => JSX.Element; role?: "editor" | "admin" }> = {
  "/tracker": { el: (u) => <TrackerPage user={u} /> },
  "/emails": { el: (u) => <SentEmails user={u} /> },
  "/applications": { el: (u) => <Applications user={u} /> },
  "/questions": { el: (u) => <Questions user={u} /> },
  "/lobs": { el: (u) => <Lobs user={u} /> },
  "/email": { el: (u) => <InvitationEmail user={u} /> },
  "/delivery": { el: (u) => <EmailDelivery user={u} /> },
  "/team": { el: (u) => <Team user={u} />, role: "admin" },
  "/activity": { el: () => <Activity /> },
  "/admin": { el: (u) => <Administration user={u} />, role: "admin" },
  "/security": { el: () => <SecurityLog />, role: "admin" },
};

export default function App() {
  const path = usePath();
  if (path.startsWith("/s/")) return <Survey token={decodeURIComponent(path.slice(3))} />;
  return <Portal path={path} />;
}

function Portal({ path }: { path: string }) {
  const qc = useQueryClient();
  const auth = useQuery({ queryKey: ["auth"], queryFn: () => api.get<AuthState>("/api/auth/state") });
  const [notice, setNotice] = useState<string | null>(null);
  useEffect(() => {
    const on = (e: Event) => {
      const msg = (e as CustomEvent<string>).detail;
      if (msg && /without activity/.test(msg)) setNotice(msg);
      qc.invalidateQueries({ queryKey: ["auth"] });
    };
    window.addEventListener("qec:signed-out", on);
    return () => window.removeEventListener("qec:signed-out", on);
  }, [qc]);

  useAccent(auth.data?.organization?.accent);
  if (auth.isLoading) return <div className="loading">Loading QE Connect…</div>;
  if (auth.isError || !auth.data) return <div className="loading">QE Connect isn't responding. Check that it is running, then reload this page.</div>;
  const st = auth.data;
  if (!st.user) return <SignIn needsSetup={st.needs_setup} version={st.version} org={st.organization} pending={st.pending} notice={st.notice || notice} />;
  if (path === "/preview") return <Survey preview />;
  if (!PAGES[path]) {
    navigate("/tracker", true);
    return null;
  }
  return <Shell user={st.user} campaign={st.campaign} org={st.organization} version={st.version} path={path} />;
}

function Shell({ user, campaign, org, version, path }: { user: User; campaign: string; org: Organization; version: string; path: string }) {
  const tracker = useQuery({ queryKey: ["tracker"], queryFn: () => api.get<Tracker>("/api/tracker"), refetchInterval: 15_000 });
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => api.get<Settings>("/api/settings") });
  const qcount = useQuery({ queryKey: ["questions"], queryFn: () => api.get<unknown[]>("/api/questions") });
  const lobs = useQuery({ queryKey: ["lobs"], queryFn: () => api.get<unknown[]>("/api/lobs") });
  const [menu, setMenu] = useState(false);
  const [account, setAccount] = useState(false);
  const qc = useQueryClient();
  const page = PAGES[path];
  const allowed = !page.role || (page.role === "admin" ? user.role === "admin" : user.role !== "viewer");
  const t = tracker.data;
  const d = settings.data?.delivery;
  const dot = d ? (d.mode !== "sim" && d.tested?.ok ? "ok" : "warn") : undefined;
  const menuRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!menu) return;
    const close = (e: MouseEvent) => { if (!menuRef.current?.contains(e.target as Node)) setMenu(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setMenu(false); };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", esc); };
  }, [menu]);

  const nav = (to: string, label: string, n?: number | string, dotCls?: string) => (
    <Link to={to} className={path === to ? "on" : ""} aria-current={path === to ? "page" : undefined}>
      <span>{label}</span>
      {n !== undefined && <span className="n">{n}</span>}
      {dotCls && <span className={`ndot ${dotCls}`} title={dotCls === "ok" ? "Connected and tested" : "Not connected or not tested"} />}
    </Link>
  );
  const signOut = async () => {
    await api.post("/api/auth/logout");
    qc.clear();
    window.location.assign("/");
  };
  const initials = (user.name || user.email).split(/[\s@.]+/).filter(Boolean).slice(0, 2).map((s) => s[0]!.toUpperCase()).join("");

  return (
    <>
      <header className="top">
        <div className="wrap">
          <Brand org={org} sub={`Assessment portal · ${campaign}`} />
          <div className="who" ref={menuRef}>
            <button type="button" onClick={() => setMenu((m) => !m)} aria-expanded={menu} aria-haspopup="menu">
              <span className="avatar">{initials}</span><span>{user.name}</span>
            </button>
            {menu && (
              <div className="menu" role="menu">
                <div className="meta">{user.email}<br />Role: {user.role} · v{version}</div>
                <button type="button" className="mi" role="menuitem" onClick={() => { setMenu(false); setAccount(true); }}>Password and sign-in codes</button>
                <button type="button" className="mi" role="menuitem" onClick={signOut}>Sign out</button>
              </div>
            )}
          </div>
        </div>
      </header>
      <div className="wrap shell">
        <nav className="nav" aria-label="Portal">
          <h4>Survey</h4>
          {nav("/tracker", "Tracker", t ? `${t.counts.completed}/${t.total}` : undefined)}
          {nav("/emails", "Sent emails")}
          <h4>Setup</h4>
          {nav("/applications", "Applications", t?.total)}
          {nav("/questions", "Questions", qcount.data?.length)}
          {nav("/lobs", "Lines of business", lobs.data?.length)}
          {nav("/email", "Invitation email")}
          {nav("/delivery", "Email delivery", undefined, dot)}
          <h4>Admin</h4>
          {user.role === "admin" && nav("/team", "Team")}
          {nav("/activity", "Activity")}
          {user.role === "admin" && nav("/security", "Security log")}
          {user.role === "admin" && nav("/admin", "Administration")}
        </nav>
        <main id="main">
          {allowed ? page.el(user) : <div className="panel">This page needs the {page.role} role. Ask an administrator if you need access.</div>}
        </main>
      </div>
      {account && <AccountModal user={user} onClose={() => setAccount(false)} />}
    </>
  );
}
