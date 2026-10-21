"use client";

/**
 * Admin pipeline dashboard on the Home screen (CRM feedback DB-01..03): one
 * count per stage with the drop-off between stages, and a date filter that
 * recounts everything. Clicking a stage filters the jobs table below to its
 * jobs and shows a card per section of that stage with its count; clicking a
 * section narrows the table to those jobs. Counting rules: backend
 * apps/jobs/dashboard.py.
 */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Input } from "@/design-system";
import { apiFetch } from "@/lib/api";

type JobRef = { id: number; ref: string; property: string; status: string };
type Stage = { key: string; label: string; count: number; jobs: JobRef[]; drop?: { count: number; pct: number | null } };
type Funnel = { from: string; to: string; stages: Stage[] };
type Section = { label: string; count: number; jobs: JobRef[] };

/** What the jobs table is filtered to: the jobs behind a card. */
export type CardFilter = { label: string; ids: number[] } | null;

const PRESETS = [
  { key: "today", label: "Today" },
  { key: "week", label: "This week" },
  { key: "month", label: "This month" },
  { key: "30d", label: "Last 30 days" },
  { key: "custom", label: "Custom" },
] as const;

type Range = { preset: string; from: string; to: string };

const query = (r: Range) =>
  r.preset === "custom" ? new URLSearchParams({ from: r.from, to: r.to }) : new URLSearchParams({ range: r.preset });

function dropText(drop: Stage["drop"]): string {
  if (!drop) return " ";
  if (drop.count > 0) return `−${drop.count}${drop.pct !== null ? ` (${drop.pct}%)` : ""}`;
  if (drop.count < 0) return `+${-drop.count}`;
  return "No drop";
}

export function PipelineFunnel({ selected, onFilter }: { selected: CardFilter; onFilter: (f: CardFilter) => void }) {
  const today = new Date().toISOString().slice(0, 10);
  const [range, setRange] = useState<Range>({ preset: "30d", from: today, to: today });
  const [open, setOpen] = useState<string | null>(null);

  const funnel = useQuery({
    queryKey: ["funnel", query(range).toString()],
    queryFn: () => apiFetch<Funnel>(`/api/jobs/funnel/?${query(range)}`),
  });
  const stage = funnel.data?.stages.find((s) => s.key === open) ?? null;
  const sections = useQuery({
    queryKey: ["funnel-sections", open, query(range).toString()],
    queryFn: () => apiFetch<{ sections: Section[] }>(`/api/jobs/funnel/?stage=${open}&${query(range)}`),
    enabled: Boolean(open && open !== "sent"),
  });

  const pickStage = (s: Stage) => {
    if (open === s.key) {
      setOpen(null);
      onFilter(null);
    } else {
      setOpen(s.key);
      onFilter({ label: `Reached ${s.label}`, ids: s.jobs.map((j) => j.id) });
    }
  };
  const pickSection = (sec: Section) => {
    const label = `${stage?.label ?? ""} · ${sec.label}`;
    if (selected?.label === label) onFilter(stage ? { label: `Reached ${stage.label}`, ids: stage.jobs.map((j) => j.id) } : null);
    else onFilter({ label, ids: sec.jobs.map((j) => j.id) });
  };

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="row wrap" style={{ justifyContent: "space-between", gap: 10, marginBottom: 14 }}>
        <div>
          <div style={{ fontSize: 16, fontWeight: 700 }}>Pipeline</div>
          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
            Jobs that reached each stage in the period. Click a stage to filter the jobs below.
          </div>
        </div>
        <div className="row wrap" style={{ gap: 8 }}>
          <div className="seg">
            {PRESETS.map((p) => (
              <button key={p.key} type="button" className={range.preset === p.key ? "on" : ""}
                onClick={() => {
                  setRange({ ...range, preset: p.key });
                  setOpen(null);
                  onFilter(null);
                }}>
                {p.label}
              </button>
            ))}
          </div>
          {range.preset === "custom" && (
            <span className="row" style={{ gap: 6 }}>
              <Input type="date" value={range.from} onChange={(e) => setRange({ ...range, from: e.target.value })} style={{ width: 160 }} aria-label="From" />
              <span style={{ color: "var(--text-muted)" }}>to</span>
              <Input type="date" value={range.to} onChange={(e) => setRange({ ...range, to: e.target.value })} style={{ width: 160 }} aria-label="To" />
            </span>
          )}
        </div>
      </div>

      {funnel.isError ? (
        <div style={{ color: "var(--text-error)", fontSize: 14 }}>Couldn&apos;t load the pipeline.</div>
      ) : (
        <div className="funnel-grid">
          {(funnel.data?.stages ?? []).map((s) => (
            <button
              key={s.key}
              type="button"
              onClick={() => pickStage(s)}
              title={s.drop ? "Change from the previous stage" : undefined}
              aria-pressed={open === s.key}
              style={{
                textAlign: "left", padding: "12px 14px", borderRadius: 10, cursor: "pointer", fontFamily: "inherit",
                border: `1px solid ${open === s.key ? "var(--action-primary)" : "var(--border-subtle)"}`,
                background: open === s.key ? "var(--surface-accent)" : "var(--surface-card)",
              }}
            >
              <div style={{ fontSize: 13, color: "var(--text-muted)" }}>{s.label}</div>
              <div className="num" style={{ fontSize: 26, fontWeight: 700 }}>{s.count}</div>
              <div style={{ fontSize: 12, color: s.drop && s.drop.count > 0 ? "var(--text-error)" : "var(--text-muted)", minHeight: 16 }}>
                {dropText(s.drop)}
              </div>
            </button>
          ))}
          {funnel.isLoading && [...Array(6)].map((_, i) => <div key={i} className="skel" style={{ height: 88 }} />)}
        </div>
      )}

      {/* The open stage, section by section: jobs still in it, by where they are. */}
      {stage && stage.key !== "sent" && (
        <div style={{ marginTop: 14, paddingTop: 14, borderTop: "1px solid var(--border-divider)" }}>
          <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 8 }}>
            {stage.label}: jobs still in this stage, by section
          </div>
          <div className="section-grid">
            {(sections.data?.sections ?? []).map((sec) => {
              const on = selected?.label === `${stage.label} · ${sec.label}`;
              return (
                <button
                  key={sec.label}
                  type="button"
                  onClick={() => pickSection(sec)}
                  aria-pressed={on}
                  style={{
                    textAlign: "left", padding: "10px 12px", borderRadius: 10, cursor: "pointer", fontFamily: "inherit",
                    border: `1px solid ${on ? "var(--action-primary)" : "var(--border-subtle)"}`,
                    background: on ? "var(--surface-accent)" : "var(--surface-card)",
                  }}
                >
                  <div style={{ fontSize: 13, color: "var(--text-muted)" }}>{sec.label}</div>
                  <div className="num" style={{ fontSize: 22, fontWeight: 700 }}>{sec.count}</div>
                </button>
              );
            })}
            {sections.isLoading && [...Array(4)].map((_, i) => <div key={i} className="skel" style={{ height: 66 }} />)}
          </div>
        </div>
      )}
    </div>
  );
}
