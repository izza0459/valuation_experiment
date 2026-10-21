import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./api";

/**
 * Mirrors backend/apps/jobs/field_config.py — the backend is the source of
 * truth; these types just describe the JSON it serves at /api/field-config/
 * so the UI and the (future) client-side validation share one shape.
 */
export type FieldType =
  | "text"
  | "textarea"
  | "number"
  | "decimal"
  | "boolean"
  | "date"
  | "datetime"
  | "select"
  | "multiselect"
  | "user"
  | "library"
  /** One or more names (owners, applicants), edited as a list. */
  | "names"
  /** Rooms per storey of a villa: {basement: [...], ground: [...], ...}. */
  | "storeys";

export type VisibilityRule = {
  /** Dotted path resolved against the job's values, e.g.
   * "summary.property_category" or "bank.rules.requires_service_charge". */
  field: string;
  op: "eq" | "in" | "not_in" | "is_true";
  value?: unknown;
};

export type FieldDef = {
  key: string;
  label: string;
  type: FieldType;
  required: boolean;
  default: unknown;
  options_key: string | null;
  visible_if: VisibilityRule | null;
  calculated: boolean;
  help_text: string;
  /** The option label is stored (community, emirate). Options are only
   * suggestions unless `dropdown` is set, which makes it a strict pick. */
  free_text: boolean;
  dropdown?: boolean;
  /** Library fields: picking an entry adds its text instead of replacing it. */
  append?: boolean;
  /** Multiselects: entries not in the list can be typed in. */
  custom?: boolean;
  /** May be left out of the report (include-in-report step). */
  report_optional?: boolean;
  /** In the include-in-report step: always printed, worked out from other
   * fields, or the valuer's choice. */
  report?: "always" | "derived" | "optional";
};

export type TabDef = {
  key: string;
  label: string;
  /** The workspace groups tabs under stages (field_config.STAGES). */
  stage: StageKey;
  order: number;
  fields: FieldDef[];
};

export type StageKey = "setup" | "inspection" | "valuation" | "review";

/** Mirrors field_config.STAGES: the stages the tabs are grouped under. */
export const STAGES: { key: StageKey; label: string }[] = [
  { key: "setup", label: "Setup" },
  { key: "inspection", label: "Inspection" },
  { key: "valuation", label: "Valuation" },
  { key: "review", label: "Review & Send" },
];

export function useFieldConfig() {
  return useQuery({
    queryKey: ["field-config"],
    queryFn: () => apiFetch<TabDef[]>("/api/field-config/"),
    staleTime: 5 * 60 * 1000,
  });
}

/** Walks a dotted path like "summary.bua_sqft" or
 * "bank.rules.requires_service_charge" through a nested values object. */
function resolvePath(path: string, values: Record<string, unknown>): unknown {
  return path.split(".").reduce<unknown>((current, segment) => {
    if (current === null || current === undefined || typeof current !== "object") {
      return undefined;
    }
    return (current as Record<string, unknown>)[segment];
  }, values);
}

/** Evaluates a field's visible_if rule against the job's current values
 * (tab data plus `bank`). Mirrors the rule shape in field_config.py. */
export function isFieldVisible(
  field: FieldDef,
  values: Record<string, unknown>
): boolean {
  const rule = field.visible_if;
  if (!rule) return true;

  const actual = resolvePath(rule.field, values);
  switch (rule.op) {
    case "eq":
      return actual === rule.value;
    case "in":
      return Array.isArray(rule.value) && rule.value.includes(actual as never);
    case "not_in":
      return Array.isArray(rule.value) && !rule.value.includes(actual as never);
    case "is_true":
      return Boolean(actual);
    default:
      return true;
  }
}
