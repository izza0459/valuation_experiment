"use client";

/**
 * Job workspace — design brief S3.
 *
 * The job moves through five stages, shown as the main tabs, each with the
 * person responsible for it:
 *
 *   Setup (ops) → Inspection (valuer) → Valuation (valuer)
 *     → Review (peer reviewer) → Send to bank (ops)
 *
 * A stage's sections (the data-entry tabs from the field config) sit under
 * it. Completing a stage's sections moves the job on by itself (server:
 * transitions.sync_stage). Moving forward into a later stage needs every
 * earlier stage complete: Next (or a later stage's tab) says what is missing
 * instead. Leaving a completed Valuation stage asks what goes in the report.
 *
 * Sections are edited in place through `TabEditor`, which renders each one
 * from the shared field config and autosaves via the per-tab PATCH endpoint.
 * Completion rings come from the server, which evaluates the same
 * required/visible rules, so there is one answer to "is this section done?".
 */

import { useEffect, useState, useSyncExternalStore } from "react";
import { ReportFieldsDialog } from "@/components/vp/ReportFieldsDialog";
import Link from "next/link";
import { Avatar, Button, Icon } from "@/design-system";
import { Banner, Ring, Shell, StatusChip } from "@/components/vp/ui";
import { EvidenceTab } from "@/components/vp/EvidenceTab";
import { FitText } from "@/components/vp/FitText";
import { ReportActions } from "@/components/vp/ReportActions";
import { ReviewPanel, SendPanel } from "@/components/vp/ReviewPanel";
import { RightPanel } from "@/components/vp/RightPanel";
import { LiveReport } from "@/components/vp/LiveReport";
import { useMedia } from "@/lib/media";
import { TabEditor } from "@/components/vp/TabEditor";
import { useFieldConfig, type TabDef } from "@/lib/fieldConfig";
import { buildTabValues, useJob, type JobDetail } from "@/lib/jobs";
import { useMe } from "@/lib/auth";

type NavStage = "setup" | "inspection" | "valuation" | "review" | "send";

/** The main tabs, and whose stage each is (a role on the job). */
const NAV: { key: NavStage; label: string; role: string; roleLabel: string }[] = [
  { key: "setup", label: "Setup", role: "admin", roleLabel: "Ops" },
  { key: "inspection", label: "Inspection", role: "valuer", roleLabel: "Valuer" },
  { key: "valuation", label: "Valuation", role: "valuer", roleLabel: "Valuer" },
  { key: "review", label: "Review", role: "peer_reviewer", roleLabel: "Peer reviewer" },
  { key: "send", label: "Send to bank", role: "admin", roleLabel: "Ops" },
];

/** Where the job's status sits among the stages. */
const STAGE_FOR_STATUS: Record<string, NavStage> = {
  instruction_received: "setup",
  setup: "setup",
  inspection_scheduled: "inspection",
  inspected: "inspection",
  valuation_in_progress: "valuation",
  peer_review: "review",
  approved_signed: "review",
  issued: "send",
};

/** `within`: a tab shown inside another section rather than as its own
 * (the Check List sits at the top of Inspection). */
type Page = { key: string; label: string; stage: NavStage; tab?: TabDef; within?: string };

/** Tabs rendered inside another section: tab -> the section that holds it. */
const SHOWN_WITHIN: Record<string, string> = { checklist: "inspection" };
type Assignee = { id: number; name: string; roles: string[] };

function stageDone(stage: NavStage, job: JobDetail, pages: Page[]): boolean {
  if (stage === "review") return job.status === "approved_signed" || job.status === "issued";
  if (stage === "send") return (job.deliveries ?? []).length > 0;
  const inStage = pages.filter((p) => p.stage === stage && p.tab);
  return inStage.length > 0 && inStage.every((p) => (job.tabs[p.key]?.completion.pct ?? 0) === 100);
}

/** Whether the report shows beside the form: a per-browser preference. */
const LIVE_REPORT_KEY = "live-report";
function readLiveReport() {
  try {
    return window.localStorage.getItem(LIVE_REPORT_KEY) !== "off";
  } catch {
    return true;
  }
}
function subscribeLiveReport(onChange: () => void) {
  window.addEventListener(LIVE_REPORT_KEY, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(LIVE_REPORT_KEY, onChange);
    window.removeEventListener("storage", onChange);
  };
}

