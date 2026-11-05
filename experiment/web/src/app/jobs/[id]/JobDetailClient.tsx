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
 * it as an accordion: each shows its progress, and opens to its form; the
 * first unfinished one starts open. Completing a stage's sections moves the job on by itself (server:
 * transitions.sync_stage). Moving forward into a later stage needs every
 * earlier stage complete: Next (or a later stage's tab) says what is missing
 * instead. Leaving a completed Valuation stage asks what goes in the report.
 *
 * Sections are edited in place through `TabEditor`, which renders each one
 * from the shared field config and autosaves via the per-tab PATCH endpoint.
 * Completion rings come from the server, which evaluates the same
 * required/visible rules, so there is one answer to "is this section done?".
 */

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError, apiFetch } from "@/lib/api";
import { ReportFieldsDialog } from "@/components/vp/ReportFieldsDialog";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Avatar, Button, Icon } from "@/design-system";
import { Banner, LocationPath, Shell } from "@/components/vp/ui";
import { EvidenceTab } from "@/components/vp/EvidenceTab";
import { FitText } from "@/components/vp/FitText";
import { ReportActions } from "@/components/vp/ReportActions";
import { ReassignDialog } from "@/components/vp/ReassignDialog";
import { CallForm } from "@/components/vp/CallForm";

/** Logged together with Save call (CallForm), not autosaved field by field. */
const CALL_FIELDS = ["call_status", "call_remark", "inspection_booked_at"];
import { ReviewPanel, SendPanel } from "@/components/vp/ReviewPanel";
import { LostDialog } from "@/components/vp/LostDialog";
import { RightPanel } from "@/components/vp/RightPanel";
import { MediaTab } from "@/components/vp/MediaTab";
import { TabEditor } from "@/components/vp/TabEditor";
import { useFieldConfig, type TabDef } from "@/lib/fieldConfig";
import { buildTabValues, useJob, type CallAttempt, type JobDetail } from "@/lib/jobs";
import { formatDateTime } from "@/components/vp/format";
import { useMe } from "@/lib/auth";

type NavStage = "setup" | "scheduling" | "inspection" | "valuation" | "review" | "send";

/** The main tabs, and whose stage each is (a role on the job). */
const NAV: { key: NavStage; label: string; role: string; roleLabel: string }[] = [
  { key: "setup", label: "Setup", role: "admin", roleLabel: "Ops" },
  { key: "scheduling", label: "Scheduling", role: "inspector", roleLabel: "Inspector" },
  { key: "inspection", label: "Inspection", role: "valuer", roleLabel: "Valuer" },
  { key: "valuation", label: "Valuation", role: "valuer", roleLabel: "Valuer" },
  { key: "review", label: "Review", role: "peer_reviewer", roleLabel: "Peer reviewer" },
  { key: "send", label: "Send to bank", role: "admin", roleLabel: "Ops" },
];

