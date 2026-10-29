"use client";

/**
 * Dashboard: how the leads are doing. An admin sees every lead, a manager
 * their own and their team's, anyone else their own (backend
 * apps/jobs/dashboard.overview). Every count opens its leads in Jobs.
 */

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Select } from "@/design-system";
import { LeadsMap, STAGE_COLOURS, type Pin } from "@/components/vp/LeadsMap";
import { PageHead, Shell, Tip } from "@/components/vp/ui";
import { formatDate } from "@/components/vp/format";
import { apiFetch } from "@/lib/api";

type Count = { key: string; label: string; count: number; ids: number[] };
type FunnelStage = {
  key: string;
  label: string;
  count: number;
  jobs: { id: number }[];
  drop?: { count: number; pct: number | null };
  lost: { count: number; ids: number[] };
};
type Overview = {
  scope: "all" | "team" | "mine";
  people: { id: number; name: string }[];
  from: string;
  to: string;
  tiles: {
    active: number;
    new: number;
    issued: number;
    lost: number;
    win_rate: number | null;
    avg_turnaround_hours: number | null;
  };
  by_stage: Count[];
  funnel: FunnelStage[];
  lost_reasons: Count[];
  by_community: Count[];
  by_bank: Count[];
  by_person: Count[];
  pins: Pin[];
  unmapped: number;
};

const RANGES = [
  { value: "today", label: "Today" },
  { value: "week", label: "This week" },
  { value: "month", label: "This month" },
  { value: "30d", label: "Last 30 days" },
];

const SCOPE_TIP = {
  all: "Every lead on the platform.",
  team: "Your leads and those of everyone who reports to you.",
  mine: "The leads you hold a role on.",
};

/** The Jobs list showing just these leads. */
const jobsLink = (label: string, ids: number[]) =>
  `/jobs?ids=${ids.join(",") || "0"}&label=${encodeURIComponent(label)}`;

export default function DashboardPage() {
  const [range, setRange] = useState("30d");
  const [person, setPerson] = useState("");
  const { data, isLoading, isError } = useQuery({
    queryKey: ["dashboard", range, person],
    queryFn: () =>
      apiFetch<Overview>(`/api/dashboard/?range=${range}${person ? `&person=${person}` : ""}`),
  });

  return (
    <Shell>
      <PageHead
        title="Dashboard"
        sub={data ? `${formatDate(data.from)} – ${formatDate(data.to)}` : undefined}
        tip={data ? SCOPE_TIP[data.scope] : undefined}
      >
        {data && data.people.length > 0 && (
          <Select
            value={person}
            style={{ width: 200 }}
            options={[{ value: "", label: data.scope === "all" ? "Everyone" : "My team" }, ...data.people.map((p) => ({ value: String(p.id), label: p.name }))]}
            onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setPerson(e.target.value)}
          />
        )}
        <Select
          value={range}
          style={{ width: 170 }}
          options={RANGES}
          onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setRange(e.target.value)}
        />
      </PageHead>

      {isLoading ? (
        <div className="skel" style={{ height: 400 }} />
      ) : isError || !data ? (
        <div className="card" style={{ color: "var(--text-error)" }}>Could not load the dashboard.</div>
      ) : (
        <div style={{ display: "grid", gap: 16 }}>
          <div className="dash-tiles">
            <Tile label="Active leads" value={data.tiles.active} tip="Leads not yet issued or lost, whatever the dates." tone="teal" />
            <Tile label="New" value={data.tiles.new} tip="Leads created in the period." tone="blue" />
            <Tile label="Issued" value={data.tiles.issued} tip="Reports issued in the period." tone="green" />
            <Tile label="Lost" value={data.tiles.lost} tip="Leads marked lost in the period." tone="red" />
            <Tile label="Win rate" value={data.tiles.win_rate === null ? "—" : `${data.tiles.win_rate}%`}
              tip="Of the leads closed in the period, the share issued rather than lost." />
            <Tile label="Turnaround" value={data.tiles.avg_turnaround_hours === null ? "—" : `${Math.round(data.tiles.avg_turnaround_hours)} h`}
              tip="Average time from the request arriving to the report being issued, for reports issued in the period." />
          </div>

          <div className="dash-cols">
            <Card title="Funnel and drop-off" tip="Leads that reached each stage in the period. Drop-off is the share of the previous stage's leads that didn't reach this one; lost counts leads marked lost at that stage.">
              <Funnel stages={data.funnel} />
            </Card>
            <Card title="Active leads by stage" tip="Where today's open leads are.">
              <Bars items={data.by_stage} colour={(c) => `var(--stage-${c.key})`} />
            </Card>
          </div>

          <Card
            title="Where the active leads are"
            tip="One dot per open lead with coordinates, coloured by stage. Click a dot to open it."
            right={data.unmapped ? <span style={{ fontSize: 13, color: "var(--text-muted)" }}>{data.unmapped} without coordinates</span> : null}
          >
            <LeadsMap pins={data.pins} />
            <div className="row wrap" style={{ gap: 14, marginTop: 10, fontSize: 13, color: "var(--text-secondary)" }}>
              {Object.entries(STAGE_COLOURS).map(([stage, colour]) => (
                <span key={stage} className="row" style={{ gap: 6 }}>
                  <i style={{ width: 10, height: 10, borderRadius: 5, background: colour, display: "inline-block" }} />
                  {stage}
                </span>
              ))}
            </div>
          </Card>

          <div className="dash-cols three">
            <Card title="By community" tip="Open leads per community.">
              <Bars items={data.by_community} limit={10} />
            </Card>
            <Card title="By bank" tip="Open leads per bank or client.">
              <Bars items={data.by_bank} limit={10} />
            </Card>
            <Card title="By person" tip="Open leads per valuer.">
              <Bars items={data.by_person} limit={10} />
            </Card>
          </div>

          <Card title="Why leads were lost" tip="Leads marked lost in the period, by reason.">
            {data.lost_reasons.length ? <Bars items={data.lost_reasons} colour={() => "var(--red-600)"} /> : <Empty />}
          </Card>
        </div>
      )}
    </Shell>
  );
}

