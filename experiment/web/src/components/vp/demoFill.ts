/**
 * "Fill demo data": plausible values for the empty fields of a form, so a
 * demo can move through the stages without typing everything. Only empty,
 * editable, visible fields are filled; nothing already entered is touched.
 * The values go through the normal save, so the server validates them like
 * anything typed.
 *
 * The property is a real one in the loaded DLD sales (Sobha Hartland, The
 * Crest, 2-bed apartment, ~1,085 sqft), so the Evidence tab's DLD search
 * finds matching sales for a demo job straight away.
 */

import type { QueryClient } from "@tanstack/react-query";
import { ApiError, apiFetch } from "@/lib/api";
import { isFieldVisible, type FieldDef, type TabDef } from "@/lib/fieldConfig";
import type { Option, UserOption } from "@/lib/options";

const today = () => new Date().toISOString().slice(0, 10);

/** Field-specific values where a generic one would read oddly in the report. */
const BY_KEY: Record<string, unknown> = {
  bank_reference_no: "DEMO-REF-1001",
  client_name: "Demo Client",
  billing_address: "PO Box 12345, Dubai, United Arab Emirates",
  contact_name: "Ahmed Khan",
  contact_number: "+971 50 123 4567",
  // What the DLD search matches on: community, building, type, beds, BUA.
  unit_number: "1407",
  building_name: "Sobha Hartland - The Crest",
  community_name: "Sobha Hartland",
  latitude: "25.180500",
  longitude: "55.311500",
  applicant_name: ["Demo Applicant"],
  ownership_name: ["Demo Owner"],
  title_doc_property_no: "1407",
  title_doc_plot_no: "614-1234",
  title_doc_municipality_no: "614-5678",
  title_doc_building_no: "1",
  title_doc_building_name: "Sobha Hartland - The Crest",
  title_doc_community_name: "Sobha Hartland",
  title_doc_emirate: "Dubai",
  // Check List: what a normal full inspection records.
  dld_location_checked: true,
  makani_photo: true,
  dewa_photo: true,
  newly_handed_over: false,
  satellite_measurement: false,
  makani_number: "31245 89012",
  dewa_number: "2001234567",
  property_floor_no: "14",
  floor_configuration: "B+G+4P+40",
  total_floors: "45",
  ground_elevation: "5",
  no_of_bedrooms: "2",
  parking: true,
  no_of_parkings: "1",
  bua_sqft: "1085",
  plot_area_sqft: "3000",
  departures: "None",
  rent_if_any: "150000",
  sale_price_if_any: "2335000",
  front_views: "Downtown and Burj Khalifa view",
  rear_views: "Lagoon and community view",
  upgraded: false,
  upgrade_comment: "Kitchen and flooring upgraded by the owner.",
  repairs: "None noted.",
  built_about: "2022",
  built_date: "2022-06-30",
  developer: "Sobha Realty",
  remaining_economic_life_years: "50",
  market_value: "2335000",
  market_rent: "150000",
  reinstatement_note: "Not applicable for an apartment.",
  reinstatement_value: "900000",
  material_valuation_uncertainty: false,
};

/** Preferred option per field where the first preset isn't the typical case. */
const PREFER: Record<string, string> = {
  property_category: "apartment",
  property_status: "complete",
  inspection_type: "full",
  basis_of_valuation: "market_value",
  valuation_approaches: "market_approach_comparable_method",
  interest_valued: "international_freehold",
  purpose: "mortgage_security",
  title_doc_type: "title_deed",
  occupancy: "owner_occupied",
  electrical_services: "connected",
  water: "connected",
  sewerage: "connected",
  bua_source: "title_deed",
  plot_area_source: "title_deed",
  capacity_of_valuer: "external",
};

/** The role a user field is for, so the demo picks someone who holds it. */
const USER_ROLE: Record<string, string> = {
  inspected_by: "inspector",
  valuer: "valuer",
  registered_valuer: "valuer",
  peer_reviewer: "peer_reviewer",
};

