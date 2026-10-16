"use client";

/**
 * Job workspace — design brief S3.
 *
 * Ported from the prototype's `job-workspace-and-review.jsx`: job header,
 * stage progress, the tab rail grouped by stage with completion rings,
 * previous/next buttons, and the right panel.
 *
 * Tabs are edited in place through `TabEditor`, which renders each tab from
 * the shared field config and autosaves via the per-tab PATCH endpoint.
 * Completion rings come from the server, which evaluates the same
 * required/visible rules, so there is one answer to "is this tab done?".
 *
 * Not built on top of this yet: the prototype's bespoke composites
 * (per-floor accommodation, photo grid, document table, AVM deviation).
 * They need backend that doesn't exist (build order steps 5 and 7).
 */

import { useState } from "react";
import Link from "next/link";
import { Avatar, Button, Icon } from "@/design-system";
import { Banner, Ring, Shell, StatusChip } from "@/components/vp/ui";
import { EvidenceTab } from "@/components/vp/EvidenceTab";
import { ReportActions } from "@/components/vp/ReportActions";
import { ReviewPanel } from "@/components/vp/ReviewPanel";
import { RightPanel } from "@/components/vp/RightPanel";
import { TabEditor } from "@/components/vp/TabEditor";
import { STAGES, useFieldConfig, type StageKey } from "@/lib/fieldConfig";
import { buildTabValues, useJob } from "@/lib/jobs";

/** Which stage the job's status sits in. The stages before review move on by
 * themselves as their tabs are completed (server: transitions.sync_stage). */
const STAGE_FOR_STATUS: Record<string, StageKey> = {
  instruction_received: "setup",
  setup: "setup",
  inspection_scheduled: "inspection",
  inspected: "inspection",
  valuation_in_progress: "valuation",
  peer_review: "review",
  approved_signed: "review",
  issued: "review",
};
const REVIEW_PROGRESS: Record<string, number> = { peer_review: 33, approved_signed: 66, issued: 100 };

type Assignee = { id: number; name: string; roles: string[] };