export function JobDetailClient({ id }: { id: string }) {
  const { data: job, isLoading: jobLoading, isError } = useJob(id);
  const { data: tabs, isLoading: tabsLoading } = useFieldConfig();
  const { data: me } = useMe();
  const [active, setActive] = useState<string | null>(null);
  // A small notification card (top right) that goes after 5 seconds: what
  // stops moving on, or which stage the job has moved to.
  const [notice, setNotice] = useState<{ tone: "red" | "green"; title: string; lines?: string[] } | null>(null);
  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 5000);
    return () => window.clearTimeout(timer);
  }, [notice]);
  // The include-in-report step, and where to go once it is saved.
  const [reportStep, setReportStep] = useState<string | null>(null);
  // The report beside the form (wide screens only); remembered per browser.
  const liveReport = useSyncExternalStore(subscribeLiveReport, readLiveReport, () => true);
  const toggleLiveReport = (on: boolean) => {
    try {
      window.localStorage.setItem(LIVE_REPORT_KEY, on ? "on" : "off");
    } catch {
      /* storage blocked: nothing to remember it in */
    }
    window.dispatchEvent(new Event(LIVE_REPORT_KEY));
  };
  // Photos and documents print too, so their lists are part of what reloads it.
  const photosList = useMedia(id, "photos");
  const docsList = useMedia(id, "documents");
  // Phones: the section pills scroll sideways; keep the open one in view.
  useEffect(() => {
    const pill = document.querySelector<HTMLElement>(".stickybar [data-on='1']");
    const row = pill?.parentElement;
    if (pill && row && row.scrollWidth > row.clientWidth) {
      const offset = pill.getBoundingClientRect().left - row.getBoundingClientRect().left;
      row.scrollLeft += offset - (row.clientWidth - pill.offsetWidth) / 2;
    }
  });

  if (jobLoading || tabsLoading) {
    return (
      <Shell>
        <div className="card" style={{ height: 150, marginBottom: 16 }} />
        <div className="skel" style={{ height: 320 }} />
      </Shell>
    );
  }

  if (isError || !job) {
    return (
      <Shell>
        <div className="card" style={{ textAlign: "center", padding: "60px 24px" }}>
          <div style={{ fontSize: 17 }}>Could not load this job.</div>
          <div style={{ color: "var(--text-muted)", fontSize: 14, marginTop: 6 }}>
            It may not exist, or you may not hold a role on it.
          </div>
        </div>
      </Shell>
    );
  }

  const allValues = buildTabValues(job);
  // Every section in order, then the Send to bank page (not a form tab).
  const pages: Page[] = [
    ...[...(tabs ?? [])]
      .sort((a, b) => a.order - b.order)
      .map((t) => ({
        key: t.key,
        label: t.key === "review" ? "Review & sign off" : t.label,
        stage: t.stage as NavStage,
        tab: t,
        within: SHOWN_WITHIN[t.key],
      })),
    { key: "send", label: "Send to bank", stage: "send" },
  ];
  // What the user moves between: sections shown inside another are left out.
  const navPages = pages.filter((p) => !p.within);
  /** A section's completion, including any tab shown inside it. */
  const completionOf = (key: string) => {
    const parts = [key, ...pages.filter((p) => p.within === key).map((p) => p.key)]
      .map((k) => job.tabs[k]?.completion)
      .filter((c): c is { pct: number; missing: string[] } => Boolean(c));
    if (parts.length === 0) return { pct: 0, missing: [] as string[] };
    return { pct: Math.min(...parts.map((c) => c.pct)), missing: parts.flatMap((c) => c.missing) };
  };

  // Ops look after Setup only: once it is done the job is the valuer's, so
  // the later stages are greyed out for them rather than opened read-only.
  const opsView =
    Boolean(me?.authenticated && me.user.roles.includes("ops")) &&
    Boolean(job.tabs.instructions?.can_edit) &&
    !job.tabs.inspection?.can_edit &&
    !job.tabs.summary?.can_edit;
  const statusStage = opsView ? "setup" : STAGE_FOR_STATUS[job.status] ?? "setup";
  const defaultPage =
    navPages.find((p) => p.stage === statusStage && p.tab && completionOf(p.key).pct < 100) ??
    navPages.find((p) => p.stage === statusStage) ??
    navPages[0];
  const current = navPages.find((p) => p.key === active && (!opsView || p.stage === "setup")) ?? defaultPage;
  const index = navPages.findIndex((p) => p.key === current.key);
  const prev = index > 0 ? navPages[index - 1] : null;
  const nextPage = index < navPages.length - 1 ? navPages[index + 1] : null;
  // For ops the walk ends with Setup: the next stage is the valuer's.
  const next = opsView && nextPage && nextPage.stage !== "setup" ? null : nextPage;
  const setupDone = (pages.filter((p) => p.stage === "setup" && p.tab)).every((p) => (job.tabs[p.key]?.completion.pct ?? 0) === 100);
  const valuerName = (job.assignees as { name: string; roles: string[] }[] | undefined)?.find((a) => a.roles.includes("valuer"))?.name;
  const stageLabel = (key: NavStage) => NAV.find((s) => s.key === key)?.label ?? key;
  const stagePages = navPages.filter((p) => p.stage === current.stage);

  const STAGE_ORDER: NavStage[] = ["setup", "inspection", "valuation", "review", "send"];
  /** What is still missing in a data-entry stage, as "Section: field, field". */
  const missingIn = (stage: NavStage): string[] =>
    pages
      .filter((p) => p.stage === stage && p.tab && job.tabs[p.key])
      .flatMap((p) => {
        const missing = job.tabs[p.key].completion.missing;
        return missing.length ? [`${p.label}: ${missing.join(", ")}`] : [];
      });
  /** The first earlier data-entry stage that isn't complete, if moving to
   * `target` would skip past it. Going back is always allowed. */
  const blockingStage = (target: NavStage) => {
    if (isLocked) return null;
    for (const stage of STAGE_ORDER.slice(0, STAGE_ORDER.indexOf(target))) {
      if (stage === "review" || stage === "send") continue;
      const missing = missingIn(stage);
      if (missing.length) return { stage: stageLabel(stage), missing };
    }
    return null;
  };
  // v2: the step moved from after Inspection to after Valuation, with more
  // fields, so jobs confirmed under the old step are asked again.
  const reportStepKey = `report-fields-confirmed-v2:${id}`;
  const reportStepDone = () => {
    try {
      return window.localStorage.getItem(reportStepKey) === "1";
    } catch {
      return false;
    }
  };

  const go = (key: string) => {
    const target = pages.find((p) => p.key === key);
    if (target && target.stage !== current.stage && STAGE_ORDER.indexOf(target.stage) > STAGE_ORDER.indexOf(current.stage)) {
      const block = blockingStage(target.stage);
      if (block) {
        setNotice({ tone: "red", title: `Complete the ${block.stage} stage before moving on`, lines: block.missing });
        return;
      }
      // Leaving a complete Valuation stage: choose what goes in the report.
      const canChoose = Boolean(job.tabs.valuation?.can_edit);
      if (current.stage === "valuation" && canChoose && !reportStepDone()) {
        setReportStep(key);
        return;
      }
    }
    if (target && target.stage !== current.stage && STAGE_ORDER.indexOf(target.stage) > STAGE_ORDER.indexOf(current.stage)) {
      setNotice({ tone: "green", title: `On to ${stageLabel(target.stage)}` });
    }
    setActive(key);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const goStage = (stage: NavStage) => {
    const inStage = navPages.filter((p) => p.stage === stage);
    const firstOpen = inStage.find((p) => p.tab && completionOf(p.key).pct < 100);
    go((firstOpen ?? inStage[0]).key);
  };

  // Review and Send show the report themselves; an issued job no longer changes.
  const showLiveReport = liveReport && !job.is_locked && current.stage !== "review" && current.stage !== "send";
  const reportSignature = [
    job.updated_at,
    ...Object.entries(job.tabs ?? {}).map(([k, t]) => `${k}:${t.version}`),
    ...(photosList.data?.items ?? []).map((p) => `${p.id}:${p.include_in_report}:${p.caption}`),
    ...(docsList.data?.items ?? []).map((d) => `${d.id}:${d.include_in_report}`),
  ].join("|");

  const property = (job.property ?? {}) as Record<string, string>;
  const assignees = (job.assignees ?? []) as Assignee[];
  const ownerOf = (role: string) => assignees.find((a) => a.roles.includes(role))?.name;
  const isLocked = job.is_locked;

  const nextLabel = (p: Page) =>
    p.stage === current.stage ? `Next: ${p.label}` : `Next: ${stageLabel(p.stage)}${p.label !== stageLabel(p.stage) && stagePagesCount(p.stage) > 1 ? ` · ${p.label}` : ""}`;
  const prevLabel = (p: Page) => (p.stage === current.stage ? p.label : `${stageLabel(p.stage)}${stagePagesCount(p.stage) > 1 ? ` · ${p.label}` : ""}`);
  function stagePagesCount(stage: NavStage) {
    return navPages.filter((p) => p.stage === stage).length;
  }

  return (
    <Shell>
      {/* --- header: the job, then its stages ------------------------- */}
      <div className="card" style={{ marginBottom: 12, padding: "18px 22px" }}>
        <div className="row jobtop" style={{ justifyContent: "space-between", alignItems: "flex-start", gap: 20 }}>
          <div style={{ minWidth: 0 }}>
            <Link href="/jobs" className="show-app backlink">
              ‹ Jobs
            </Link>
            <div className="hide-app" style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 4 }}>
              <Link href="/jobs" style={{ textDecoration: "none" }}>
                Jobs
              </Link>{" "}
              › {job.bayut_internal_reference_no}
            </div>
            <div className="row" style={{ gap: 10 }}>
              <h1 style={{ margin: 0, fontSize: 22, fontWeight: 500 }}>{job.property_label}</h1>
              {isLocked && <Icon name="lock" size={18} color="var(--text-muted)" />}
            </div>
            <div className="row wrap" style={{ gap: "4px 14px", marginTop: 6, fontSize: 14, color: "var(--text-secondary)" }}>
              <span>{property.title_doc_emirate || "Dubai"}</span>
              <span>
                Bayut ref <span className="num">{job.bayut_internal_reference_no}</span>
              </span>
              {job.bank_reference_no ? (
                <span>
                  Bank ref <span className="num">{job.bank_reference_no}</span>
                </span>
              ) : null}
              <span>{job.bank_name}</span>
            </div>
          </div>

          <div className="row jobmeta" style={{ gap: 12, flexShrink: 0 }}>
            {!isLocked && current.stage !== "review" && current.stage !== "send" && (
              <>
                {!liveReport && (
                  <button type="button" className="livereport-toggle hide-app" onClick={() => toggleLiveReport(true)}>
                    <Icon name="file-text" size={16} /> Show report beside the form
                  </button>
                )}
                <ReportActions jobId={id} />
              </>
            )}
            <StatusChip s={job.status_label as string} />
            <div className="row" style={{ gap: 0 }}>
              {assignees.map((person, i) => (
                <span
                  key={person.id}
                  title={`${person.name} · ${person.roles.map((r) => r.replace(/_/g, " ")).join(", ")}`}
                  style={{ marginLeft: i ? -8 : 0, boxShadow: "0 0 0 2px #fff", borderRadius: "50%" }}
                >
                  <Avatar name={person.name} size={32} />
                </span>
              ))}
            </div>
          </div>
        </div>

      </div>

      {/* --- the stages and their sections, kept in view while scrolling --- */}
      <div className="card stickybar" style={{ padding: "0 22px", marginBottom: 16 }}>
        <div className="show-app stagelab">
          Stage {STAGE_ORDER.indexOf(current.stage) + 1} of {NAV.length} ·{" "}
          <b style={{ color: "var(--text-accent)" }}>{stageLabel(current.stage)}</b>
        </div>
        <nav aria-label="Stages" className="stagenav" style={{ display: "flex" }}>
          {NAV.map((stage, i) => {
            const done = stageDone(stage.key, job, pages);
            const selected = stage.key === current.stage;
            const now = stage.key === statusStage && !done;
            const owner = ownerOf(stage.role);
            const greyed = opsView && stage.key !== "setup";
            return (
              <button
                key={stage.key}
                type="button"
                disabled={greyed}
                title={greyed ? "The valuer's stage" : undefined}
                onClick={() => goStage(stage.key)}
                aria-current={selected ? "step" : undefined}
                style={{
                  opacity: greyed ? 0.4 : 1,
                  cursor: greyed ? "not-allowed" : "pointer",
                  flex: 1,
                  minWidth: 0,
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  padding: "14px 10px 12px",
                  border: 0,
                  borderBottom: `2px solid ${selected ? "var(--action-primary)" : "transparent"}`,
                  background: "none",
                  textAlign: "left",
                  fontFamily: "inherit",
                }}
              >
                <span
                  style={{
                    width: 26,
                    height: 26,
                    borderRadius: 13,
                    flexShrink: 0,
                    display: "grid",
                    placeItems: "center",
                    fontSize: 13,
                    background: done ? "var(--green-600)" : now ? "var(--action-primary)" : "var(--gray-150)",
                    color: done || now ? "#fff" : "var(--text-secondary)",
                  }}
                >
                  {done ? <Icon name="check" size={14} color="#fff" /> : i + 1}
                </span>
                <span style={{ minWidth: 0 }}>
                  <span
                    style={{
                      display: "block",
                      fontSize: 14,
                      fontWeight: selected ? 500 : 400,
                      color: selected ? "var(--text-accent)" : "var(--text-primary)",
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                  >
                    <FitText min={12}>{stage.label}</FitText>
                  </span>
                  <span
                    style={{
                      display: "block",
                      fontSize: 12,
                      color: "var(--text-muted)",
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                    title={owner ? `${stage.roleLabel}: ${owner}` : undefined}
                  >
                    {owner ?? `${stage.roleLabel} not assigned`}
                  </span>
                </span>
              </button>
            );
          })}
        </nav>
        {/* The stage's sections, when it has more than one. */}
        {stagePages.length > 1 && (
          <div className="row wrap" style={{ gap: 6, padding: "10px 0 12px", borderTop: "1px solid var(--border-divider)" }}>
            {stagePages.map((p) => {
                  const { pct, missing } = completionOf(p.key);
                  const on = p.key === current.key;
                  return (
                    <button
                      key={p.key}
                      type="button"
                      data-on={on ? "1" : undefined}
                      onClick={() => go(p.key)}
                      title={missing.length ? `Missing: ${missing.join(", ")}` : undefined}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 7,
                        padding: "7px 12px",
                        borderRadius: 999,
                        border: `1px solid ${on ? "var(--action-primary)" : "var(--border-subtle)"}`,
                        background: on ? "var(--surface-subtle)" : "var(--surface-card)",
                        color: on ? "var(--text-accent)" : "var(--text-secondary)",
                        fontFamily: "inherit",
                        fontSize: 14,
                        cursor: "pointer",
                        whiteSpace: "nowrap",
                      }}
                    >
                      <Ring pct={pct} size={18} warn={missing.length > 0} />
                      {p.label}
                    </button>
                  );
                })}
          </div>
        )}
      </div>

      {notice && (
        <div
          role="status"
          aria-live="polite"
          className="notice"
          style={{ borderLeft: `4px solid ${notice.tone === "red" ? "var(--text-error)" : "var(--green-600)"}` }}
        >
          <div className="row" style={{ justifyContent: "space-between", gap: 10, alignItems: "flex-start" }}>
            <b style={{ fontSize: 14, fontWeight: 700 }}>{notice.title}</b>
            <button type="button" aria-label="Dismiss" onClick={() => setNotice(null)}
              style={{ border: 0, background: "none", cursor: "pointer", padding: 0, display: "flex" }}>
              <Icon name="x" size={14} />
            </button>
          </div>
          {notice.lines && notice.lines.length > 0 && (
            <ul style={{ margin: "6px 0 0", paddingLeft: 18, fontSize: 13, color: "var(--text-secondary)" }}>
              {notice.lines.map((m) => (
                <li key={m}>{m}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {job.issue_in_progress && (
        <Banner tone="blue" icon="loader">
          <b style={{ fontWeight: 500 }}>Producing the final report…</b> This page updates when it&apos;s done.
        </Banner>
      )}

      {!isLocked && !job.issue_in_progress && job.issue_error && (
        <Banner tone="red" icon="alert-circle">
          <b style={{ fontWeight: 500 }}>The final report couldn&apos;t be produced.</b> {job.issue_error}
        </Banner>
      )}

      {/* --- body + right panel -------------------------------------- */}
      <div className="jobcols" style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="card">

            {current.key === "review" ? (
              <ReviewPanel job={job} jobId={id} onSend={() => go("send")} />
            ) : current.key === "send" ? (
              <SendPanel job={job} jobId={id} />
            ) : current.key === "evidence" ? (
              <EvidenceTab
                jobId={id}
                canEdit={Boolean(job.tabs.evidence?.can_edit)}
                readOnlyReason={job.tabs.evidence?.read_only_reason ?? ""}
              />
            ) : (
              current.tab &&
              job.tabs[current.key] && (
                <>
                  {/* Tabs shown inside this section (the Check List at the top of Inspection). */}
                  {pages
                    .filter((p) => p.within === current.key && p.tab && job.tabs[p.key])
                    .map((p) => (
                      <div key={p.key} style={{ marginBottom: 28, paddingBottom: 8, borderBottom: "1px solid var(--border-divider)" }}>
                        <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 4 }}>{p.label}</div>
                        <TabEditor key={p.key} jobId={id} tab={p.tab!} state={job.tabs[p.key]} allValues={allValues} />
                      </div>
                    ))}
                  {pages.some((p) => p.within === current.key) && (
                    <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 4 }}>{current.label}</div>
                  )}
                  {/* Keyed so each section gets its own autosave state, and
                      leaving one flushes whatever was typed last. */}
                  <TabEditor key={current.key} jobId={id} tab={current.tab} state={job.tabs[current.key]} allValues={allValues} />
                </>
              )
            )}

            {/* --- previous / next, across stages (fixed above the tab bar on phones) --- */}
            <div
              className="row pagenav"
              style={{ justifyContent: "space-between", marginTop: 24, paddingTop: 16, borderTop: "1px solid var(--border-divider)" }}
            >
              {opsView && current.stage === "setup" && !next && (
                <span className="row" style={{ gap: 8, fontSize: 14, color: setupDone ? "var(--green-600)" : "var(--text-muted)", order: 2 }}>
                  <Icon name={setupDone ? "check-circle" : "user-check"} size={16} />
                  {setupDone
                    ? `Setup complete. Handed off to the valuer${valuerName ? ` (${valuerName})` : ""}.`
                    : "Complete Setup to hand the job off to the valuer."}
                </span>
              )}
              {prev ? (
                <Button variant="outline" size="sm" icon={<Icon name="chevron-left" size={16} />} onClick={() => go(prev.key)}>
                  <FitText>{prevLabel(prev)}</FitText>
                </Button>
              ) : (
                <span />
              )}
              <div className="row" style={{ gap: 8 }}>
                {(current.stage === "inspection" || current.stage === "valuation") && Boolean(job.tabs.valuation?.can_edit) && (
                  <Button size="sm" variant="outline" icon={<Icon name="file-text" size={16} />} onClick={() => setReportStep("")} aria-label="Report fields">
                    <span className="hide-app">Report fields</span>
                  </Button>
                )}
                {next && (
                  <Button size="sm" onClick={() => go(next.key)}>
                    <FitText>{nextLabel(next)}</FitText>
                    <Icon name="chevron-right" size={16} />
                  </Button>
                )}
              </div>
            </div>
          </div>
        </div>
        {showLiveReport ? (
          <LiveReport jobId={id} tabKey={current.key} signature={reportSignature} onClose={() => toggleLiveReport(false)} />
        ) : (
          /* Evidence has the AVM in the page and needs the width for its table. */
          current.stage === "valuation" && current.key !== "evidence" && <RightPanel jobId={id} />
        )}
      </div>

      {reportStep !== null && (
        <ReportFieldsDialog
          open
          jobId={id}
          tabs={(tabs ?? []).filter((t) => t.stage === "setup" || t.stage === "inspection" || t.stage === "valuation")}
          excluded={Array.isArray(job.report_exclusions) ? (job.report_exclusions as string[]) : []}
          onClose={() => setReportStep(null)}
          onSaved={() => {
            try {
              window.localStorage.setItem(reportStepKey, "1");
            } catch {
              /* private mode: the step simply shows again next time */
            }
            const target = reportStep;
            setReportStep(null);
            if (target) {
              setNotice({ tone: "green", title: `On to ${stageLabel(pages.find((p) => p.key === target)?.stage ?? "valuation")}` });
              setActive(target);
              window.scrollTo({ top: 0, behavior: "smooth" });
            }
          }}
        />
      )}
    </Shell>
  );
}
