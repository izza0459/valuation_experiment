"use client";

/**
 * The Photos and Documents tabs (design brief S3, build-order step 5).
 *
 * Upload (several at once, by drag-and-drop or the file picker), caption, put
 * in order, leave out of the report, remove. What may be uploaded, who may
 * change what, and what the job still needs all come from the server; a
 * saved caption is based on the version the user was looking at, so if
 * someone else changed it first theirs stays and the screen shows it.
 */

import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button, Dialog, Icon, Input, Select } from "@/design-system";
import { apiUrl } from "@/lib/api";
import {
  useMedia,
  useMediaActions,
  type ChangeOutcome,
  type MediaItem,
  type MediaKind,
  type Rejected,
} from "@/lib/media";
import { uploadDemoFiles } from "./demoFill";
import { Banner } from "./ui";

/** Same switch as the form sections' "Fill demo data" button. */
const DEMO_FILL = process.env.NEXT_PUBLIC_DEMO_FILL !== "false";

const SLOTS = [
  { value: "general", label: "General photograph" },
  { value: "makani", label: "Makani number" },
  { value: "dewa", label: "DEWA number" },
];

const ACCEPT: Record<MediaKind, string> = {
  photos: ".jpg,.jpeg,.png,.heic,.heif,image/jpeg,image/png,image/heic,image/heif",
  documents: ".pdf,.jpg,.jpeg,.png,.heic,.heif,application/pdf,image/jpeg,image/png,image/heic,image/heif",
};

const COPY = {
  photos: { noun: "photograph", empty: "No photographs yet.", drop: "Drop photographs here", pick: "Choose photographs" },
  documents: { noun: "document", empty: "No documents yet.", drop: "Drop documents here", pick: "Choose documents" },
};

type Notice = { tone: "green" | "red" | "amber"; text: string };

const sizeText = (bytes: number) => (bytes >= 1048576 ? `${(bytes / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`);

