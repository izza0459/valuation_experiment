"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError, apiFetch } from "./api";
import type { JobDetail, TabState } from "./jobs";

/**
 * Autosave for one tab, against `PATCH /api/jobs/<id>/tabs/<tab>/`.
 *
 * Rules this implements (see backend/apps/jobs/tabs.py):
 *  - Only changed fields are sent, debounced, one request in flight at a
 *    time. Edits made while a save is running go out in the next one.
 *  - Every save names the tab version it is based on. If someone else saved
 *    first the server answers 409 and applies nothing (first edit wins):
 *    autosave stops and the user decides whether to drop their edits or
 *    re-apply them on top of the other version.
 *  - A save is all-or-nothing, so a field the server rejected is held back
 *    from later batches until it is edited again; otherwise one bad field
 *    would block every other field's save.
 */

export type SaveStatus = "idle" | "saving" | "saved" | "error" | "conflict" | "blocked";

type PatchResponse = {
  tab: string;
  /** The job's status after the save: completing a stage's tabs moves it on. */
  status: string;
  values: Record<string, unknown>;
  version: number;
  computed: Record<string, Record<string, unknown>>;
  completion: Record<string, TabState["completion"]>;
};

type TabSnapshot = Pick<TabState, "values" | "computed" | "completion" | "version">;

const DEBOUNCE_MS = 600;

/** Saving these changes who may see/edit the job or which rules apply to it
 * (bank rules, header), so the whole job is reloaded rather than patched. */
const NEEDS_JOB_REFRESH = new Set([
  "bank",
  "inspected_by",
  "valuer",
  "peer_reviewer",
  "counter_signatory",
  "registered_valuer",
]);

const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

