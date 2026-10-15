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

const PENDING: Record<string, string> = {
  evidence: "Comparables and the AVM arrive with build-order step 7.",
};

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
        {PENDING[tab.key] ?? "Nothing to enter on this tab yet."}
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

  return (
    <div>
      <div className="row" style={{ justifyContent: "flex-end", marginBottom: 12, minHeight: 22 }}>
        {state.can_edit && <SaveIndicator status={save.status} dirty={save.dirty} onRetry={save.retry} />}
      </div>

      {!state.can_edit && state.read_only_reason && (
        <Banner tone="blue" icon="lock">
          {state.read_only_reason}
        </Banner>
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
          return (
            <F
              key={field.key}
              span={WIDE.has(field.type) ? 2 : undefined}
              label={
                <>
                  {field.label}
                  {field.required && <span style={{ color: "var(--text-accent)" }}> *</span>}
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
                />
              )}
            </F>
          );
        })}
      </div>

      {tab.key === "valuation" && <ValueInWords words={state.computed.market_value_in_words} />}
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