const TONES = { teal: "var(--stage-valuation)", blue: "var(--stage-scheduling)", green: "var(--stage-send)", red: "var(--red-600)" };

function Tile({ label, value, tip, tone }: { label: string; value: number | string; tip: string; tone?: keyof typeof TONES }) {
  const colour = tone ? TONES[tone] : undefined;
  return (
    <div className="card dash-tile" style={{ borderTop: `3px solid ${colour ?? "var(--border-default)"}` }}>
      <div className="row eyebrow" style={{ gap: 6 }}>
        {label}
        <Tip text={tip} size={13} />
      </div>
      <div className="num" style={{ fontSize: 28, fontWeight: 900, marginTop: 4, color: colour }}>{value}</div>
    </div>
  );
}

function Card({ title, tip, right, children }: { title: string; tip: string; right?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="card" style={{ minWidth: 0 }}>
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 14, gap: 8 }}>
        <div className="row" style={{ gap: 6, fontSize: 16, fontWeight: 500 }}>
          {title}
          <Tip text={tip} />
        </div>
        {right}
      </div>
      {children}
    </section>
  );
}

function Empty() {
  return <div style={{ fontSize: 14, color: "var(--text-muted)" }}>None in this period.</div>;
}

function Bars({ items, limit, colour }: { items: Count[]; limit?: number; colour?: (c: Count) => string | undefined }) {
  if (!items.length) return <Empty />;
  const shown = limit ? items.slice(0, limit) : items;
  const max = Math.max(...shown.map((c) => c.count), 1);
  return (
    <div style={{ display: "grid", gap: 8 }}>
      {shown.map((c) => (
        <Link key={c.key} href={jobsLink(c.label, c.ids)} className="dash-bar">
          <span className="dash-bar-label">{c.label}</span>
          <span className="dash-bar-track">
            <span style={{ width: `${(c.count / max) * 100}%`, background: colour?.(c) ?? "var(--action-primary)" }} />
          </span>
          <b className="num">{c.count}</b>
        </Link>
      ))}
      {limit && items.length > limit && (
        <div style={{ fontSize: 12.5, color: "var(--text-muted)" }}>+ {items.length - limit} more</div>
      )}
    </div>
  );
}

function Funnel({ stages }: { stages: FunnelStage[] }) {
  const max = Math.max(...stages.map((s) => s.count), 1);
  return (
    <div style={{ display: "grid", gap: 10 }}>
      {stages.map((s) => (
        <div key={s.key}>
          <Link href={jobsLink(s.label, s.jobs.map((j) => j.id))} className="dash-bar">
            <span className="dash-bar-label">{s.label}</span>
            <span className="dash-bar-track">
              <span style={{ width: `${(s.count / max) * 100}%`, background: "var(--action-primary)" }} />
            </span>
            <b className="num">{s.count}</b>
          </Link>
          <div className="row" style={{ gap: 12, fontSize: 12.5, color: "var(--text-muted)", paddingLeft: 132 }}>
            {s.drop && s.drop.pct !== null && <span>{s.drop.pct}% drop-off</span>}
            {s.lost.count > 0 && (
              <Link href={jobsLink(`Lost at ${s.label}`, s.lost.ids)} style={{ color: "var(--red-600)" }}>
                {s.lost.count} lost
              </Link>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
