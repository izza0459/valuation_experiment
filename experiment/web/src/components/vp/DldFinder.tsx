"use client";

/**
 * Finding DLD sales for the Evidence tab. The search starts from what the job
 * already holds (community, building, type, bedrooms, BUA ±20%, last 12
 * months, ready or off-plan) and every filter can be changed. Ticked sales
 * are added as comparables. The sales come from DLD's open data, loaded into
 * the app by an admin (backend/apps/evidence/dld.py); nothing calls DLD.
 */

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Icon, Input, Select } from "@/design-system";
import { ApiError, apiFetch } from "@/lib/api";
import { useMe } from "@/lib/auth";
import { formatDate } from "./format";
import { Banner } from "./ui";

type Filters = {
  community: string;
  building: string;
  type: string;
  beds: string;
  bua_min: string;
  bua_max: string;
  months: string;
  status: string;
};

type Sale = {
  id: number;
  transaction_number: string;
  date: string;
  building: string;
  community: string;
  master_project: string;
  type: string;
  rooms: string;
  bua_sqft: string | null;
  price_aed: string;
  aed_per_sqft: string | null;
  offplan: boolean | null;
  added: boolean;
};

type DataStatus = { count: number; earliest: string | null; latest: string | null };
type SearchResult = { filters: Record<string, unknown>; defaults: Record<string, unknown>; results: Sale[]; data: DataStatus };

const asFilters = (raw: Record<string, unknown>): Filters => ({
  community: String(raw.community ?? ""),
  building: String(raw.building ?? ""),
  type: String(raw.type ?? ""),
  beds: raw.beds === null || raw.beds === undefined ? "" : String(raw.beds),
  bua_min: String(raw.bua_min ?? ""),
  bua_max: String(raw.bua_max ?? ""),
  months: String(raw.months ?? "12"),
  status: String(raw.status ?? "any"),
});

const num = (v: string | null) => (v ? Number(v).toLocaleString("en-US", { maximumFractionDigits: 0 }) : "—");