export function JobDetailClient({ id }: { id: string }) {
  const { data: job, isLoading: jobLoading, isError } = useJob(id);
  const { data: tabs, isLoading: tabsLoading } = useFieldConfig();
  const [activeTab, setActiveTab] = useState<string | null>(null);

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
            It may not exist, or you may not hold a role on it. SSO isn&apos;t wired up yet — sign in
            via the Django admin first.
          </div>
        </div>
      </Shell>
    );
  }

  const allValues = buildTabValues(job);
  const orderedTabs = [...(tabs ?? [])].sort((a, b) => a.order - b.order);
  const currentStage = STAGE_FOR_STATUS[job.status] ?? "setup";
  // A job under review or issued opens on Review & Send; otherwise on the first tab.
  const defaultTab = currentStage === "review" ? "review" : orderedTabs[0]?.key;
  const currentTab = orderedTabs.find((t) => t.key === (activeTab ?? defaultTab)) ?? orderedTabs[0];
  const index = orderedTabs.findIndex((t) => t.key === currentTab?.key);
  const prevTab = index > 0 ? orderedTabs[index - 1] : null;
  const nextTab = index >= 0 && index < orderedTabs.length - 1 ? orderedTabs[index + 1] : null;
  const stageLabel = (key: StageKey) => STAGES.find((s) => s.key === key)?.label ?? key;
  const go = (key: string) => {
    setActiveTab(key);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const stagePct = (key: StageKey) => {
    if (key === "review") return REVIEW_PROGRESS[job.status] ?? 0;
    const inStage = orderedTabs.filter((t) => t.stage === key);
    if (!inStage.length) return 0;
    return Math.round(inStage.reduce((sum, t) => sum + (job.tabs[t.key]?.completion.pct ?? 0), 0) / inStage.length);
  };

  const property = (job.property ?? {}) as Record<string, string>;
  const assignees = (job.assignees ?? []) as Assignee[];
  const isLocked = job.is_locked;

  return (
    <Shell>
      {/* --- header ------------------------------------------------- */}
      <div className="card" style={{ marginBottom: 16, padding: "18px 22px" }}>
        <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start", gap: 20 }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 4 }}>
              <Link href="/jobs" style={{ textDecoration: "none" }}>
                Jobs
              </Link>{" "}
              › {job.bayut_internal_reference_no}
            </div>
            <div className="row" style={{ gap: 10 }}>
              <h1 style={{ margin: 0, fontSize: 24, fontWeight: 500 }}>{job.property_label}</h1>
              {isLocked && <Icon name="lock" size={20} color="var(--text-muted)" />}
            </div>
            <div className="row wrap" style={{ gap: "4px 14px", marginTop: 6, fontSize: 14, color: "var(--text-secondary)" }}>
              <span>
                {job.property_type || "—"} · {property.title_doc_emirate || "Dubai"}
              </span>
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

          <div className="row" style={{ gap: 18, flexShrink: 0 }}>
            <StatusChip s={job.status_label as string} />
            <div className="row" style={{ gap: 0 }}>
              {assignees.map((person, i) => (
                <span
                  key={person.id}
                  title={`${person.name} · ${person.roles.map((r) => r.replace(/_/g, " ")).join(", ")}`}
                  style={{ marginLeft: i ? -8 : 0, boxShadow: "0 0 0 2px #fff", borderRadius: "50%" }}
                >
                  <Avatar name={person.name} size={34} />
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* --- stages: each fills as its tabs are completed ----------- */}
        <div className="row" style={{ gap: 10, marginTop: 16 }}>
          {STAGES.map((stage) => {
            const pct = stagePct(stage.key);
            const on = stage.key === currentStage;
            const first = orderedTabs.find((t) => t.stage === stage.key);
            return (
              <button
                key={stage.key}
                type="button"
                onClick={() => first && go(first.key)}
                style={{ flex: 1, border: 0, background: "none", padding: 0, textAlign: "left", cursor: "pointer", fontFamily: "inherit" }}
              >
                <div style={{ height: 4, borderRadius: 2, background: "var(--gray-200)", overflow: "hidden" }}>
                  <div style={{ width: `${pct}%`, height: "100%", background: pct === 100 ? "var(--green-600)" : "var(--action-primary)" }} />
                </div>
                <div className="row" style={{ justifyContent: "space-between", fontSize: 13, marginTop: 6 }}>
                  <span style={{ color: on ? "var(--text-accent)" : "var(--text-secondary)", fontWeight: on ? 500 : 400 }}>
                    {stage.label}
                  </span>
                  <span className="num" style={{ color: "var(--text-muted)" }}>{pct}%</span>
                </div>
              </button>
            );
          })}
        </div>

        {/* The Review & Send tab has these itself. */}
        {!isLocked && currentTab?.key !== "review" && (
          <div className="row" style={{ justifyContent: "flex-end", gap: 10, marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--border-divider)" }}>
            <ReportActions jobId={id} />
            <Button size="sm" variant="soft" icon={<Icon name="send" size={16} />} onClick={() => go("review")}>
              Review &amp; Send
            </Button>
          </div>
        )}
      </div>

      {job.issue_in_progress && (
        <Banner tone="blue" icon="loader">
          <b style={{ fontWeight: 500 }}>Issuing the final report…</b> This page updates when it&apos;s done.
        </Banner>
      )}

      {!isLocked && !job.issue_in_progress && job.issue_error && (
        <Banner tone="red" icon="alert-circle">
          <b style={{ fontWeight: 500 }}>The last attempt to issue failed.</b> {job.issue_error}
        </Banner>
      )}

      {job.status === "approved_signed" && !job.issue_in_progress && (
        <Banner tone={job.countersigned_at ? "green" : "amber"} icon={job.countersigned_at ? "check" : "pen-tool"}>
          {job.countersigned_at
            ? `Counter-signed by ${job.countersigned_by_name ?? "the counter-signatory"} on ${new Date(job.countersigned_at).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" })}.`
            : "Waiting for the counter-signatory to counter-sign before the report can be issued."}
        </Banner>
      )}

      {isLocked && (
        <Banner tone="blue" icon="lock">
          <b style={{ fontWeight: 500 }}>
            Issued as v{job.version}
            {job.issued_at ? ` on ${new Date(job.issued_at as string).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" })}` : ""}.
          </b>{" "}
          This job is locked — the server rejects edits. To amend it, create a revision: a new version that keeps this one as signed.
        </Banner>
      )}

      {/* --- tab rail ----------------------------------------------- */}
      <div className="card" style={{ padding: "0 8px", marginBottom: 16, display: "flex", overflowX: "auto" }}>
        {orderedTabs.map((tab, i) => {
          const { pct, missing } = job.tabs[tab.key]?.completion ?? { pct: 0, missing: [] };
          const on = tab.key === currentTab?.key;
          const startsStage = i === 0 || orderedTabs[i - 1].stage !== tab.stage;
          return (
            <div
              key={tab.key}
              style={{
                display: "flex",
                flexDirection: "column",
                borderLeft: startsStage && i > 0 ? "1px solid var(--border-divider)" : undefined,
                paddingLeft: startsStage && i > 0 ? 6 : 0,
              }}
            >
              <div
                style={{
                  fontSize: 11,
                  letterSpacing: ".04em",
                  textTransform: "uppercase",
                  color: "var(--text-muted)",
                  padding: "8px 14px 0",
                  visibility: startsStage ? "visible" : "hidden",
                  whiteSpace: "nowrap",
                }}
              >
                {stageLabel(tab.stage)}
              </div>
            <button
              onClick={() => go(tab.key)}
              title={missing.length ? `Missing: ${missing.join(", ")}` : undefined}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "6px 14px 12px",
                border: 0,
                background: "none",
                fontFamily: "inherit",
                fontSize: 14,
                whiteSpace: "nowrap",
                cursor: "pointer",
                color: on ? "var(--text-accent)" : "var(--text-secondary)",
                borderBottom: "2px solid " + (on ? "var(--action-primary)" : "transparent"),
              }}
            >
              <Ring pct={pct} warn={missing.length > 0} />
              {tab.label}
              {missing.length > 0 && <i className="dot" style={{ background: "var(--amber-600)" }} />}
            </button>
            </div>
          );
        })}
      </div>

      {/* --- body + right panel -------------------------------------- */}
      <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="card">
            {currentTab?.key === "review" ? (
              <ReviewPanel job={job} jobId={id} />
            ) : currentTab?.key === "evidence" ? (
              <EvidenceTab
                jobId={id}
                canEdit={Boolean(job.tabs.evidence?.can_edit)}
                readOnlyReason={job.tabs.evidence?.read_only_reason ?? ""}
              />
            ) : (
              currentTab &&
              job.tabs[currentTab.key] && (
                // Keyed so each tab gets its own autosave state, and leaving a
                // tab flushes whatever was typed last.
                <TabEditor
                  key={currentTab.key}
                  jobId={id}
                  tab={currentTab}
                  state={job.tabs[currentTab.key]}
                  allValues={allValues}
                />
              )
            )}

            {/* --- previous / next tab, across stages ----------------- */}
            <div
              className="row"
              style={{ justifyContent: "space-between", marginTop: 24, paddingTop: 16, borderTop: "1px solid var(--border-divider)" }}
            >
              {prevTab ? (
                <Button variant="outline" size="sm" icon={<Icon name="chevron-left" size={16} />} onClick={() => go(prevTab.key)}>
                  {prevTab.stage === currentTab?.stage || prevTab.label === stageLabel(prevTab.stage)
                    ? prevTab.label
                    : `${stageLabel(prevTab.stage)}: ${prevTab.label}`}
                </Button>
              ) : (
                <span />
              )}
              {nextTab && (
                <Button size="sm" onClick={() => go(nextTab.key)}>
                  {nextTab.stage === currentTab?.stage
                    ? `Next: ${nextTab.label}`
                    : nextTab.label === stageLabel(nextTab.stage)
                      ? `Next stage: ${nextTab.label}`
                      : `Next stage: ${stageLabel(nextTab.stage)} · ${nextTab.label}`}
                  <Icon name="chevron-right" size={16} />
                </Button>
              )}
            </div>
          </div>
        </div>
        <RightPanel jobId={id} />
      </div>
    </Shell>
  );
}
