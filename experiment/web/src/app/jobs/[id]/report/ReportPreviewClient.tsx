"use client";

/**
 * The report preview inside the app, with a way back to the job. (Opening it
 * in a new window left the phone app with no way back.) The report itself is
 * the API's HTML preview in a frame; it fits the screen width on phones.
 */

import { useState } from "react";
import Link from "next/link";
import { Button, Icon } from "@/design-system";
import { Shell } from "@/components/vp/ui";
import { apiUrl } from "@/lib/api";

export function ReportPreviewClient({ id }: { id: string }) {
  const [loaded, setLoaded] = useState(false);
  const [nonce, setNonce] = useState(0);
  const src = apiUrl(`/api/jobs/${id}/report/preview/`);

  return (
    <Shell>
      <div className="row reportbar" style={{ justifyContent: "space-between", gap: 10, marginBottom: 12 }}>
        <Link href={`/jobs/${id}`} style={{ textDecoration: "none" }}>
          <Button variant="outline" size="sm" icon={<Icon name="chevron-left" size={16} />}>
            Back to job
          </Button>
        </Link>
        <div className="row" style={{ gap: 8 }}>
          <Button
            variant="outline"
            size="sm"
            icon={<Icon name="refresh-cw" size={16} />}
            onClick={() => {
              setLoaded(false);
              setNonce((n) => n + 1);
            }}
          >
            Refresh
          </Button>
          <a href={src} target="_blank" rel="noopener" className="hide-app" style={{ textDecoration: "none" }}>
            <Button variant="outline" size="sm" icon={<Icon name="external-link" size={16} />}>
              New window
            </Button>
          </a>
        </div>
      </div>
      <div className="reportframe" style={{ position: "relative" }}>
        {!loaded && (
          <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", color: "var(--text-muted)", fontSize: 14 }}>
            Putting the report together…
          </div>
        )}
        <iframe
          key={nonce}
          title="Report preview"
          src={src}
          onLoad={() => setLoaded(true)}
          style={{
            display: "block",
            width: "100%",
            height: "calc(100vh - 170px)",
            minHeight: 480,
            border: "1px solid var(--border-subtle)",
            borderRadius: 10,
            background: "#fff",
          }}
        />
      </div>
    </Shell>
  );
}