const isEmpty = (v: unknown) => v === null || v === undefined || v === "" || (Array.isArray(v) && v.length === 0);

function pickOption(field: FieldDef, options: Option[]): Option | undefined {
  const preferred = PREFER[field.key];
  return (preferred && options.find((o) => String(o.value) === preferred)) || options[0];
}

function pickUser(field: FieldDef, users: UserOption[], chosen: Record<string, unknown>): unknown {
  if (!users.length) return undefined;
  const role = USER_ROLE[field.key];
  const withRole = role ? users.filter((u) => u.roles.includes(role)) : [];
  const pool = withRole.length ? withRole : users;
  // A peer reviewer must not be the valuer when there is anyone else.
  if (field.key === "peer_reviewer") {
    const valuer = chosen.valuer ?? chosen.registered_valuer;
    const other = pool.find((u) => u.value !== valuer) ?? users.find((u) => u.value !== valuer);
    if (other) return other.value;
  }
  return pool[0].value;
}

function demoValue(field: FieldDef, options: Option[], users: UserOption[], chosen: Record<string, unknown>): unknown {
  if (field.key in BY_KEY) return BY_KEY[field.key];
  switch (field.type) {
    case "text":
      return `Demo ${field.label.toLowerCase()}`;
    case "textarea":
      return `Demo ${field.label.toLowerCase()}.`;
    case "number":
      return "1";
    case "decimal":
      return "100";
    case "boolean":
      return false;
    case "date":
      return today();
    case "datetime":
      return new Date().toISOString();
    case "select": {
      const o = pickOption(field, options);
      // Free-text selects store the label (community, emirate); others the key.
      return o ? (field.free_text ? o.label : o.value) : undefined;
    }
    case "multiselect": {
      const o = pickOption(field, options);
      return o ? [String(o.value)] : undefined;
    }
    case "user":
      return pickUser(field, users, chosen);
    case "names":
      return ["Demo Name"];
    case "library": {
      if (!options.length) return undefined;
      const o = options[0];
      // List-style library fields hold entries; the rest hold the paragraph.
      return Array.isArray(field.default) ? [{ title: o.label, body: o.report_text ?? "" }] : (o.report_text ?? o.label);
    }
    default:
      return undefined;
  }
}

/** Values to set for the given fields, skipping any that are already filled. */
export function demoValuesFor(
  fields: FieldDef[],
  current: Record<string, unknown>,
  options: Record<string, Option[]> | undefined,
  users: UserOption[],
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const field of fields) {
    if (!isEmpty(current[field.key])) continue;
    const value = demoValue(field, options?.[field.options_key ?? ""] ?? [], users, { ...current, ...out });
    if (value !== undefined) out[field.key] = value;
  }
  return out;
}

/** Demo values for one tab, in a few passes so fields an earlier answer
 * reveals (parking count, plot area) are filled too. `allValues` is every
 * tab's values plus `bank`, for rules that cross tabs. */
export function demoValuesForTab(
  tab: TabDef,
  current: Record<string, unknown>,
  allValues: Record<string, unknown>,
  readOnlyFields: string[],
  options: (Record<string, Option[]> & { users?: UserOption[] }) | undefined,
): Record<string, unknown> {
  const filled: Record<string, unknown> = {};
  for (let pass = 0; pass < 3; pass++) {
    const values = { ...current, ...filled };
    const showing = tab.fields.filter((f) => isFieldVisible(f, { ...allValues, [tab.key]: values }));
    const editable = showing.filter((f) => !f.calculated && !readOnlyFields.includes(f.key));
    const more = demoValuesFor(editable, values, options, options?.users ?? []);
    if (Object.keys(more).length === 0) break;
    Object.assign(filled, more);
  }
  return filled;
}

// --- dummy files -------------------------------------------------------------

