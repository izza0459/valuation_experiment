"use client";

/**
 * Shared screen primitives, ported from the prototype's `shared/ui.jsx`.
 *
 * Changes from the prototype, per its own INTEGRATION.md:
 *  - `window.*` globals replaced with imports/exports
 *  - the demo job-state switcher (VPS/useVP/setJob) removed; real status
 *    comes from the API
 *  - hash routing replaced with next/navigation
 */

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { Avatar, Icon, Tag, Toast } from "@/design-system";
import { ROLE_LABELS, signOut, useMe } from "@/lib/auth";

/* --- small controls ------------------------------------------------ */

export function Chip({
  on,
  onClick,
  children,
  style,
  ...rest
}: {
  on?: boolean;
  onClick?: () => void;
  children: React.ReactNode;
  style?: React.CSSProperties;
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      onClick={onClick}
      {...rest}
      style={{
        height: 34,
        padding: "0 12px",
        borderRadius: 6,
        fontSize: 14,
        fontFamily: "inherit",
        cursor: "pointer",
        border: "1px solid " + (on ? "var(--border-focus)" : "var(--border-default)"),
        background: on ? "var(--surface-accent)" : "#fff",
        color: on ? "var(--text-accent)" : "var(--text-primary)",
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        ...style,
      }}
    >
      {on && <Icon name="check" size={14} />}
      {children}
    </button>
  );
}

export function MultiChips({
  options,
  value = [],
  onChange,
}: {
  options: string[];
  value?: string[];
  onChange: (next: string[]) => void;
}) {
  return (
    <div className="row wrap" style={{ gap: 6 }}>
      {options.map((o) => (
        <Chip
          key={o}
          on={value.includes(o)}
          onClick={() => onChange(value.includes(o) ? value.filter((x) => x !== o) : [...value, o])}
        >
          {o}
        </Chip>
      ))}
    </div>
  );
}

export function Seg<T extends string>({
  options,
  value,
  onChange,
  size,
}: {
  options: readonly T[];
  value: T | "";
  onChange: (next: T) => void;
  size?: "lg";
}) {
  return (
    <div className="seg">
      {options.map((o) => (
        <button
          key={o}
          type="button"
          className={o === value ? "on" : ""}
          onClick={() => onChange(o)}
          style={size === "lg" ? { height: 44, padding: "0 18px", fontSize: 15 } : undefined}
        >
          {o}
        </button>
      ))}
    </div>
  );
}

export const YN = (p: { value: "Yes" | "No" | ""; onChange: (v: "Yes" | "No") => void }) => (
  <Seg options={["Yes", "No"] as const} {...p} />
);

const TRI_COLOURS: Record<string, string> = {
  Connected: "var(--green-600)",
  "Not connected": "var(--error-500)",
  Assumed: "var(--amber-600)",
};

export function TriState({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="seg">
      {["Connected", "Not connected", "Assumed"].map((o) => (
        <button
          key={o}
          type="button"
          className={o === value ? "on" : ""}
          onClick={() => onChange(o)}
          style={o === value ? { color: TRI_COLOURS[o], background: "#fff", borderColor: TRI_COLOURS[o] } : undefined}
        >
          {o}
        </button>
      ))}
    </div>
  );
}

export function Toggle({
  on,
  onChange,
  label,
}: {
  on: boolean;
  onChange: (next: boolean) => void;
  label?: string;
}) {
  return (
    <label className="row" style={{ gap: 10, cursor: "pointer" }}>
      <span
        onClick={() => onChange(!on)}
        style={{
          width: 40,
          height: 22,
          borderRadius: 11,
          background: on ? "var(--action-primary)" : "var(--gray-400)",
          position: "relative",
          transition: ".15s",
          flexShrink: 0,
        }}
      >
        <span
          style={{
            position: "absolute",
            top: 2,
            left: on ? 20 : 2,
            width: 18,
            height: 18,
            borderRadius: 9,
            background: "#fff",
            transition: ".15s",
          }}
        />
      </span>
      {label && <span style={{ fontSize: 15 }}>{label}</span>}
    </label>
  );
}

/* --- indicators ---------------------------------------------------- */

/** Per-tab completion ring (design brief S3). */
export function Ring({ pct, size = 22, warn }: { pct: number; size?: number; warn?: boolean }) {
  const r = size / 2 - 2.5;
  const c = 2 * Math.PI * r;
  const col = pct >= 100 ? "var(--green-600)" : warn ? "var(--amber-600)" : "var(--action-primary)";
  return (
    <svg width={size} height={size} style={{ flexShrink: 0 }}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--gray-200)" strokeWidth="3" />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke={col}
        strokeWidth="3"
        strokeDasharray={c}
        strokeDashoffset={c * (1 - pct / 100)}
        strokeLinecap="round"
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
      {pct >= 100 && (
        <path
          d={`M${size * 0.3} ${size * 0.52}l${size * 0.14} ${size * 0.14} ${size * 0.27}-${size * 0.3}`}
          stroke={col}
          strokeWidth="2"
          fill="none"
        />
      )}
    </svg>
  );
}

