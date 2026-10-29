"use client";

/** The emails reports go to banks with. A bank's own template wins; banks
 * without one get the default. Merge fields in braces fill in per job. */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, Icon, Input, Select, Tag, Textarea } from "@/design-system";
import { F, Tip, Toggle } from "@/components/vp/ui";
import { apiFetch } from "@/lib/api";
import { flattenErrors, useAdminList, useAdminSave } from "@/lib/admin";
import { Empty, FormDialog, Grid, muted } from "./parts";

type Template = {
  id: number;
  name: string;
  bank: number | null;
  bank_name: string;
  subject: string;
  body: string;
  is_default: boolean;
  active: boolean;
  updated_at: string;
};

const BLANK = { name: "", bank: "", subject: "", body: "", is_default: false, active: true };

export function EmailTemplatesPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ["admin", "email-templates/"],
    queryFn: () => apiFetch<{ results: Template[]; merge_fields: Record<string, string> }>("/api/admin/email-templates/"),
  });
  const { data: banks } = useAdminList<{ id: number; name: string }>("banks/");
  const save = useAdminSave("email-templates");
  const [editing, setEditing] = useState<Template | "new" | null>(null);
  const [form, setForm] = useState(BLANK);
  const [errors, setErrors] = useState<Record<string, string>>({});

  function open(t: Template | "new") {
    setEditing(t);
    setErrors({});
    setForm(t === "new" ? BLANK : { ...t, bank: t.bank ? String(t.bank) : "" });
  }

  async function submit() {
    try {
      await save.mutateAsync({
        id: editing === "new" ? undefined : (editing as Template).id,
        body: { ...form, bank: form.bank ? Number(form.bank) : null },
      });
      setEditing(null);
    } catch (err) {
      setErrors(flattenErrors(err));
    }
  }

  const fields = data?.merge_fields ?? {};
  const insert = (key: string) => setForm((f) => ({ ...f, body: `${f.body}{${key}}` }));

  return (
    <div className="card">
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 14, gap: 10 }}>
        <div className="row" style={{ gap: 6, fontSize: 16, fontWeight: 500 }}>
          Email templates
          <Tip text="The email an issued report is sent with. A bank's own template wins; other banks get the default. The sender can still edit it before sending." />
        </div>
        <Button size="sm" icon={<Icon name="plus" size={16} />} onClick={() => open("new")}>
          Add template
        </Button>
      </div>

      {isLoading ? (
        <div className="skel" style={{ height: 160 }} />
      ) : !data?.results.length ? (
        <Empty>No email templates yet.</Empty>
      ) : (
        <div style={{ display: "grid", gap: 10 }}>
          {data.results.map((t) => (
            <button key={t.id} type="button" className="admin-item" onClick={() => open(t)}>
              <div style={{ minWidth: 0 }}>
                <div className="row wrap" style={{ gap: 8 }}>
                  <b style={{ fontWeight: 500 }}>{t.name}</b>
                  {t.is_default && <Tag tone="green">Default</Tag>}
                  {t.bank_name && <Tag tone="neutral">{t.bank_name}</Tag>}
                  {!t.active && <Tag tone="neutral">Off</Tag>}
                </div>
                <div style={{ ...muted, marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {t.subject}
                </div>
              </div>
              <Icon name="chevron-right" size={18} color="var(--text-muted)" />
            </button>
          ))}
        </div>
      )}

      <FormDialog
        open={editing !== null}
        title={editing === "new" ? "Add email template" : "Edit email template"}
        busy={save.isPending}
        error={errors._form}
        onClose={() => setEditing(null)}
        onSave={() => void submit()}
      >
        <Grid>
          <F label="Name" error={errors.name}>
            <Input value={form.name} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, name: e.target.value })} />
          </F>
          <F label="Bank" error={errors.bank} helper="Leave empty for a general template.">
            <Select
              value={form.bank}
              placeholder="All banks"
              options={(banks ?? []).map((b) => ({ value: String(b.id), label: b.name }))}
              onChange={(e: React.ChangeEvent<HTMLSelectElement>) =>
                setForm({ ...form, bank: e.target.value, is_default: e.target.value ? false : form.is_default })}
            />
          </F>
          <F label="Subject" span={2} error={errors.subject}>
            <Input value={form.subject} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, subject: e.target.value })} />
          </F>
          <F label="Body" span={2} error={errors.body} helper="Click a merge field below to add it. It fills in from the job when the email is written.">
            <Textarea rows={9} value={form.body} onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setForm({ ...form, body: e.target.value })} />
            <div className="row wrap" style={{ gap: 6, marginTop: 8 }}>
              {Object.entries(fields).map(([key, label]) => (
                <button key={key} type="button" className="merge-chip" title={label} onClick={() => insert(key)}>
                  {`{${key}}`}
                </button>
              ))}
            </div>
          </F>
          <F label="Default" error={errors.is_default} helper="Used for every bank without its own template. Only one can be the default.">
            <Toggle on={form.is_default} onChange={(v) => setForm({ ...form, is_default: v, bank: v ? "" : form.bank })}
              label={form.is_default ? "Default" : "Not the default"} />
          </F>
          <F label="In use" error={errors.active}>
            <Toggle on={form.active} onChange={(v) => setForm({ ...form, active: v })} label={form.active ? "On" : "Off"} />
          </F>
        </Grid>
      </FormDialog>
    </div>
  );
}
