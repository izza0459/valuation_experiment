"use client";

/**
 * The Evidence tab (CLAUDE.md §6): comparables entered by hand, ticked for the
 * report, and the AVM that runs on the ticked ones.
 *
 * Each comparable names its source and links to the listing or record it came
 * from. Connectors (DLD open data, Bayut, Property Monitor) will add rows to
 * the same list later, searched from what the job already holds.
 */

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Icon, Input, Select, Textarea } from "@/design-system";
import { ApiError, apiFetch } from "@/lib/api";
import { aed, formatDate } from "./format";
import { Banner, Conf } from "./ui";

type Comparable = {
  id: number;
  selected: boolean;
  source: string;
  source_label: string;
  link: string;
  building_name: string;
  community_name: string;
  property_type: string;
  beds: number | null;
  floor: string;
  view: string;
  bua_sqft: string | null;
  price_aed: string | null;
  aed_per_sqft: string | null;
  transaction_date: string | null;
  status: "sold" | "asking";
  notes: string;
};

type AvmRun = {
  id: number;
  suggested_value: string;
  low_value: string;
  high_value: string;
  aed_per_sqft: string;
  confidence: "high" | "medium" | "low";
  created_at: string;
  created_by: string;
  workings: {
    subject_bua_sqft: string;
    median_aed_per_sqft: string;
    range_aed_per_sqft: [string, string];
    range_basis: string;
    spread_pct: string;
    formula: string;
    comparables: { id: number; label: string; aed_per_sqft: string }[];
    market_value?: string;
    deviation_pct?: string;
    deviation_over_threshold?: boolean;
  };
};

type EvidenceState = { comparables: Comparable[]; avm: AvmRun | null; sources: { value: string; label: string }[] };

const BLANK = {
  source: "",
  link: "",
  building_name: "",
  community_name: "",
  property_type: "",
  beds: "",
  floor: "",
  view: "",
  bua_sqft: "",
  price_aed: "",
  transaction_date: "",
  status: "sold",
  notes: "",
};

const num = (v: string | null) => (v === null || v === "" ? "—" : Number(v).toLocaleString("en-US", { maximumFractionDigits: 0 }));

function failure(err: unknown): { message: string; errors: Record<string, string> } {
  if (err instanceof ApiError) return { message: err.message, errors: (err.body?.errors as Record<string, string>) ?? {} };
  return { message: "Couldn't reach the server. Try again.", errors: {} };
}