/** The stage a status or stage label belongs to, for its colour. */
const STAGE_OF: Record<string, string> = {
  "Instruction Received": "setup", Setup: "setup",
  Scheduling: "scheduling",
  "Inspection Scheduled": "inspection", Inspected: "inspection", Inspection: "inspection",
  "Valuation In Progress": "valuation", Valuation: "valuation",
  "Peer Review": "review", "Approved & Signed": "review", Review: "review",
  Issued: "send", "Send to bank": "send", "Sent to Bank": "send",
  Lost: "lost", Returned: "lost",
};

/** A status as a small uppercase pill in its stage's colour (theme.css
 * --stage-*). The colour says where the lead is, the same on every screen. */
export const StatusChip = ({ s }: { s: string }) => {
  const stage = STAGE_OF[s] ?? "setup";
  return (
    <span className="stage-pill" style={{ color: `var(--stage-${stage})`, background: `var(--stage-${stage}-bg)` }}>
      {s}
    </span>
  );
};

const SOURCE_COLOURS: Record<string, [string, string]> = {
  DLD: ["#e8f0fe", "#3b6fd8"],
  Bayut: ["#e7f6ea", "#2e9b4a"],
  Manual: ["#f2f2f2", "#6b6b6b"],
  "Property Monitor": ["#efeafd", "#7b5ce0"],
  "Title Deed": ["#fff4dc", "#c98a00"],
  SPA: ["#fff4dc", "#c98a00"],
  "Site Affection Plan": ["#fff4dc", "#c98a00"],
};

/** Every value shows where it came from (design brief §3.4). */
export const SourceBadge = ({ s }: { s: string }) => {
  const [bg, fg] = SOURCE_COLOURS[s] ?? SOURCE_COLOURS.Manual;
  return (
    <span style={{ background: bg, color: fg, fontSize: 12, padding: "2px 8px", borderRadius: 4, whiteSpace: "nowrap" }}>
      {s}
    </span>
  );
};

export const Conf = ({ l }: { l: "High" | "Medium" | "Low" }) => {
  const m = {
    High: ["var(--green-50)", "var(--green-600)"],
    Medium: ["var(--amber-50)", "var(--amber-600)"],
    Low: ["var(--red-150)", "var(--red-600)"],
  }[l];
  const bars = { High: 3, Medium: 2, Low: 1 }[l];
  return (
    <span style={{ background: m[0], color: m[1], fontSize: 13, padding: "3px 10px", borderRadius: 12, display: "inline-flex", gap: 6, alignItems: "center" }}>
      <span style={{ display: "flex", gap: 2 }}>
        {[1, 2, 3].map((i) => (
          <i key={i} style={{ width: 4, height: 10, borderRadius: 1, background: m[1], opacity: i <= bars ? 1 : 0.25 }} />
        ))}
      </span>
      {l} confidence
    </span>
  );
};

/** AVM range with the valuer's value marked against it (design brief S3). */
export function RangeBar({
  lo,
  hi,
  mv,
  avm,
  min,
  max,
}: {
  lo: number;
  hi: number;
  mv?: number | null;
  avm?: number | null;
  min: number;
  max: number;
}) {
  const p = (v: number) => ((v - min) / (max - min)) * 100 + "%";
  return (
    <div style={{ position: "relative", height: 44, margin: "6px 0" }}>
      <div style={{ position: "absolute", top: 20, left: 0, right: 0, height: 4, borderRadius: 2, background: "var(--gray-200)" }} />
      <div style={{ position: "absolute", top: 18, left: p(lo), width: `calc(${p(hi)} - ${p(lo)})`, height: 8, borderRadius: 4, background: "var(--red-200)" }} />
      {avm != null && <div style={{ position: "absolute", left: p(avm), top: 12, width: 2, height: 20, background: "var(--text-primary)" }} />}
      {mv != null && (
        <div style={{ position: "absolute", left: p(mv), top: 14, width: 14, height: 14, marginLeft: -7, borderRadius: 7, background: "var(--action-primary)", border: "2px solid #fff", boxShadow: "0 0 0 1px var(--red-600)" }} />
      )}
      <span className="num" style={{ position: "absolute", left: p(lo), top: 32, fontSize: 12, color: "var(--text-muted)", transform: "translateX(-50%)" }}>
        {Math.round(lo / 1000)}k
      </span>
      <span className="num" style={{ position: "absolute", left: p(hi), top: 32, fontSize: 12, color: "var(--text-muted)", transform: "translateX(-50%)" }}>
        {Math.round(hi / 1000)}k
      </span>
    </div>
  );
}

