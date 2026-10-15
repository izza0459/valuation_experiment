import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./api";

export type JobListItem = {
  id: number;
  bayut_internal_reference_no: string;
  bank_reference_no: string;
  bank_name: string;
  property_label: string;
  property_type: string;
  valuer_name: string;
  purpose: string;
  status: string;
  status_label: string;
  version: number;
  is_locked: boolean;
  date_time_request_received: string | null;
  created_at: string;
  updated_at: string;
};

/** One tab as the server sees it: see backend/apps/jobs/tabs.py. */
export type TabState = {
  values: Record<string, unknown>;
  /** Server-derived values (sqft, DMS, rate/sqft ...): shown, never sent. */
  computed: Record<string, unknown>;
  /** Over the tab's visible required fields; the server is authoritative. */
  completion: { pct: number; missing: string[] };
  /** Edit counter; a save names the version it is based on (first edit wins). */
  version: number;
  can_edit: boolean;
  read_only_reason: string;
  /** Fields on an otherwise editable tab this user may not change. */
  read_only_fields: string[];
};

/** A lifecycle move this user may make now (backend/apps/jobs/transitions.py). */
export type JobAction = {
  to: string;
  label: string;
  tone: "primary" | "outline";
  comments_required: boolean;
  /** False while something blocks it; `blockers` says what. */
  enabled: boolean;
  blockers: string[];
};

export type TransitionEntry = {
  id: number;
  from_status: string;
  to_status: string;
  to_label: string;
  label: string;
  who: string;
  comments: string;
  at: string;
};

export type JobDetail = JobListItem & {
  tabs: Record<string, TabState>;
  available_actions: JobAction[];
  /** The signed-off PDF once issued. */
  issued_report?: { id: number; issued_at: string } | null;
  /** The newer version made from this issued job, if any. */
  revision?: { id: number; reference: string; version: number } | null;
  /** Issued, no revision yet, and this user is an admin. */
  can_revise?: boolean;
  /** The final report is being produced in the background; no moves until it ends. */
  issue_in_progress?: boolean;
  /** Why the last issue attempt failed, if it did. */
  issue_error?: string;
  /** Who gave the second signature, and when; null until they have. */
  countersigned_by_name?: string | null;
  countersigned_at?: string | null;
  bank_rules?: Record<string, unknown>;
} & Record<string, unknown>;

/** DRF PageNumberPagination envelope. */
export type Paginated<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

export type JobFilters = {
  view?: "all" | "mine" | "review";
  status?: string;
  bank?: string;
  valuer?: string;
  type?: string;
  q?: string;
};

function toQueryString(filters: JobFilters): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value && value !== "all") params.set(key, value);
  }
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export function useJobs(filters: JobFilters = {}) {
  return useQuery({
    queryKey: ["jobs", filters],
    queryFn: () => apiFetch<Paginated<JobListItem>>(`/api/jobs/${toQueryString(filters)}`),
  });
}

export type JobKpis = {
  in_progress: number;
  awaiting_peer_review: number;
  issued_this_week: number;
  avg_turnaround_hours: number | null;
};

export function useJobKpis() {
  return useQuery({
    queryKey: ["job-kpis"],
    queryFn: () => apiFetch<JobKpis>("/api/jobs/kpis/"),
  });
}

export function useTransitions(id: string) {
  return useQuery({
    queryKey: ["job-transitions", id],
    queryFn: () => apiFetch<TransitionEntry[]>(`/api/jobs/${id}/transitions/`),
    enabled: Boolean(id),
  });
}

export function useJob(id: string) {
  return useQuery({
    queryKey: ["jobs", id],
    queryFn: () => apiFetch<JobDetail>(`/api/jobs/${id}/`),
    enabled: Boolean(id),
    // While the report is being issued in the background, check back until it's done.
    refetchInterval: (query) => (query.state.data?.issue_in_progress ? 2000 : false),
  });
}

/**
 * Every tab's current values keyed by tab, plus `bank`. The server flattens
 * each tab (Check List and Instructions span Job and Property rows), so the
 * UI never has to know where a field is stored. `bank` isn't a tab:
 * conditional rules reference the bank master's rules (the ADIB service
 * charge) rather than matching a bank name.
 */
export function buildTabValues(job: JobDetail): Record<string, unknown> {
  const values: Record<string, unknown> = {
    bank: { name: job.bank_name, rules: job.bank_rules ?? {} },
  };
  for (const [key, tab] of Object.entries(job.tabs ?? {})) values[key] = tab.values;
  return values;
}

export const JOB_STATUS_LABELS: Record<string, string> = {
  instruction_received: "Instruction Received",
  setup: "Setup",
  inspection_scheduled: "Inspection Scheduled",
  inspected: "Inspected",
  valuation_in_progress: "Valuation In Progress",
  peer_review: "Peer Review",
  approved_signed: "Approved & Signed",
  issued: "Issued",
};