/** A labelled placeholder image (PNG), standing in for a site photograph. */
export async function demoPhoto(label: string, hue: number): Promise<File> {
  const canvas = document.createElement("canvas");
  canvas.width = 1200;
  canvas.height = 800;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = `hsl(${hue} 35% 72%)`;
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "rgba(0,0,0,0.65)";
  ctx.font = "bold 64px sans-serif";
  ctx.textAlign = "center";
  ctx.fillText(label, canvas.width / 2, canvas.height / 2);
  ctx.font = "32px sans-serif";
  ctx.fillText("DEMO PHOTO", canvas.width / 2, canvas.height / 2 + 60);
  const blob = await new Promise<Blob>((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("Couldn't draw the demo photo."))), "image/png"),
  );
  return new File([blob], `demo-${label.toLowerCase().replace(/\W+/g, "-")}.png`, { type: "image/png" });
}

/** A one-page PDF with a title, standing in for a title deed or SPA. */
export function demoPdf(title: string): File {
  const text = title.replace(/[()\\]/g, "");
  const stream = `BT /F1 28 Tf 72 720 Td (${text}) Tj 0 -40 Td /F1 16 Tf (DEMO DOCUMENT - not a real record) Tj ET`;
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
    `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`,
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
  ];
  let pdf = "%PDF-1.4\n";
  const offsets: number[] = [];
  objects.forEach((body, i) => {
    offsets.push(pdf.length);
    pdf += `${i + 1} 0 obj\n${body}\nendobj\n`;
  });
  const xref = pdf.length;
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  pdf += offsets.map((o) => `${String(o).padStart(10, "0")} 00000 n \n`).join("");
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return new File([pdf], `demo-${title.toLowerCase().replace(/\W+/g, "-")}.pdf`, { type: "application/pdf" });
}

/** Which dummy files a "Fill demo data" button adds. */
export type DemoFiles = "title" | "slot_photos" | "photos" | "documents";

type Listed = { items: { slot?: string; doc_type?: string; include_in_report?: boolean }[] };

/** Uploads dummy photographs or documents for a job, skipping any kind the
 * job already has, then refreshes what shows them. Returns problems, if any. */
export async function uploadDemoFiles(jobId: string, which: DemoFiles, qc: QueryClient): Promise<string[]> {
  const kind = which === "title" || which === "documents" ? "documents" : "photos";
  const base = `/api/jobs/${jobId}/${kind}/`;
  const { items } = await apiFetch<Listed>(base);
  const problems: string[] = [];

  const send = async (files: File[], extra: Record<string, string>) => {
    if (!files.length) return;
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    Object.entries(extra).forEach(([k, v]) => form.append(k, v));
    try {
      await apiFetch(base, { method: "POST", body: form });
    } catch (err) {
      problems.push(err instanceof ApiError ? err.message : "Couldn't upload the demo files.");
    }
  };

  if (kind === "documents") {
    if (!items.some((d) => d.doc_type === "title_deed")) await send([demoPdf("Title Deed")], { doc_type: "title_deed" });
    if (which === "documents" && !items.some((d) => d.doc_type === "spa")) await send([demoPdf("Sale and Purchase Agreement")], { doc_type: "spa" });
  } else {
    if (which === "photos" && items.filter((p) => (p.slot ?? "general") === "general").length < 3) {
      const views = ["Building exterior", "Living room", "Kitchen", "Bedroom", "Balcony view"];
      await send(await Promise.all(views.map((v, i) => demoPhoto(v, i * 60))), { slot: "general" });
    }
    if (!items.some((p) => p.slot === "makani")) await send([await demoPhoto("Makani 31245 89012", 200)], { slot: "makani" });
    if (!items.some((p) => p.slot === "dewa")) await send([await demoPhoto("DEWA 2001234567", 30)], { slot: "dewa" });
  }

  await Promise.all([
    qc.invalidateQueries({ queryKey: ["media", jobId, kind] }),
    qc.invalidateQueries({ queryKey: ["jobs", jobId] }),
    qc.invalidateQueries({ queryKey: ["job-activity", jobId] }),
  ]);
  return problems;
}