/* --- layout -------------------------------------------------------- */

export function Section({
  title,
  sub,
  right,
  children,
  style,
  collapsed: initiallyCollapsed,
  collapsible,
}: {
  title: React.ReactNode;
  sub?: React.ReactNode;
  right?: React.ReactNode;
  children?: React.ReactNode;
  style?: React.CSSProperties;
  collapsed?: boolean;
  collapsible?: boolean;
}) {
  const [collapsed, setCollapsed] = useState(!!initiallyCollapsed);
  return (
    <section className="card" style={style}>
      <div
        className="row"
        style={{ justifyContent: "space-between", marginBottom: collapsed ? 0 : 16, cursor: collapsible ? "pointer" : "default" }}
        onClick={collapsible ? () => setCollapsed(!collapsed) : undefined}
      >
        <div className="row" style={{ gap: 8 }}>
          <div style={{ fontSize: 17, fontWeight: 500 }}>{title}</div>
          <Tip text={sub} />
        </div>
        <div className="row" style={{ gap: 8 }}>
          {right}
          {collapsible && <Icon name={collapsed ? "chevron-down" : "chevron-up"} size={18} />}
        </div>
      </div>
      {!collapsed && children}
    </section>
  );
}

/** An ⓘ that explains what it sits next to, on hover, focus or tap. The app
 * keeps explanations here rather than as text on the screen. */
export function Tip({ text, size = 15 }: { text?: React.ReactNode; size?: number }) {
  if (!text) return null;
  return (
    <span className="tip" tabIndex={0} role="note" aria-label={typeof text === "string" ? text : undefined}
      onClick={(e) => e.stopPropagation()}>
      <Icon name="info" size={size} />
      <span className="tip-body" role="tooltip">{text}</span>
    </span>
  );
}

/** Labelled field wrapper: label, optional source badge, error; the helper
 * text is a tooltip on the label. */
export const F = ({
  label,
  src,
  children,
  span,
  badge,
  optional,
  error,
  helper,
}: {
  label: React.ReactNode;
  src?: string;
  children?: React.ReactNode;
  span?: number;
  badge?: string;
  optional?: boolean;
  error?: React.ReactNode;
  helper?: React.ReactNode;
}) => (
  <div style={{ gridColumn: span ? `span ${span}` : undefined, minWidth: 0 }}>
    <div className="row" style={{ justifyContent: "space-between", marginBottom: 6, gap: 8 }}>
      <span className="row" style={{ fontSize: 14, color: "var(--text-secondary)", gap: 6, minWidth: 0 }}>
        <span>
          {label}
          {optional && <span style={{ color: "var(--text-muted)" }}> (optional)</span>}
        </span>
        <Tip text={helper} />
      </span>
      <span className="row" style={{ gap: 6 }}>
        {badge && <Tag tone="amber">{badge}</Tag>}
        {src && <SourceBadge s={src} />}
      </span>
    </div>
    {children}
    {error && <div style={{ color: "var(--text-error)", fontSize: 13, marginTop: 4 }}>{error}</div>}
  </div>
);

export const G = ({ cols = 2, children, gap = 18 }: { cols?: number; children: React.ReactNode; gap?: number }) => (
  <div style={{ display: "grid", gridTemplateColumns: `repeat(${cols},minmax(0,1fr))`, gap }}>{children}</div>
);

// Pages that exist. "Valuation register" (S9) isn't built, so it isn't linked:
// a nav item that leads to a 404 is worse than no item.
const NAV: { key: string; label: string; icon: string; adminOnly?: boolean }[] = [
  { key: "dashboard", label: "Dashboard", icon: "layout-dashboard" },
  { key: "jobs", label: "Jobs", icon: "briefcase" },
  { key: "admin", label: "Admin", icon: "settings", adminOnly: true },
];

