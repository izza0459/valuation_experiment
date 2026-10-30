"use client";

/** Reassigning a lead: hand one of its roles to someone else (apps.jobs.assign).
 * The change shows in the lead's Activity. */

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Dialog, Select } from "@/design-system";
import { ApiError, apiFetch } from "@/lib/api";
import { F } from "./ui";

type Choices = { roles: { key: string; label: string }[]; people: Record<string, { id: number; name: string }[]> };

export function ReassignDialog({ jobId, current, onClose }: {
  jobId: string;
  /** Who holds each role now, by role key. */
  current: Record<string, number | undefined>;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["assign-choices", jobId],
    queryFn: () => apiFetch<Choices>(`/api/jobs/${jobId}/assign/`),
  });
  const [role, setRole] = useState("valuer");
  const [person, setPerson] = useState("");
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failed, setFailed] = useState<string | null>(null);
  const people = data?.people[role] ?? [];
  const holder = people.find((p) => p.id === current[role]);

  async function submit() {
    setBusy(true);
    setErrors({});
    setFailed(null);
    try {
      await apiFetch(`/api/jobs/${jobId}/assign/`, { method: "POST", body: JSON.stringify({ role, person: Number(person) }) });
      await qc.invalidateQueries({ queryKey: ["jobs"] });
      await qc.invalidateQueries({ queryKey: ["job-activity", jobId] });
      onClose();
    } catch (err) {
      if (err instanceof ApiError) {
        const body = (err.body ?? {}) as { errors?: Record<string, string> };
        if (body.errors) setErrors(body.errors);
        else setFailed(err.message);
      } else setFailed("Couldn't reach the server. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open
      title="Reassign this lead"
      onClose={onClose}
      width={440}
      actions={
        <>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button disabled={busy || !person || Number(person) === current[role]} onClick={() => void submit()}>
            {busy ? "Saving…" : "Reassign"}
          </Button>
        </>
      }
    >
      <div style={{ display: "grid", gap: 16 }}>
        <F label="Role" error={errors.role}>
          <Select
            value={role}
            options={(data?.roles ?? []).map((r) => ({ value: r.key, label: r.label }))}
            onChange={(e: React.ChangeEvent<HTMLSelectElement>) => { setRole(e.target.value); setPerson(""); }}
          />
        </F>
        <F label="Hand it to" error={errors.person} helper={holder ? `Now: ${holder.name}` : "Nobody holds this role yet."}>
          <Select
            value={person}
            placeholder="Select…"
            invalid={Boolean(errors.person)}
            options={people.map((p) => ({ value: String(p.id), label: p.name }))}
            onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setPerson(e.target.value)}
          />
        </F>
        {failed && <div style={{ color: "var(--text-error)", fontSize: 14 }}>{failed}</div>}
      </div>
    </Dialog>
  );
}
