"use client";

/**
 * New instruction (design brief S2): the minimum needed to open a job, plus
 * who is on it. The rest (title-deed details and so on) is entered in the
 * workspace afterwards.
 *
 * Built from the field config, like the workspace tabs, and saved through
 * POST /api/jobs/, which applies the values with the same validation as a tab
 * edit. The server creates the job, its property and its tab rows in one go.
 */

import { useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { Button, Icon, Input, Select } from "@/design-system";
import { FieldInput } from "@/components/vp/FieldInput";
import { Banner, F, PageHead, Section, Shell } from "@/components/vp/ui";
import { ApiError, apiFetch } from "@/lib/api";
import { useMe } from "@/lib/auth";
import { isFieldVisible, useFieldConfig, type FieldDef } from "@/lib/fieldConfig";
import { useOptions } from "@/lib/options";

/** Field keys, grouped as the form shows them. Must be a subset of what the
 * server accepts (backend/apps/jobs/intake.py INTAKE_FIELDS). */
const SECTIONS: { title: string; sub?: string; keys: string[] }[] = [
  {
    title: "Client",
    sub: "Mortgage work is for a bank (its code and billing address come from the bank master); audit and internal work names the client.",
    // One date: the instruction's. When the request arrived is on the Instructions tab if it differs.
    keys: ["purpose", "bank", "bank_reference_no", "client_name", "date_of_instruction"],
  },
  {
    title: "Property",
    keys: ["property_category", "unit_number", "building_name", "community_name", "latitude", "longitude"],
  },
  {
    title: "Parties",
    sub: "Add every owner and applicant named on the request.",
    keys: ["applicant_name", "ownership_name", "contact_name", "contact_role", "contact_number"],
  },
  {
    title: "Team",
    sub: "Who works on this job. These can be changed later on the Check List.",
    keys: ["valuer", "registered_valuer", "inspected_by", "peer_reviewer"],
  },
];

const WIDE = new Set<string>([]);

/** What a document received with the instruction can be (document_type presets). */
const DOC_TYPES = [
  { value: "bank_instruction", label: "Bank instruction" },
  { value: "title_deed", label: "Title Deed" },
  { value: "spa", label: "SPA" },
  { value: "initial_contract_of_sale", label: "Initial Contract of Sale" },
  { value: "site_plan", label: "Site Plan" },
  { value: "other", label: "Other" },
];
type InstructionDoc = { file: File; docType: string; caption: string };


export function NewInstruction() {
  const router = useRouter();
  const qc = useQueryClient();
  const { data: me } = useMe();
  const { data: tabs } = useFieldConfig();
  const { data: options } = useOptions();

  const [values, setValues] = useState<Record<string, unknown>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Documents that came with the instruction (the bank's request, a title
  // deed, an SPA...), each with its type and a caption. Uploaded once the lead
  // exists; the inspector sees them under Documents received.
  const [bankDocs, setBankDocs] = useState<InstructionDoc[]>([]);
  const setDoc = (doc: InstructionDoc, change: Partial<InstructionDoc>) =>
    setBankDocs((docs) => docs.map((d) => (d === doc ? { ...d, ...change } : d)));
  const [createdId, setCreatedId] = useState<number | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const fields = new Map<string, FieldDef>();
  for (const tab of tabs ?? []) for (const f of tab.fields) fields.set(f.key, f);

  const canCreate = me?.authenticated ? Boolean(me.user.can_create_jobs ?? me.user.is_admin) : false;

  // A field's configured default (the purpose) is what the form starts on.
  const valueOf = (field: FieldDef) => (field.key in values ? values[field.key] : (field.default ?? ""));
  // The purpose decides between a bank and a named client.
  const purposeField = fields.get("purpose");
  const context = { instructions: { purpose: purposeField ? valueOf(purposeField) : "mortgage_security" } };
  const shown = (field: FieldDef) => !field.visible_if || field.visible_if.field !== "instructions.purpose" || isFieldVisible(field, context);

  function set(key: string, value: unknown) {
    if (key === "bank") {
      // Picking a bank fills the reference with its code, unless one was typed.
      const banks = options?.bank ?? [];
      const codeOf = (id: unknown) => banks.find((b) => b.value === id)?.code ?? "";
      setValues((v) => {
        const current = String(v.bank_reference_no ?? "");
        const replace = current === "" || current === codeOf(v.bank);
        return { ...v, bank: value, ...(replace ? { bank_reference_no: codeOf(value) } : {}) };
      });
      setErrors((e) => {
        const { bank: _gone, ...rest } = e;
        void _gone;
        return rest;
      });
      return;
    }
    setValues((v) => ({ ...v, [key]: value }));
    setErrors((e) => {
      const { [key]: _gone, ...rest } = e;
      void _gone;
      return rest;
    });
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setFormError(null);

    // Defaults the user never touched are sent too, so what they see is what is saved.
    const payload: Record<string, unknown> = {};
    for (const section of SECTIONS) {
      for (const key of section.keys) {
        const field = fields.get(key);
        if (!field || !shown(field)) continue;
        const value = valueOf(field);
        if (value !== "" && value !== null && value !== undefined) payload[key] = value;
      }
    }

    try {
      const created = await apiFetch<{ id: number }>("/api/jobs/", {
        method: "POST",
        body: JSON.stringify({ values: payload }),
      });
      if (bankDocs.length) {
        const problem = await uploadBankDocs(created.id);
        if (problem) {
          // The lead exists: don't create it twice. Say what didn't upload.
          setCreatedId(created.id);
          setFormError(`The instruction was created, but the bank's documents weren't all added: ${problem}`);
          setBusy(false);
          return;
        }
      }
      // Back to the dashboard, where the new job now shows, rather than
      // straight into its workspace.
      await Promise.all([qc.invalidateQueries({ queryKey: ["jobs"] }), qc.invalidateQueries({ queryKey: ["job-kpis"] })]);
      router.push("/jobs");
    } catch (err) {
      if (err instanceof ApiError && err.status === 400 && err.body?.errors) {
        setErrors(err.body.errors as Record<string, string>);
        setFormError("Some details need fixing. See the highlighted fields.");
      } else {
        setFormError(err instanceof ApiError ? err.message : "Couldn't reach the server. Try again.");
      }
      setBusy(false);
    }
  }

  /** One upload per document, so each keeps its own type and caption. */
  async function uploadBankDocs(jobId: number): Promise<string | null> {
    const problems: string[] = [];
    for (const doc of bankDocs) {
      const form = new FormData();
      form.append("files", doc.file);
      form.append("doc_type", doc.docType);
      if (doc.caption.trim()) form.append("caption", doc.caption.trim());
      try {
        const res = await apiFetch<{ rejected: { name: string; reason: string }[] }>(`/api/jobs/${jobId}/documents/`, {
          method: "POST",
          body: form,
        });
        res.rejected?.forEach((r) => problems.push(`${r.name}: ${r.reason}`));
      } catch (err) {
        const rejected = err instanceof ApiError && Array.isArray(err.body?.rejected)
          ? (err.body.rejected as { name: string; reason: string }[]).map((r) => `${r.name}: ${r.reason}`)
          : [];
        problems.push(...(rejected.length ? rejected : [`${doc.file.name}: ${err instanceof ApiError ? err.message : "Couldn't reach the server."}`]));
      }
    }
    return problems.length ? problems.join("; ") : null;
  }

  if (me && !canCreate) {
    return (
      <Shell>
        <div className="card" style={{ textAlign: "center", padding: "60px 24px" }}>
          <div style={{ fontSize: 17 }}>Only ops or an admin can create an instruction.</div>
          <div style={{ color: "var(--text-muted)", fontSize: 14, marginTop: 6 }}>
            <Link href="/jobs">Back to jobs</Link>
          </div>
        </div>
      </Shell>
    );
  }

  return (
    <Shell>
      <PageHead title="New valuation instruction" tip="Open a job from a bank's or client's request.">
        <Link href="/jobs">
          <Button variant="outline">Cancel</Button>
        </Link>
      </PageHead>

      <form onSubmit={submit} style={{ display: "grid", gap: 16, maxWidth: 880 }}>
        {formError && (
          <Banner tone="red" icon="alert-circle">
            {formError}
          </Banner>
        )}

        {SECTIONS.map((section) => (
          <Section key={section.title} title={section.title} sub={section.sub}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: "18px 24px" }}>
              {section.keys.map((key) => {
                const field = fields.get(key);
                if (!field || !shown(field)) return null;
                const starred = key === "bank" || key === "client_name" || key === "applicant_name";
                return (
                  <F
                    key={key}
                    span={WIDE.has(key) ? 2 : undefined}
                    label={
                      <>
                        {field.label}
                        {starred && <span style={{ color: "var(--text-accent)" }}> *</span>}
                      </>
                    }
                    error={errors[key]}
                    helper={field.help_text || undefined}
                  >
                    <FieldInput
                      field={field}
                      value={valueOf(field)}
                      onChange={(v) => set(key, v)}
                      options={options?.[field.options_key ?? ""] ?? []}
                      users={options?.users ?? []}
                      readOnly={false}
                      invalid={Boolean(errors[key])}
                    />
                  </F>
                );
              })}
            </div>
          </Section>
        ))}

        <Section title="Documents received" sub="What came with the instruction: the bank's request, a title deed, an SPA… (PDF or image). Optional. The inspector sees them on the lead.">
          <input ref={fileInput} type="file" multiple hidden accept=".pdf,.jpg,.jpeg,.png,.heic,application/pdf,image/*"
            onChange={(e) => {
              const picked = Array.from(e.target.files ?? []);
              setBankDocs((docs) => [
                ...docs,
                ...picked
                  .filter((f) => !docs.some((d) => d.file.name === f.name && d.file.size === f.size))
                  .map((file) => ({ file, docType: "bank_instruction", caption: "" })),
              ]);
              e.target.value = "";
            }} />
          <div style={{ display: "grid", gap: 8 }}>
            {bankDocs.map((doc) => (
              <div key={`${doc.file.name}-${doc.file.size}`} style={{ display: "grid", gap: 8, padding: 12, borderRadius: 8,
                border: "1px solid var(--border-subtle)" }}>
                <div className="row" style={{ gap: 10, fontSize: 14 }}>
                  <Icon name="file-text" size={16} color="var(--text-muted)" />
                  <span className="one-line" style={{ flex: 1, minWidth: 0 }} title={doc.file.name}>{doc.file.name}</span>
                  <span style={{ color: "var(--text-muted)", fontSize: 13 }}>{(doc.file.size / 1024 / 1024).toFixed(1)} MB</span>
                  {!createdId && (
                    <button type="button" className="linkbtn" aria-label={`Remove ${doc.file.name}`}
                      onClick={() => setBankDocs((docs) => docs.filter((d) => d !== doc))}>
                      Remove
                    </button>
                  )}
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: 10 }}>
                  <Select aria-label="Document type" value={doc.docType} options={DOC_TYPES} disabled={Boolean(createdId)}
                    onChange={(e) => setDoc(doc, { docType: e.target.value })} />
                  <Input placeholder="Caption (optional)" maxLength={255} value={doc.caption} disabled={Boolean(createdId)}
                    onChange={(e) => setDoc(doc, { caption: e.target.value })} />
                </div>
              </div>
            ))}
            {!createdId && (
              <div>
                <Button type="button" variant="outline" icon={<Icon name="upload" size={16} />} onClick={() => fileInput.current?.click()}>
                  {bankDocs.length ? "Add more" : "Add documents"}
                </Button>
              </div>
            )}
          </div>
        </Section>

        <div className="row" style={{ justifyContent: "flex-end", gap: 10 }}>
          {createdId ? (
            <Link href={`/jobs/${createdId}`}>
              <Button type="button" icon={<Icon name="arrow-right" size={18} />}>Open the lead</Button>
            </Link>
          ) : (
            <Button type="submit" disabled={busy} icon={<Icon name="check" size={18} />}>
              {busy ? "Creating…" : "Create instruction"}
            </Button>
          )}
        </div>
      </form>
    </Shell>
  );
}