export function EvidenceTab({ jobId, canEdit, readOnlyReason }: { jobId: string; canEdit: boolean; readOnlyReason: string }) {
  const qc = useQueryClient();
  const key = ["job-evidence", jobId];
  const { data, isLoading, isError } = useQuery({
    queryKey: key,
    queryFn: () => apiFetch<EvidenceState>(`/api/jobs/${jobId}/evidence/`),
  });
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = () => qc.invalidateQueries({ queryKey: key });

  async function act(path: string, init: RequestInit) {
    setError(null);
    try {
      await apiFetch(path, init);
      await refresh();
    } catch (err) {
      setError(failure(err).message);
    }
  }

  if (isLoading) return <div className="skel" style={{ height: 200 }} />;
  if (isError || !data) return <div style={{ color: "var(--text-error)" }}>Could not load the evidence.</div>;

  const ticked = data.comparables.filter((c) => c.selected).length;

  return (
    <div style={{ display: "grid", gap: 18 }}>
      {!canEdit && readOnlyReason && (
        <Banner tone="blue" icon="lock">
          {readOnlyReason}
        </Banner>
      )}
      {error && (
        <Banner tone="red" icon="alert-circle">
          {error}
        </Banner>
      )}

      <AvmCard jobId={jobId} run={data.avm} ticked={ticked} canEdit={canEdit} onRun={refresh} />

      <div>
        <div className="row" style={{ justifyContent: "space-between", marginBottom: 10 }}>
          <div>
            <div style={{ fontSize: 16 }}>Comparables</div>
            <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
              Ticked ones go into the report&apos;s comparables table and the AVM.
            </div>
          </div>
          {canEdit && !adding && (
            <Button size="sm" icon={<Icon name="plus" size={16} />} onClick={() => setAdding(true)}>
              Add comparable
            </Button>
          )}
        </div>

        {adding && (
          <AddForm
            jobId={jobId}
            sources={data.sources}
            onDone={() => {
              setAdding(false);
              void refresh();
            }}
            onCancel={() => setAdding(false)}
          />
        )}

        {data.comparables.length === 0 && !adding ? (
          <div style={{ fontSize: 14, color: "var(--text-muted)", padding: "18px 0" }}>
            No comparables yet. Add sales or asking prices from DLD, Bayut, Property Finder, Property Monitor or an agent.
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="grid" style={{ width: "100%", fontSize: 14, borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ textAlign: "left", color: "var(--text-muted)", fontSize: 13 }}>
                  <th style={{ padding: 8 }}>In report</th>
                  <th style={{ padding: 8 }}>Building / community</th>
                  <th style={{ padding: 8 }}>Type</th>
                  <th style={{ padding: 8 }}>Floor · view</th>
                  <th style={{ padding: 8, textAlign: "right" }}>BUA (sqft)</th>
                  <th style={{ padding: 8, textAlign: "right" }}>Price (AED)</th>
                  <th style={{ padding: 8, textAlign: "right" }}>AED / sqft</th>
                  <th style={{ padding: 8 }}>Date</th>
                  <th style={{ padding: 8 }}>Source</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.comparables.map((c) => (
                  <tr key={c.id} style={{ borderTop: "1px solid var(--border-divider)", opacity: c.selected ? 1 : 0.55 }}>
                    <td style={{ padding: 8 }}>
                      <input
                        type="checkbox"
                        checked={c.selected}
                        disabled={!canEdit}
                        aria-label="Include in report"
                        onChange={(e) =>
                          void act(`/api/jobs/${jobId}/evidence/${c.id}/`, {
                            method: "PATCH",
                            body: JSON.stringify({ selected: e.target.checked }),
                          })
                        }
                      />
                    </td>
                    <td style={{ padding: 8 }} title={c.notes || undefined}>
                      {[c.building_name, c.community_name].filter(Boolean).join(", ") || "—"}
                      {c.notes && <Icon name="message-square" size={13} color="var(--text-muted)" />}
                    </td>
                    <td style={{ padding: 8 }}>{[c.beds !== null ? `${c.beds} BR` : "", c.property_type].filter(Boolean).join(" ") || "—"}</td>
                    <td style={{ padding: 8 }}>{[c.floor, c.view].filter(Boolean).join(" · ") || "—"}</td>
                    <td className="num" style={{ padding: 8, textAlign: "right" }}>{num(c.bua_sqft)}</td>
                    <td className="num" style={{ padding: 8, textAlign: "right" }}>{num(c.price_aed)}</td>
                    <td className="num" style={{ padding: 8, textAlign: "right" }}>{num(c.aed_per_sqft)}</td>
                    <td style={{ padding: 8, whiteSpace: "nowrap" }}>
                      {c.status === "sold" ? "Sold" : "Asking"}
                      {c.transaction_date ? ` · ${formatDate(c.transaction_date)}` : ""}
                    </td>
                    <td style={{ padding: 8, whiteSpace: "nowrap" }}>
                      {c.link ? (
                        <a href={c.link} target="_blank" rel="noopener noreferrer" style={{ color: "var(--text-accent)" }}>
                          {c.source_label} <Icon name="external-link" size={13} />
                        </a>
                      ) : (
                        c.source_label
                      )}
                    </td>
                    <td style={{ padding: 8 }}>
                      {canEdit && (
                        <button
                          type="button"
                          aria-label="Remove comparable"
                          onClick={() => void act(`/api/jobs/${jobId}/evidence/${c.id}/`, { method: "DELETE" })}
                          style={{ border: 0, background: "none", cursor: "pointer", padding: 4 }}
                        >
                          <Icon name="trash-2" size={16} color="var(--text-muted)" />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function AddForm({
  jobId,
  sources,
  onDone,
  onCancel,
}: {
  jobId: string;
  sources: { value: string; label: string }[];
  onDone: () => void;
  onCancel: () => void;
}) {
  const [form, setForm] = useState<Record<string, string>>(BLANK);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: string) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });

  const rate =
    Number(form.price_aed.replace(/,/g, "")) > 0 && Number(form.bua_sqft.replace(/,/g, "")) > 0
      ? Number(form.price_aed.replace(/,/g, "")) / Number(form.bua_sqft.replace(/,/g, ""))
      : null;

  async function save() {
    setBusy(true);
    setErrors({});
    setMessage(null);
    try {
      await apiFetch(`/api/jobs/${jobId}/evidence/`, {
        method: "POST",
        body: JSON.stringify({ ...form, beds: form.beds === "" ? null : form.beds }),
      });
      onDone();
    } catch (err) {
      const f = failure(err);
      setErrors(f.errors);
      setMessage(f.message);
    } finally {
      setBusy(false);
    }
  }

  const field = (key: string, label: string, input: React.ReactNode, span?: number) => (
    <div style={{ gridColumn: span ? `span ${span}` : undefined, minWidth: 0 }}>
      <div style={{ fontSize: 14, color: "var(--text-secondary)", marginBottom: 6 }}>{label}</div>
      {input}
      {errors[key] && <div style={{ color: "var(--text-error)", fontSize: 13, marginTop: 4 }}>{errors[key]}</div>}
    </div>
  );

  return (
    <div className="card" style={{ padding: 18, marginBottom: 14, display: "grid", gap: 14 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,minmax(0,1fr))", gap: 14 }}>
        {field("source", "Source *", <Select value={form.source} onChange={set("source")} placeholder="Choose…" options={sources} />)}
        {field("link", "Link", <Input value={form.link} onChange={set("link")} placeholder="https://www.bayut.com/…" />, 3)}
        {field("building_name", "Building / development", <Input value={form.building_name} onChange={set("building_name")} />, 2)}
        {field("community_name", "Community", <Input value={form.community_name} onChange={set("community_name")} />, 2)}
        {field("property_type", "Type", <Input value={form.property_type} onChange={set("property_type")} placeholder="Apartment" />)}
        {field("beds", "Bedrooms", <Input inputMode="numeric" value={form.beds} onChange={set("beds")} />)}
        {field("floor", "Floor", <Input value={form.floor} onChange={set("floor")} />)}
        {field("view", "View", <Input value={form.view} onChange={set("view")} />)}
        {field("bua_sqft", "BUA (sqft) *", <Input inputMode="decimal" value={form.bua_sqft} onChange={set("bua_sqft")} />)}
        {field("price_aed", "Price (AED) *", <Input inputMode="decimal" value={form.price_aed} onChange={set("price_aed")} />)}
        {field(
          "rate",
          "AED / sqft",
          <div className="num" style={{ height: 44, display: "flex", alignItems: "center", padding: "0 14px", borderRadius: 6, background: "var(--surface-subtle)" }}>
            {rate ? rate.toLocaleString("en-US", { maximumFractionDigits: 0 }) : "—"}
          </div>,
        )}
        {field(
          "status",
          "Sold or asking",
          <Select value={form.status} onChange={set("status")} options={[{ value: "sold", label: "Sold" }, { value: "asking", label: "Asking" }]} />,
        )}
        {field("transaction_date", "Date", <Input type="date" value={form.transaction_date} onChange={set("transaction_date")} />)}
        {field("notes", "Notes", <Textarea rows={2} value={form.notes} onChange={set("notes")} placeholder="Agent feedback, condition, anything that affects the value" />, 3)}
      </div>
      {message && Object.keys(errors).length === 0 && <div style={{ color: "var(--text-error)", fontSize: 13 }}>{message}</div>}
      <div className="row" style={{ gap: 10, justifyContent: "flex-end" }}>
        <Button variant="outline" size="sm" onClick={onCancel}>
          Cancel
        </Button>
        <Button size="sm" disabled={busy} onClick={() => void save()}>
          {busy ? "Adding…" : "Add comparable"}
        </Button>
      </div>
    </div>
  );
}

function AvmCard({
  jobId,
  run,
  ticked,
  canEdit,
  onRun,
}: {
  jobId: string;
  run: AvmRun | null;
  ticked: number;
  canEdit: boolean;
  onRun: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showWorkings, setShowWorkings] = useState(false);
  const confidence = run ? ((run.confidence[0].toUpperCase() + run.confidence.slice(1)) as "High" | "Medium" | "Low") : null;

  async function runAvm() {
    setBusy(true);
    setError(null);
    try {
      await apiFetch(`/api/jobs/${jobId}/avm/`, { method: "POST" });
      onRun();
    } catch (err) {
      const f = failure(err);
      setError(f.errors.avm ?? f.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card" style={{ padding: 18, display: "grid", gap: 12, background: "var(--surface-subtle)" }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <div style={{ fontSize: 16 }}>Suggested value (AVM)</div>
          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
            Median AED/sqft of the {ticked} ticked comparable{ticked === 1 ? "" : "s"} × the subject&apos;s BUA. You set and
            sign the final value.
          </div>
        </div>
        {canEdit && (
          <Button size="sm" variant={run ? "outline" : "primary"} disabled={busy || ticked === 0} onClick={() => void runAvm()}>
            {busy ? "Running…" : run ? "Run again" : "Run AVM"}
          </Button>
        )}
      </div>

      {error && <div style={{ fontSize: 13, color: "var(--text-error)" }}>{error}</div>}

      {run ? (
        <>
          <div className="row wrap" style={{ gap: 28, alignItems: "baseline" }}>
            <div>
              <div style={{ fontSize: 12, color: "var(--text-muted)" }}>SUGGESTED</div>
              <div style={{ fontSize: 24 }}>{aed(run.suggested_value)}</div>
            </div>
            <div>
              <div style={{ fontSize: 12, color: "var(--text-muted)" }}>RANGE</div>
              <div style={{ fontSize: 16 }}>
                {aed(run.low_value)} – {aed(run.high_value)}
              </div>
            </div>
            <div>
              <div style={{ fontSize: 12, color: "var(--text-muted)" }}>AED / SQFT</div>
              <div style={{ fontSize: 16 }}>{Number(run.aed_per_sqft).toLocaleString("en-US", { maximumFractionDigits: 0 })}</div>
            </div>
            <div>
              <div style={{ fontSize: 12, color: "var(--text-muted)" }}>CONFIDENCE</div>
              {confidence && <Conf l={confidence} />}
            </div>
          </div>

          {run.workings.deviation_pct && (
            <div style={{ fontSize: 14, color: run.workings.deviation_over_threshold ? "var(--text-error)" : "var(--text-secondary)" }}>
              Your market value ({aed(run.workings.market_value)}) is {run.workings.deviation_pct}% from the suggestion
              {run.workings.deviation_over_threshold ? ": more than the 10% the firm allows without a reason." : "."}
            </div>
          )}

          <div>
            <button
              type="button"
              onClick={() => setShowWorkings(!showWorkings)}
              style={{ border: 0, background: "none", padding: 0, cursor: "pointer", color: "var(--text-accent)", fontFamily: "inherit", fontSize: 14 }}
            >
              {showWorkings ? "Hide the workings" : "Show the workings"}
            </button>
            {showWorkings && (
              <div style={{ fontSize: 13, color: "var(--text-secondary)", marginTop: 8, display: "grid", gap: 4 }}>
                {run.workings.comparables.map((c) => (
                  <div key={c.id}>
                    {c.label}: AED {Number(c.aed_per_sqft).toLocaleString("en-US", { maximumFractionDigits: 0 })} / sqft
                  </div>
                ))}
                <div>
                  Median {Number(run.workings.median_aed_per_sqft).toLocaleString("en-US", { maximumFractionDigits: 0 })} ×{" "}
                  {Number(run.workings.subject_bua_sqft).toLocaleString("en-US")} sqft; range from the {run.workings.range_basis}{" "}
                  (spread {run.workings.spread_pct}%).
                </div>
                <div>{run.workings.formula}. No adjustments applied yet.</div>
                <div style={{ color: "var(--text-muted)" }}>
                  Run by {run.created_by || "—"} on {formatDate(run.created_at)}.
                </div>
              </div>
            )}
          </div>
        </>
      ) : (
        <div style={{ fontSize: 14, color: "var(--text-muted)" }}>Not run yet. Add and tick comparables, then run it.</div>
      )}
    </div>
  );
}
