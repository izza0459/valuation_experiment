/**
 * "Fill demo data": plausible values for the empty fields of one tab, so a
 * demo can move through the stages without typing everything. Only empty,
 * editable, visible fields are filled; nothing already entered is touched.
 * The values go through the normal autosave, so the server validates them
 * like anything typed.
 */

import type { FieldDef } from "@/lib/fieldConfig";
import type { Option, UserOption } from "@/lib/options";

const today = () => new Date().toISOString().slice(0, 10);

/** Field-specific values where a generic one would read oddly in the report. */
const BY_KEY: Record<string, unknown> = {
  bank_reference_no: "DEMO-REF-1001",
  client_name: "Demo Client",
  billing_address: "PO Box 12345, Dubai, United Arab Emirates",
  contact_name: "Ahmed Khan",
  contact_number: "+971 50 123 4567",
  unit_number: "1204",
  building_name: "Marina Heights",
  community_name: "Dubai Marina",
  latitude: "25.080000",
  longitude: "55.140000",
  applicant_name: ["Demo Applicant"],
  ownership_name: ["Demo Owner"],
  title_doc_property_no: "1204",
  title_doc_plot_no: "392-1234",
  title_doc_municipality_no: "392-5678",
  title_doc_building_no: "1",
  title_doc_building_name: "Marina Heights",
  title_doc_community_name: "Dubai Marina",
  title_doc_emirate: "Dubai",
  makani_number: "12345 67890",
  dewa_number: "2001234567",
  property_floor_no: "12",
  floor_configuration: "B+G+2P+30",
  total_floors: "33",
  ground_elevation: "5",
  no_of_bedrooms: "2",
  no_of_parkings: "1",
  bua_sqft: "1250",
  plot_area_sqft: "3000",
  departures: "None",
  rent_if_any: "120000",
  sale_price_if_any: "1850000",
  front_views: "Marina view",
  rear_views: "Community view",
  upgrade_comment: "Kitchen and flooring upgraded by the owner.",
  repairs: "None noted.",
  built_about: "2015",
  developer: "Emaar Properties",
  remaining_economic_life_years: "40",
  market_value: "1850000",
  market_rent: "120000",
  reinstatement_note: "Not applicable.",
  reinstatement_value: "900000",
  material_valuation_uncertainty_note: "",
};

const isEmpty = (v: unknown) => v === null || v === undefined || v === "" || (Array.isArray(v) && v.length === 0);

function pick(field: FieldDef, options: Option[]): unknown {
  if (!options.length) return undefined;
  const first = options[0];
  // Free-text selects store the label (community, emirate); others the key.
  return field.free_text ? first.label : first.value;
}

function demoValue(field: FieldDef, options: Option[], users: UserOption[]): unknown {
  if (field.key in BY_KEY) {
    const v = BY_KEY[field.key];
    return v === "" ? undefined : v;
  }
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
    case "select":
      return pick(field, options);
    case "multiselect":
      return options.length ? [String(options[0].value)] : undefined;
    case "user":
      return users.length ? users[0].value : undefined;
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
    const value = demoValue(field, options?.[field.options_key ?? ""] ?? [], users);
    if (value !== undefined) out[field.key] = value;
  }
  return out;
}
