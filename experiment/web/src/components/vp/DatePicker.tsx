"use client";

/**
 * Date and date-and-time picker with OK / Cancel / Clear inside the calendar.
 * Nothing is applied until OK, so browsing months never saves a half-chosen
 * value. (The browser's own picker can't hold buttons, hence our own.)
 *
 * Values: dates as "YYYY-MM-DD"; date-times as local "YYYY-MM-DDTHH:MM"
 * (the caller converts to and from ISO).
 */

import { useEffect, useRef, useState } from "react";
import { Button, Icon } from "@/design-system";

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
  "November", "December"];
const DAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];

const pad = (n: number) => String(n).padStart(2, "0");
const iso = (y: number, m: number, d: number) => `${y}-${pad(m + 1)}-${pad(d)}`;

function parse(value: string): { date: string; time: string } {
  const [date = "", time = ""] = value.split("T");
  return { date, time: time.slice(0, 5) };
}

/** A date typed in: 07/10/2015, 7/10/2015, 2015-10-07, 7 Oct 2015 or
 * 7 October 2015 (day first, as in the UAE). "YYYY-MM-DD", or null. */
export function parseTyped(text: string): string | null {
  const t = text.trim();
  let y: number, m: number, d: number;
  let match = t.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
  if (match) {
    [y, m, d] = [Number(match[1]), Number(match[2]), Number(match[3])];
  } else if ((match = t.match(/^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})$/))) {
    [d, m, y] = [Number(match[1]), Number(match[2]), Number(match[3])];
  } else if ((match = t.match(/^(\d{1,2})\s+([A-Za-z]{3,})\s+(\d{4})$/))) {
    const idx = MONTHS.findIndex((name) => name.toLowerCase().startsWith(match![2].toLowerCase().slice(0, 3)));
    if (idx < 0) return null;
    [d, m, y] = [Number(match[1]), idx + 1, Number(match[3])];
  } else {
    return null;
  }
  const date = new Date(y, m - 1, d);
  if (date.getFullYear() !== y || date.getMonth() !== m - 1 || date.getDate() !== d) return null;
  return iso(y, m - 1, d);
}

/** Years offered in the header: 1950 to five years ahead (and the one in view). */
function yearsAround(viewYear: number): number[] {
  const last = new Date().getFullYear() + 5;
  const first = Math.min(1950, viewYear);
  const years: number[] = [];
  for (let y = Math.max(last, viewYear); y >= first; y--) years.push(y);
  return years;
}

function label(value: string, withTime: boolean): string {
  const { date, time } = parse(value);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return "";
  const [y, m, d] = date.split("-").map(Number);
  const text = `${d} ${MONTHS[m - 1].slice(0, 3)} ${y}`;
  return withTime && time ? `${text}, ${time}` : text;
}

