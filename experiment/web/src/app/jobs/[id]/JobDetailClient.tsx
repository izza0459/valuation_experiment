"use client";

/**
 * Job workspace — design brief S3.
 *
 * Ported from the prototype's `job-workspace-and-review.jsx`: job header,
 * status stepper, 9-tab rail with completion rings, and the right panel.
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
import { Avatar, Icon } from "@/design-system";
import { Banner, Ring, Shell, StatusChip } from "@/components/vp/ui";
import { RightPanel } from "@/components/vp/RightPanel";
import { TabEditor } from "@/components/vp/TabEditor";
import { TransitionBar } from "@/components/vp/TransitionBar";
import { useFieldConfig } from "@/lib/fieldConfig";
import { buildTabValues, useJob } from "@/lib/jobs";

/** The workflow's eight states collapsed onto the brief's seven steps. */
const STEPS = ["Received", "Setup", "Inspection", "Valuation", "Peer review", "Signed", "Issued"];
const STEP_FOR_STATUS: Record<string, number> = {
  instruction_received: 0,
  setup: 1,
  inspection_scheduled: 2,
  inspected: 2,
  valuation_in_progress: 3,
  peer_review: 4,
  approved_signed: 5,
  issued: 6,
};

type Assignee = { id: number; name: string; roles: string[] };

export function JobDetailClient({ id }: { id: string }) {
  const { data: job, isLoading: jobLoading, isError } = useJob(id);
  const { data: tabs, isLoading: tabsLoading } = useFieldConfig();
  const [activeTab, setActiveTab] = useState("checklist");

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
  const currentTab = orderedTabs.find((t) => t.key === activeTab) ?? orderedTabs[0];

  const property = (job.property ?? {}) as Record<string, string>;
  const assignees = (job.assignees ?? []) as Assignee[];
  const step = STEP_FOR_STATUS[job.status] ?? 0;
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

        {/* --- status stepper --------------------------------------- */}
        <div className="row" style={{ gap: 6, marginTop: 16 }}>
          {STEPS.map((label, i) => (
            <div key={label} style={{ flex: 1 }}>
              <div
                style={{
                  height: 4,
                  borderRadius: 2,
                  background: i < step ? "var(--red-200)" : i === step ? "var(--action-primary)" : "var(--gray-200)",
                }}
              />
              <div
                style={{
                  fontSize: 13,
                  marginTop: 6,
                  color: i === step ? "var(--text-accent)" : i < step ? "var(--text-secondary)" : "var(--text-muted)",
                }}
              >
                {label}
              </div>
            </div>
          ))}
        </div>

        <TransitionBar job={job} jobId={id} />
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
        {orderedTabs.map((tab) => {
          const { pct, missing } = job.tabs[tab.key]?.completion ?? { pct: 0, missing: [] };
          const on = tab.key === currentTab?.key;
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              title={missing.length ? `Missing: ${missing.join(", ")}` : undefined}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "14px 14px",
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
          );
        })}
      </div>

      {/* --- body + right panel -------------------------------------- */}
      <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="card">
            {currentTab && job.tabs[currentTab.key] && (
              // Keyed so each tab gets its own autosave state, and leaving a
              // tab flushes whatever was typed last.
              <TabEditor
                key={currentTab.key}
                jobId={id}
                tab={currentTab}
                state={job.tabs[currentTab.key]}
                allValues={allValues}
              />
            )}
          </div>
        </div>
        <RightPanel jobId={id} />
      </div>
    </Shell>
  );
}
