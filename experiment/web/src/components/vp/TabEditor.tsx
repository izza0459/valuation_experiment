"use client";

/**
 * Editable tab body (design brief S3), rendered from the shared field
 * config and saved through the per-tab PATCH endpoint with autosave.
 *
 * The config decides which fields exist and when they show; the server
 * decides what is valid, what is calculated, and whether this user may edit.
 * Nothing about a particular tab is hard-coded here.
 */

import { Button, Icon } from "@/design-system";
import { isFieldVisible, type FieldDef, type TabDef } from "@/lib/fieldConfig";
import type { TabState } from "@/lib/jobs";
import { useOptions } from "@/lib/options";
import { useTabAutosave, type SaveStatus } from "@/lib/useTabAutosave";
import { ChecklistUploads } from "./ChecklistUploads";
import { FieldInput, formatComputed } from "./FieldInput";
import { MediaTab } from "./MediaTab";
import { Banner, F } from "./ui";

type Props = {
  jobId: string;
  tab: TabDef;
  state: TabState;
  /** Every tab's saved values plus `bank`, for rules that cross tabs. */
  allValues: Record<string, unknown>;
};

/** Fields that need the full width: long text and pick-lists. */
const WIDE = new Set(["textarea", "library", "multiselect"]);

const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

export function TabEditor({ jobId, tab, state, allValues }: Props) {
  const { data: options, isError: optionsFailed } = useOptions();
  const save = useTabAutosave(jobId, tab.key, state);

  // Photos and documents have no form fields: they are files.
  if (tab.key === "photos" || tab.key === "documents") {
    return <MediaTab jobId={jobId} kind={tab.key} />;
  }

  if (tab.fields.length === 0) {
    return (
      <p style={{ fontSize: 15, color: "var(--text-muted)", margin: 0 }}>
        Nothing to enter on this tab yet.
      </p>
    );
  }

  const merged = { ...state.values, ...save.draft };
  // Rules can reach across tabs, and a field just edited here can change
  // what is visible here before it has even been saved.
  const context = { ...allValues, [tab.key]: merged };
  const visible = tab.fields.filter((f) => isFieldVisible(f, context));

  const paused = save.status === "conflict" || save.status === "blocked";
  const tabReadOnly = !state.can_edit || paused;
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
  const summary = (tab.key === "summary" ? merged : (allValues.summary as Record<string, unknown> | undefined)) ?? {};
  const propertyCategory = typeof summary.property_category === "string" ? summary.property_category : undefined;

  return (
    <div>
      <div className="row" style={{ justifyContent: "flex-end", marginBottom: 12, minHeight: 22 }}>
        {state.can_edit && <SaveIndicator status={save.status} dirty={save.dirty} onRetry={save.retry} />}
      </div>

      {/* Another role's stage is shown read-only without an error; locked or
          frozen jobs still say why. */}
      {!state.can_edit && state.read_only_reason && state.read_only_code !== "forbidden" && (
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

      <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: "18px 24px" }}>
        {visible.map((field) => {
          const readOnly = tabReadOnly || field.calculated || state.read_only_fields.includes(field.key);
          const isMissing = missing.includes(field);
          return (
            <div key={field.key} id={`field-${tab.key}-${field.key}`} style={{ gridColumn: WIDE.has(field.type) ? "span 2" : undefined, minWidth: 0 }}>
            <F
              label={
                <>
                  {field.label}
                  {field.required && <span style={{ color: isMissing ? "var(--text-error)" : "var(--text-accent)" }}> *</span>}
                  {isMissing && <span className="field-missing">Required</span>}
                </>
              }
              badge={field.calculated ? "Calculated" : undefined}
              error={save.errors[field.key]}
              helper={field.help_text || undefined}
            >
              {field.calculated ? (
                <ComputedValue field={field} value={state.computed[field.key]} />
              ) : (
                <FieldInput
                  field={field}
                  value={merged[field.key]}
                  onChange={(v) => save.setField(field.key, v)}
                  options={options?.[field.options_key ?? ""] ?? []}
                  users={options?.users ?? []}
                  readOnly={readOnly}
                  invalid={Boolean(save.errors[field.key])}
                  propertyCategory={propertyCategory}
                />
              )}
            </F>
            </div>
          );
        })}
      </div>

      {tab.key === "valuation" && <ValueInWords words={state.computed.market_value_in_words} />}

      {/* The title document is uploaded where its details are asked for. */}
      {tab.key === "address" && <ChecklistUploads jobId={jobId} mode="title" canEdit={!tabReadOnly} />}

      {tab.key === "checklist" && (merged.makani_photo === true || merged.dewa_photo === true) && (
        <ChecklistUploads
          jobId={jobId}
          mode="photos"
          makani={merged.makani_photo === true}
          dewa={merged.dewa_photo === true}
          canEdit={!tabReadOnly}
        />
      )}
    </div>
  );
}

function ComputedValue({ field, value }: { field: FieldDef; value: unknown }) {
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
