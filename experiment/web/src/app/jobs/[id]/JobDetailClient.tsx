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
 * instead. Leaving a completed Inspection stage asks what goes in the report.
 *
 * Sections are edited in place through `TabEditor`, which renders each one
 * from the shared field config and autosaves via the per-tab PATCH endpoint.
 * Completion rings come from the server, which evaluates the same
 * required/visible rules, so there is one answer to "is this section done?".
 */

import { useState } from "react";
import { ReportFieldsDialog } from "@/components/vp/ReportFieldsDialog";
import Link from "next/link";
import { Avatar, Button, Icon } from "@/design-system";
import { Banner, Ring, Shell, StatusChip } from "@/components/vp/ui";
import { EvidenceTab } from "@/components/vp/EvidenceTab";
import { ReportActions } from "@/components/vp/ReportActions";
import { ReviewPanel, SendPanel } from "@/components/vp/ReviewPanel";
import { RightPanel } from "@/components/vp/RightPanel";
import { TabEditor } from "@/components/vp/TabEditor";
import { useFieldConfig, type TabDef } from "@/lib/fieldConfig";
import { buildTabValues, useJob, type JobDetail } from "@/lib/jobs";

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

type Page = { key: string; label: string; stage: NavStage; tab?: TabDef };
type Assignee = { id: number; name: string; roles: string[] };

function stageDone(stage: NavStage, job: JobDetail, pages: Page[]): boolean {
  if (stage === "review") return job.status === "approved_signed" || job.status === "issued";
  if (stage === "send") return (job.deliveries ?? []).length > 0;
  const inStage = pages.filter((p) => p.stage === stage && p.tab);
  return inStage.length > 0 && inStage.every((p) => (job.tabs[p.key]?.completion.pct ?? 0) === 100);
}

