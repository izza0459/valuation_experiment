"use client";

/**
 * "Preview report" (design brief S5): the report as HTML straight from the
 * live job, for checking wording at any point. It opens on its own page in
 * the app, with a Back button. There is no draft PDF: the PDF is produced
 * once, when the peer reviewer signs off, and is downloaded from the Send to
 * bank stage.
 */

import Link from "next/link";
import { Button, Icon } from "@/design-system";

export function ReportActions({ jobId }: { jobId: string }) {
  return (
    <Link href={`/jobs/${jobId}/report`} prefetch style={{ textDecoration: "none" }}>
      <Button variant="outline" size="sm" icon={<Icon name="eye" size={16} />}>
        Preview report
      </Button>
    </Link>
  );
}
