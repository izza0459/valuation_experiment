"use client";

import { Table, Tag } from "@/design-system";
import { Toggle } from "@/components/vp/ui";
import { formatDate } from "@/components/vp/format";
import { useAdminList, useAdminSave } from "@/lib/admin";
import { Empty, muted } from "./parts";

type Template = {
  id: number; name: string; version: string; bank_name: string; active: boolean; created_at: string; reports_count: number;
};

export function TemplatesPanel() {
  const { data: templates, isLoading } = useAdminList<Template>("templates/");
  const save = useAdminSave("templates");

  return (
    <div className="card">
      <div style={{ ...muted, marginBottom: 14 }}>
        Report template versions. The default template ships with the app and gets a new version whenever it changes;
        a version a report was generated from is never altered. Edit or add templates in the Django admin. Switch one
        off here to stop new reports using it.
      </div>
      {isLoading ? (
        <div className="skel" style={{ height: 120 }} />
      ) : !templates?.length ? (
        <Empty>No templates yet. One is created the first time a report is generated.</Empty>
      ) : (
        <Table
          rows={templates}
          columns={[
            { key: "name", label: "Template", render: (t: Template) => <span>{t.name}</span> },
            { key: "version", label: "Version", render: (t: Template) => <code style={{ fontSize: 12 }}>{t.version}</code> },
            { key: "bank", label: "Bank", render: (t: Template) => (t.bank_name ? <span>{t.bank_name}</span> : <Tag tone="neutral">All banks</Tag>) },
            { key: "created", label: "Created", render: (t: Template) => <span>{formatDate(t.created_at)}</span> },
            { key: "reports", label: "Reports", align: "right", render: (t: Template) => <span className="num">{t.reports_count}</span> },
            { key: "active", label: "Active", align: "right", render: (t: Template) => (
              <Toggle on={t.active} onChange={(v) => save.mutate({ id: t.id, body: { active: v } })} />
            ) },
          ]}
        />
      )}
    </div>
  );
}
