"use client";

/**
 * "Preview report" (design brief S5): the report as HTML straight from the
 * live job, for checking wording at any point. There is no draft PDF: the PDF
 * is produced once, when the peer reviewer signs off, and is downloaded from
 * the Send to bank stage.
 */

import { Button, Icon } from "@/design-system";
import { apiUrl } from "@/lib/api";

export function ReportActions({ jobId }: { jobId: string }) {
  return (
    <Button
      variant="outline"
      size="sm"
      icon={<Icon name="eye" size={16} />}
      onClick={() => window.open(apiUrl(`/api/jobs/${jobId}/report/preview/`), "_blank", "noopener")}
    >
      Preview report
    </Button>
  );
}
