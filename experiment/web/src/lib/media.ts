"use client";

/**
 * Photographs and documents for a job (build-order step 5), against
 * `/api/jobs/<id>/photos/` and `/documents/` (see backend/apps/media_files).
 *
 * The server decides what is acceptable, who may change what, and what the job
 * still needs; this only carries that to the screen.
 */

import { useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, apiFetch } from "./api";

export type MediaKind = "photos" | "documents";

export type MediaItem = {
  id: number;
  caption: string;
  order: number;
  include_in_report: boolean;
  original_name: string;
  content_type: string;
  size_bytes: number;
  edit_version: number;
  uploaded_at: string;
  uploaded_by: string;
  /** API paths; prefix with `apiUrl`. Behind the same sign-in as everything else. */
  url: string;
  thumb_url: string;
  // photos
  slot?: "general" | "makani" | "dewa";
  width?: number;
  height?: number;
  // documents
  doc_type?: string;
  page_count?: number;
  is_pdf?: boolean;
};

export type MediaList = {
  items: MediaItem[];
  can_edit: boolean;
  read_only_reason: string;
  needs: { label: string; met: boolean }[];
  limits: {
    max_items: number;
    max_file_mb: number;
    files_per_upload: number;
    accepts: string;
    exec_summary_photos: number;
  };
  doc_types: { value: string; label: string }[];
};

export type Rejected = { name: string; reason: string };
export type UploadOutcome = { created: MediaItem[]; rejected: Rejected[]; error?: string };
export type ChangeOutcome = { ok: true; item?: MediaItem } | { ok: false; conflict: boolean; message: string };

export function useMedia(jobId: string, kind: MediaKind) {
  return useQuery({
    queryKey: ["media", jobId, kind],
    queryFn: () => apiFetch<MediaList>(`/api/jobs/${jobId}/${kind}/`),
  });
}

export function useMediaActions(jobId: string, kind: MediaKind) {
  const qc = useQueryClient();
  const base = `/api/jobs/${jobId}/${kind}/`;

  /** Whatever changed here can change what the job needs, who can send it
   * for review, and the activity feed. */
  const refresh = useCallback(async () => {
    await Promise.all([
      qc.invalidateQueries({ queryKey: ["media", jobId, kind] }),
      qc.invalidateQueries({ queryKey: ["jobs", jobId] }),
      qc.invalidateQueries({ queryKey: ["job-activity", jobId] }),
    ]);
  }, [qc, jobId, kind]);

  const failure = (err: unknown): { ok: false; conflict: boolean; message: string } => {
    if (err instanceof ApiError) {
      return { ok: false, conflict: err.status === 409 && err.body?.code === "conflict", message: err.message };
    }
    return { ok: false, conflict: false, message: "Couldn't reach the server. Try again." };
  };

  const upload = useCallback(
    async (files: File[], extra: Record<string, string> = {}): Promise<UploadOutcome> => {
      const form = new FormData();
      files.forEach((f) => form.append("files", f));
      Object.entries(extra).forEach(([k, v]) => v && form.append(k, v));
      try {
        const res = await apiFetch<UploadOutcome>(base, { method: "POST", body: form });
        await refresh();
        return res;
      } catch (err) {
        // "None of the files could be added" still says why for each one.
        if (err instanceof ApiError && Array.isArray(err.body?.rejected)) {
          return { created: [], rejected: err.body.rejected as Rejected[], error: err.message };
        }
        return { created: [], rejected: [], error: failure(err).message };
      }
    },
    [base, refresh],
  );

  const change = useCallback(
    async (item: MediaItem, changes: Record<string, unknown>): Promise<ChangeOutcome> => {
      try {
        const updated = await apiFetch<MediaItem>(`${base}${item.id}/`, {
          method: "PATCH",
          body: JSON.stringify({ base_version: item.edit_version, ...changes }),
        });
        await refresh();
        return { ok: true, item: updated };
      } catch (err) {
        await refresh(); // on a conflict this shows the version that won
        return failure(err);
      }
    },
    [base, refresh],
  );

  const remove = useCallback(
    async (item: MediaItem): Promise<ChangeOutcome> => {
      try {
        await apiFetch<void>(`${base}${item.id}/`, { method: "DELETE" });
        await refresh();
        return { ok: true };
      } catch (err) {
        await refresh();
        return failure(err);
      }
    },
    [base, refresh],
  );

  const reorder = useCallback(
    async (ids: number[]): Promise<ChangeOutcome> => {
      try {
        await apiFetch<MediaItem[]>(`${base}reorder/`, { method: "POST", body: JSON.stringify({ ids }) });
        await refresh();
        return { ok: true };
      } catch (err) {
        await refresh();
        return failure(err);
      }
    },
    [base, refresh],
  );

  return { upload, change, remove, reorder };
}