export function MediaTab({ jobId, kind }: { jobId: string; kind: MediaKind }) {
  const { data, isLoading, isError } = useMedia(jobId, kind);
  const actions = useMediaActions(jobId, kind);
  const qc = useQueryClient();
  const copy = COPY[kind];

  const input = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [rejected, setRejected] = useState<Rejected[]>([]);
  const [slot, setSlot] = useState("general");
  const [docType, setDocType] = useState("title_deed");
  const [removing, setRemoving] = useState<MediaItem | null>(null);
  const [removeBusy, setRemoveBusy] = useState(false);

  if (isLoading) return <p style={{ margin: 0, color: "var(--text-muted)" }}>Loading…</p>;
  if (isError || !data) {
    return (
      <Banner tone="red" icon="alert-circle">
        Couldn&apos;t load the {kind}. Reload to try again.
      </Banner>
    );
  }

  const items = data.items;
  const canEdit = data.can_edit;
  const docTypes = data.doc_types;
  const typeLabel = (value?: string) => docTypes.find((t) => t.value === value)?.label ?? value ?? "";
  const summaryIds = new Set(
    kind === "photos"
      ? items
          .filter((p) => p.include_in_report && p.slot === "general")
          .slice(0, data.limits.exec_summary_photos)
          .map((p) => p.id)
      : [],
  );

  const outcome = (res: ChangeOutcome, done?: string) => {
    if (res.ok) {
      if (done) setNotice({ tone: "green", text: done });
    } else {
      setNotice({
        tone: res.conflict ? "amber" : "red",
        text: res.conflict ? `${res.message} The version now shown is the one that was saved first.` : res.message,
      });
    }
  };

  async function handleFiles(list: FileList | File[] | null) {
    const files = Array.from(list ?? []);
    if (files.length === 0 || uploading || !canEdit) return;
    setUploading(true);
    setNotice(null);
    setRejected([]);
    const res = await actions.upload(files, kind === "photos" ? { slot } : { doc_type: docType });
    setUploading(false);
    setRejected(res.rejected);
    if (res.created.length > 0) {
      const n = res.created.length;
      setNotice({ tone: "green", text: `${n} ${copy.noun}${n === 1 ? "" : "s"} added.` });
    } else if (res.error) {
      setNotice({ tone: "red", text: res.error });
    }
    if (input.current) input.current.value = "";
  }

  async function move(item: MediaItem, delta: -1 | 1) {
    const ids = items.map((i) => i.id);
    const from = ids.indexOf(item.id);
    const to = from + delta;
    if (to < 0 || to >= ids.length) return;
    [ids[from], ids[to]] = [ids[to], ids[from]];
    outcome(await actions.reorder(ids));
  }

  async function confirmRemove() {
    if (!removing) return;
    setRemoveBusy(true);
    const res = await actions.remove(removing);
    setRemoveBusy(false);
    setRemoving(null);
    outcome(res, `${removing.original_name || `The ${copy.noun}`} was removed.`);
  }

  const itemProps = (item: MediaItem, index: number) => ({
    item,
    index,
    count: items.length,
    canEdit,
    onMove: (delta: -1 | 1) => void move(item, delta),
    onChange: async (changes: Record<string, unknown>) => outcome(await actions.change(item, changes)),
    onRemove: () => setRemoving(item),
  });

  // Dummy photographs (general, Makani, DEWA) or documents (title deed, SPA).
  async function fillDemo() {
    setUploading(true);
    setNotice(null);
    const problems = await uploadDemoFiles(jobId, kind, qc);
    setUploading(false);
    setNotice(problems.length ? { tone: "red", text: problems.join(" ") } : { tone: "green", text: "Demo files added." });
  }

  return (
    <div>
      {DEMO_FILL && canEdit && (
        <div className="row" style={{ justifyContent: "flex-end", marginBottom: 12 }}>
          <Button variant="outline" size="sm" disabled={uploading} onClick={() => void fillDemo()}>
            Fill demo data
          </Button>
        </div>
      )}

      {!canEdit && data.read_only_reason && (
        <Banner tone="blue" icon="lock">
          {data.read_only_reason}
        </Banner>
      )}

      {data.needs.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 6 }}>THIS JOB NEEDS</div>
          <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 6 }}>
            {data.needs.map((need) => (
              <li key={need.label} className="row" style={{ gap: 8, fontSize: 14, alignItems: "flex-start" }}>
                <Icon
                  name={need.met ? "check" : "alert-circle"}
                  size={16}
                  color={need.met ? "var(--green-600)" : "var(--amber-600)"}
                  style={{ marginTop: 3 }}
                />
                <span style={{ color: need.met ? "var(--text-secondary)" : "var(--text-primary)" }}>{need.label}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {notice && (
        <Banner tone={notice.tone} icon={notice.tone === "green" ? "check" : "alert-circle"}>
          {notice.text}
        </Banner>
      )}

      {rejected.length > 0 && (
        <Banner tone="amber" icon="alert-triangle">
          <b style={{ fontWeight: 500 }}>
            {rejected.length === 1 ? "1 file wasn't added:" : `${rejected.length} files weren't added:`}
          </b>
          <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
            {rejected.map((r, i) => (
              <li key={`${r.name}-${i}`}>
                <b style={{ fontWeight: 500 }}>{r.name}</b>: {r.reason}
              </li>
            ))}
          </ul>
        </Banner>
      )}

      {canEdit && (
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            void handleFiles(e.dataTransfer.files);
          }}
          style={{
            border: "1.5px dashed " + (dragging ? "var(--border-focus)" : "var(--border-default)"),
            background: dragging ? "var(--surface-accent)" : "var(--surface-subtle)",
            borderRadius: 10,
            padding: "20px 16px",
            marginBottom: 18,
            textAlign: "center",
          }}
        >
          <Icon name="upload" size={24} color="var(--text-muted)" />
          <div style={{ fontSize: 15, margin: "6px 0 2px" }}>{uploading ? "Uploading…" : copy.drop}</div>
          <div style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 12 }}>
            {data.limits.accepts} · up to {data.limits.max_file_mb} MB each · {data.limits.files_per_upload} at a time ·{" "}
            {items.length} of {data.limits.max_items} added
          </div>
          <div className="row" style={{ justifyContent: "center", gap: 10, flexWrap: "wrap" }}>
            <div style={{ width: 220, textAlign: "left" }}>
              {kind === "photos" ? (
                <Select value={slot} options={SLOTS} onChange={(e) => setSlot(e.target.value)} aria-label="Photograph type" />
              ) : (
                <Select
                  value={docType}
                  options={docTypes}
                  onChange={(e) => setDocType(e.target.value)}
                  aria-label="Document type"
                />
              )}
            </div>
            <Button size="sm" disabled={uploading} onClick={() => input.current?.click()}>
              {copy.pick}
            </Button>
          </div>
          <input
            ref={input}
            type="file"
            multiple
            hidden
            accept={ACCEPT[kind]}
            onChange={(e) => void handleFiles(e.target.files)}
          />
        </div>
      )}

      {items.length === 0 ? (
        <p style={{ margin: 0, color: "var(--text-muted)", fontSize: 15 }}>{copy.empty}</p>
      ) : kind === "photos" ? (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(230px,1fr))", gap: 16 }}>
          {items.map((item, index) => (
            <PhotoCard key={item.id} {...itemProps(item, index)} summaryNumber={summaryNumber(item, items, summaryIds)} />
          ))}
        </div>
      ) : (
        <div style={{ display: "grid", gap: 12 }}>
          {items.map((item, index) => (
            <DocumentRow key={item.id} {...itemProps(item, index)} docTypes={docTypes} typeLabel={typeLabel(item.doc_type)} />
          ))}
        </div>
      )}

      <Dialog
        open={removing !== null}
        title={`Remove this ${copy.noun}?`}
        subtitle="It will no longer appear on the job or in the report. The change is recorded in the job's history."
        onClose={() => setRemoving(null)}
        actions={
          <>
            <Button variant="outline" onClick={() => setRemoving(null)}>
              Cancel
            </Button>
            <Button disabled={removeBusy} onClick={() => void confirmRemove()}>
              {removeBusy ? "Removing…" : "Remove"}
            </Button>
          </>
        }
      >
        {removing && <div style={{ fontSize: 14, color: "var(--text-secondary)" }}>{removing.original_name}</div>}
      </Dialog>
    </div>
  );
}

