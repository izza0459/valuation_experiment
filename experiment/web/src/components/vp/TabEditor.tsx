"use client";

/**
 * Editable tab body (design brief S3), rendered from the shared field
 * config and saved through the per-tab PATCH endpoint with autosave.
 *
 * The config decides which fields exist and when they show; the server
 * decides what is valid, what is calculated, and whether this user may edit.
 * Nothing about a particular tab is hard-coded here.
 */

import { Fragment, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button, Icon } from "@/design-system";
import { isFieldVisible, type FieldDef, type TabDef } from "@/lib/fieldConfig";
import { ApiError, apiFetch } from "@/lib/api";
import type { Suggestion, TabState } from "@/lib/jobs";
import { useOptions } from "@/lib/options";
import { useTabAutosave, type SaveStatus } from "@/lib/useTabAutosave";
import { ChecklistUploads } from "./ChecklistUploads";
import { CoiCard } from "./CoiCard";
import { demoValuesForTab, uploadDemoFiles } from "./demoFill";
import { FieldInput, formatComputed } from "./FieldInput";
import { MapPreview } from "./MapPreview";
import { MediaTab } from "./MediaTab";
import { SuggestionItem } from "./Suggestions";
import { Banner, F } from "./ui";

type Props = {
  jobId: string;
  tab: TabDef;
  state: TabState;
  /** Every tab's saved values plus `bank`, for rules that cross tabs. */
  allValues: Record<string, unknown>;
  /** Fields entered elsewhere on the page, not autosaved here (the call
   * status, remark and booked date are logged with Save call). */
  omit?: string[];
  /** The peer reviewer's suggestions on this lead, shown under their fields. */
  suggestions?: Suggestion[];
  /** This user (the valuer) may accept or decline them. */
  canDecide?: boolean;
};

/** The "Fill demo data" button; set NEXT_PUBLIC_DEMO_FILL=false to hide it
 * once real valuations are entered. */
const DEMO_FILL = process.env.NEXT_PUBLIC_DEMO_FILL !== "false";

/** Fields that need the full width: long text and pick-lists. */
const WIDE = new Set(["textarea", "library", "multiselect", "storeys"]);
const COI_IN_CARD = new Set(["coi_suggestion", "coi_confirmed"]);

const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