export function useTabAutosave(jobId: string, tabKey: string, tab: TabState) {
  const qc = useQueryClient();
  // `draft` is what the user has typed and keeps showing as typed; `acked` is
  // the part of it the server has accepted. Only the difference is pending.
  // (Dropping a field from the draft on save would swap the user's text for
  // the server's canonical form - "7250" becoming "7250.00" - mid-typing.)
  const [draft, setDraftState] = useState<Record<string, unknown>>({});
  const [acked, setAckedState] = useState<Record<string, unknown>>({});
  const [errors, setErrorsState] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<SaveStatus>("idle");
  const [notice, setNotice] = useState<string | null>(null);
  const [conflict, setConflict] = useState<TabSnapshot | null>(null);

  const draftRef = useRef(draft);
  const ackedRef = useRef(acked);
  const errorsRef = useRef(errors);
  const versionRef = useRef(tab.version);
  const serverValuesRef = useRef(tab.values);
  const inflight = useRef(false);
  const stopped = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const sendRef = useRef<() => Promise<void>>(async () => {});

  const commitDraft = useCallback((next: Record<string, unknown>) => {
    draftRef.current = next;
    setDraftState(next);
  }, []);
  const commitAcked = useCallback((next: Record<string, unknown>) => {
    ackedRef.current = next;
    setAckedState(next);
  }, []);
  const commitErrors = useCallback((next: Record<string, string>) => {
    errorsRef.current = next;
    setErrorsState(next);
  }, []);

  // Follow the cache. If the version moved and it wasn't our own save, someone
  // else saved (or we refetched): fields already saved stop shadowing the
  // server's value, so their change shows up instead of our stale text.
  useEffect(() => {
    serverValuesRef.current = tab.values;
    if (inflight.current || tab.version === versionRef.current) return;
    versionRef.current = tab.version;
    const pending = Object.fromEntries(
      Object.entries(draftRef.current).filter(([key, value]) => !same(value, ackedRef.current[key])),
    );
    if (Object.keys(pending).length !== Object.keys(draftRef.current).length) {
      commitDraft(pending);
      commitAcked({});
    }
  }, [tab.values, tab.version, commitDraft, commitAcked]);

  const setJob = useCallback(
    (update: (job: JobDetail) => JobDetail) =>
      qc.setQueryData<JobDetail>(["jobs", jobId], (old) => (old ? update(old) : old)),
    [qc, jobId],
  );

  /** Takes the server's view of this tab as the new baseline. */
  const adopt = useCallback(
    (snapshot: TabSnapshot) => {
      versionRef.current = snapshot.version;
      setJob((job) => ({
        ...job,
        tabs: { ...job.tabs, [tabKey]: { ...job.tabs[tabKey], ...snapshot } },
      }));
    },
    [setJob, tabKey],
  );

  const sendable = useCallback(
    () =>
      Object.entries(draftRef.current).filter(
        ([key, value]) => !(key in errorsRef.current) && !same(value, ackedRef.current[key]),
      ),
    [],
  );

  const send = useCallback(async () => {
    if (inflight.current || stopped.current) return;
    const pending = sendable();
    if (pending.length === 0) return;

    inflight.current = true;
    setStatus("saving");
    let saved = false;
    try {
      const res = await apiFetch<PatchResponse>(`/api/jobs/${jobId}/tabs/${tabKey}/`, {
        method: "PATCH",
        body: JSON.stringify({ base_version: versionRef.current, values: Object.fromEntries(pending) }),
      });

      versionRef.current = res.version;
      setJob((job) => ({
        ...job,
        tabs: Object.fromEntries(
          Object.entries(job.tabs).map(([key, t]) => [
            key,
            {
              ...t,
              computed: res.computed[key] ?? t.computed,
              completion: res.completion[key] ?? t.completion,
              ...(key === res.tab ? { values: res.values, version: res.version } : {}),
            },
          ]),
        ),
      }));

      // Record what the server accepted. If the user has typed more since,
      // the draft differs from this and goes out in the next save.
      commitAcked({ ...ackedRef.current, ...Object.fromEntries(pending) });

      setStatus("saved");
      saved = true;
      qc.invalidateQueries({ queryKey: ["job-activity", jobId] });
      const statusBefore = qc.getQueryData<JobDetail>(["jobs", jobId])?.status;
      if (pending.some(([key]) => NEEDS_JOB_REFRESH.has(key)) || (res.status && res.status !== statusBefore)) {
        qc.invalidateQueries({ queryKey: ["jobs", jobId] });
      }
    } catch (err) {
      const body = err instanceof ApiError ? err.body : null;
      const code = body && typeof body.code === "string" ? body.code : null;

      if (err instanceof ApiError && err.status === 400 && code === "validation") {
        commitErrors({ ...errorsRef.current, ...((body?.errors as Record<string, string>) ?? {}) });
        setStatus("error");
      } else if (err instanceof ApiError && err.status === 409 && code === "conflict") {
        stopped.current = true;
        setConflict(body?.current as TabSnapshot);
        setStatus("conflict");
      } else if (err instanceof ApiError && (err.status === 403 || (err.status === 409 && code))) {
        // Locked, frozen, or no longer permitted: nothing more will save.
        stopped.current = true;
        setNotice(err.message);
        setStatus("blocked");
        qc.invalidateQueries({ queryKey: ["jobs", jobId] });
      } else {
        setStatus("error");
      }
    } finally {
      inflight.current = false;
    }

    // Anything typed while that request was running.
    if (saved && sendable().length > 0) {
      clearTimeout(timer.current);
      timer.current = setTimeout(() => void sendRef.current(), DEBOUNCE_MS);
    }
  }, [jobId, tabKey, qc, setJob, commitAcked, commitErrors, sendable]);

  useEffect(() => {
    sendRef.current = send;
  }, [send]);

  const setField = useCallback(
    (key: string, value: unknown) => {
      if (stopped.current) return;
      commitDraft({ ...draftRef.current, [key]: value });

      if (key in errorsRef.current) {
        const { [key]: _cleared, ...rest } = errorsRef.current;
        void _cleared;
        commitErrors(rest);
      }
      setStatus((s) => (s === "saved" || s === "error" ? "idle" : s));

      clearTimeout(timer.current);
      timer.current = setTimeout(() => void sendRef.current(), DEBOUNCE_MS);
    },
    [commitDraft, commitErrors],
  );

  // Leaving the tab (or the page) must not lose what was typed in the last
  // fraction of a second.
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (inflight.current || sendable().length > 0) event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => {
      window.removeEventListener("beforeunload", warn);
      clearTimeout(timer.current);
      if (!stopped.current && sendable().length > 0) void sendRef.current();
    };
  }, [sendable]);

  const resume = useCallback(() => {
    stopped.current = false;
    setConflict(null);
    setNotice(null);
  }, []);

  /** Take the other person's version; throw away my unsaved edits. */
  const discardMine = useCallback(() => {
    if (conflict) adopt(conflict);
    commitDraft({});
    commitAcked({});
    commitErrors({});
    setStatus("idle");
    resume();
  }, [conflict, adopt, commitDraft, commitAcked, commitErrors, resume]);

  /** Keep my edits and send them again on top of the other person's version. */
  const reapplyMine = useCallback(() => {
    if (conflict) adopt(conflict);
    resume();
    void sendRef.current();
  }, [conflict, adopt, resume]);

  const retry = useCallback(() => {
    resume();
    void sendRef.current();
  }, [resume]);

  const pending = Object.fromEntries(
    Object.entries(draft).filter(([key, value]) => !same(value, acked[key])),
  );

  return {
    draft,
    /** Edits the server hasn't accepted yet (what a conflict would discard). */
    pending,
    errors,
    status,
    notice,
    conflict,
    dirty: Object.keys(pending).length > 0,
    setField,
    discardMine,
    reapplyMine,
    retry,
  };
}
