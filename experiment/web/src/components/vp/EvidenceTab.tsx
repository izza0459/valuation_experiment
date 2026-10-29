"use client";

/**
 * The Evidence tab (CLAUDE.md §6): comparables entered by hand, ticked for the
 * report, and the AVM that runs on the ticked ones.
 *
 * Each comparable names its source and links to the listing or record it came
 * from. Comparables are added by hand only (pasted from a listing or typed in).
 */

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Icon, Input, Select, Textarea } from "@/design-system";
import { ApiError, apiFetch } from "@/lib/api";
import { aed, formatDate } from "./format";
import { Banner, Conf, Tip } from "./ui";

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
  /** sold, sold_primary, under_offer, mou_signed, asking, asking_good_interest, asking_no_interest */
  status: string;
  status_label?: string;
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

type Choice = { value: string; label: string };
type EvidenceState = { comparables: Comparable[]; avm: AvmRun | null; sources: Choice[]; statuses?: Choice[] };

/** Until the API sends its list (an older server): the two original statuses. */
const STATUSES: Choice[] = [
  { value: "sold", label: "Sold" },
  { value: "asking", label: "Asking" },
];
const statusLabel = (c: Comparable) => c.status_label ?? (c.status === "sold" ? "Sold" : "Asking");

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
  const [mode, setMode] = useState<null | "paste" | "manual">(null);
  const [prefill, setPrefill] = useState<{ values: Record<string, string>; found: string[] } | null>(null);
  const adding = mode === "manual";
  const close = () => {
    setMode(null);
    setPrefill(null);
  };
  const [error, setError] = useState<string | null>(null);
  // Once some are ticked, the unticked ones fold away under a link.
  const [showUnused, setShowUnused] = useState(false);

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
  const unused = data.comparables.filter((c) => !c.selected);
  const shown = ticked > 0 && !showUnused ? data.comparables.filter((c) => c.selected) : data.comparables;
  const toggle = (c: Comparable, selected: boolean) =>
    void act(`/api/jobs/${jobId}/evidence/${c.id}/`, { method: "PATCH", body: JSON.stringify({ selected }) });
  const remove = (c: Comparable) => void act(`/api/jobs/${jobId}/evidence/${c.id}/`, { method: "DELETE" });

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
        <div className="row wrap" style={{ justifyContent: "space-between", gap: 10, marginBottom: 10 }}>
          <div className="row" style={{ minWidth: 0, gap: 6 }}>
            <div style={{ fontSize: 16 }}>Comparables</div>
            <Tip text="Ticked ones go into the report's comparables table and the AVM." />
          </div>
          {canEdit && mode === null && (
            <div className="row wrap" style={{ gap: 8 }}>
              <Button size="sm" icon={<Icon name="clipboard" size={16} />} onClick={() => setMode("paste")}>
                Paste a listing
              </Button>
              <Button size="sm" variant="outline" icon={<Icon name="plus" size={16} />} onClick={() => setMode("manual")}>
                Add manually
              </Button>
            </div>
          )}
        </div>

        {mode === "paste" && (
          <PasteListing
            jobId={jobId}
            onRead={(values, found) => {
              setPrefill({ values, found });
              setMode("manual");
            }}
            onCancel={close}
          />
        )}

        {adding && (
          <AddForm
            key={prefill ? "prefilled" : "blank"}
            jobId={jobId}
            sources={data.sources}
            statuses={data.statuses ?? STATUSES}
            initial={prefill?.values}
            found={prefill?.found}
            onDone={() => {
              close();
              void refresh();
            }}
            onCancel={close}
          />
        )}

        {data.comparables.length === 0 && !adding ? (
          <div style={{ fontSize: 14, color: "var(--text-muted)", padding: "18px 0" }}>
            No comparables yet. Paste a listing from Bayut, Property Finder or Property Monitor, or add one by hand.
          </div>
        ) : (
          <>
            {/* Phones: one card per comparable. */}
            <div className="show-app stack8">
              {shown.map((c) => (
                <CompCard key={c.id} c={c} canEdit={canEdit} onToggle={toggle} onRemove={remove} />
              ))}
            </div>
            <div className="hide-app" style={{ overflowX: "auto" }}>
              <table className="grid" style={{ width: "100%", fontSize: 14, borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ textAlign: "left", color: "var(--text-muted)", fontSize: 13 }}>
                    <th style={{ padding: 8 }}>In report</th>
                    <th style={{ padding: 8 }}>Building / community</th>
                    <th style={{ padding: 8 }}>Type · floor · view</th>
                    <th style={{ padding: 8, textAlign: "right" }}>BUA (sqft)</th>
                    <th style={{ padding: 8, textAlign: "right" }}>Price (AED)</th>
                    <th style={{ padding: 8, textAlign: "right" }}>AED / sqft</th>
                    <th style={{ padding: 8 }}>Date · source</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {shown.map((c) => (
                    <tr key={c.id} style={{ borderTop: "1px solid var(--border-divider)", opacity: c.selected ? 1 : 0.55 }}>
                      <td style={{ padding: 8 }}>
                        <input
                          type="checkbox"
                          checked={c.selected}
                          disabled={!canEdit}
                          aria-label="Include in report"
                          onChange={(e) => toggle(c, e.target.checked)}
                        />
                      </td>
                      <td style={{ padding: 8 }} title={c.notes || undefined}>
                        {[c.building_name, c.community_name].filter(Boolean).join(", ") || "—"}
                        {c.notes && <Icon name="message-square" size={13} color="var(--text-muted)" />}
                      </td>
                      <td style={{ padding: 8 }}>{describe(c)}</td>
                      <td className="num" style={{ padding: 8, textAlign: "right" }}>{num(c.bua_sqft)}</td>
                      <td className="num" style={{ padding: 8, textAlign: "right" }}>{num(c.price_aed)}</td>
                      <td className="num" style={{ padding: 8, textAlign: "right" }}>{num(c.aed_per_sqft)}</td>
                      <td style={{ padding: 8 }}>
                        <div style={{ whiteSpace: "nowrap" }}>
                          {statusLabel(c)}
                          {c.transaction_date ? ` · ${formatDate(c.transaction_date)}` : ""}
                        </div>
                        <Source c={c} />
                      </td>
                      <td style={{ padding: 8 }}>{canEdit && <RemoveButton onClick={() => remove(c)} />}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {ticked > 0 && unused.length > 0 && (
              <button
                type="button"
                onClick={() => setShowUnused(!showUnused)}
                style={{ marginTop: 10, border: 0, background: "none", padding: 0, minHeight: 0, cursor: "pointer", color: "var(--text-accent)", fontFamily: "inherit", fontSize: 14 }}
              >
                {showUnused ? "Hide the ones not used" : `Show ${unused.length} not used in the report`}
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}

const describe = (c: Comparable) =>
  [[c.beds !== null ? `${c.beds} BR` : "", c.property_type].filter(Boolean).join(" "), c.floor, c.view]
    .filter(Boolean)
    .join(" · ") || "—";

function Source({ c }: { c: Comparable }) {
  return c.link ? (
    <a href={c.link} target="_blank" rel="noopener noreferrer" style={{ color: "var(--text-accent)", fontSize: 13 }}>
      {c.source_label} <Icon name="external-link" size={12} />
    </a>
  ) : (
    <span style={{ fontSize: 13, color: "var(--text-muted)" }}>{c.source_label}</span>
  );
}

function RemoveButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      aria-label="Remove comparable"
      onClick={onClick}
      style={{ border: 0, background: "none", cursor: "pointer", padding: 4, minHeight: 0, display: "flex" }}
    >
      <Icon name="trash-2" size={16} color="var(--text-muted)" />
    </button>
  );
}

/** A comparable on a phone: what it is, its price and rate, tick and remove. */
function CompCard({
  c,
  canEdit,
  onToggle,
  onRemove,
}: {
  c: Comparable;
  canEdit: boolean;
  onToggle: (c: Comparable, selected: boolean) => void;
  onRemove: (c: Comparable) => void;
}) {
  return (
    <div
      style={{
        display: "flex",
        gap: 10,
        alignItems: "flex-start",
        padding: "10px 12px",
        border: "1px solid var(--border-subtle)",
        borderRadius: 10,
        opacity: c.selected ? 1 : 0.6,
      }}
    >
      <input
        type="checkbox"
        checked={c.selected}
        disabled={!canEdit}
        aria-label="Include in report"
        onChange={(e) => onToggle(c, e.target.checked)}
        style={{ marginTop: 3, width: 18, height: 18 }}
      />
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ fontSize: 14, fontWeight: 700, overflowWrap: "anywhere" }}>
          {[c.building_name, c.community_name].filter(Boolean).join(", ") || "—"}
        </div>
        <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>{describe(c)}</div>
        <div className="num" style={{ fontSize: 14, marginTop: 2 }}>
          AED {num(c.price_aed)} · {num(c.bua_sqft)} sqft · <b>{num(c.aed_per_sqft)}</b>/sqft
        </div>
        <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
          {statusLabel(c)}
          {c.transaction_date ? ` ${formatDate(c.transaction_date)}` : ""} · <Source c={c} />
        </div>
      </div>
      {canEdit ? <RemoveButton onClick={() => onRemove(c)} /> : <span />}
    </div>
  );
}

const FOUND_LABELS: Record<string, string> = {
  price_aed: "price",
  bua_sqft: "size",
  beds: "bedrooms",
  property_type: "type",
  building_name: "building",
  community_name: "community",
};

/** Paste a listing copied from a portal (select all, copy) with its link; the
 * server reads what it can to prefill the form. Nothing is fetched from the
 * portal. */
function PasteListing({
  jobId,
  onRead,
  onCancel,
}: {
  jobId: string;
  onRead: (values: Record<string, string>, found: string[]) => void;
  onCancel: () => void;
}) {
  const [link, setLink] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function read() {
    setBusy(true);
    setError(null);
    try {
      const res = await apiFetch<Record<string, unknown>>(`/api/jobs/${jobId}/evidence/parse/`, {
        method: "POST",
        body: JSON.stringify({ text, link }),
      });
      const values: Record<string, string> = {};
      for (const [k, v] of Object.entries(res)) if (k !== "found" && v !== null && v !== undefined) values[k] = String(v);
      onRead(values, (res.found as string[]) ?? []);
    } catch (err) {
      setError(failure(err).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card" style={{ padding: 18, marginBottom: 14, display: "grid", gap: 12 }}>
      <div className="row" style={{ gap: 6 }}>
        <div style={{ fontSize: 16 }}>Paste a listing</div>
        <Tip text="Open the listing on Bayut, Property Finder or Property Monitor, select everything on the page (Ctrl+A), copy it (Ctrl+C) and paste it below with the page's link. The form fills in for you to check." />
      </div>
      <Input value={link} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setLink(e.target.value)} placeholder="https://www.bayut.com/property/details-…" />
      <Textarea rows={6} value={text} onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setText(e.target.value)} placeholder="Paste the listing's text here" />
      {error && <div style={{ fontSize: 13, color: "var(--text-error)" }}>{error}</div>}
      <div className="row" style={{ gap: 10, justifyContent: "flex-end" }}>
        <Button variant="outline" size="sm" onClick={onCancel}>
          Cancel
        </Button>
        <Button size="sm" disabled={busy || !text.trim()} onClick={() => void read()}>
          {busy ? "Reading…" : "Fill in the details"}
        </Button>
      </div>
    </div>
  );
}

function AddForm({
  jobId,
  sources,
  statuses,
  initial,
  found,
  onDone,
  onCancel,
}: {
  jobId: string;
  sources: Choice[];
  statuses: Choice[];
  initial?: Record<string, string>;
  found?: string[];
  onDone: () => void;
  onCancel: () => void;
}) {
  const [form, setForm] = useState<Record<string, string>>({ ...BLANK, ...(initial ?? {}) });
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
      {found && (
        <Banner tone={found.length >= 3 ? "green" : "amber"} icon={found.length >= 3 ? "check" : "alert-triangle"}>
          {found.length === 0
            ? "Couldn't read anything from that text. Fill the details in below."
            : `Read from the listing: ${found.map((k) => FOUND_LABELS[k] ?? k).join(", ")}. Check everything before adding.`}
        </Banner>
      )}
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
          "Status",
          <Select value={form.status} onChange={set("status")} options={statuses} />,
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
      <div className="row wrap" style={{ justifyContent: "space-between", gap: 10 }}>
        <div className="row" style={{ minWidth: 0, flex: "1 1 240px", gap: 6 }}>
          <div style={{ fontSize: 16 }}>Suggested value (AVM)</div>
          <Tip text={`Median AED/sqft of the ${ticked} ticked comparable${ticked === 1 ? "" : "s"} × the subject's BUA. You set and sign the final value.`} />
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
          <div className="row wrap" style={{ gap: "12px 28px", alignItems: "baseline" }}>
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
