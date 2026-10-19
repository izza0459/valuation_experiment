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

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { Button, Icon } from "@/design-system";
import { FieldInput } from "@/components/vp/FieldInput";
import { demoValuesFor } from "@/components/vp/demoFill";
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
    keys: ["purpose", "bank", "bank_reference_no", "client_name", "date_time_request_received", "date_of_instruction"],
  },
  {
    title: "Property",
    keys: ["property_category", "unit_number", "building_name", "community_name", "latitude", "longitude"],
  },
  {
    title: "Parties",
    sub: "Add every owner and applicant named on the request.",
    keys: ["applicant_name", "ownership_name", "contact_name", "contact_number"],
  },
  {
    title: "Team",
    sub: "Who works on this job. These can be changed later on the Check List.",
    keys: ["valuer", "registered_valuer", "inspected_by", "peer_reviewer"],
  },
];

const WIDE = new Set<string>([]);

/** Same switch as the workspace's "Fill demo data" button. */
const DEMO_FILL = process.env.NEXT_PUBLIC_DEMO_FILL !== "false";

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

  // Fills only the empty fields on screen; anything typed stays.
  function fillDemo() {
    const onScreen = SECTIONS.flatMap((s) => s.keys)
      .map((key) => fields.get(key))
      .filter((f): f is FieldDef => Boolean(f && shown(f)));
    const current = Object.fromEntries(onScreen.map((f) => [f.key, valueOf(f)]));
    const demo = demoValuesFor(onScreen, current, options, options?.users ?? []);
    // The bank goes through set() so its code fills the reference as usual.
    if ("bank" in demo) {
      set("bank", demo.bank);
      delete demo.bank;
      delete demo.bank_reference_no;
    }
    for (const [key, value] of Object.entries(demo)) set(key, value);
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
      await apiFetch<{ id: number }>("/api/jobs/", {
        method: "POST",
        body: JSON.stringify({ values: payload }),
      });
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
      <PageHead title="New valuation instruction" sub="Open a job from a bank's or client's request.">
        {DEMO_FILL && (
          <Button variant="outline" onClick={fillDemo}>
            Fill demo data
          </Button>
        )}
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

        <div className="row" style={{ justifyContent: "flex-end", gap: 10 }}>
          <Button type="submit" disabled={busy} icon={<Icon name="check" size={18} />}>
            {busy ? "Creating…" : "Create instruction"}
          </Button>
        </div>
      </form>
    </Shell>
  );
}
