// Feature API module: every profile-editor request goes through here (no fetch in components).

const apiUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const base = `${apiUrl}/api/v1/profiles`;

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: init?.body ? { "Content-Type": "application/json", ...init.headers } : init?.headers,
  });
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail)) {
        detail = body.detail.map((d: { loc?: unknown[]; msg?: string }) => `${(d.loc ?? []).slice(-1)[0] ?? "field"}: ${d.msg ?? "invalid"}`).join("; ");
      }
    } catch {
      /* keep the generic message */
    }
    throw new ApiError(detail, response.status);
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}

const json = (method: string, body: unknown): RequestInit => ({ method, body: JSON.stringify(body) });

export interface Profile {
  id: string;
  slug: string;
  display_name: string;
  headline: string | null;
  summary: string | null;
  timezone: string;
}

export type Record_ = Record<string, unknown> & { id: string };
export type ItemKind = "experiences" | "achievements" | "education" | "portfolio" | "role-families" | "role-targets";

export interface SkillRecord {
  skill_id: string;
  canonical_name: string;
  category: string | null;
  proficiency: string | null;
  years_experience: number | null;
  verified: boolean;
  aliases: string[];
}

export const profileApi = {
  list: () => request<Profile[]>(base),
  create: (slug: string, displayName: string) => request<Profile>(base, json("POST", { slug, display_name: displayName })),
  update: (id: string, values: Omit<Profile, "id">) => request<Profile>(`${base}/${id}`, json("PUT", values)),

  contact: (id: string) => request<Record<string, string | null> | null>(`${base}/${id}/contact`),
  saveContact: (id: string, values: Record<string, string | null>) => request(`${base}/${id}/contact`, json("PUT", values)),

  items: (id: string, kind: ItemKind) => request<Record_[]>(`${base}/${id}/${kind}`),
  addItem: (id: string, kind: ItemKind, values: Record<string, unknown>) => request<Record_>(`${base}/${id}/${kind}`, json("POST", values)),
  saveItem: (id: string, kind: ItemKind, itemId: string, values: Record<string, unknown>) =>
    request<Record_>(`${base}/${id}/${kind}/${itemId}`, json("PUT", values)),
  deleteItem: (id: string, kind: ItemKind, itemId: string) => request<void>(`${base}/${id}/${kind}/${itemId}`, { method: "DELETE" }),

  skills: (id: string) => request<SkillRecord[]>(`${base}/${id}/skills`),
  addSkill: (id: string, values: Record<string, unknown>) => request<SkillRecord>(`${base}/${id}/skills`, json("POST", values)),
  saveSkill: (id: string, skillId: string, values: Record<string, unknown>) =>
    request<SkillRecord>(`${base}/${id}/skills/${skillId}`, json("PUT", values)),
  deleteSkill: (id: string, skillId: string) => request<void>(`${base}/${id}/skills/${skillId}`, { method: "DELETE" }),
  addAlias: (id: string, skillId: string, alias: string) => request<string[]>(`${base}/${id}/skills/${skillId}/aliases`, json("POST", { alias })),
  removeAlias: (id: string, skillId: string, alias: string) =>
    request<void>(`${base}/${id}/skills/${skillId}/aliases/${encodeURIComponent(alias)}`, { method: "DELETE" }),

  searchPreferences: (id: string) => request<Record<string, unknown> | null>(`${base}/${id}/search-preferences`),
  saveSearchPreferences: (id: string, values: Record<string, unknown>) => request(`${base}/${id}/search-preferences`, json("PUT", values)),
  scoring: (id: string) => request<{ weights: Record<string, number> } | null>(`${base}/${id}/scoring-preferences`),
  saveScoring: (id: string, weights: Record<string, number>) => request(`${base}/${id}/scoring-preferences`, json("PUT", { weights })),

  exportProfile: (id: string) => request<Record<string, unknown>>(`${base}/${id}/export`),
  importProfile: (data: Record<string, unknown>) => request<Profile>(`${base}/import`, json("POST", data)),
};