export function JobDetailClient({ id }: { id: string }) {
  const { data: job, isLoading: jobLoading, isError } = useJob(id);
  const { data: tabs, isLoading: tabsLoading } = useFieldConfig();
  const [active, setActive] = useState<string | null>(null);
  // What stops moving on to the next stage, shown when Next is pressed.
  const [stageBlock, setStageBlock] = useState<{ stage: string; missing: string[] } | null>(null);
  // The include-in-report step, and where to go once it is saved.
  const [reportStep, setReportStep] = useState<string | null>(null);

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
      .map((t) => ({ key: t.key, label: t.key === "review" ? "Review & sign off" : t.label, stage: t.stage as NavStage, tab: t })),
    { key: "send", label: "Send to bank", stage: "send" },
  ];

  const statusStage = STAGE_FOR_STATUS[job.status] ?? "setup";
  const defaultPage =
    pages.find((p) => p.stage === statusStage && p.tab && (job.tabs[p.key]?.completion.pct ?? 100) < 100) ??
    pages.find((p) => p.stage === statusStage) ??
    pages[0];
  const current = pages.find((p) => p.key === active) ?? defaultPage;
  const index = pages.findIndex((p) => p.key === current.key);
  const prev = index > 0 ? pages[index - 1] : null;
  const next = index < pages.length - 1 ? pages[index + 1] : null;
  const stageLabel = (key: NavStage) => NAV.find((s) => s.key === key)?.label ?? key;
  const stagePages = pages.filter((p) => p.stage === current.stage);

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
  const reportStepKey = `report-fields-confirmed:${id}`;
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
        setStageBlock(block);
        window.scrollTo({ top: 0, behavior: "smooth" });
        return;
      }
      // Leaving a complete Inspection stage: choose what goes in the report.
      const canChoose = Boolean(job.tabs.inspection?.can_edit);
      if (current.stage === "inspection" && canChoose && !reportStepDone()) {
        setReportStep(key);
        return;
      }
    }
    setStageBlock(null);
    setActive(key);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const goStage = (stage: NavStage) => {
    const inStage = pages.filter((p) => p.stage === stage);
    const firstOpen = inStage.find((p) => p.tab && (job.tabs[p.key]?.completion.pct ?? 100) < 100);
    go((firstOpen ?? inStage[0]).key);
  };

  const property = (job.property ?? {}) as Record<string, string>;
  const assignees = (job.assignees ?? []) as Assignee[];
  const ownerOf = (role: string) => assignees.find((a) => a.roles.includes(role))?.name;
  const isLocked = job.is_locked;

  const nextLabel = (p: Page) =>
    p.stage === current.stage ? `Next: ${p.label}` : `Next: ${stageLabel(p.stage)}${p.label !== stageLabel(p.stage) && stagePagesCount(p.stage) > 1 ? ` · ${p.label}` : ""}`;
  const prevLabel = (p: Page) => (p.stage === current.stage ? p.label : `${stageLabel(p.stage)}${stagePagesCount(p.stage) > 1 ? ` · ${p.label}` : ""}`);
  function stagePagesCount(stage: NavStage) {
    return pages.filter((p) => p.stage === stage).length;
  }

  return (
    <Shell>
      {/* --- header: the job, then its stages ------------------------- */}
      <div className="card" style={{ marginBottom: 16, padding: "18px 22px 0" }}>
        <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start", gap: 20 }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 4 }}>
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

          <div className="row" style={{ gap: 12, flexShrink: 0 }}>
            {!isLocked && current.stage !== "review" && current.stage !== "send" && <ReportActions jobId={id} />}
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

        {/* --- the stages, as tabs ------------------------------------ */}
        <nav aria-label="Stages" className="stagenav" style={{ display: "flex", marginTop: 18, borderTop: "1px solid var(--border-divider)" }}>
          {NAV.map((stage, i) => {
            const done = stageDone(stage.key, job, pages);
            const selected = stage.key === current.stage;
            const now = stage.key === statusStage && !done;
            const owner = ownerOf(stage.role);
            return (
              <button
                key={stage.key}
                type="button"
                onClick={() => goStage(stage.key)}
                aria-current={selected ? "step" : undefined}
                style={{
                  flex: 1,
                  minWidth: 0,
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  padding: "14px 10px 12px",
                  border: 0,
                  borderBottom: `2px solid ${selected ? "var(--action-primary)" : "transparent"}`,
                  background: "none",
                  cursor: "pointer",
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
                    {stage.label}
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
      </div>

      {stageBlock && (
        <Banner tone="red" icon="alert-circle">
          <b style={{ fontWeight: 500 }}>Complete the {stageBlock.stage} stage before moving on.</b> Still required:
          <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
            {stageBlock.missing.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </Banner>
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
            {/* The stage's sections, when it has more than one. */}
            {stagePages.length > 1 && (
              <div className="row wrap" style={{ gap: 6, marginBottom: 20 }}>
                {stagePages.map((p) => {
                  const { pct, missing } = job.tabs[p.key]?.completion ?? { pct: 0, missing: [] };
                  const on = p.key === current.key;
                  return (
                    <button
                      key={p.key}
                      type="button"
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
                // Keyed so each section gets its own autosave state, and
                // leaving one flushes whatever was typed last.
                <TabEditor key={current.key} jobId={id} tab={current.tab} state={job.tabs[current.key]} allValues={allValues} />
              )
            )}

            {/* --- previous / next, across stages ---------------------- */}
            <div
              className="row"
              style={{ justifyContent: "space-between", marginTop: 24, paddingTop: 16, borderTop: "1px solid var(--border-divider)" }}
            >
              {prev ? (
                <Button variant="outline" size="sm" icon={<Icon name="chevron-left" size={16} />} onClick={() => go(prev.key)}>
                  {prevLabel(prev)}
                </Button>
              ) : (
                <span />
              )}
              <div className="row" style={{ gap: 8 }}>
                {current.stage === "inspection" && Boolean(job.tabs.inspection?.can_edit) && (
                  <Button size="sm" variant="outline" icon={<Icon name="file-text" size={16} />} onClick={() => setReportStep("")}>
                    Report fields
                  </Button>
                )}
                {next && (
                  <Button size="sm" onClick={() => go(next.key)}>
                    {nextLabel(next)}
                    <Icon name="chevron-right" size={16} />
                  </Button>
                )}
              </div>
            </div>
          </div>
        </div>
        <RightPanel jobId={id} />
      </div>

      {reportStep !== null && (
        <ReportFieldsDialog
          open
          jobId={id}
          tabs={(tabs ?? []).filter((t) => t.key === "summary" || t.key === "inspection")}
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
              setStageBlock(null);
              setActive(target);
              window.scrollTo({ top: 0, behavior: "smooth" });
            }
          }}
        />
      )}
    </Shell>
  );
}
