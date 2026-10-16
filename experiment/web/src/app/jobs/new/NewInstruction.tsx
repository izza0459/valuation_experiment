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
import { Button, Icon } from "@/design-system";
import { FieldInput } from "@/components/vp/FieldInput";
import { Banner, F, PageHead, Section, Shell } from "@/components/vp/ui";
import { ApiError, apiFetch } from "@/lib/api";
import { useMe } from "@/lib/auth";
import { useFieldConfig, type FieldDef } from "@/lib/fieldConfig";
import { useOptions } from "@/lib/options";

/** Field keys, grouped as the form shows them. Must be a subset of what the
 * server accepts (backend/apps/jobs/intake.py INTAKE_FIELDS). */
const SECTIONS: { title: string; sub?: string; keys: string[] }[] = [
  {
    title: "Client",
    sub: "The billing address fills in from the bank once its SLA is signed.",
    keys: ["bank", "bank_reference_no", "purpose", "date_time_request_received", "date_of_instruction"],
  },
  {
    title: "Property",
    keys: ["property_category", "unit_number", "building_name", "development", "community_name", "latitude", "longitude"],
  },
  { title: "Parties", keys: ["applicant_name", "ownership_name"] },
  {
    title: "Team",
    sub: "Who works on this job. These can be changed later on the Check List.",
    keys: ["valuer", "registered_valuer", "inspected_by", "peer_reviewer"],
  },
];

const WIDE = new Set<string>([]);

export function NewInstruction() {
  const router = useRouter();
  const { data: me } = useMe();
  const { data: tabs } = useFieldConfig();
  const { data: options } = useOptions();

  const [values, setValues] = useState<Record<string, unknown>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const fields = new Map<string, FieldDef>();
  for (const tab of tabs ?? []) for (const f of tab.fields) fields.set(f.key, f);

  const isAdmin = me?.authenticated ? me.user.is_admin : false;

  // A field's configured default (the purpose) is what the form starts on.
  const valueOf = (field: FieldDef) => (field.key in values ? values[field.key] : (field.default ?? ""));

  function set(key: string, value: unknown) {
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
        if (!field) continue;
        const value = valueOf(field);
        if (value !== "" && value !== null && value !== undefined) payload[key] = value;
      }
    }

    try {
      const created = await apiFetch<{ id: number }>("/api/jobs/", {
        method: "POST",
        body: JSON.stringify({ values: payload }),
      });
      router.push(`/jobs/${created.id}`);
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

  if (me && !isAdmin) {
    return (
      <Shell>
        <div className="card" style={{ textAlign: "center", padding: "60px 24px" }}>
          <div style={{ fontSize: 17 }}>Only an admin can create an instruction.</div>
          <div style={{ color: "var(--text-muted)", fontSize: 14, marginTop: 6 }}>
            <Link href="/jobs">Back to jobs</Link>
          </div>
        </div>
      </Shell>
    );
  }

  return (
    <Shell>
      <PageHead title="New valuation instruction" sub="Open a job from a bank's request.">
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
                if (!field) return null;
                return (
                  <F
                    key={key}
                    span={WIDE.has(key) ? 2 : undefined}
                    label={
                      <>
                        {field.label}
                        {key === "bank" && <span style={{ color: "var(--text-accent)" }}> *</span>}
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
