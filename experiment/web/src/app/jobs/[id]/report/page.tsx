import { ReportPreviewClient } from "./ReportPreviewClient";

export default async function ReportPreviewPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ReportPreviewClient id={id} />;
}
