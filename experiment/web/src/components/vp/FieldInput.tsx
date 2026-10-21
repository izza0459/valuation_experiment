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
import { DatePicker } from "./DatePicker";
import { formatDate, formatDateTime } from "./format";
import { Chip } from "./ui";

type Props = {
  field: FieldDef;
  value: unknown;
  onChange: (value: unknown) => void;
  options: Option[];
  users: UserOption[];
  readOnly: boolean;
  invalid?: boolean;
  /** The job's property category: library entries are offered for it only. */
  propertyCategory?: string;
};

/** Coordinates keep their decimals; every other figure is a whole number. */
const KEEPS_DECIMALS = new Set(["latitude", "longitude", "bua_sqm"]);
/** Years read as "2015", never "2,015". */
const NO_SEPARATORS = new Set(["built_about"]);

/** "1250000.00" -> "1,250,000". Text that isn't a number is shown as typed. */
export function formatWhole(value: unknown): string {
  const raw = str(value).replace(/,/g, "").trim();
  if (raw === "") return "";
  const n = Number(raw);
  return Number.isFinite(n) ? Math.round(n).toLocaleString("en-US") : str(value);
}

type LibraryEntry = { title: string; body: string };

/** How many choices still read better as a segmented control than a menu,
 * and how much text they can hold between them before the row would run out
 * of its half-width column (then it becomes a dropdown). */
const SEGMENT_MAX = 4;
const SEGMENT_MAX_CHARS = 50;

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

export function FieldInput({ field, value, onChange, options, users, readOnly, invalid, propertyCategory }: Props) {
  const choices = field.type === "user" ? users : options;

  if (readOnly) return <ReadOnlyValue field={field} value={value} choices={choices} />;

  switch (field.type) {
    case "text":
      return <Input value={str(value)} invalid={invalid} onChange={(e) => onChange(e.target.value)} />;

    case "textarea":
      return <Textarea rows={3} value={str(value)} invalid={invalid} onChange={(e) => onChange(e.target.value)} />;

    case "number":
    case "decimal":
      if (KEEPS_DECIMALS.has(field.key) || NO_SEPARATORS.has(field.key)) {
        return (
          <Input className="num" inputMode="decimal" value={str(value)} invalid={invalid}
            onChange={(e) => onChange(e.target.value)} />
        );
      }
      return <WholeNumberInput value={value} invalid={invalid} onChange={onChange} />;

    case "names":
      return <NamesInput value={value} invalid={invalid} onChange={onChange} />;

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
      return <DatePicker value={str(value)} invalid={invalid} onConfirm={(v) => onChange(v || null)} />;

    case "datetime":
      return (
        <DatePicker
          withTime
          value={toLocalInput(value)}
          invalid={invalid}
          onConfirm={(v) => onChange(v ? new Date(v).toISOString() : null)}
        />
      );

    case "select":
      if (field.free_text && !field.dropdown) {
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
      const labelChars = options.reduce((n, o) => n + o.label.length, 0);
      if (options.length > 0 && options.length <= SEGMENT_MAX && labelChars <= SEGMENT_MAX_CHARS) {
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
      const listed = new Set(options.map((o) => String(o.value)));
      // Entries typed in (Custom), shown as chips beside the list.
      const custom = field.custom ? selected.filter((v) => !listed.has(v)) : [];
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
          {custom.map((v) => (
            <Chip key={`custom-${v}`} on onClick={() => onChange(selected.filter((s) => s !== v))}>
              {v} ✕
            </Chip>
          ))}
          {field.custom && <CustomEntry onAdd={(text) => !selected.includes(text) && onChange([...selected, text])} />}
        </div>
      );
    }

    case "library": {
      // Entries tagged with property categories (commentary) are offered
      // only for those; untagged entries are offered for every property.
      const offered = options.filter(
        (o) => !o.categories?.length || (propertyCategory ? o.categories.includes(propertyCategory) : true),
      );
      return (
        <LibraryField value={value} options={offered} invalid={invalid} onChange={onChange} append={Boolean(field.append)}
          filtered={offered.length < options.length} />
      );
    }

    default:
      return <ReadOnlyValue field={field} value={value} choices={choices} />;
  }
}

