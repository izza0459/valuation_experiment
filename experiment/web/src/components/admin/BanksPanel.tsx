"use client";

import { useState } from "react";
import { Button, Icon, Input, Table, Tag, Textarea } from "@/design-system";
import { F, Toggle } from "@/components/vp/ui";
import { emptyToNull, flattenErrors, useAdminList, useAdminSave } from "@/lib/admin";
import { Empty, FormDialog, Grid, muted } from "./parts";

type Contact = { name: string; email: string; phone: string };
type Bank = {
  id: number;
  name: string;
  code: string;
  billing_address: string;
  po_box: string;
  contacts: Contact[];
  sla_signed: boolean;
  sla_signed_date: string | null;
  rules: Record<string, boolean | number>;
  active: boolean;
};

/** The rules the backend reads (backend/apps/banks/api.py); a rule not listed
 * there would silently do nothing, so the form offers exactly these. */
const RULES: { key: string; label: string; help: string }[] = [
  { key: "requires_service_charge", label: "Service charge", help: "Show the service charge on the Inspection tab and report." },
  { key: "requires_makani_photo", label: "Makani photo required", help: "" },
  { key: "requires_dewa_photo", label: "DEWA photo required", help: "" },
  { key: "requires_exact_age", label: "Exact age required", help: "Print the building's exact age on the report." },
  { key: "requires_forced_sale_value", label: "Forced sale value", help: "Print the forced sale value on the report." },
];

const BLANK: Bank = {
  id: 0, name: "", code: "", billing_address: "", po_box: "", contacts: [], sla_signed: false,
  sla_signed_date: null, rules: {}, active: true,
};

