export type FieldType = "text" | "textarea" | "number" | "date" | "checkbox" | "list";
export interface Field {
  name: string;
  label: string;
  type: FieldType;
  required?: boolean;
}

export type Values = Record<string, string | boolean>;

export function toForm(fields: Field[], record?: Record<string, unknown>): Values {
  const values: Values = {};
  for (const f of fields) {
    const raw = record?.[f.name];
    if (f.type === "checkbox") values[f.name] = Boolean(raw);
    else if (f.type === "list") values[f.name] = Array.isArray(raw) ? raw.join(", ") : "";
    else values[f.name] = raw == null ? "" : String(raw);
  }
  return values;
}

export function toPayload(fields: Field[], values: Values): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const f of fields) {
    const v = values[f.name];
    if (f.type === "checkbox") out[f.name] = Boolean(v);
    else if (f.type === "list") out[f.name] = String(v).split(",").map((s) => s.trim()).filter(Boolean);
    else if (f.type === "number") out[f.name] = String(v) === "" ? null : Number(v);
    else out[f.name] = String(v) === "" ? (f.required ? "" : null) : v;
  }
  return out;
}