export function TabEditor({ jobId, tab, state, allValues, omit, suggestions, canDecide }: Props) {
  const qc = useQueryClient();
  const { data: options, isError: optionsFailed } = useOptions();
  const save = useTabAutosave(jobId, tab.key, state);
  // The peer reviewer, during review: what they change is sent as a
  // suggestion, and the valuer's saved values stay as they are.
  const suggesting = Boolean(state.can_suggest);
  const suggest = useSuggest(jobId, tab.key);
  const open = (suggestions ?? []).filter((s) => s.tab === tab.key && s.status === "open");

  // Photos and documents have no form fields: they are files. Photos also
  // shows the location map from the coordinates.
  if (tab.key === "photos" || tab.key === "documents") {
    const address = (allValues.address ?? {}) as Record<string, unknown>;
    return (
      <>
        {tab.key === "photos" && <MapPreview latitude={address.latitude} longitude={address.longitude} />}
        <MediaTab jobId={jobId} kind={tab.key} />
      </>
    );
  }

  if (tab.fields.length === 0) {
    return (
      <p style={{ fontSize: 15, color: "var(--text-muted)", margin: 0 }}>
        Nothing to enter on this tab yet.
      </p>
    );
  }

  const suggested = Object.fromEntries(open.map((s) => [s.field, s.new]));
  const merged = suggesting ? { ...state.values, ...suggested, ...suggest.draft } : { ...state.values, ...save.draft };
  // Rules can reach across tabs, and a field just edited here can change
  // what is visible here before it has even been saved.
  const context = { ...allValues, [tab.key]: merged };
  // The COI suggestion and who confirmed it are shown in the COI card instead.
  const visible = tab.fields.filter(
    (f) => isFieldVisible(f, context) && !omit?.includes(f.key) && !COI_IN_CARD.has(f.key),
  );

  const paused = save.status === "conflict" || save.status === "blocked";
  // Uploads and demo data follow the real edit right; fields also open up
  // for the reviewer's suggestions.
  const editable = state.can_edit && !paused;
  const tabReadOnly = !(editable || suggesting);
  const label = (key: string) => tab.fields.find((f) => f.key === key)?.label ?? key;
  const empty = (v: unknown) => v === null || v === undefined || v === "" || (Array.isArray(v) && v.length === 0);
  // Required fields still to fill in, shown on the field and listed at the top.
  const missing = state.can_edit
    ? visible.filter((f) => f.required && !f.calculated && empty(merged[f.key]))
    : [];
  const jump = (key: string) => {
    const el = document.getElementById(`field-${tab.key}-${key}`);
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
    el?.querySelector<HTMLElement>("input, select, textarea, button")?.focus({ preventScroll: true });
  };
  // Fills only what is empty, editable and on screen; typed values stay.
  // Fills what is empty and editable, including fields an earlier answer
  // reveals. Sections with uploads get dummy files as well.
  const fillDemo = () => {
    const filled = demoValuesForTab(tab, merged, allValues, state.read_only_fields, options);
    for (const [key, value] of Object.entries(filled)) save.setField(key, value);
    const files = tab.key === "address" ? "title" : tab.key === "checklist" ? "slot_photos" : null;
    if (files) void uploadDemoFiles(jobId, files, qc);
  };
  const summary = (tab.key === "summary" ? merged : (allValues.summary as Record<string, unknown> | undefined)) ?? {};
  const propertyCategory = typeof summary.property_category === "string" ? summary.property_category : undefined;

  return (
    <div>
      <div className="row" style={{ justifyContent: "flex-end", gap: 12, marginBottom: 12, minHeight: 22 }}>
        {DEMO_FILL && editable && (
          <Button variant="outline" size="sm" onClick={fillDemo}>
            Fill demo data
          </Button>
        )}
        {state.can_edit && <SaveIndicator status={save.status} dirty={save.dirty} onRetry={save.retry} />}
        {suggesting && suggest.status && (
          <span style={{ fontSize: 13, color: suggest.status === "error" ? "var(--text-error)" : "var(--purple-600)" }}>
            {suggest.status === "saving" ? "Sending suggestion…" : suggest.status === "error" ? "Couldn't send" : "Suggestion sent"}
          </span>
        )}
      </div>

      {suggesting && (
        <Banner tone="purple" icon="sparkles">
          You&apos;re reviewing. Anything you change here is sent to the valuer as a suggestion; their saved value stays until they accept it.
        </Banner>
      )}

      {/* Another role's stage is shown read-only without an error; locked or
          frozen jobs still say why. */}
      {!state.can_edit && !suggesting && state.read_only_reason && state.read_only_code !== "forbidden" && (
        <Banner tone="blue" icon="lock">
          {state.read_only_reason}
        </Banner>
      )}

      {missing.length > 0 && (
        <div className="row wrap" style={{ gap: 6, marginBottom: 16, fontSize: 13 }}>
          <span style={{ color: "var(--text-error)", fontWeight: 700 }}>
            {missing.length} still required:
          </span>
          {missing.map((f) => (
            <button
              key={f.key}
              type="button"
              onClick={() => jump(f.key)}
              style={{
                border: "1px solid var(--red-200)",
                background: "var(--red-50)",
                color: "var(--text-error)",
                borderRadius: 999,
                padding: "3px 10px",
                fontFamily: "inherit",
                fontSize: 13,
                cursor: "pointer",
              }}
            >
              {f.label}
            </button>
          ))}
        </div>
      )}

      {save.status === "blocked" && save.notice && (
        <Banner tone="red" icon="alert-circle">
          {save.notice} Your latest changes were not saved.
        </Banner>
      )}

      {save.conflict && (
        <ConflictBanner
          mine={save.pending}
          theirs={save.conflict.values}
          baseline={state.values}
          label={label}
          onDiscard={save.discardMine}
          onReapply={save.reapplyMine}
        />
      )}

      {optionsFailed && (
        <Banner tone="amber" icon="alert-triangle">
          Couldn&apos;t load the dropdown options, so selects may appear empty. Reload to try again.
        </Banner>
      )}

      <div className="form-grid" style={{ display: "grid", gridTemplateColumns: "repeat(3,minmax(0,1fr))", gap: "14px 20px" }}>
        {visible.map((field) => {
          const readOnly = tabReadOnly || field.calculated || state.read_only_fields.includes(field.key);
          const isMissing = missing.includes(field);
          return (
            <Fragment key={field.key}>
            {field.key === "coi_check" && (
              <div style={{ gridColumn: "1 / -1", minWidth: 0 }}>
                <CoiCard jobId={jobId} />
              </div>
            )}
            <div id={`field-${tab.key}-${field.key}`} style={{ gridColumn: WIDE.has(field.type) ? "1 / -1" : undefined, minWidth: 0 }}>
            <F
              label={
                <>
                  {field.label}
                  {field.required && <span style={{ color: isMissing ? "var(--text-error)" : "var(--text-accent)" }}> *</span>}
                  {isMissing && <span className="field-missing">Required</span>}
                </>
              }
              badge={field.calculated ? "Calculated" : undefined}
              error={suggesting ? suggest.errors[field.key] : save.errors[field.key]}
              helper={field.help_text || undefined}
            >
              {field.calculated ? (
                <ComputedValue field={field} value={state.computed[field.key]} />
              ) : (
                <FieldInput
                  field={field}
                  value={merged[field.key]}
                  onChange={(v) => (suggesting ? suggest.setField(field.key, v) : save.setField(field.key, v))}
                  options={options?.[field.options_key ?? ""] ?? []}
                  users={options?.users ?? []}
                  readOnly={readOnly}
                  invalid={Boolean((suggesting ? suggest.errors : save.errors)[field.key])}
                  propertyCategory={propertyCategory}
                  siblings={merged}
                />
              )}
            </F>
            {!suggesting && open.filter((s) => s.field === field.key).map((s) => (
              <div key={s.id} style={{ marginTop: 8 }}>
                <SuggestionItem jobId={jobId} s={s} canDecide={Boolean(canDecide)} compact />
              </div>
            ))}
            {suggesting && field.key in suggested && !(field.key in suggest.draft) && (
              <div className="sugg-tag"><Icon name="sparkles" size={12} /> Suggested · saved value: {String(state.values[field.key] ?? "(empty)")}</div>
            )}
            </div>
            {/* The title document is uploaded right where its type is chosen,
                above the details read from it. */}
            {field.key === "title_doc_type" && (
              <div style={{ gridColumn: "1 / -1", minWidth: 0 }}>
                <ChecklistUploads jobId={jobId} mode="title" canEdit={editable} inline
                  lockedReason={state.read_only_reason} />
              </div>
            )}
            {/* A conflict of interest needs the client's consent, uploaded here. */}
            {field.key === "coi_check" && merged.coi_check === "yes" && (
              <div style={{ gridColumn: "1 / -1", minWidth: 0 }}>
                <ChecklistUploads jobId={jobId} mode="coi" canEdit={editable} inline
                  lockedReason={state.read_only_reason} />
              </div>
            )}
            </Fragment>
          );
        })}
      </div>

      {tab.key === "valuation" && <ValueInWords words={state.computed.market_value_in_words} />}


      {tab.key === "checklist" && (merged.makani_photo === true || merged.dewa_photo === true) && (
        <ChecklistUploads
          jobId={jobId}
          mode="photos"
          makani={merged.makani_photo === true}
          dewa={merged.dewa_photo === true}
          canEdit={editable}
          lockedReason={state.read_only_reason}
        />
      )}
    </div>
  );
}

