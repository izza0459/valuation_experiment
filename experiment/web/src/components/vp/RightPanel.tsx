"use client";

/**
 * Workspace right panel (design brief S3): the latest AVM result and review
 * comments.
 *
 * Every field change is still recorded in the audit trail (DLD / RICS need
 * it, and the Django admin shows it); it just isn't listed here.
 */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Icon, Tabs } from "@/design-system";
import { apiFetch } from "@/lib/api";
import { useTransitions } from "@/lib/jobs";
import { aed, formatDateTime } from "./format";
import { Conf } from "./ui";

type AvmSummary = {
  suggested_value: string;
  low_value: string;
  high_value: string;
  aed_per_sqft: string;
  confidence: "high" | "medium" | "low";
  created_at: string;
};

export function RightPanel({ jobId }: { jobId: string }) {
  const [sub, setSub] = useState("AVM");

  return (
    <aside
      className="rightpanel"
      style={{
        width: 340,
        flexShrink: 0,
        display: "flex",
        flexDirection: "column",
        gap: 14,
        position: "sticky",
        top: 84, // below the sticky top bar
        alignSelf: "flex-start",
        maxHeight: "calc(100vh - 104px)",
      }}
    >
      <div className="card" style={{ padding: 0, overflow: "hidden", display: "flex", flexDirection: "column" }}>
        <Tabs size="sm" items={["AVM", "Comments"]} active={sub} onChange={setSub} style={{ gap: 22, padding: "0 18px" }} />
        <div style={{ padding: 18, overflowY: "auto" }}>
          {sub === "AVM" && <Avm jobId={jobId} />}
          {sub === "Comments" && <Comments jobId={jobId} />}
        </div>
      </div>
    </aside>
  );
}

function PendingFeature({ icon, title, body }: { icon: string; title: string; body: string }) {
  return (
    <div style={{ textAlign: "center", padding: "22px 6px" }}>
      <div style={{ width: 44, height: 44, borderRadius: 22, background: "var(--gray-150)", margin: "0 auto 12px", display: "grid", placeItems: "center" }}>
        <Icon name={icon} size={20} color="var(--text-muted)" />
      </div>
      <div style={{ fontSize: 15, marginBottom: 4 }}>{title}</div>
      <div style={{ fontSize: 13, color: "var(--text-muted)", lineHeight: 1.5 }}>{body}</div>
    </div>
  );
}

/** The latest AVM run, from the Evidence tab. */
function Avm({ jobId }: { jobId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["job-evidence", jobId],
    queryFn: () => apiFetch<{ avm: AvmSummary | null }>(`/api/jobs/${jobId}/evidence/`),
  });
  if (isLoading) return <div className="skel" style={{ height: 60 }} />;
  const run = data?.avm;
  if (!run) {
    return (
      <PendingFeature
        icon="scale"
        title="No AVM run yet"
        body="Add comparables on the Evidence tab, tick the ones to use, and run the AVM there."
      />
    );
  }
  const level = (run.confidence[0].toUpperCase() + run.confidence.slice(1)) as "High" | "Medium" | "Low";
  return (
    <div style={{ display: "grid", gap: 10 }}>
      <div>
        <div style={{ fontSize: 12, color: "var(--text-muted)" }}>SUGGESTED VALUE</div>
        <div style={{ fontSize: 22 }}>{aed(run.suggested_value)}</div>
      </div>
      <div style={{ fontSize: 14, color: "var(--text-secondary)" }}>
        {aed(run.low_value)} – {aed(run.high_value)}
      </div>
      <div className="row" style={{ justifyContent: "space-between", fontSize: 14 }}>
        <span>AED {Number(run.aed_per_sqft).toLocaleString("en-US", { maximumFractionDigits: 0 })} / sqft</span>
        <Conf l={level} />
      </div>
      <div style={{ fontSize: 12, color: "var(--text-muted)" }}>Run {formatDateTime(run.created_at)}</div>
    </div>
  );
}

/** Review comments: what a reviewer said when returning or reopening a job,
 * read from the lifecycle log. */
function Comments({ jobId }: { jobId: string }) {
  const { data, isLoading, isError } = useTransitions(jobId);

  if (isLoading) return <div className="skel" style={{ height: 60 }} />;
  if (isError) return <div style={{ fontSize: 14, color: "var(--text-error)" }}>Could not load comments.</div>;

  const withComments = (data ?? []).filter((e) => e.comments);
  if (withComments.length === 0) {
    return <PendingFeature icon="message-square" title="No comments" body="Reasons given when a job is returned or reopened appear here." />;
  }
  return (
    <div style={{ display: "grid", gap: 14 }}>
      {withComments.map((e) => (
        <div key={e.id} style={{ fontSize: 14, lineHeight: 1.45 }}>
          <div>
            <span style={{ fontWeight: 500 }}>{e.who}</span>{" "}
            <span style={{ color: "var(--text-secondary)" }}>· {e.label}</span>
          </div>
          <div style={{ marginTop: 2, whiteSpace: "pre-wrap" }}>{e.comments}</div>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>{formatDateTime(e.at)}</div>
        </div>
      ))}
    </div>
  );
}
