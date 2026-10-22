"use client";

import { useState } from "react";
import { Button, Icon, Input, Select, Table, Tag, Textarea } from "@/design-system";
import { Chip, F, Toggle } from "@/components/vp/ui";
import { useOptions } from "@/lib/options";
import { flattenErrors, useAdminDelete, useAdminList, useAdminSave } from "@/lib/admin";
import { Empty, FormDialog, Grid, muted } from "./parts";

type Item = {
  id: number;
  category: string;
  title: string;
  body: string;
  order: number;
  active: boolean;
  /** Property types it is offered for; empty: all of them. */
  property_categories: string[];
};

/** The libraries in use (backend TextLibraryCategory, without the retired
 * "Other matters" and combined commentary). */
const CATEGORIES = [
  { value: "assumption", label: "Assumptions" },
  { value: "special_assumption", label: "Special assumptions" },
  { value: "condition", label: "Property condition" },
  { value: "specification", label: "Property specification" },
  { value: "market_commentary", label: "Market commentary" },
  { value: "valuation_commentary", label: "Valuation commentary" },
  { value: "reinstatement", label: "Reinstatement cost" },
  { value: "special_note", label: "Special note" },
];

const PLACEHOLDER = "[PLACEHOLDER";

export function LibraryPanel() {
  const [category, setCategory] = useState(CATEGORIES[0].value);
  const { data: items, isLoading } = useAdminList<Item>(`library/?category=${category}`);
  const save = useAdminSave("library");
  const remove = useAdminDelete("library");
  const [editing, setEditing] = useState<Item | "new" | null>(null);
  // Deleting asks once more in the same spot before it goes.
  const [confirming, setConfirming] = useState(false);
  const [form, setForm] = useState({ category, title: "", body: "", order: "0", active: true, property_categories: [] as string[] });
  const { data: options } = useOptions();
  const types = (options?.property_category ?? []).map((o) => ({ value: String(o.value), label: o.label }));
  const typeLabel = (v: string) => types.find((t) => t.value === v)?.label ?? v;
  const [errors, setErrors] = useState<Record<string, string>>({});

  function open(item: Item | "new") {
    setEditing(item);
    setErrors({});
    setConfirming(false);
    setForm(item === "new"
      ? { category, title: "", body: "", order: String((items?.length ?? 0) + 1), active: true, property_categories: [] }
      : { category: item.category, title: item.title, body: item.body, order: String(item.order), active: item.active,
          property_categories: item.property_categories ?? [] });
  }

  async function submit() {
    try {
      await save.mutateAsync({ id: editing === "new" ? undefined : (editing as Item).id, body: { ...form, order: Number(form.order) || 0 } });
      setEditing(null);
    } catch (err) {
      setErrors(flattenErrors(err));
    }
  }

  async function destroy() {
    if (editing === null || editing === "new") return;
    try {
      await remove.mutateAsync(editing.id);
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
            { key: "for", label: "Offered for", render: (i: Item) => (
              <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>
                {i.property_categories?.length ? i.property_categories.map(typeLabel).join(", ") : "All property types"}
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
        subtitle="Jobs keep their own copy of the text: editing or deleting an entry doesn't change them."
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
          <F label="Offered for" span={2} helper="Leave all unticked to offer it for every property type.">
            <div className="row wrap" style={{ gap: 6 }}>
              {types.map((t) => {
                const on = form.property_categories.includes(t.value);
                return (
                  <Chip key={t.value} on={on} onClick={() => setForm({ ...form,
                    property_categories: on ? form.property_categories.filter((v) => v !== t.value) : [...form.property_categories, t.value] })}>
                    {t.label}
                  </Chip>
                );
              })}
            </div>
          </F>
          <F label="Status" span={2}>
            <Toggle on={form.active} onChange={(v) => setForm({ ...form, active: v })} label={form.active ? "Active" : "Inactive: hidden from the picker"} />
          </F>
          {editing !== null && editing !== "new" && (
            <F label="Delete" span={2} helper="Removes the entry from the library for good. Jobs that used it keep their text.">
              <div className="row wrap" style={{ gap: 8 }}>
                {confirming ? (
                  <>
                    <Button size="sm" variant="danger" disabled={remove.isPending} onClick={() => void destroy()}>
                      {remove.isPending ? "Deleting…" : `Yes, delete “${editing.title}”`}
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => setConfirming(false)}>Keep it</Button>
                  </>
                ) : (
                  <Button size="sm" variant="danger" icon={<Icon name="trash-2" size={16} />} onClick={() => setConfirming(true)}>
                    Delete entry
                  </Button>
                )}
              </div>
            </F>
          )}
        </Grid>
      </FormDialog>
    </div>
  );
}