/** The reviewer's edits, each sent as a suggestion shortly after typing
 * stops. A value set back to the saved one withdraws the suggestion. */
function useSuggest(jobId: string, tabKey: string) {
  const qc = useQueryClient();
  const [draft, setDraft] = useState<Record<string, unknown>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<"" | "saving" | "sent" | "error">("");
  const timers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  useEffect(() => () => Object.values(timers.current).forEach(clearTimeout), []);

  const send = async (field: string, value: unknown) => {
    setStatus("saving");
    try {
      await apiFetch(`/api/jobs/${jobId}/suggestions/`, {
        method: "POST",
        body: JSON.stringify({ tab: tabKey, field, value }),
      });
      setErrors((e) => Object.fromEntries(Object.entries(e).filter(([k]) => k !== field)));
      await qc.invalidateQueries({ queryKey: ["jobs", jobId] });
      setDraft((d) => (Object.is(d[field], value) ? Object.fromEntries(Object.entries(d).filter(([k]) => k !== field)) : d));
      setStatus("sent");
    } catch (err) {
      const body = err instanceof ApiError ? (err.body as { errors?: Record<string, string> } | null) : null;
      setErrors((e) => ({ ...e, [field]: body?.errors?.[field] ?? (err instanceof Error ? err.message : "Couldn't send") }));
      setStatus("error");
    }
  };
  const setField = (field: string, value: unknown) => {
    setDraft((d) => ({ ...d, [field]: value }));
    clearTimeout(timers.current[field]);
    timers.current[field] = setTimeout(() => void send(field, value), 900);
  };
  return { draft, errors, status, setField };
}

