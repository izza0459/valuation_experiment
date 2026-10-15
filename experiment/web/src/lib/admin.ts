import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, apiFetch } from "./api";

/** Data hooks for the Admin screens (backend/config/admin_api.py). */

export function useAdminList<T>(path: string) {
  return useQuery({
    queryKey: ["admin", path],
    queryFn: () => apiFetch<T[]>(`/api/admin/${path}`),
  });
}

/** Create (no id) or update (id) one record, then refresh everything that
 * could be showing it, including the form dropdowns that read these lists. */
export function useAdminSave(resource: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id?: number; body: unknown }) =>
      apiFetch<{ id: number }>(`/api/admin/${resource}/${id ? `${id}/` : ""}`, {
        method: id ? "PATCH" : "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: async () => {
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["admin"] }),
        qc.invalidateQueries({ queryKey: ["options"] }),
      ]);
    },
  });
}

/**
 * DRF validation errors come back as `{field: ["message"]}`, nested for
 * sub-objects (`{valuer_profile: {rera_registration_no: [...]}}`). Flatten to
 * `{field: "message"}` so a form can show each under its input.
 */
export function flattenErrors(err: unknown): Record<string, string> {
  if (!(err instanceof ApiError) || !err.body) return { _form: err instanceof Error ? err.message : "Something went wrong." };
  const out: Record<string, string> = {};
  const walk = (value: unknown, key: string) => {
    if (typeof value === "string") out[key] = value;
    else if (Array.isArray(value)) out[key] = value.map(String).join(" ");
    else if (value && typeof value === "object") {
      for (const [k, v] of Object.entries(value)) walk(v, k);
    }
  };
  for (const [k, v] of Object.entries(err.body)) walk(v, k === "detail" || k === "non_field_errors" ? "_form" : k);
  return Object.keys(out).length ? out : { _form: err.message };
}

export const emptyToNull = (value: string) => (value.trim() === "" ? null : value.trim());