/** Where the job's status sits among the stages. */
const STAGE_FOR_STATUS: Record<string, NavStage> = {
  instruction_received: "setup",
  setup: "setup",
  scheduling: "scheduling",
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

export function JobDetailClient({ id }: { id: string }) {
  const { data: job, isLoading: jobLoading, isError } = useJob(id);
  const qc = useQueryClient();
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
  const [losing, setLosing] = useState(false);
  const [reassigning, setReassigning] = useState(false);
  // The stage's open sections; null until the user opens or closes one, when
  // the section the stage opened on is the open one.
  const [openStages, setOpenStages] = useState<NavStage[]>([]);
  // The current stage starts open; these are the ones folded up by hand.
  const [closedStages, setClosedStages] = useState<NavStage[]>([]);

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
    // The documents Admin uploaded, for the inspector to read on site (QA #10).
    // They're added and managed on Documents in the Valuation stage.
    { key: "documents-received", label: "Documents received", stage: "inspection" },
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
  // Ops look after Setup and book the inspection on Scheduling.
  const OPS_STAGES: NavStage[] = ["setup", "scheduling"];
  const jobStage = STAGE_FOR_STATUS[job.status] ?? "setup";
  const statusStage = opsView && !OPS_STAGES.includes(jobStage) ? "scheduling" : jobStage;
  const defaultPage =
    navPages.find((p) => p.stage === statusStage && p.tab && completionOf(p.key).pct < 100) ??
    navPages.find((p) => p.stage === statusStage) ??
    navPages[0];
  const current = navPages.find((p) => p.key === active && (!opsView || OPS_STAGES.includes(p.stage))) ?? defaultPage;
  // The page opens on the first unfinished section, then stays there: finishing
  // a section (or the job's status changing) never moves the screen on; only
  // Next, Previous or a click on the left does.
  if (active === null) setActive(defaultPage.key);
  // Previous / Next move between stages; a stage's sections are all on its page.
  // Previous / Next walk the sub-stages one at a time; past the last one of a
  // stage, Next moves on to the next stage (and asks the server to, QA #9).
  // For ops the walk ends with Scheduling: the stages after are the valuer's.
  const flow = opsView ? navPages.filter((p) => OPS_STAGES.includes(p.stage)) : navPages;
  const at = flow.findIndex((p) => p.key === current.key);
  const prev = at > 0 ? flow[at - 1] : null;
  const next = at >= 0 && at < flow.length - 1 ? flow[at + 1] : null;
  const setupDone = (pages.filter((p) => p.stage === "setup" && p.tab)).every((p) => (job.tabs[p.key]?.completion.pct ?? 0) === 100);
  const valuerName = (job.assignees as { name: string; roles: string[] }[] | undefined)?.find((a) => a.roles.includes("valuer"))?.name;
  const stageLabel = (key: NavStage) => NAV.find((s) => s.key === key)?.label ?? key;

  const STAGE_ORDER: NavStage[] = ["setup", "scheduling", "inspection", "valuation", "review", "send"];
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

  /** The job moves on only when Next is pressed (QA #9): each complete stage
   * the job is still in, short of `target`, is advanced on the server. */
  const ADVANCES: NavStage[] = ["setup", "scheduling", "inspection"];
  const advanceTo = async (target: NavStage) => {
    let moved = false;
    for (const stage of ADVANCES) {
      if (STAGE_ORDER.indexOf(stage) < STAGE_ORDER.indexOf(jobStage)) continue; // already past it
      if (STAGE_ORDER.indexOf(stage) >= STAGE_ORDER.indexOf(target)) break;
      await apiFetch(`/api/jobs/${id}/advance/`, { method: "POST", body: JSON.stringify({ stage }) });
      moved = true;
    }
    if (moved) await qc.invalidateQueries({ queryKey: ["jobs", id] });
  };

  const go = (key: string) => {
    const target = pages.find((p) => p.key === key);
    // Moving on from a section with required fields still empty isn't allowed
    // for whoever fills it in; going back always is.
    const ahead = flow.findIndex((p) => p.key === key) > flow.findIndex((p) => p.key === current.key);
    const here = completionOf(current.key);
    if (ahead && current.tab && job.tabs[current.key]?.can_edit && here.missing.length && !isLocked) {
      setNotice({ tone: "red", title: `Fill in the required fields on ${current.label} first`, lines: here.missing });
      return;
    }
    const forward = Boolean(target && target.stage !== current.stage && STAGE_ORDER.indexOf(target.stage) > STAGE_ORDER.indexOf(current.stage));
    if (target && forward) {
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
      if (!isLocked) {
        void advanceTo(target.stage)
          .then(() => open(key, target))
          .catch((err) => setNotice({ tone: "red", title: err instanceof ApiError ? err.message : "Couldn't move the lead on. Try again." }));
        return;
      }
    }
    open(key, target);
  };
  const open = (key: string, target: (typeof pages)[number] | undefined) => {
    if (target && target.stage !== current.stage && STAGE_ORDER.indexOf(target.stage) > STAGE_ORDER.indexOf(current.stage)) {
      setNotice({ tone: "green", title: `On to ${stageLabel(target.stage)}` });
    }
    if (target) setClosedStages((closed) => closed.filter((s) => s !== target.stage));
    setActive(key);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const goStage = (stage: NavStage) => {
    const inStage = navPages.filter((p) => p.stage === stage);
    const firstOpen = inStage.find((p) => p.tab && completionOf(p.key).pct < 100);
    go((firstOpen ?? inStage[0]).key);
  };

  const assignees = (job.assignees ?? []) as Assignee[];
  const ownerOf = (role: string) => assignees.find((a) => a.roles.includes(role))?.name;
  const isLocked = job.is_locked;

  // Within a stage the buttons name the sub-stage; across stages, the stage.
  const nameOf = (p: Page) => (p.stage === current.stage ? p.label : stageLabel(p.stage));
  const nextLabel = (p: Page) => `Next: ${nameOf(p)}`;
  const prevLabel = (p: Page) => nameOf(p);
  const shownStages = new Set<NavStage>([
    ...openStages,
    ...(closedStages.includes(current.stage) ? [] : [current.stage]),
  ]);
  const toggleStage = (stage: NavStage) => {
    const shown = shownStages.has(stage);
    setOpenStages((open) => (shown ? open.filter((s) => s !== stage) : [...open, stage]));
    setClosedStages((closed) => (shown ? [...closed, stage] : closed.filter((s) => s !== stage)));
  };
  /** A stage's progress: the average of its sub-stages with a form. */
  const stagePct = (stage: NavStage) => {
    const tabbed = navPages.filter((p) => p.stage === stage && p.tab);
    if (!tabbed.length) return stageDone(stage, job, pages) ? 100 : 0;
    return Math.round(tabbed.reduce((n, p) => n + completionOf(p.key).pct, 0) / tabbed.length);
  };
  // The lead card shows beside every stage but Send to bank, which needs the width.
  const showPanel = current.stage !== "send";

  /** One section's form (or Evidence's table), as it was shown on its own. */
  const sectionBody = (page: Page) => {
    if (page.key === "evidence") {
      return (
        <EvidenceTab
          jobId={id}
          canEdit={Boolean(job.tabs.evidence?.can_edit)}
          readOnlyReason={job.tabs.evidence?.read_only_reason ?? ""}
        />
      );
    }
    if (page.key === "documents-received") return <MediaTab jobId={id} kind="documents" readOnly />;
    if (!page.tab || !job.tabs[page.key]) return null;
    return (
      <>
        {/* Tabs shown inside this section (the Check List at the top of Inspection). */}
        {pages
          .filter((p) => p.within === page.key && p.tab && job.tabs[p.key])
          .map((p) => (
            <div key={p.key} style={{ marginBottom: 24, paddingBottom: 8, borderBottom: "1px solid var(--border-divider)" }}>
              <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 4 }}>{p.label}</div>
              <TabEditor key={p.key} jobId={id} tab={p.tab!} state={job.tabs[p.key]} allValues={allValues}
                suggestions={job.suggestions} canDecide={job.can_decide_suggestions} />
            </div>
          ))}
        {pages.some((p) => p.within === page.key) && (
          <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 4 }}>{page.label}</div>
        )}
        {/* Keyed so each section keeps its own autosave state. */}
        <TabEditor key={page.key} jobId={id} tab={page.tab} state={job.tabs[page.key]} allValues={allValues}
          omit={page.key === "scheduling" ? CALL_FIELDS : undefined}
          suggestions={job.suggestions} canDecide={job.can_decide_suggestions} />
        {page.key === "scheduling" && (
          <>
            <CallForm
              jobId={id}
              canEdit={Boolean(job.tabs.scheduling?.can_edit)}
              current={String(job.tabs.scheduling?.values.call_status ?? "")}
            />
            <CallLog calls={job.call_log ?? []} />
          </>
        )}
      </>
    );
  };

  return (
    <Shell>
      {/* --- header: the job, then its stages ------------------------- */}
      <div className="card jobhead">
        {/* Breadcrumb on the left; status, report preview and the team on the right. */}
        <div className="row jobtop" style={{ justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
          <Link href="/jobs" className="show-app backlink">
            ‹ Jobs
          </Link>
          <div className="jh-crumb hide-app">
            <Link href="/jobs">Jobs</Link>
            <span>/</span>
            <span className="jh-ref num">{job.bayut_internal_reference_no}</span>
          </div>
          <div className="row jobmeta" style={{ gap: 12, flexShrink: 0 }}>
            {!isLocked && current.stage !== "review" && current.stage !== "send" && <ReportActions jobId={id} />}
            <span className="jh-status"><span />{job.status_label as string}</span>
            {job.can_mark_lost && !showPanel && (
              <button type="button" className="lost-btn sm" onClick={() => setLosing(true)} aria-label="Mark as lost">
                <Icon name="circle-x" size={16} />
                <span className="hide-app">Mark as lost</span>
              </button>
            )}
            <div className="row" style={{ gap: 0 }}>
              {assignees.map((person, i) => (
                <span
                  key={person.id}
                  title={`${person.name} · ${person.roles.map((r) => r.replace(/_/g, " ")).join(", ")}`}
                  style={{ marginLeft: i ? -6 : 0, boxShadow: "0 0 0 2px #fff", borderRadius: "50%" }}
                >
                  <Avatar name={person.name} size={32} />
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* Title and its references; the checks that have passed on the right. */}
        <div className="row jh-main">
          <div style={{ minWidth: 0 }}>
            <div className="row" style={{ gap: 10 }}>
              <h1 className="page-title" style={{ margin: 0 }}>{job.property_label}</h1>
              {isLocked && <span title="Issued and locked"><Icon name="lock" size={18} color="var(--text-muted)" /></span>}
            </div>
            <div className="jh-meta">
              {(job.location_path ?? []).length > 0 && (
                <>
                  <LocationPath parts={job.location_path} />
                  <span className="jh-sep">•</span>
                </>
              )}
              <span>Bayut ref: <b className="num">{job.bayut_internal_reference_no}</b></span>
              {job.bank_reference_no ? (
                <>
                  <span className="jh-sep">•</span>
                  <span>Bank ref: <b className="num">{job.bank_reference_no}</b></span>
                </>
              ) : null}
              <span className="jh-sep">•</span>
              <span className="jh-bank">{job.bank_name}</span>
            </div>
          </div>
        </div>
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

      {job.lost && (
        <Banner tone="red" icon="circle-x">
          <b style={{ fontWeight: 500 }}>Lost at {job.lost.stage}: {job.lost.reason}.</b>
          {job.lost.note ? ` ${job.lost.note}` : ""}
        </Banner>
      )}
      {losing && <LostDialog jobId={id} onClose={() => setLosing(false)} />}
      {reassigning && (
        <ReassignDialog jobId={id} onClose={() => setReassigning(false)}
          current={Object.fromEntries(assignees.flatMap((p) => p.roles.map((r) => [r, p.id])))} />
      )}

      {job.issue_in_progress && (
        <Banner tone="blue" icon="loader">
          <b style={{ fontWeight: 500 }}>Producing the final report…</b> This page updates when it&apos;s done.
        </Banner>
      )}

      {!isLocked && !job.issue_in_progress && job.issue_error && (
        <Banner tone="red" icon="circle-alert">
          <b style={{ fontWeight: 500 }}>The final report couldn&apos;t be produced.</b> {job.issue_error}
        </Banner>
      )}

      {/* --- body + right panel -------------------------------------- */}
      <div className="jobcols" style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
        {/* --- the stages down the left, each opening onto its sub-stages --- */}
        <nav aria-label="Stages" className="card stagecol">
          {/* Overall progress: how many of the stages are finished. */}
          {(() => {
            const finished = NAV.filter((s) => stageDone(s.key, job, pages)).length;
            const overall = Math.round((finished / NAV.length) * 100);
            return (
              <div className="sc-overall">
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <span className="sc-eyebrow">Workflow progress</span>
                  <b>{overall}% done</b>
                </div>
                <div className="sc-overall-sub">{finished} of {NAV.length} stages finalised</div>
                <span className="sc-bar"><span style={{ width: `${overall}%` }} /></span>
              </div>
            );
          })()}
          <div className="sc-line-wrap">
            {NAV.map((stage, i) => {
              const done = stageDone(stage.key, job, pages);
              const selected = stage.key === current.stage;
              const now = stage.key === statusStage && !done;
              const owner = ownerOf(stage.role);
              const greyed = opsView && !OPS_STAGES.includes(stage.key);
              const subs = navPages.filter((p) => p.stage === stage.key);
              const open = subs.length > 1 && shownStages.has(stage.key);
              const pct = stagePct(stage.key);
              const hasBar = stage.key !== "review" && stage.key !== "send" && subs.some((p) => p.tab);
              const last = i === NAV.length - 1;
              return (
                <div key={stage.key} className={"sc-stage" + (selected ? " on" : "") + (done ? " done" : "")}>
                  {/* The line down to the next stage: solid once this one is done. */}
                  {!last && <span className={"sc-line" + (done ? " done" : now ? " now" : "")} />}
                  <button type="button" className="sc-head" disabled={greyed} aria-expanded={subs.length > 1 ? open : undefined}
                    aria-current={selected ? "step" : undefined} title={greyed ? "The valuer's stage" : undefined}
                    onClick={() => (subs.length > 1 ? toggleStage(stage.key) : goStage(stage.key))}>
                    <span className={"sc-dot" + (done ? " done" : now || selected ? " now" : "")}>
                      {done ? <Icon name="check" size={15} /> : now || selected ? i + 1 : <span className="sc-pip" />}
                    </span>
                    <span className="sc-text">
                      <span className="row" style={{ justifyContent: "space-between", gap: 6 }}>
                        <span className="sc-label">{stage.label}</span>
                        {selected ? (
                          <span className="sc-pill active">Active</span>
                        ) : hasBar || done ? (
                          <span className={"sc-pill num" + (done || pct === 100 ? " done" : "")}>{done ? "100" : pct}%</span>
                        ) : null}
                      </span>
                      <span className="sc-owner" title={owner ? `${stage.roleLabel}: ${owner}` : undefined}>
                        {owner ?? `${stage.roleLabel} not assigned`}
                      </span>
                    </span>
                    {/* Every stage keeps the chevron's slot, so the pills line up. */}
                    <span className="sc-chev">
                      {subs.length > 1 && <Icon name={open ? "chevron-down" : "chevron-right"} size={16} color="var(--text-muted)" />}
                    </span>
                  </button>
                  {open && (
                    <div className="sc-subs">
                      {subs.map((p) => {
                        const c = completionOf(p.key);
                        return (
                          <button key={p.key} type="button" className={"sc-sub" + (p.key === current.key ? " on" : "")}
                            aria-current={p.key === current.key ? "page" : undefined} disabled={greyed} onClick={() => go(p.key)}
                            title={c.missing.length ? `Missing: ${c.missing.join(", ")}` : undefined}>
                            <span className={"sc-subdot" + (p.tab && c.pct === 100 ? " done" : p.key === current.key ? " on" : "")} />
                            <span className="sc-sub-label">{p.label}</span>
                            {p.tab && (c.pct === 100
                              ? <span className="sc-pct done">✓</span>
                              : <span className="sc-pct num">{c.pct}%</span>)}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </nav>

        <div className="maincol">
          {/* The stage and sub-stage being worked on, with its progress. */}
          <div className="card stagehead">
            <div className="row" style={{ justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
              <div style={{ minWidth: 0 }}>
                <div className="sh-eyebrow">{current.stage === statusStage ? "Active stage" : "Viewing stage"}</div>
                <h2 className="sh-title">
                  {stageLabel(current.stage)}
                  {current.label !== stageLabel(current.stage) && (
                    <>
                      <span className="sh-sep">›</span>
                      <span className="sh-sub">{current.label}</span>
                    </>
                  )}
                </h2>
              </div>
              {current.tab && (() => {
                const { pct, missing } = completionOf(current.key);
                return (
                  <span className="acc-meta">
                    {missing.length > 0 && (
                      <span className="acc-req" title={`Missing: ${missing.join(", ")}`}>{missing.length} required</span>
                    )}
                    <span className="acc-bar"><span style={{ width: `${pct}%` }} className={pct === 100 ? "done" : ""} /></span>
                    <span className={"sh-pct num" + (pct === 100 ? " done" : "")}>{pct}%</span>
                  </span>
                );
              })()}
            </div>
            {isLocked && <LockedBanner job={job} jobId={id} />}
          </div>

          <div className="card">
            {current.key === "review" ? (
              <ReviewPanel job={job} jobId={id} onSend={() => go("send")} />
            ) : current.key === "send" ? (
              <SendPanel job={job} jobId={id} />
            ) : (
              <section id={`section-${current.key}`}>{sectionBody(current)}</section>
            )}

            {/* --- previous / next, across stages (fixed above the tab bar on phones) --- */}
            <div
              className="row pagenav"
              style={{ justifyContent: "space-between", marginTop: 24, paddingTop: 16, borderTop: "1px solid var(--border-divider)" }}
            >
              {opsView && OPS_STAGES.includes(current.stage) && !next && (
                <span className="row" style={{ gap: 8, fontSize: 14, color: setupDone ? "var(--green-600)" : "var(--text-muted)", order: 2 }}>
                  <Icon name={setupDone ? "circle-check" : "user-check"} size={16} />
                  {setupDone && STAGE_ORDER.indexOf(jobStage) > STAGE_ORDER.indexOf("scheduling")
                    ? `Inspection booked. Handed off to the valuer${valuerName ? ` (${valuerName})` : ""}.`
                    : "Book the inspection to hand the job off to the valuer."}
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
        {/* The lead card beside the data-entry stages, with Mark as lost under
            it (Review and Send to bank need the full width). */}
        {showPanel && (
          <div className="sidecol">
            <RightPanel jobId={id} />
            {job.can_mark_lost && (
              <button type="button" className="lost-btn" onClick={() => setLosing(true)}>
                <Icon name="circle-x" size={16} />
                Mark lead as lost
              </button>
            )}
            {job.can_reassign && (
              <Button variant="outline" icon={<Icon name="user-round-pen" size={16} />} onClick={() => setReassigning(true)}
                style={{ width: "100%", height: 40 }}>
                Reassign lead
              </Button>
            )}
          </div>
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

/** An issued job is locked: say so, and offer the next version to whoever
 * may start one (admins, once; then a link to it). */
function LockedBanner({ job, jobId }: { job: JobDetail; jobId: string }) {
  const router = useRouter();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function revise() {
    setBusy(true);
    setError(null);
    try {
      const revision = await apiFetch<{ id: number }>(`/api/jobs/${jobId}/revise/`, { method: "POST" });
      await qc.invalidateQueries({ queryKey: ["jobs"] });
      router.push(`/jobs/${revision.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't reach the server. Try again.");
      setBusy(false);
    }
  }
  return (
    <div className="lockbar">
      <span className="lockbar-icon"><Icon name="lock" size={16} /></span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <b>This job has been issued and is locked.</b>
        <div>Any change needs a new revision of the job.</div>
        {error && <div style={{ color: "var(--text-error)", marginTop: 4 }}>{error}</div>}
      </div>
      {job.revision ? (
        <Link href={`/jobs/${job.revision.id}`} className="lockbar-btn">
          Open v{job.revision.version}
        </Link>
      ) : job.can_revise ? (
        <button type="button" className="lockbar-btn" disabled={busy} onClick={() => void revise()}>
          {busy ? "Creating…" : "Create revision"}
        </button>
      ) : null}
    </div>
  );
}

/** Every call made to book the inspection, newest first (CRM feedback SC-04). */
function CallLog({ calls }: { calls: CallAttempt[] }) {
  return (
    <div className="calllog">
      <div className="row" style={{ gap: 8, marginBottom: 10 }}>
        <b style={{ fontSize: 15 }}>Call log</b>
        <span className="calllog-count">{calls.length} {calls.length === 1 ? "entry" : "entries"}</span>
      </div>
      {calls.length === 0 ? (
        <div style={{ fontSize: 14, color: "var(--text-muted)" }}>No calls logged yet. Each save above is logged here.</div>
      ) : (
        <div className="stack8">
          {calls.map((c) => (
            <div key={c.id} className="calllog-item">
              <div className="row wrap calllog-top">
                <span className="row" style={{ gap: 8 }}>
                  <span className={"calllog-dot" + (c.booked_for ? " ok" : "")} />
                  <b>{c.status_label}</b>
                </span>
                <span className="calllog-when">
                  {formatDateTime(c.at)}
                  {c.by ? ` • ${c.by}` : ""}
                </span>
              </div>
              {(c.booked_for || c.remark) && (
                <div className="calllog-body">
                  {c.booked_for && (
                    <div className="row" style={{ justifyContent: "space-between", gap: 8 }}>
                      <span>Booked for <b>{formatDateTime(c.booked_for)}</b></span>
                      <span className="calllog-ok"><Icon name="check" size={14} /> Booked</span>
                    </div>
                  )}
                  {c.remark && <div style={{ color: "var(--text-secondary)", whiteSpace: "pre-wrap" }}>{c.remark}</div>}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