/** "Custom": type something the list doesn't have; it prints as typed. */
function CustomEntry({ onAdd }: { onAdd: (text: string) => void }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const add = () => {
    const t = text.trim();
    if (t) onAdd(t.slice(0, 100));
    setText("");
    setOpen(false);
  };
  if (!open) {
    return (
      <Chip on={false} onClick={() => setOpen(true)}>
        + Custom
      </Chip>
    );
  }
  return (
    <span className="row" style={{ gap: 6, flex: "1 1 220px", minWidth: 0 }}>
      <Input
        autoFocus
        value={text}
        placeholder="Type it in"
        maxLength={100}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            add();
          }
          if (e.key === "Escape") setOpen(false);
        }}
        style={{ height: 36 }}
      />
      <Button size="sm" onClick={add}>
        Add
      </Button>
    </span>
  );
}

/** Figures are typed with or without thousands separators and shown with
 * them; the server rounds to whole numbers. The text stays as typed while
 * the field has focus, so the cursor never jumps. */
function WholeNumberInput({ value, invalid, onChange }: { value: unknown; invalid?: boolean; onChange: (v: unknown) => void }) {
  const [focused, setFocused] = useState(false);
  return (
    <Input
      className="num"
      inputMode="decimal"
      value={focused ? str(value) : formatWhole(value)}
      invalid={invalid}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      onChange={(e) => onChange(e.target.value.replace(/[^0-9.,-]/g, ""))}
    />
  );
}

/** Several names (owners, applicants): one line each, add or remove. */
function NamesInput({ value, invalid, onChange }: { value: unknown; invalid?: boolean; onChange: (v: unknown) => void }) {
  const names = Array.isArray(value) ? (value as string[]) : str(value) ? [str(value)] : [];
  const rows = names.length ? names : [""];
  const set = (next: string[]) => onChange(next);
  return (
    <div style={{ display: "grid", gap: 8 }}>
      {rows.map((name, i) => (
        <div key={i} className="row" style={{ gap: 8 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <Input
              value={name}
              invalid={invalid && i === 0}
              placeholder={i === 0 ? "Enter name" : "Enter another name"}
              onChange={(e) => set(rows.map((n, j) => (j === i ? e.target.value : n)))}
            />
          </div>
          {rows.length > 1 && (
            <button
              type="button"
              aria-label="Remove this name"
              onClick={() => set(rows.filter((_, j) => j !== i))}
              style={{ border: 0, background: "none", cursor: "pointer", display: "flex", padding: 4 }}
            >
              <Icon name="x" size={16} />
            </button>
          )}
        </div>
      ))}
      <div>
        <Button size="sm" variant="soft" icon={<Icon name="plus" size={16} />} onClick={() => set([...rows, ""])}>
          Add another
        </Button>
      </div>
    </div>
  );
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
  append = false,
  filtered = false,
}: {
  value: unknown;
  options: Option[];
  invalid?: boolean;
  onChange: (v: unknown) => void;
  append?: boolean;
  filtered?: boolean;
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
    // Several entries can apply (assumptions): each one is added to the text.
    else if (append) onChange([str(value).trim(), o.report_text ?? ""].filter(Boolean).join("\n\n"));
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
          {asList || append ? "Add from library" : str(value) ? "Replace from library" : "Choose from library"}
        </Button>
      </div>

      {open && (
        <div style={{ display: "grid", gap: 10 }}>
          <Input placeholder="Search text library" value={query} onChange={(e) => setQuery(e.target.value)} />
          {matches.length === 0 && (
            <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
              {options.length === 0
                ? filtered
                  ? "No entries for this property category. Set the category on the Preliminary Check first."
                  : "The text library has no entries for this field yet."
                : "No matches."}
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
      if (KEEPS_DECIMALS.has(field.key)) return str(value);
      return /\(AED/.test(field.label) ? `AED ${formatWhole(value)}` : formatWhole(value);
    case "number":
      return NO_SEPARATORS.has(field.key) ? str(value) : formatWhole(value);
    case "names":
      return Array.isArray(value) && value.length ? value.join(", ") : str(value) || "—";
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
  // No decimals anywhere: areas, rates and values are rounded.
  if (key.endsWith("_sqft") && !key.includes("rate")) return `${formatWhole(value)} sqft`;
  if (key.endsWith("_sqm")) return `${formatWhole(value)} sqm`;
  if (key === "market_value_rate_per_sqft") return `AED ${formatWhole(value)} / sqft`;
  if (key === "forced_sale_value") return `AED ${formatWhole(value)}`;
  if (key === "report_date") return formatDate(value as string);
  if (key === "remaining_economic_life") return `${str(value)} years`;
  return str(value);
}
