"use client";

/**
 * One form control per config field type (CLAUDE.md §8: config-driven
 * fields). The same component renders the read-only view, so a locked or
 * not-yours tab shows labels ("Mortgage Security") rather than the stored
 * keys ("mortgage_security") or record ids.
 */

import { useState } from "react";
import { Button, Icon, Input, Select, Textarea } from "@/design-system";
import type { FieldDef } from "@/lib/fieldConfig";
import type { Option, UserOption } from "@/lib/options";
import { aed, formatDate, formatDateTime } from "./format";
import { Chip } from "./ui";

type Props = {
  field: FieldDef;
  value: unknown;
  onChange: (value: unknown) => void;
  options: Option[];
  users: UserOption[];
  readOnly: boolean;
  invalid?: boolean;
};

type LibraryEntry = { title: string; body: string };

/** How many choices still read better as a segmented control than a menu. */
const SEGMENT_MAX = 4;

const str = (value: unknown) => (value === null || value === undefined ? "" : String(value));
const labelFor = (options: Option[], value: unknown) =>
  options.find((o) => String(o.value) === String(value))?.label ?? str(value);

/** `<input type=datetime-local>` wants local wall time, the API speaks ISO. */
function toLocalInput(iso: unknown): string {
  if (typeof iso !== "string" || !iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function FieldInput({ field, value, onChange, options, users, readOnly, invalid }: Props) {
  const choices = field.type === "user" ? users : options;

  if (readOnly) return <ReadOnlyValue field={field} value={value} choices={choices} />;

  switch (field.type) {
    case "text":
      return <Input value={str(value)} invalid={invalid} onChange={(e) => onChange(e.target.value)} />;

    case "textarea":
      return <Textarea rows={3} value={str(value)} invalid={invalid} onChange={(e) => onChange(e.target.value)} />;

    case "number":
    case "decimal":
      return (
        <Input
          className="num"
          inputMode={field.type === "number" ? "numeric" : "decimal"}
          value={str(value)}
          invalid={invalid}
          onChange={(e) => onChange(e.target.value)}
        />
      );

    case "boolean":
      return (
        <div className="seg">
          {([["Yes", true], ["No", false]] as const).map(([label, v]) => (
            <button key={label} type="button" className={value === v ? "on" : ""} onClick={() => onChange(v)}>
              {label}
            </button>
          ))}
        </div>
      );

    case "date":
      return <Input type="date" value={str(value)} invalid={invalid} onChange={(e) => onChange(e.target.value || null)} />;

    case "datetime":
      return (
        <Input
          type="datetime-local"
          value={toLocalInput(value)}
          invalid={invalid}
          onChange={(e) => onChange(e.target.value ? new Date(e.target.value).toISOString() : null)}
        />
      );

    case "select":
      if (field.free_text) {
        const listId = `suggest-${field.key}`;
        return (
          <>
            <Input list={listId} value={str(value)} invalid={invalid} onChange={(e) => onChange(e.target.value)} />
            <datalist id={listId}>
              {options.map((o) => (
                <option key={String(o.value)} value={o.label} />
              ))}
            </datalist>
          </>
        );
      }
      if (options.length > 0 && options.length <= SEGMENT_MAX) {
        return (
          <div className="seg">
            {options.map((o) => (
              <button
                key={String(o.value)}
                type="button"
                className={String(o.value) === str(value) ? "on" : ""}
                onClick={() => onChange(o.value)}
              >
                {o.label}
              </button>
            ))}
          </div>
        );
      }
      return <Dropdown value={value} choices={options} invalid={invalid} onChange={onChange} />;

    case "user":
      return <Dropdown value={value} choices={users} invalid={invalid} onChange={onChange} />;

    case "multiselect": {
      const selected = Array.isArray(value) ? (value as string[]) : [];
      return (
        <div className="row wrap" style={{ gap: 6 }}>
          {options.length === 0 && <span style={{ fontSize: 13, color: "var(--text-muted)" }}>No options set up yet.</span>}
          {options.map((o) => {
            const on = selected.includes(String(o.value));
            return (
              <Chip
                key={String(o.value)}
                on={on}
                onClick={() =>
                  onChange(on ? selected.filter((v) => v !== String(o.value)) : [...selected, String(o.value)])
                }
              >
                {o.label}
              </Chip>
            );
          })}
        </div>
      );
    }

    case "library":
      return <LibraryField value={value} options={options} invalid={invalid} onChange={onChange} />;

    default:
      return <ReadOnlyValue field={field} value={value} choices={choices} />;
  }
}

function Dropdown({
  value,
  choices,
  invalid,
  onChange,
}: {
  value: unknown;
  choices: Option[];
  invalid?: boolean;
  onChange: (v: unknown) => void;
}) {
  return (
    <Select
      value={str(value)}
      invalid={invalid}
      placeholder="Select…"
      options={choices.map((o) => ({ value: String(o.value), label: o.label }))}
      onChange={(e) => {
        // Record ids are numbers; the dropdown only deals in strings.
        const picked = choices.find((o) => String(o.value) === e.target.value);
        onChange(picked ? picked.value : "");
      }}
    />
  );
}

/* --- library text -------------------------------------------------------- */

/**
 * Report text the valuer picks from the library and then edits for this job.
 * Plain text on most tabs; a list of {title, body} entries where several are
 * picked (special assumptions, other matters). The server stores the job's
 * own copy, so editing here never touches the shared library.
 */
function LibraryField({
  value,
  options,
  invalid,
  onChange,
}: {
  value: unknown;
  options: Option[];
  invalid?: boolean;
  onChange: (v: unknown) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const asList = Array.isArray(value);
  const entries = asList ? (value as LibraryEntry[]) : [];
  const picked = new Set(entries.map((e) => e.title));

  const matches = options.filter(
    (o) =>
      (!asList || !picked.has(o.label)) &&
      (o.label + " " + (o.report_text ?? "")).toLowerCase().includes(query.toLowerCase()),
  );

  const insert = (o: Option) => {
    if (asList) onChange([...entries, { title: o.label, body: o.report_text ?? "" }]);
    // One answer per field (a property is an apartment or a villa, not both):
    // choosing replaces the text rather than adding to it.
    else onChange(o.report_text ?? "");
    setOpen(false);
    setQuery("");
  };

  return (
    <div style={{ display: "grid", gap: 10 }}>
      {asList ? (
        entries.map((entry, i) => (
          <div key={entry.title + i} style={{ border: "1px solid var(--border-subtle)", borderRadius: 8, padding: 12 }}>
            <div className="row" style={{ justifyContent: "space-between", marginBottom: 6 }}>
              <span style={{ fontSize: 15 }}>{entry.title}</span>
              <button
                type="button"
                aria-label={`Remove ${entry.title}`}
                onClick={() => onChange(entries.filter((_, j) => j !== i))}
                style={{ border: 0, background: "none", cursor: "pointer", display: "flex", padding: 4 }}
              >
                <Icon name="x" size={16} />
              </button>
            </div>
            <Textarea
              rows={3}
              value={entry.body}
              onChange={(e) => onChange(entries.map((x, j) => (j === i ? { ...x, body: e.target.value } : x)))}
            />
          </div>
        ))
      ) : (
        <Textarea rows={4} value={str(value)} invalid={invalid} onChange={(e) => onChange(e.target.value)} />
      )}

      <div>
        <Button
          size="sm"
          variant="soft"
          icon={<Icon name={open ? "chevron-up" : "book-open"} size={16} />}
          onClick={() => setOpen(!open)}
        >
          {asList ? "Add from library" : str(value) ? "Replace from library" : "Choose from library"}
        </Button>
      </div>

      {open && (
        <div style={{ display: "grid", gap: 10 }}>
          <Input placeholder="Search text library" value={query} onChange={(e) => setQuery(e.target.value)} />
          {matches.length === 0 && (
            <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
              {options.length === 0 ? "The text library has no entries for this field yet." : "No matches."}
            </div>
          )}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: 10 }}>
            {matches.map((o) => (
              <button
                key={String(o.value)}
                type="button"
                onClick={() => insert(o)}
                style={{
                  textAlign: "left",
                  fontFamily: "inherit",
                  padding: 12,
                  borderRadius: 8,
                  cursor: "pointer",
                  border: "1px solid var(--border-subtle)",
                  background: "var(--surface-card)",
                }}
              >
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <span style={{ fontSize: 15 }}>{o.label}</span>
                  <Icon name="plus" size={16} color="var(--gray-500)" />
                </div>
                <div
                  style={{
                    fontSize: 13,
                    color: "var(--text-muted)",
                    marginTop: 4,
                    display: "-webkit-box",
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: "vertical",
                    overflow: "hidden",
                  }}
                >
                  {o.report_text}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* --- read-only ------------------------------------------------------------ */

export function ReadOnlyValue({
  field,
  value,
  choices,
}: {
  field: FieldDef;
  value: unknown;
  choices: Option[];
}) {
  return <div style={{ fontSize: 15, minHeight: 24, whiteSpace: "pre-wrap" }}>{displayValue(field, value, choices)}</div>;
}

function displayValue(field: FieldDef, value: unknown, choices: Option[]): string {
  if (value === null || value === undefined || value === "") return "—";
  switch (field.type) {
    case "boolean":
      return value ? "Yes" : "No";
    case "date":
      return formatDate(value as string);
    case "datetime":
      return formatDateTime(value as string);
    case "decimal":
      return /\(AED/.test(field.label) ? aed(value as string) : str(value);
    case "select":
    case "user":
      return field.free_text ? str(value) : labelFor(choices, value);
    case "multiselect":
      return Array.isArray(value) && value.length ? value.map((v) => labelFor(choices, v)).join(", ") : "—";
    case "library":
      return Array.isArray(value)
        ? value.length
          ? (value as LibraryEntry[]).map((e) => e.title).join(", ")
          : "—"
        : str(value);
    default:
      return str(value);
  }
}

/** Server-derived values (sqft, DMS, rate/sqft ...) are shown, never edited. */
export function formatComputed(key: string, value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (key.endsWith("_sqft") && !key.includes("rate")) return `${Number(value).toLocaleString("en-US")} sqft`;
  if (key.endsWith("_sqm")) return `${Number(value).toLocaleString("en-US")} sqm`;
  if (key === "market_value_rate_per_sqft") {
    const rate = Number(value).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    return `AED ${rate} / sqft`;
  }
  if (key === "forced_sale_value") return aed(value as string);
  if (key === "exact_age") return `${value} years`;
  return str(value);
}