export function Shell({ children, bare }: { children: React.ReactNode; bare?: boolean }) {
  const pathname = usePathname();
  const router = useRouter();
  const qc = useQueryClient();
  const { data: me, isLoading } = useMe();
  const active = (pathname ?? "/jobs").split("/")[1] || "jobs";

  const user = me?.authenticated ? me.user : null;

  // Everything inside the shell needs a signed-in user.
  useEffect(() => {
    if (me && !me.authenticated) router.replace(`/login?next=${encodeURIComponent(pathname ?? "/jobs")}`);
  }, [me, pathname, router]);

  /** Leaves at once: waiting for the server (asleep on the free hosting)
   * made the button look broken. The session is ended in the background. */
  function leave() {
    void signOut();
    qc.clear(); // nothing fetched as this user may be shown to the next
    qc.setQueryData(["me"], { authenticated: false });
    router.replace("/login");
  }

  if (isLoading || !user) {
    return <div className="skel" style={{ minHeight: "100vh" }} aria-busy="true" />;
  }

  return (
    <div style={{ minHeight: "100vh" }}>
      <header className="topbar">
        <div className="row topbar-main" style={{ gap: 28, flex: 1, minWidth: 0 }}>
          <Link href="/jobs" className="row" style={{ gap: 12, textDecoration: "none" }}>
            {/* eslint-disable-next-line @next/next/no-img-element -- small static logo */}
            <img src="/bayut-icon.svg" alt="" className="brand-logo" />
            <span className="brand-word">bayut</span>
            <span className="brand-name">Valuations</span>
          </Link>
          <nav className="row" style={{ gap: 4 }}>
            {NAV.filter((item) => !item.adminOnly || user.is_admin).map((item) => (
              <Link key={item.key} href={"/" + item.key} className={"nav" + (active === item.key ? " on" : "")}>
                <Icon name={item.icon} size={16} />
                {item.label}
              </Link>
            ))}
          </nav>
        </div>
        <div className="row topbar-user" style={{ gap: 12, minWidth: 0 }}>
          <Avatar name={user.name} size={30} />
          <div className="topbar-who" style={{ lineHeight: 1.3, minWidth: 0 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text-primary)" }}>{user.name}</div>
            <div style={{ fontSize: 11.5, color: "var(--text-muted)" }}>
              {user.roles.map((r) => ROLE_LABELS[r] ?? r).join(", ") || "No role"}
            </div>
          </div>
          <button type="button" className="signout" onClick={leave}>
            Sign out
          </button>
        </div>
      </header>
      <main style={{ maxWidth: bare ? undefined : 1360, margin: "0 auto", padding: bare ? 0 : "24px 28px 56px" }}>
        {children}
      </main>
      {/* Phones (and the app): the sections as a bottom tab bar. */}
      <nav className="tabbar" aria-label="Primary">
        {NAV.filter((item) => !item.adminOnly || user.is_admin).map((item) => (
          <Link key={item.key} href={"/" + item.key} className={active === item.key ? "on" : ""}>
            <Icon name={item.icon} size={18} />
            {item.label}
          </Link>
        ))}
      </nav>
    </div>
  );
}

/** Page title. `sub` is a value shown beside it (a count, say); `tip`
 * explains the page. */
export const PageHead = ({
  title,
  sub,
  tip,
  children,
}: {
  title: React.ReactNode;
  sub?: React.ReactNode;
  tip?: React.ReactNode;
  children?: React.ReactNode;
}) => (
  <div className="row" style={{ justifyContent: "space-between", marginBottom: 18, gap: 16 }}>
    <div className="row" style={{ gap: 10, alignItems: "baseline" }}>
      <h1 style={{ margin: 0, fontSize: 26 }}>{title}</h1>
      {sub && <span style={{ color: "var(--text-muted)", fontSize: 14 }}>{sub}</span>}
      <Tip text={tip} />
    </div>
    <div className="row" style={{ gap: 10 }}>
      {children}
    </div>
  </div>
);

export const Banner = ({
  tone = "amber",
  icon,
  children,
  right,
}: {
  tone?: "amber" | "red" | "blue" | "green";
  icon?: string;
  children: React.ReactNode;
  right?: React.ReactNode;
}) => {
  const m = {
    amber: ["var(--amber-50)", "var(--amber-600)"],
    red: ["var(--red-100)", "var(--red-600)"],
    blue: ["var(--blue-50)", "var(--blue-600)"],
    green: ["var(--green-50)", "var(--green-600)"],
  }[tone];
  return (
    <div
      className="row"
      style={{ background: m[0], color: "var(--text-primary)", borderRadius: 10, padding: "12px 16px", gap: 12, marginBottom: 14, border: "1px solid " + m[1] + "33" }}
    >
      {icon && <Icon name={icon} size={20} color={m[1]} />}
      <div style={{ flex: 1, fontSize: 15 }}>{children}</div>
      {right}
    </div>
  );
};

export function useToast(): [React.ReactNode, (message: string) => void] {
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!message) return;
    const timer = setTimeout(() => setMessage(null), 2200);
    return () => clearTimeout(timer);
  }, [message]);

  const node = message ? (
    <div style={{ position: "fixed", bottom: 24, left: "50%", transform: "translateX(-50%)", zIndex: 90 }}>
      <Toast message={message} />
    </div>
  ) : null;

  return [node, setMessage];
}
