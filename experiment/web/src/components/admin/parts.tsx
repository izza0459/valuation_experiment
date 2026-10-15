"use client";

import { Button, Dialog } from "@/design-system";
import { Banner } from "@/components/vp/ui";

/** Modal form shell shared by the Admin panels: title, scrollable body, a
 * form-level error banner, Cancel and Save. */
export function FormDialog({
  title,
  subtitle,
  open,
  busy,
  error,
  saveLabel = "Save",
  onClose,
  onSave,
  children,
}: {
  title: string;
  subtitle?: string;
  open: boolean;
  busy: boolean;
  error?: string;
  saveLabel?: string;
  onClose: () => void;
  onSave: () => void;
  children: React.ReactNode;
}) {
  return (
    <Dialog
      open={open}
      title={title}
      subtitle={subtitle}
      onClose={onClose}
      width={680}
      actions={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={busy} onClick={onSave}>
            {busy ? "Saving…" : saveLabel}
          </Button>
        </>
      }
    >
      <div style={{ maxHeight: "62vh", overflowY: "auto", padding: 2 }}>
        {error && (
          <Banner tone="red" icon="alert-circle">
            {error}
          </Banner>
        )}
        {children}
      </div>
    </Dialog>
  );
}

export const Grid = ({ children, cols = 2 }: { children: React.ReactNode; cols?: number }) => (
  <div style={{ display: "grid", gridTemplateColumns: `repeat(${cols},minmax(0,1fr))`, gap: "16px 20px" }}>{children}</div>
);

export const Empty = ({ children }: { children: React.ReactNode }) => (
  <div style={{ textAlign: "center", padding: "36px 12px", color: "var(--text-muted)", fontSize: 15 }}>{children}</div>
);

export const muted: React.CSSProperties = { color: "var(--text-muted)", fontSize: 13 };
