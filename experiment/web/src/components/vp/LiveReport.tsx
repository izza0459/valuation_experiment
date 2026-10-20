"use client";

/**
 * The report filling in beside the form (web only): the same HTML preview as
 * "Preview report", reloaded quietly after each save and scrolled to the
 * section the open tab feeds.
 *
 * Two frames take turns: the next version loads in the hidden one and is
 * swapped in once it has finished, so the page never flashes blank while
 * someone types. The preview runs no scripts (it is sandboxed), so the
 * section is chosen with the URL's #anchor.
 */

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Icon } from "@/design-system";
import { apiUrl } from "@/lib/api";

/** Which report section each tab's answers appear in. */
const SECTION_FOR_TAB: Record<string, string> = {
  instructions: "s-cover",
  address: "s-summary",
  checklist: "s-diligence",
  summary: "s-terms",
  inspection: "s-property",
  location: "s-property",
  valuation: "s-opinion",
  evidence: "s-methodology",
  photos: "s-photos",
  documents: "s-documents",
};

/** How long after the last change the report reloads. */
const SETTLE_MS = 700;

export function LiveReport({
  jobId,
  tabKey,
  signature,
  onClose,
}: {
  jobId: string;
  /** The open tab, to scroll the report to what it fills. */
  tabKey: string;
  /** Changes whenever anything that prints may have changed. */
  signature: string;
  onClose: () => void;
}) {
  const base = apiUrl(`/api/jobs/${jobId}/report/preview/`);
  const anchor = SECTION_FOR_TAB[tabKey] ?? "s-cover";

  // Which reload each frame shows (null: not used yet) and which is in front.
  // The #anchor is added at render, so changing tab just scrolls the report.
  const [frames, setFrames] = useState<[number, number | null]>([0, null]);
  const [front, setFront] = useState<0 | 1>(0);
  const [updating, setUpdating] = useState(false);
  const frontRef = useRef<0 | 1>(0);
  const reloads = useRef(0);
  const seen = useRef(signature);

  // Something that prints changed: once typing settles, load the new version
  // in the hidden frame; it comes to the front when it has loaded.
  useEffect(() => {
    if (seen.current === signature) return;
    seen.current = signature;
    const timer = setTimeout(() => {
      reloads.current += 1;
      const back = frontRef.current === 0 ? 1 : 0;
      setUpdating(true);
      setFrames((f) => {
        const next: [number, number | null] = [f[0], f[1]];
        next[back] = reloads.current;
        return next;
      });
    }, SETTLE_MS);
    return () => clearTimeout(timer);
  }, [signature]);

  const srcOf = (i: 0 | 1) => (frames[i] === null ? "" : `${base}?r=${frames[i]}#${anchor}`);
  const onLoad = (i: 0 | 1) => {
    if (i !== frontRef.current && frames[i] !== null) {
      frontRef.current = i;
      setFront(i);
      setUpdating(false);
    }
  };

  return (
    <aside className="card livereport" aria-label="Live report">
      <div className="row livereport-head">
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 15, fontWeight: 700 }}>Report</div>
          <div style={{ fontSize: 12, color: updating ? "var(--text-accent)" : "var(--text-muted)" }}>
            {updating ? "Updating…" : "Fills in as you save each field"}
          </div>
        </div>
        <div className="row" style={{ gap: 4 }}>
          <Link
            href={`/jobs/${jobId}/report`}
            className="livereport-btn"
            title="Open the full report"
            aria-label="Open the full report"
          >
            <Icon name="maximize-2" size={16} />
          </Link>
          <button type="button" className="livereport-btn" onClick={onClose} title="Hide the report" aria-label="Hide the report">
            <Icon name="x" size={16} />
          </button>
        </div>
      </div>
      <div className="livereport-frames">
        {([0, 1] as const).map((i) =>
          srcOf(i) ? (
            <iframe
              key={i}
              title={i === front ? "Report preview" : "Report preview (loading)"}
              src={srcOf(i)}
              onLoad={() => onLoad(i)}
              aria-hidden={i !== front}
              tabIndex={i === front ? 0 : -1}
              style={{ visibility: i === front ? "visible" : "hidden" }}
            />
          ) : null,
        )}
      </div>
    </aside>
  );
}
