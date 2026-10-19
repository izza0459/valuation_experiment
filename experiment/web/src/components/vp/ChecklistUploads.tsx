"use client";

/**
 * Uploads that belong with the Check List: the title document, and the
 * Makani / DEWA number photographs once the checklist says one was taken.
 * They are ordinary documents and photographs (the Makani and DEWA ones in
 * their own photo slots), so they show on the Documents and Photos tabs too.
 */

import { useRef, useState } from "react";
import { Button, Icon } from "@/design-system";
import { useMedia, useMediaActions, type MediaItem } from "@/lib/media";

type Slot = "makani" | "dewa";

export function ChecklistUploads({
  jobId,
  makani,
  dewa,
  canEdit,
}: {
  jobId: string;
  makani: boolean;
  dewa: boolean;
  canEdit: boolean;
}) {
  const docs = useMedia(jobId, "documents");
  const photos = useMedia(jobId, "photos");
  const docActions = useMediaActions(jobId, "documents");
  const photoActions = useMediaActions(jobId, "photos");

  const titleDocs = (docs.data?.items ?? []).filter((d) => d.doc_type === "title_deed");
  const inSlot = (slot: Slot) => (photos.data?.items ?? []).filter((p) => p.slot === slot);

  return (
    <div style={{ display: "grid", gap: 14, marginTop: 24, paddingTop: 18, borderTop: "1px solid var(--border-divider)" }}>
      <div style={{ fontSize: 15, fontWeight: 700 }}>Uploads</div>
      <UploadRow
        label="Title document"
        hint="Title deed or the document the address is taken from. Also listed on the Documents tab."
        items={titleDocs}
        accept={docs.data?.limits.accepts}
        canEdit={canEdit && Boolean(docs.data?.can_edit)}
        onUpload={(files) => docActions.upload(files, { doc_type: "title_deed" })}
      />
      {makani && (
        <UploadRow
          label="Makani photo"
          hint="The Makani number plate. Also shown on the Photos tab."
          items={inSlot("makani")}
          accept="image/*"
          canEdit={canEdit && Boolean(photos.data?.can_edit)}
          onUpload={(files) => photoActions.upload(files, { slot: "makani" })}
        />
      )}
      {dewa && (
        <UploadRow
          label="DEWA photo"
          hint="The DEWA meter / account number. Also shown on the Photos tab."
          items={inSlot("dewa")}
          accept="image/*"
          canEdit={canEdit && Boolean(photos.data?.can_edit)}
          onUpload={(files) => photoActions.upload(files, { slot: "dewa" })}
        />
      )}
    </div>
  );
}

function UploadRow({
  label,
  hint,
  items,
  accept,
  canEdit,
  onUpload,
}: {
  label: string;
  hint: string;
  items: MediaItem[];
  accept?: string;
  canEdit: boolean;
  onUpload: (files: File[]) => Promise<{ created: MediaItem[]; rejected: { name: string; reason: string }[]; error?: string }>;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function pick(files: FileList | null) {
    if (!files || files.length === 0) return;
    setBusy(true);
    setError(null);
    const res = await onUpload(Array.from(files));
    setBusy(false);
    if (res.error || res.rejected.length) {
      setError(res.rejected.map((r) => `${r.name}: ${r.reason}`).join(" ") || res.error || "Upload failed.");
    }
    if (input.current) input.current.value = "";
  }

  return (
    <div className="row wrap" style={{ gap: 12, justifyContent: "space-between", alignItems: "flex-start" }}>
      <div style={{ minWidth: 0, flex: "1 1 260px" }}>
        <div style={{ fontSize: 14 }}>
          {label}
          {items.length > 0 && (
            <span style={{ color: "var(--green-600)", marginLeft: 8, fontSize: 13 }}>
              <Icon name="check" size={13} /> {items.length} uploaded
            </span>
          )}
        </div>
        <div style={{ fontSize: 12.5, color: "var(--text-muted)", marginTop: 2 }}>{hint}</div>
        {items.length > 0 && (
          <div style={{ fontSize: 13, color: "var(--text-secondary)", marginTop: 4 }}>
            {items.map((i) => i.caption || i.original_name).join(", ")}
          </div>
        )}
        {error && <div style={{ fontSize: 13, color: "var(--text-error)", marginTop: 4 }}>{error}</div>}
      </div>
      {canEdit && (
        <>
          <input ref={input} type="file" multiple hidden accept={accept} onChange={(e) => void pick(e.target.files)} />
          <Button size="sm" variant="outline" disabled={busy} icon={<Icon name="upload" size={16} />} onClick={() => input.current?.click()}>
            {busy ? "Uploading…" : items.length ? "Add more" : "Upload"}
          </Button>
        </>
      )}
    </div>
  );
}