export function DatePicker({
  value,
  withTime = false,
  invalid,
  onConfirm,
}: {
  value: string;
  withTime?: boolean;
  invalid?: boolean;
  onConfirm: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  // What is being chosen in the open calendar (applied on OK).
  const today = new Date();
  const initial = parse(value);
  const [picked, setPicked] = useState(initial.date);
  const [time, setTime] = useState(initial.time || "09:00");
  const start = initial.date ? new Date(`${initial.date}T00:00`) : today;
  const [view, setView] = useState({ y: start.getFullYear(), m: start.getMonth() });
  const [typed, setTyped] = useState("");
  const [typedBad, setTypedBad] = useState(false);

  function show() {
    const p = parse(value);
    const s = p.date ? new Date(`${p.date}T00:00`) : new Date();
    setPicked(p.date);
    setTime(p.time || "09:00");
    setView({ y: s.getFullYear(), m: s.getMonth() });
    setTyped("");
    setTypedBad(false);
    setOpen(true);
  }

  /** Jump the calendar to a picked day (typed, or Today). */
  function pick(day: string) {
    const [y, m] = day.split("-").map(Number);
    setPicked(day);
    setView({ y, m: m - 1 });
  }

  function applyTyped() {
    if (!typed.trim()) return;
    const day = parseTyped(typed);
    setTypedBad(!day);
    if (day) pick(day);
  }

  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  const first = new Date(view.y, view.m, 1);
  const lead = (first.getDay() + 6) % 7; // Monday first
  const days = new Date(view.y, view.m + 1, 0).getDate();
  const cells = [...Array(lead).fill(null), ...Array.from({ length: days }, (_, i) => i + 1)];
  const todayIso = iso(today.getFullYear(), today.getMonth(), today.getDate());
  const move = (by: number) => setView((v) => {
    const d = new Date(v.y, v.m + by, 1);
    return { y: d.getFullYear(), m: d.getMonth() };
  });

  const ok = () => {
    onConfirm(picked ? (withTime ? `${picked}T${time || "00:00"}` : picked) : "");
    setOpen(false);
  };

  const shown = label(value, withTime);

  return (
    <div ref={box} style={{ position: "relative" }}>
      <button
        type="button"
        onClick={() => (open ? setOpen(false) : show())}
        aria-haspopup="dialog"
        aria-expanded={open}
        style={{
          width: "100%",
          height: "var(--control-height-input)",
          boxSizing: "border-box",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
          padding: "0 14px",
          border: `1px solid ${invalid || open ? "var(--border-focus)" : "var(--border-default)"}`,
          borderRadius: "var(--radius-sm)",
          background: "var(--surface-card)",
          fontFamily: "inherit",
          fontSize: "var(--font-size-lg)",
          color: shown ? "var(--text-value)" : "var(--text-placeholder)",
          cursor: "pointer",
          textAlign: "left",
        }}
      >
        <span>{shown || (withTime ? "Select date and time" : "Select date")}</span>
        <Icon name="calendar" size={18} color="var(--text-muted)" />
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Choose a date"
          className="cal"
          style={{
            position: "absolute",
            top: "calc(100% + 6px)",
            left: 0,
            zIndex: 30,
            // The field's width on a phone, a comfortable size elsewhere.
            width: "100%",
            minWidth: 272,
            maxWidth: 320,
            boxSizing: "border-box",
            background: "var(--surface-card)",
            border: "1px solid var(--border-subtle)",
            borderRadius: 10,
            boxShadow: "0 8px 28px rgba(0,0,0,.14)",
            padding: 12,
          }}
        >
          {/* Type it, or pick the month and year straight from the lists. */}
          <input
            className="cal-typed"
            value={typed}
            placeholder="Type a date, e.g. 07/10/2015"
            aria-label="Type a date"
            onChange={(e) => {
              setTyped(e.target.value);
              setTypedBad(false);
            }}
            onBlur={applyTyped}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                applyTyped();
              }
            }}
            style={{ borderColor: typedBad ? "var(--text-error)" : undefined }}
          />
          {typedBad && <div style={{ fontSize: 12, color: "var(--text-error)", margin: "-4px 0 6px" }}>Not a date: try 07/10/2015.</div>}
          <div className="row" style={{ justifyContent: "space-between", gap: 4, marginBottom: 8 }}>
            <button type="button" aria-label="Previous month" onClick={() => move(-1)} style={navBtn}>
              <Icon name="chevron-left" size={16} />
            </button>
            <span className="row" style={{ gap: 4 }}>
              <select className="cal-select" aria-label="Month" value={view.m}
                onChange={(e) => setView((v) => ({ ...v, m: Number(e.target.value) }))}>
                {MONTHS.map((name, i) => (
                  <option key={name} value={i}>{name}</option>
                ))}
              </select>
              <select className="cal-select" aria-label="Year" value={view.y}
                onChange={(e) => setView((v) => ({ ...v, y: Number(e.target.value) }))}>
                {yearsAround(view.y).map((y) => (
                  <option key={y} value={y}>{y}</option>
                ))}
              </select>
            </span>
            <button type="button" aria-label="Next month" onClick={() => move(1)} style={navBtn}>
              <Icon name="chevron-right" size={16} />
            </button>
          </div>
          {/* Columns set by class: phone CSS flattens inline grids to one column. */}
          <div className="cal-grid">
            {DAYS.map((d) => (
              <span key={d} style={{ fontSize: 11, color: "var(--text-muted)", padding: "4px 0" }}>{d}</span>
            ))}
            {cells.map((d, i) => {
              if (d === null) return <span key={`e${i}`} />;
              const day = iso(view.y, view.m, d);
              const on = day === picked;
              return (
                <button
                  key={day}
                  type="button"
                  className="cal-day"
                  onClick={() => setPicked(day)}
                  style={{
                    border: day === todayIso && !on ? "1px solid var(--border-active)" : "1px solid transparent",
                    borderRadius: 6,
                    background: on ? "var(--action-primary)" : "transparent",
                    color: on ? "#fff" : "var(--text-primary)",
                    fontFamily: "inherit",
                    fontSize: 13,
                    fontWeight: on ? 700 : 400,
                    cursor: "pointer",
                  }}
                >
                  {d}
                </button>
              );
            })}
          </div>
          {withTime && (
            <div className="row" style={{ gap: 8, marginTop: 10 }}>
              <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>Time</span>
              <input
                type="time"
                value={time}
                onChange={(e) => setTime(e.target.value)}
                style={{ flex: 1, height: 34, border: "1px solid var(--border-default)", borderRadius: 6, padding: "0 8px", fontFamily: "inherit" }}
              />
            </div>
          )}
          <div className="row" style={{ justifyContent: "space-between", marginTop: 12, gap: 8 }}>
            <span className="row" style={{ gap: 2 }}>
              <button type="button" onClick={() => setPicked("")} style={{ ...navBtn, width: "auto", padding: "0 8px", fontSize: 13, color: "var(--text-muted)" }}>
                Clear
              </button>
              <button type="button" onClick={() => pick(todayIso)} style={{ ...navBtn, width: "auto", padding: "0 8px", fontSize: 13, color: "var(--text-accent)" }}>
                Today
              </button>
            </span>
            <div className="row" style={{ gap: 8 }}>
              <Button size="sm" variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
              <Button size="sm" onClick={ok}>OK</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const navBtn: React.CSSProperties = {
  width: 30,
  height: 30,
  display: "grid",
  placeItems: "center",
  border: 0,
  borderRadius: 6,
  background: "none",
  cursor: "pointer",
  fontFamily: "inherit",
};
