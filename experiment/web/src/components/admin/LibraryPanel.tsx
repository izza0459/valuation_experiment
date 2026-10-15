"use client";

import { useState } from "react";
import { Button, Icon, Input, Select, Table, Tag, Textarea } from "@/design-system";
import { F, Toggle } from "@/components/vp/ui";
import { flattenErrors, useAdminList, useAdminSave } from "@/lib/admin";
import { Empty, FormDialog, Grid, muted } from "./parts";

type Item = { id: number; category: string; title: string; body: string; order: number; active: boolean };

/** Mirrors backend TextLibraryCategory. */
const CATEGORIES = [
  { value: "assumption", label: "Assumptions" },
  { value: "special_assumption", label: "Special assumptions" },
  { value: "other_matter", label: "Other matters" },
  { value: "condition", label: "Property condition" },
  { value: "specification", label: "Property specification" },
  { value: "commentary", label: "Market / valuation commentary" },
];

const PLACEHOLDER = "[PLACEHOLDER";

export function LibraryPanel() {
  const [category, setCategory] = useState(CATEGORIES[0].value);
  const { data: items, isLoading } = useAdminList<Item>(`library/?category=${category}`);
  const save = useAdminSave("library");
  const [editing, setEditing] = useState<Item | "new" | null>(null);
  const [form, setForm] = useState({ category, title: "", body: "", order: "0", active: true });
  const [errors, setErrors] = useState<Record<string, string>>({});

  function open(item: Item | "new") {
    setEditing(item);
    setErrors({});
    setForm(item === "new"
      ? { category, title: "", body: "", order: String((items?.length ?? 0) + 1), active: true }
      : { category: item.category, title: item.title, body: item.body, order: String(item.order), active: item.active });
  }

  async function submit() {
    try {
      await save.mutateAsync({ id: editing === "new" ? undefined : (editing as Item).id, body: { ...form, order: Number(form.order) || 0 } });
      setEditing(null);
    } catch (err) {
      setErrors(flattenErrors(err));
    }
  }

  return (
    <div className="card">
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 14, gap: 16 }}>
        <div className="row" style={{ gap: 12 }}>
          <div style={{ width: 280 }}>
            <Select value={category} options={CATEGORIES} onChange={(e) => setCategory(e.target.value)} />
          </div>
          <span style={muted}>Text the valuer inserts into a job, then edits for that job only.</span>
        </div>
        <Button size="sm" icon={<Icon name="plus" size={16} />} onClick={() => open("new")}>
          Add entry
        </Button>
      </div>

      {isLoading ? (
        <div className="skel" style={{ height: 160 }} />
      ) : !items?.length ? (
        <Empty>No entries in this library yet.</Empty>
      ) : (
        <Table
          rows={items}
          columns={[
            { key: "title", label: "Title", render: (i: Item) => <span>{i.title}</span> },
            { key: "body", label: "Text", render: (i: Item) => (
              <span style={{ fontSize: 14, color: "var(--text-secondary)" }}>
                {i.body.length > 110 ? i.body.slice(0, 110) + "…" : i.body}
                {i.body.includes(PLACEHOLDER) && <> <Tag tone="amber">Placeholder</Tag></>}
              </span>
            ) },
            { key: "active", label: "Status", render: (i: Item) => <Tag tone={i.active ? "green" : "neutral"}>{i.active ? "Active" : "Inactive"}</Tag> },
            { key: "edit", label: "", align: "right", render: (i: Item) => <Button size="sm" variant="outline" onClick={() => open(i)}>Edit</Button> },
          ]}
        />
      )}

      <FormDialog
        open={editing !== null}
        title={editing === "new" ? "Add entry" : "Edit entry"}
        subtitle="Entries marked Placeholder must be replaced with approved wording before a report can be issued."
        busy={save.isPending}
        error={errors._form}
        onClose={() => setEditing(null)}
        onSave={() => void submit()}
      >
        <Grid>
          <F label="Library" error={errors.category}>
            <Select value={form.category} options={CATEGORIES} onChange={(e) => setForm({ ...form, category: e.target.value })} />
          </F>
          <F label="Order" error={errors.order}>
            <Input inputMode="numeric" value={form.order} onChange={(e) => setForm({ ...form, order: e.target.value })} />
          </F>
          <F label="Title" span={2} error={errors.title}>
            <Input invalid={Boolean(errors.title)} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
          </F>
          <F label="Text" span={2} error={errors.body}>
            <Textarea rows={9} invalid={Boolean(errors.body)} value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} />
          </F>
          <F label="Status" span={2}>
            <Toggle on={form.active} onChange={(v) => setForm({ ...form, active: v })} label={form.active ? "Active" : "Inactive: hidden from the picker"} />
          </F>
        </Grid>
      </FormDialog>
    </div>
  );
}