export function BanksPanel() {
  const { data: banks, isLoading } = useAdminList<Bank>("banks/");
  const save = useAdminSave("banks");
  const [editing, setEditing] = useState<Bank | null>(null);
  const [form, setForm] = useState<Bank>(BLANK);
  const [errors, setErrors] = useState<Record<string, string>>({});

  function open(bank: Bank) {
    setEditing(bank);
    setForm({ ...bank, contacts: bank.contacts.map((c) => ({ ...c })), rules: { ...bank.rules } });
    setErrors({});
  }

  async function submit() {
    const rules = { ...form.rules };
    if (rules.forced_sale_discount_pct === undefined || rules.forced_sale_discount_pct === ("" as unknown)) {
      delete rules.forced_sale_discount_pct;
    }
    const body = {
      name: form.name, code: form.code, billing_address: form.billing_address, po_box: form.po_box,
      contacts: form.contacts.filter((c) => c.name || c.email || c.phone),
      sla_signed: form.sla_signed, sla_signed_date: emptyToNull(form.sla_signed_date ?? ""),
      rules, active: form.active,
    };
    try {
      await save.mutateAsync({ id: editing?.id || undefined, body });
      setEditing(null);
    } catch (err) {
      setErrors(flattenErrors(err));
    }
  }

  const setContact = (i: number, patch: Partial<Contact>) =>
    setForm((f) => ({ ...f, contacts: f.contacts.map((c, j) => (j === i ? { ...c, ...patch } : c)) }));

  return (
    <div className="card">
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 14 }}>
        <div style={muted}>Client banks, their contacts and the report rules specific to each.</div>
        <Button size="sm" icon={<Icon name="plus" size={16} />} onClick={() => open(BLANK)}>
          Add bank
        </Button>
      </div>

      {isLoading ? (
        <div className="skel" style={{ height: 160 }} />
      ) : !banks?.length ? (
        <Empty>No banks yet. Add the first client.</Empty>
      ) : (
        <Table
          rows={banks}
          columns={[
            { key: "name", label: "Bank", render: (b: Bank) => <span>{b.name}</span> },
            { key: "sla", label: "SLA", render: (b: Bank) => <Tag tone={b.sla_signed ? "green" : "amber"}>{b.sla_signed ? "Signed" : "Not signed"}</Tag> },
            { key: "rules", label: "Rules", render: (b: Bank) => {
              const on = RULES.filter((r) => b.rules[r.key] === true).map((r) => r.label);
              const pct = b.rules.forced_sale_discount_pct;
              if (typeof pct === "number") on.push(`Forced sale ${pct}%`);
              return on.length ? <span className="row wrap" style={{ gap: 4 }}>{on.map((l) => <Tag key={l} tone="neutral">{l}</Tag>)}</span> : <span style={muted}>None</span>;
            } },
            { key: "active", label: "Status", render: (b: Bank) => <Tag tone={b.active ? "green" : "neutral"}>{b.active ? "Active" : "Inactive"}</Tag> },
            { key: "edit", label: "", align: "right", render: (b: Bank) => <Button size="sm" variant="outline" onClick={() => open(b)}>Edit</Button> },
          ]}
        />
      )}

      <FormDialog
        open={editing !== null}
        title={editing?.id ? "Edit bank" : "Add bank"}
        busy={save.isPending}
        error={errors._form}
        onClose={() => setEditing(null)}
        onSave={() => void submit()}
      >
        <Grid>
          <F label="Name" error={errors.name}>
            <Input invalid={Boolean(errors.name)} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </F>
          <F label="Bank code" error={errors.code} helper="Filled in on a job when this bank is picked.">
            <Input value={form.code ?? ""} onChange={(e) => setForm({ ...form, code: e.target.value })} />
          </F>
          <F label="Billing address" span={2} error={errors.billing_address} helper="Fills into new jobs once the SLA is signed.">
            <Textarea rows={2} value={form.billing_address} onChange={(e) => setForm({ ...form, billing_address: e.target.value })} />
          </F>
          <F label="PO box" error={errors.po_box}>
            <Input value={form.po_box} onChange={(e) => setForm({ ...form, po_box: e.target.value })} />
          </F>
          <F label="SLA" error={errors.sla_signed_date}>
            <div className="row" style={{ gap: 12 }}>
              <Toggle on={form.sla_signed} onChange={(v) => setForm({ ...form, sla_signed: v })} label={form.sla_signed ? "Signed" : "Not signed"} />
              {form.sla_signed && (
                <Input type="date" style={{ width: 170 }} value={form.sla_signed_date ?? ""} onChange={(e) => setForm({ ...form, sla_signed_date: e.target.value })} />
              )}
            </div>
          </F>
        </Grid>

        <h4 style={{ margin: "22px 0 8px", fontSize: 15, fontWeight: 500 }}>Contacts</h4>
        {errors.contacts && <div style={{ color: "var(--text-error)", fontSize: 13, marginBottom: 6 }}>{errors.contacts}</div>}
        {form.contacts.map((c, i) => (
          <div key={i} className="row" style={{ gap: 8, marginBottom: 8 }}>
            <Input placeholder="Name" value={c.name} onChange={(e) => setContact(i, { name: e.target.value })} />
            <Input placeholder="Email" value={c.email} onChange={(e) => setContact(i, { email: e.target.value })} />
            <Input placeholder="Phone" value={c.phone} onChange={(e) => setContact(i, { phone: e.target.value })} />
            <button type="button" aria-label="Remove contact" onClick={() => setForm({ ...form, contacts: form.contacts.filter((_, j) => j !== i) })}
              style={{ border: 0, background: "none", cursor: "pointer", display: "flex", padding: 6 }}>
              <Icon name="x" size={18} />
            </button>
          </div>
        ))}
        <Button size="sm" variant="soft" icon={<Icon name="plus" size={16} />} onClick={() => setForm({ ...form, contacts: [...form.contacts, { name: "", email: "", phone: "" }] })}>
          Add contact
        </Button>

        <h4 style={{ margin: "22px 0 4px", fontSize: 15, fontWeight: 500 }}>Report rules</h4>
        <div style={{ ...muted, marginBottom: 10 }}>Changing a rule applies to this bank&apos;s jobs already in progress.</div>
        {errors.rules && <div style={{ color: "var(--text-error)", fontSize: 13, marginBottom: 6 }}>{errors.rules}</div>}
        <div style={{ display: "grid", gap: 10 }}>
          {RULES.map((r) => (
            <div key={r.key}>
              <Toggle on={form.rules[r.key] === true} onChange={(v) => setForm({ ...form, rules: { ...form.rules, [r.key]: v } })} label={r.label} />
              {r.help && <div style={{ ...muted, marginLeft: 50 }}>{r.help}</div>}
            </div>
          ))}
          <F label="Forced sale discount %" helper="Leave blank to use the platform default.">
            <Input
              style={{ width: 120 }}
              inputMode="decimal"
              value={String(form.rules.forced_sale_discount_pct ?? "")}
              onChange={(e) => {
                const raw = e.target.value;
                const rules = { ...form.rules };
                if (raw === "") delete rules.forced_sale_discount_pct;
                else rules.forced_sale_discount_pct = Number.isNaN(Number(raw)) ? (raw as unknown as number) : Number(raw);
                setForm({ ...form, rules });
              }}
            />
          </F>
        </div>

        <div style={{ marginTop: 22 }}>
          <Toggle on={form.active} onChange={(v) => setForm({ ...form, active: v })} label={form.active ? "Active" : "Inactive: hidden from new instructions"} />
        </div>
      </FormDialog>
    </div>
  );
}
