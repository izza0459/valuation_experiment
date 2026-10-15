"use client";

/**
 * Workspace right panel (design brief S3): AVM snapshot, comments and the
 * activity/audit log.
 *
 * Activity reads the audit trail and Comments reads the lifecycle log. The
 * AVM shows what it is waiting on rather than prototype sample data: it has
 * no endpoint yet (build order step 7).
 */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Icon, Tabs } from "@/design-system";
import { apiFetch } from "@/lib/api";
import { useTransitions } from "@/lib/jobs";
import { formatDateTime } from "./format";

type ActivityEntry = {
  id: number;
  who: string;
  model: string;
  field: string;
  old_value: string | null;
  new_value: string | null;
  at: string;
};

function useActivity(jobId: string) {
  return useQuery({
    queryKey: ["job-activity", jobId],
    queryFn: () => apiFetch<ActivityEntry[]>(`/api/jobs/${jobId}/activity/`),
    enabled: Boolean(jobId),
  });
}

export function RightPanel({ jobId }: { jobId: string }) {
  const [sub, setSub] = useState("Activity");

  return (
    <aside
      style={{
        width: 340,
        flexShrink: 0,
        display: "flex",
        flexDirection: "column",
        gap: 14,
        position: "sticky",
        top: 20,
        alignSelf: "flex-start",
        maxHeight: "calc(100vh - 40px)",
      }}
    >
      <div className="card" style={{ padding: 0, overflow: "hidden", display: "flex", flexDirection: "column" }}>
        <Tabs
          size="sm"
          items={["AVM", "Comments", "Activity"]}
          active={sub}
          onChange={setSub}
          style={{ gap: 22, padding: "0 18px" }}
        />
        <div style={{ padding: 18, overflowY: "auto" }}>
          {sub === "AVM" && <PendingFeature
            icon="scale"
            title="No AVM run yet"
            body="The automated valuation model runs off selected comparables. Evidence and AVM are build-order step 7."
          />}
          {sub === "Comments" && <Comments jobId={jobId} />}
          {sub === "Activity" && <Activity jobId={jobId} />}
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

function Activity({ jobId }: { jobId: string }) {
  const { data, isLoading, isError } = useActivity(jobId);

  if (isLoading) {
    return (
      <div>
        {[...Array(4)].map((_, i) => (
          <div key={i} className="skel" style={{ height: 34, marginBottom: 10 }} />
        ))}
      </div>
    );
  }
  if (isError) return <div style={{ fontSize: 14, color: "var(--text-error)" }}>Could not load activity.</div>;
  if (!data?.length) {
    return <PendingFeature icon="clock" title="Nothing yet" body="Field changes appear here as the job is worked on." />;
  }

  return (
    <div style={{ display: "grid", gap: 14 }}>
      {data.map((e) => (
        <div key={e.id} style={{ fontSize: 14, lineHeight: 1.45 }}>
          <div>
            <span style={{ fontWeight: 500 }}>{e.who}</span>{" "}
            <span style={{ color: "var(--text-secondary)" }}>
              set {humanise(e.field)}
              {e.new_value ? (
                <>
                  {" "}to <span className="num">{truncate(e.new_value)}</span>
                </>
              ) : null}
            </span>
          </div>
          <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{formatDateTime(e.at)}</div>
        </div>
      ))}
    </div>
  );
}

const humanise = (field: string) => field.replace(/_/g, " ");
const truncate = (value: string) => (value.length > 40 ? value.slice(0, 40) + "…" : value);
