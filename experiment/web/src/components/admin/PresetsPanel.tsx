"use client";

import { useState } from "react";
import { Button, Icon, Input, Table, Tag, Textarea } from "@/design-system";
import { F, Toggle } from "@/components/vp/ui";
import { Tip } from "@/components/vp/ui";
import { flattenErrors, useAdminList, useAdminSave } from "@/lib/admin";
import { Empty, FormDialog, Grid, muted } from "./parts";

type Key = { key: string; label: string; tab: string; count: number };
type Option = { id: number; field_key: string; value: string; label: string; report_text: string; order: number; active: boolean; group: string };

export function PresetsPanel() {
  const { data: keys } = useAdminList<Key>("preset-keys/");
  const [selected, setSelected] = useState<string | null>(null);
  const current = selected ?? keys?.[0]?.key ?? null;

  const { data: options, isLoading } = useAdminList<Option>(current ? `presets/?field_key=${current}` : "presets/?field_key=__none__");
  const save = useAdminSave("presets");
  const [editing, setEditing] = useState<Option | "new" | null>(null);
  const [form, setForm] = useState({ label: "", report_text: "", order: "0", active: true, group: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});

  function open(option: Option | "new") {
    setEditing(option);
    setErrors({});
    setForm(option === "new"
      ? { label: "", report_text: "", order: String((options?.length ?? 0) + 1), active: true, group: "" }
      : { label: option.label, report_text: option.report_text, order: String(option.order), active: option.active, group: option.group ?? "" });
  }

  async function submit() {
    const body = { ...form, order: Number(form.order) || 0, ...(editing === "new" ? { field_key: current } : {}) };
    try {
      await save.mutateAsync({ id: editing === "new" ? undefined : (editing as Option).id, body });
      setEditing(null);
    } catch (err) {
      setErrors(flattenErrors(err));
    }
  }

  const label = keys?.find((k) => k.key === current)?.label ?? "";

  return (
    <div className="card" style={{ display: "flex", gap: 24, alignItems: "flex-start" }}>
      <nav style={{ width: 240, flexShrink: 0, display: "grid", gap: 2, maxHeight: 560, overflowY: "auto" }}>
        {keys?.map((k) => (
          <button
            key={k.key}
            type="button"
            onClick={() => setSelected(k.key)}
            className={"nav" + (k.key === current ? " on" : "")}
            style={{ border: 0, background: undefined, cursor: "pointer", fontFamily: "inherit", justifyContent: "space-between", textAlign: "left", height: "auto", padding: "8px 12px" }}
          >
            <span>
              <span style={{ display: "block" }}>{k.label}</span>
              <span style={{ ...muted, fontSize: 12 }}>{k.tab}</span>
            </span>
            <span style={muted}>{k.count}</span>
          </button>
        ))}
      </nav>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="row" style={{ justifyContent: "space-between", marginBottom: 14 }}>
          <Tip text={`Options in the “${label}” dropdown. Deactivate an option to hide it; jobs that already use it keep their label.`} />
          <Button size="sm" icon={<Icon name="plus" size={16} />} onClick={() => open("new")} disabled={!current}>
            Add option
          </Button>
        </div>
        {isLoading ? (
          <div className="skel" style={{ height: 160 }} />
        ) : !options?.length ? (
          <Empty>No options yet for this dropdown. Until there are some, the field accepts any value.</Empty>
        ) : (
          <Table
            rows={options}
            columns={[
              { key: "order", label: "#", render: (o: Option) => <span className="num">{o.order}</span> },
              { key: "label", label: "Label", render: (o: Option) => <span>{o.label}</span> },
              { key: "value", label: "Stored as", render: (o: Option) => <code style={{ fontSize: 12, color: "var(--text-muted)" }}>{o.value}</code> },
              { key: "active", label: "Status", render: (o: Option) => <Tag tone={o.active ? "green" : "neutral"}>{o.active ? "Active" : "Inactive"}</Tag> },
              { key: "edit", label: "", align: "right", render: (o: Option) => <Button size="sm" variant="outline" onClick={() => open(o)}>Edit</Button> },
            ]}
          />
        )}
      </div>

      <FormDialog
        open={editing !== null}
        title={editing === "new" ? `Add to “${label}”` : "Edit option"}
        subtitle={editing !== "new" ? "The stored value stays the same when you rename the label." : undefined}
        busy={save.isPending}
        error={errors._form ?? errors.field_key}
        onClose={() => setEditing(null)}
        onSave={() => void submit()}
      >
        <Grid>
          <F label="Label" error={errors.label}>
            <Input invalid={Boolean(errors.label)} value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} />
          </F>
          <F label="Order" error={errors.order}>
            <Input inputMode="numeric" value={form.order} onChange={(e) => setForm({ ...form, order: e.target.value })} />
          </F>
          <F label="Group" span={2} helper="Heading this option is listed under, such as Residential or Commercial. Leave blank for none." error={errors.group}>
            <Input value={form.group} onChange={(e) => setForm({ ...form, group: e.target.value })} />
          </F>
          <F label="Report text" span={2} helper="Optional paragraph this option can insert into the report." error={errors.report_text}>
            <Textarea rows={4} value={form.report_text} onChange={(e) => setForm({ ...form, report_text: e.target.value })} />
          </F>
          <F label="Status" span={2}>
            <Toggle on={form.active} onChange={(v) => setForm({ ...form, active: v })} label={form.active ? "Active" : "Inactive: hidden from forms"} />
          </F>
        </Grid>
      </FormDialog>
    </div>
  );
}
