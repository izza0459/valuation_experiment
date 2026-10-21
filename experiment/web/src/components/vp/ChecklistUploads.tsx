"use client";

/**
 * Bulk uploads beside the form fields that ask for them:
 *   - mode "title" (Property Address): the title document, with its type from
 *     the field dictionary's Title Document list;
 *   - mode "photos" (Check List): the Makani / DEWA number photographs, when
 *     the checklist says they were taken.
 *
 * Pick or drop several files at once, say what each one is, upload them all.
 * They are ordinary documents and photographs (the Makani and DEWA ones in
 * their own photo slots), so they also show on the Documents and Photos tabs.
 */

import { useRef, useState } from "react";
import { Button, Icon, Select } from "@/design-system";
import { useMedia, useMediaActions } from "@/lib/media";
import { useOptions } from "@/lib/options";

type Pending = { file: File; type: string };

const MAKANI = "photo:makani";
const DEWA = "photo:dewa";

export function ChecklistUploads({
  jobId,
  mode,
  makani = false,
  dewa = false,
  canEdit,
  inline = false,
  lockedReason = "",
}: {
  jobId: string;
  mode: "title" | "photos" | "coi";
  makani?: boolean;
  dewa?: boolean;
  canEdit: boolean;
  /** Sits inside the form grid (under its field) rather than below the form. */
  inline?: boolean;
  /** Why uploading is closed (job in review, issued, or another role's stage). */
  lockedReason?: string;
}) {
  const forCoi = mode === "coi";
  const forTitle = mode === "title" || forCoi;
  const { data: options } = useOptions();
  const docs = useMedia(jobId, "documents");
  const photos = useMedia(jobId, "photos");
  const docActions = useMediaActions(jobId, "documents");
  const photoActions = useMediaActions(jobId, "photos");

  const input = useRef<HTMLInputElement>(null);
  const [pending, setPending] = useState<Pending[]>([]);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The title document types (same keys as the Title Document dropdown).
  const titleTypes = forCoi
    ? [{ value: "doc:coi_consent", label: "COI consent received (proof)" }]
    : (options?.title_doc_type ?? []).map((o) => ({ value: `doc:${o.value}`, label: o.label }));
  const choices = forTitle
    ? titleTypes
    : [...(makani ? [{ value: MAKANI, label: "Makani photo" }] : []), ...(dewa ? [{ value: DEWA, label: "DEWA photo" }] : [])];

  const docItems = docs.data?.items ?? [];
  const photoItems = photos.data?.items ?? [];
  const uploaded = [
    ...titleTypes
      .map((t) => ({ label: t.label, items: docItems.filter((d) => `doc:${d.doc_type}` === t.value) }))
      .filter((g) => g.items.length),
    ...(makani ? [{ label: "Makani photo", items: photoItems.filter((p) => p.slot === "makani") }] : []),
    ...(dewa ? [{ label: "DEWA photo", items: photoItems.filter((p) => p.slot === "dewa") }] : []),
  ];
  const hasTitle = uploaded.some((g) => g.items.length && g.label !== "Makani photo" && g.label !== "DEWA photo");

  /** A sensible first guess: photographs fill the Makani then DEWA slots that
   * are still empty; everything else is the title document (title deed). */
  function guess(file: File, alreadyQueued: Pending[]): string {
    const isImage = file.type.startsWith("image/") || /\.(jpe?g|png|heic|heif)$/i.test(file.name);
    if (!forTitle) {
      const taken = (slot: string, have: boolean) => have || alreadyQueued.some((p) => p.type === slot);
      if (makani && !taken(MAKANI, photoItems.some((p) => p.slot === "makani"))) return MAKANI;
      if (dewa && !taken(DEWA, photoItems.some((p) => p.slot === "dewa"))) return DEWA;
      return choices[0]?.value ?? MAKANI;
    }
    if (isImage && !forTitle) {
      const taken = (slot: string, have: boolean) => have || alreadyQueued.some((p) => p.type === slot);
      if (makani && !taken(MAKANI, photoItems.some((p) => p.slot === "makani"))) return MAKANI;
      if (dewa && !taken(DEWA, photoItems.some((p) => p.slot === "dewa"))) return DEWA;
    }
    if (forCoi) return "doc:coi_consent";
    return titleTypes.find((t) => t.value === "doc:title_deed")?.value ?? titleTypes[0]?.value ?? "doc:title_deed";
  }

  function add(files: FileList | File[] | null) {
    if (!files) return;
    setError(null);
    setPending((prev) => {
      const next = [...prev];
      for (const file of Array.from(files)) next.push({ file, type: guess(file, next) });
      return next;
    });
    if (input.current) input.current.value = "";
  }

  async function uploadAll() {
    setBusy(true);
    setError(null);
    const problems: string[] = [];
    // One request per type: the server takes several files with one type each.
    const groups = new Map<string, File[]>();
    for (const p of pending) groups.set(p.type, [...(groups.get(p.type) ?? []), p.file]);
    for (const [type, files] of groups) {
      const res = type.startsWith("photo:")
        ? await photoActions.upload(files, { slot: type.slice("photo:".length) })
        : await docActions.upload(files, { doc_type: type.slice("doc:".length) });
      problems.push(...res.rejected.map((r) => `${r.name}: ${r.reason}`));
      if (res.error && !res.rejected.length) problems.push(res.error);
    }
    setBusy(false);
    setPending([]);
    if (problems.length) setError(problems.join(" "));
  }

  return (
    <div
      style={
        inline
          ? { display: "grid", gap: 12, padding: 16, borderRadius: 8, background: "var(--surface-subtle)" }
          : { display: "grid", gap: 12, marginTop: 24, paddingTop: 18, borderTop: "1px solid var(--border-divider)" }
      }
    >
      <div>
        <div style={{ fontSize: 15, fontWeight: 700 }}>
          {forCoi ? "Consent received (proof)" : forTitle ? "Title document upload" : "Makani / DEWA photo upload"}
        </div>
        <div style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 2 }}>
          {forCoi
            ? "Required with a Yes: Setup can't finish until the client's consent is uploaded. It also shows on the Documents tab."
            : forTitle
            ? "Add the title document (several files at once if needed) and pick its type. It also shows on the Documents tab."
            : "Add the photos (several at once) and say which number each shows. They also show on the Photos tab."}
        </div>
      </div>

      {/* What is already in, and what is still needed. */}
      <div style={{ display: "grid", gap: 4, fontSize: 14 }}>
        {forTitle && (
          <Need label={forCoi ? "Consent" : "Title document"} done={hasTitle} detail={uploaded.filter((g) => g.label !== "Makani photo" && g.label !== "DEWA photo").map((g) => `${g.label} (${g.items.length})`).join(", ")} />
        )}
        {!forTitle && makani && <Need label="Makani photo" done={photoItems.some((p) => p.slot === "makani")} />}
        {!forTitle && dewa && <Need label="DEWA photo" done={photoItems.some((p) => p.slot === "dewa")} />}
      </div>

      {!canEdit && (
        <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
          Uploading is closed here{lockedReason ? `: ${lockedReason}` : "."}
        </div>
      )}
      {canEdit && (
        <>
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              add(e.dataTransfer.files);
            }}
            className="row wrap"
            style={{
              gap: 12,
              justifyContent: "space-between",
              padding: 14,
              borderRadius: 8,
              border: `1px dashed ${dragging ? "var(--action-primary)" : "var(--border-default)"}`,
              background: dragging ? "var(--surface-accent)" : "var(--surface-subtle)",
            }}
          >
            <span style={{ fontSize: 14, color: "var(--text-secondary)" }}>Drop files here, or choose them</span>
            <input ref={input} type="file" multiple hidden accept={forTitle ? docs.data?.limits.accepts : "image/*"} onChange={(e) => add(e.target.files)} />
            <Button size="sm" variant="outline" icon={<Icon name="upload" size={16} />} onClick={() => input.current?.click()}>
              Choose files
            </Button>
          </div>

          {pending.length > 0 && (
            <div style={{ display: "grid", gap: 8 }}>
              {pending.map((p, i) => (
                <div key={`${p.file.name}-${i}`} className="row wrap" style={{ gap: 10 }}>
                  <span style={{ flex: "1 1 200px", minWidth: 0, fontSize: 14, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {p.file.name}
                  </span>
                  <div style={{ flex: "0 1 280px", minWidth: 200 }}>
                    <Select
                      value={p.type}
                      aria-label={`What ${p.file.name} is`}
                      options={choices}
                      onChange={(e: React.ChangeEvent<HTMLSelectElement>) =>
                        setPending((prev) => prev.map((x, j) => (j === i ? { ...x, type: e.target.value } : x)))
                      }
                    />
                  </div>
                  <button
                    type="button"
                    aria-label={`Remove ${p.file.name}`}
                    onClick={() => setPending((prev) => prev.filter((_, j) => j !== i))}
                    style={{ border: 0, background: "none", cursor: "pointer", display: "flex", padding: 4 }}
                  >
                    <Icon name="x" size={16} />
                  </button>
                </div>
              ))}
              <div className="row" style={{ gap: 8, justifyContent: "flex-end" }}>
                <Button size="sm" variant="outline" disabled={busy} onClick={() => setPending([])}>
                  Clear
                </Button>
                <Button size="sm" disabled={busy} icon={<Icon name="upload" size={16} />} onClick={() => void uploadAll()}>
                  {busy ? "Uploading…" : `Upload ${pending.length} file${pending.length === 1 ? "" : "s"}`}
                </Button>
              </div>
            </div>
          )}
        </>
      )}

      {error && <div style={{ fontSize: 13, color: "var(--text-error)" }}>{error}</div>}
    </div>
  );
}

function Need({ label, done, detail }: { label: string; done: boolean; detail?: string }) {
  return (
    <div className="row" style={{ gap: 8 }}>
      <Icon name={done ? "check-circle" : "circle"} size={16} color={done ? "var(--green-600)" : "var(--gray-500)"} />
      <span>{label}</span>
      <span style={{ fontSize: 13, color: "var(--text-muted)" }}>{done ? detail || "uploaded" : "not uploaded yet"}</span>
    </div>
  );
}