function ComputedValue({ field, value }: { field: FieldDef; value: unknown }) {
  // Scheduling: the contact's phone is tap-to-call, the map opens Google Maps.
  const link =
    typeof value === "string" && value
      ? field.key === "contact_number"
        ? `tel:${value.replace(/[^+0-9]/g, "")}`
        : field.key === "map_link"
          ? value
          : null
      : null;
  if (link) {
    return (
      <a
        href={link}
        target={field.key === "map_link" ? "_blank" : undefined}
        rel="noopener noreferrer"
        className="row"
        style={{ gap: 8, minHeight: 44, padding: "0 14px", borderRadius: 6, background: "var(--surface-subtle)",
          color: "var(--text-accent)", fontWeight: 700, textDecoration: "none" }}
      >
        <Icon name={field.key === "map_link" ? "map-pin" : "phone"} size={16} />
        {field.key === "map_link" ? "Open in Google Maps" : String(value)}
      </a>
    );
  }
  return (
    <div
      className="num"
      style={{
        fontSize: 15,
        minHeight: 44,
        display: "flex",
        alignItems: "center",
        padding: "0 14px",
        borderRadius: 6,
        background: "var(--surface-subtle)",
        color: "var(--text-secondary)",
      }}
    >
      {formatComputed(field.key, value)}
    </div>
  );
}

/** What is printed beside the figure on the signed report, straight from
 * the server so the screen and the PDF can never disagree. */
function ValueInWords({ words }: { words: unknown }) {
  if (typeof words !== "string" || !words) return null;
  return (
    <div style={{ marginTop: 18, padding: 14, borderRadius: 8, background: "var(--surface-subtle)" }}>
      <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 4 }}>MARKET VALUE IN WORDS · as printed on the report</div>
      <div style={{ fontSize: 16 }}>{words}</div>
    </div>
  );
}

function SaveIndicator({ status, dirty, onRetry }: { status: SaveStatus; dirty: boolean; onRetry: () => void }) {
  const base = { fontSize: 13, display: "inline-flex", alignItems: "center", gap: 6 } as const;
  if (status === "saving") return <span style={{ ...base, color: "var(--text-muted)" }}>Saving…</span>;
  if (status === "error") {
    return (
      <span style={{ ...base, color: "var(--text-error)" }}>
        <Icon name="alert-circle" size={14} /> Couldn&apos;t save
        <button
          type="button"
          onClick={onRetry}
          style={{ border: 0, background: "none", color: "var(--text-accent)", cursor: "pointer", fontFamily: "inherit", fontSize: 13, padding: 0 }}
        >
          Retry
        </button>
      </span>
    );
  }
  if (status === "conflict" || status === "blocked") {
    return <span style={{ ...base, color: "var(--text-error)" }}>Not saved</span>;
  }
  if (dirty) return <span style={{ ...base, color: "var(--text-muted)" }}>Unsaved changes</span>;
  if (status === "saved") {
    return (
      <span style={{ ...base, color: "var(--green-600)" }}>
        <Icon name="check" size={14} /> All changes saved
      </span>
    );
  }
  return null;
}

function ConflictBanner({
  mine,
  theirs,
  baseline,
  label,
  onDiscard,
  onReapply,
}: {
  mine: Record<string, unknown>;
  theirs: Record<string, unknown>;
  baseline: Record<string, unknown>;
  label: (key: string) => string;
  onDiscard: () => void;
  onReapply: () => void;
}) {
  const myKeys = Object.keys(mine).filter((k) => !same(mine[k], theirs[k]));
  // Fields the other person changed since this page loaded: re-applying my
  // edits to any of these would overwrite theirs.
  const overlap = myKeys.filter((k) => !same(theirs[k], baseline[k]));

  return (
    <Banner
      tone="red"
      icon="users"
      right={
        <div className="row" style={{ gap: 8 }}>
          <Button size="sm" variant="outline" onClick={onReapply}>
            Re-apply my changes
          </Button>
          <Button size="sm" onClick={onDiscard}>
            Use their version
          </Button>
        </div>
      }
    >
      <b style={{ fontWeight: 500 }}>Someone else saved this tab first.</b> Their version is the one on record and your
      changes were not applied.
      {myKeys.length > 0 && <> Your unsaved edits: {myKeys.map(label).join(", ")}.</>}
      {overlap.length > 0 && (
        <>
          {" "}
          <b style={{ fontWeight: 500 }}>You both changed: {overlap.map(label).join(", ")}</b> — re-applying would overwrite
          theirs.
        </>
      )}
    </Banner>
  );
}