export function DldFinder({ jobId, canEdit, onClose }: { jobId: string; canEdit: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const { data: me } = useMe();
  const isAdmin = me?.authenticated ? me.user.is_admin : false;
  // null = the job's own search, which runs as soon as the finder opens.
  const [applied, setApplied] = useState<Filters | null>(null);
  const [draft, setDraft] = useState<Filters | null>(null);
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ["dld-search", jobId, applied],
    queryFn: () =>
      apiFetch<SearchResult>(
        `/api/jobs/${jobId}/evidence/dld/${applied ? `?${new URLSearchParams(applied as Record<string, string>)}` : ""}`,
      ),
  });
  const result = query.data ?? null;
  const filters = draft ?? (result ? asFilters(result.filters) : null);
  const setFilters = setDraft;
  const searching = query.isFetching;

  function search(next: Filters) {
    setError(null);
    setPicked(new Set());
    setApplied({ ...next });
  }

  async function add() {
    setBusy(true);
    setError(null);
    try {
      const res = await apiFetch<{ added: number }>(`/api/jobs/${jobId}/evidence/dld/`, {
        method: "POST",
        body: JSON.stringify({ ids: [...picked] }),
      });
      setNotice(`${res.added} sale${res.added === 1 ? "" : "s"} added to the comparables, ticked for the report.`);
      await qc.invalidateQueries({ queryKey: ["job-evidence", jobId] });
      setPicked(new Set());
      await qc.invalidateQueries({ queryKey: ["dld-search", jobId] });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't reach the server. Try again.");
    } finally {
      setBusy(false);
    }
  }

  async function upload(file: File) {
    setBusy(true);
    setError(null);
    try {
      const body = new FormData();
      body.append("file", file);
      const res = await apiFetch<{ added: number; count: number }>("/api/evidence/dld/", { method: "POST", body });
      setNotice(`Loaded ${res.added.toLocaleString("en-US")} new DLD sales (${res.count.toLocaleString("en-US")} in total).`);
      await qc.invalidateQueries({ queryKey: ["dld-search", jobId] });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't reach the server. Try again.");
    } finally {
      setBusy(false);
    }
  }

  const set = (k: keyof Filters) => (e: { target: { value: string } }) => filters && setFilters({ ...filters, [k]: e.target.value });
  const data = result?.data;
  const sales = result?.results ?? [];
  const field = (label: string, input: React.ReactNode) => (
    <div style={{ minWidth: 0 }}>
      <div style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 4 }}>{label}</div>
      {input}
    </div>
  );

  return (
    <div className="card" style={{ padding: 18, marginBottom: 14, display: "grid", gap: 14 }}>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <div style={{ fontSize: 16 }}>DLD sales</div>
          <div style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 2 }}>
            Registered sale prices from the Dubai Land Department&apos;s open data.
            {data && data.count > 0 && (
              <>
                {" "}
                {data.count.toLocaleString("en-US")} sales loaded, {formatDate(data.earliest)} to {formatDate(data.latest)}.
              </>
            )}
          </div>
        </div>
        <button
          type="button"
          aria-label="Close"
          onClick={onClose}
          style={{ border: 0, background: "none", cursor: "pointer", padding: 4 }}
        >
          <Icon name="x" size={18} />
        </button>
      </div>

      {(error || query.isError) && (
        <Banner tone="red" icon="alert-circle">
          {error ?? (query.error instanceof ApiError ? query.error.message : "Couldn't search DLD sales. Try again.")}
        </Banner>
      )}
      {notice && !error && (
        <Banner tone="green" icon="check">
          {notice}
        </Banner>
      )}

      {data && data.count === 0 && (
        <div style={{ fontSize: 14, color: "var(--text-secondary)", lineHeight: 1.5 }}>
          No DLD sales are loaded yet.{" "}
          {isAdmin
            ? "Download the transactions file from DLD's open data (Dubai Pulse, or the export on DLD's open-data page) and load it here."
            : "Ask an admin to load DLD's transactions file."}
        </div>
      )}

      {isAdmin && (
        <div className="row" style={{ gap: 10 }}>
          <label
            className="row"
            style={{ gap: 8, fontSize: 13, color: "var(--text-accent)", cursor: busy ? "default" : "pointer" }}
          >
            <Icon name="upload" size={16} />
            {data && data.count > 0 ? "Load a newer DLD file" : "Load DLD transactions file (CSV)"}
            <input
              type="file"
              accept=".csv,text/csv"
              disabled={busy}
              style={{ display: "none" }}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void upload(file);
                e.target.value = "";
              }}
            />
          </label>
        </div>
      )}

      {filters && data && data.count > 0 && (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4,minmax(0,1fr))", gap: 12 }}>
            {field("Community", <Input value={filters.community} onChange={set("community")} />)}
            {field("Building / project", <Input value={filters.building} onChange={set("building")} placeholder="Any" />)}
            {field(
              "Type",
              <Select
                value={filters.type}
                onChange={set("type")}
                options={[
                  { value: "", label: "Any" },
                  { value: "apartment", label: "Apartment" },
                  { value: "villa", label: "Villa / townhouse" },
                  { value: "office", label: "Office" },
                  { value: "retail", label: "Retail" },
                ]}
              />,
            )}
            {field(
              "Bedrooms",
              <Select
                value={filters.beds}
                onChange={set("beds")}
                options={[{ value: "", label: "Any" }, { value: "0", label: "Studio" }, ...[1, 2, 3, 4, 5, 6].map((n) => ({ value: String(n), label: String(n) }))]}
              />,
            )}
            {field("BUA from (sqft)", <Input inputMode="numeric" value={filters.bua_min} onChange={set("bua_min")} placeholder="Any" />)}
            {field("BUA to (sqft)", <Input inputMode="numeric" value={filters.bua_max} onChange={set("bua_max")} placeholder="Any" />)}
            {field(
              "Sold within",
              <Select
                value={filters.months}
                onChange={set("months")}
                options={[
                  { value: "3", label: "3 months" },
                  { value: "6", label: "6 months" },
                  { value: "12", label: "12 months" },
                  { value: "24", label: "24 months" },
                ]}
              />,
            )}
            {field(
              "Ready or off-plan",
              <Select
                value={filters.status}
                onChange={set("status")}
                options={[
                  { value: "ready", label: "Ready" },
                  { value: "offplan", label: "Off-plan" },
                  { value: "any", label: "Either" },
                ]}
              />,
            )}
          </div>
          <div className="row" style={{ gap: 10 }}>
            <Button size="sm" disabled={searching} icon={<Icon name="search" size={16} />} onClick={() => search(filters)}>
              {searching ? "Searching…" : "Search"}
            </Button>
            <button
              type="button"
              onClick={() => {
                if (!result) return;
                const own = asFilters(result.defaults);
                setFilters(own);
                search(own);
              }}
              style={{ border: 0, background: "none", color: "var(--text-accent)", cursor: "pointer", fontFamily: "inherit", fontSize: 13 }}
            >
              Reset to this job
            </button>
          </div>

          {sales.length === 0 ? (
            <div style={{ fontSize: 14, color: "var(--text-muted)" }}>
              No sales match. Try widening the BUA range, a longer period, or clearing the building.
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", fontSize: 14, borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ textAlign: "left", color: "var(--text-muted)", fontSize: 13 }}>
                    <th style={{ padding: 6 }} />
                    <th style={{ padding: 6 }}>Sold</th>
                    <th style={{ padding: 6 }}>Building / community</th>
                    <th style={{ padding: 6 }}>Type</th>
                    <th style={{ padding: 6, textAlign: "right" }}>BUA (sqft)</th>
                    <th style={{ padding: 6, textAlign: "right" }}>Price (AED)</th>
                    <th style={{ padding: 6, textAlign: "right" }}>AED / sqft</th>
                  </tr>
                </thead>
                <tbody>
                  {sales.map((s) => (
                    <tr key={s.id} style={{ borderTop: "1px solid var(--border-divider)" }}>
                      <td style={{ padding: 6 }}>
                        {s.added ? (
                          <Icon name="check" size={16} color="var(--green-600)" />
                        ) : (
                          <input
                            type="checkbox"
                            aria-label={`Add sale ${s.transaction_number}`}
                            disabled={!canEdit}
                            checked={picked.has(s.id)}
                            onChange={(e) => {
                              const next = new Set(picked);
                              if (e.target.checked) next.add(s.id);
                              else next.delete(s.id);
                              setPicked(next);
                            }}
                          />
                        )}
                      </td>
                      <td style={{ padding: 6, whiteSpace: "nowrap" }}>{formatDate(s.date)}</td>
                      <td style={{ padding: 6 }} title={s.master_project || undefined}>
                        {[s.building, s.community].filter(Boolean).join(", ") || "—"}
                      </td>
                      <td style={{ padding: 6, whiteSpace: "nowrap" }}>
                        {[s.rooms, s.type, s.offplan ? "off-plan" : ""].filter(Boolean).join(" · ")}
                      </td>
                      <td className="num" style={{ padding: 6, textAlign: "right" }}>{num(s.bua_sqft)}</td>
                      <td className="num" style={{ padding: 6, textAlign: "right" }}>{num(s.price_aed)}</td>
                      <td className="num" style={{ padding: 6, textAlign: "right" }}>{num(s.aed_per_sqft)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {canEdit && sales.length > 0 && (
            <div>
              <Button size="sm" disabled={busy || picked.size === 0} onClick={() => void add()}>
                Add {picked.size || ""} selected as comparables
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