function summaryNumber(item: MediaItem, items: MediaItem[], summaryIds: Set<number>): number | null {
  if (!summaryIds.has(item.id)) return null;
  return items.filter((p) => summaryIds.has(p.id)).findIndex((p) => p.id === item.id) + 1;
}

type RowProps = {
  item: MediaItem;
  index: number;
  count: number;
  canEdit: boolean;
  onMove: (delta: -1 | 1) => void;
  onChange: (changes: Record<string, unknown>) => Promise<void>;
  onRemove: () => void;
};

/** A caption box that saves when the user leaves it, and follows the server
 * when the saved version changes underneath it. */
function useDraft(item: MediaItem) {
  const [draft, setDraft] = useState(item.caption);
  const [seen, setSeen] = useState(item.edit_version);
  if (seen !== item.edit_version) {
    setSeen(item.edit_version);
    setDraft(item.caption);
  }
  return [draft, setDraft] as const;
}

const iconButton = {
  border: "1px solid var(--border-default)",
  background: "#fff",
  borderRadius: 6,
  width: 32,
  height: 32,
  display: "grid",
  placeItems: "center",
  cursor: "pointer",
  padding: 0,
} as const;

function PhotoCard({ item, index, count, canEdit, onMove, onChange, onRemove, summaryNumber }: RowProps & { summaryNumber: number | null }) {
  const [caption, setCaption] = useDraft(item);
  const saveCaption = () => {
    if (caption.trim() !== item.caption) void onChange({ caption });
  };
  const slotLabel = SLOTS.find((s) => s.value === item.slot)?.label;

  return (
    <div className="card" style={{ padding: 0, overflow: "hidden", opacity: item.include_in_report ? 1 : 0.65 }}>
      <a href={apiUrl(item.url)} target="_blank" rel="noopener noreferrer" title="Open full size" style={{ display: "block", position: "relative" }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={apiUrl(item.thumb_url)}
          alt={item.caption || item.original_name}
          loading="lazy"
          style={{ display: "block", width: "100%", aspectRatio: "4 / 3", objectFit: "cover", background: "var(--surface-subtle)" }}
        />
        <span style={badge("rgba(0,0,0,0.6)", { left: 8 })}>{index + 1}</span>
        {summaryNumber && <span style={badge("var(--action-primary)", { right: 8 })}>Summary photo {summaryNumber}</span>}
        {item.slot !== "general" && !summaryNumber && <span style={badge("var(--blue-600)", { right: 8 })}>{slotLabel}</span>}
      </a>
      <div style={{ padding: 12, display: "grid", gap: 8 }}>
        <Input
          value={caption}
          placeholder="Caption"
          maxLength={255}
          disabled={!canEdit}
          onChange={(e) => setCaption(e.target.value)}
          onBlur={saveCaption}
          onKeyDown={(e) => e.key === "Enter" && (e.currentTarget as HTMLInputElement).blur()}
          style={{ height: 36, fontSize: 14 }}
        />
        {canEdit && (
          <Select
            value={item.slot ?? "general"}
            options={SLOTS}
            onChange={(e) => void onChange({ slot: e.target.value })}
            aria-label="Photograph type"
            style={{ fontSize: 14 }}
          />
        )}
        <label className="row" style={{ gap: 8, fontSize: 13, color: "var(--text-secondary)" }}>
          <input
            type="checkbox"
            checked={item.include_in_report}
            disabled={!canEdit}
            onChange={(e) => void onChange({ include_in_report: e.target.checked })}
          />
          Include in report
        </label>
        <div className="row" style={{ justifyContent: "space-between" }}>
          <span style={{ fontSize: 12, color: "var(--text-muted)" }} title={item.original_name}>
            {sizeText(item.size_bytes)}
            {item.width && item.height ? ` · ${item.width}×${item.height}` : ""}
          </span>
          {canEdit && (
            <div className="row" style={{ gap: 6 }}>
              <button type="button" aria-label="Move earlier" title="Move earlier" disabled={index === 0} onClick={() => onMove(-1)} style={{ ...iconButton, opacity: index === 0 ? 0.4 : 1 }}>
                <Icon name="arrow-left" size={16} />
              </button>
              <button type="button" aria-label="Move later" title="Move later" disabled={index === count - 1} onClick={() => onMove(1)} style={{ ...iconButton, opacity: index === count - 1 ? 0.4 : 1 }}>
                <Icon name="arrow-right" size={16} />
              </button>
              <button type="button" aria-label="Remove" title="Remove" onClick={onRemove} style={iconButton}>
                <Icon name="trash-2" size={16} color="var(--text-error)" />
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function badge(background: string, side: { left?: number; right?: number }): React.CSSProperties {
  return {
    position: "absolute",
    top: 8,
    ...side,
    background,
    color: "#fff",
    fontSize: 12,
    lineHeight: "20px",
    padding: "0 8px",
    borderRadius: 10,
  };
}

function DocumentRow({
  item,
  index,
  count,
  canEdit,
  onMove,
  onChange,
  onRemove,
  docTypes,
  typeLabel,
}: RowProps & { docTypes: { value: string; label: string }[]; typeLabel: string }) {
  const [caption, setCaption] = useDraft(item);
  const saveCaption = () => {
    if (caption.trim() !== item.caption) void onChange({ caption });
  };

  return (
    <div className="card row" style={{ gap: 16, padding: 12, alignItems: "flex-start", opacity: item.include_in_report ? 1 : 0.65 }}>
      <a href={apiUrl(item.url)} target="_blank" rel="noopener noreferrer" title="Open" style={{ flexShrink: 0 }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={apiUrl(item.thumb_url)}
          alt={typeLabel}
          loading="lazy"
          style={{ display: "block", width: 84, height: 112, objectFit: "cover", borderRadius: 6, border: "1px solid var(--border-default)", background: "var(--surface-subtle)" }}
        />
      </a>
      <div style={{ flex: 1, minWidth: 0, display: "grid", gap: 8 }}>
        <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
          <span style={{ fontSize: 13, color: "var(--text-muted)" }}>{index + 1}</span>
          <div style={{ width: 220 }}>
            {canEdit ? (
              <Select
                value={item.doc_type ?? "other"}
                options={docTypes}
                onChange={(e) => void onChange({ doc_type: e.target.value })}
                aria-label="Document type"
                style={{ fontSize: 14 }}
              />
            ) : (
              <b style={{ fontWeight: 500 }}>{typeLabel}</b>
            )}
          </div>
        </div>
        <Input
          value={caption}
          placeholder="Caption (optional)"
          maxLength={255}
          disabled={!canEdit}
          onChange={(e) => setCaption(e.target.value)}
          onBlur={saveCaption}
          onKeyDown={(e) => e.key === "Enter" && (e.currentTarget as HTMLInputElement).blur()}
          style={{ height: 36, fontSize: 14 }}
        />
        <div className="row" style={{ justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
          <label className="row" style={{ gap: 8, fontSize: 13, color: "var(--text-secondary)" }}>
            <input
              type="checkbox"
              checked={item.include_in_report}
              disabled={!canEdit}
              onChange={(e) => void onChange({ include_in_report: e.target.checked })}
            />
            Include in report
          </label>
          <span style={{ fontSize: 12, color: "var(--text-muted)" }} title={item.original_name}>
            {item.original_name} · {item.is_pdf ? `PDF, ${item.page_count} page${item.page_count === 1 ? "" : "s"}` : "Image"} ·{" "}
            {sizeText(item.size_bytes)}
          </span>
        </div>
      </div>
      {canEdit && (
        <div className="row" style={{ gap: 6, flexShrink: 0 }}>
          <button type="button" aria-label="Move up" title="Move up" disabled={index === 0} onClick={() => onMove(-1)} style={{ ...iconButton, opacity: index === 0 ? 0.4 : 1 }}>
            <Icon name="arrow-up" size={16} />
          </button>
          <button type="button" aria-label="Move down" title="Move down" disabled={index === count - 1} onClick={() => onMove(1)} style={{ ...iconButton, opacity: index === count - 1 ? 0.4 : 1 }}>
            <Icon name="arrow-down" size={16} />
          </button>
          <button type="button" aria-label="Remove" title="Remove" onClick={onRemove} style={iconButton}>
            <Icon name="trash-2" size={16} color="var(--text-error)" />
          </button>
        </div>
      )}
    </div>
  );
}
