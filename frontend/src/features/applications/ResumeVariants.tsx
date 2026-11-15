import { FormEvent, useCallback, useEffect, useState } from "react";

const apiUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const base = `${apiUrl}/api/v1`;

interface Profile {
  id: string;
  display_name: string;
}
interface Family {
  id: string;
  name: string;
}
interface Variant {
  id: string;
  name: string;
  role_family_id: string | null;
  summary_strategy: string | null;
  preferred_skill_categories: string[];
}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return (await response.json()) as T;
}

export function ResumeVariants() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [profileId, setProfileId] = useState("");
  const [families, setFamilies] = useState<Family[]>([]);
  const [variants, setVariants] = useState<Variant[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const [form, setForm] = useState({ name: "", familyId: "", strategy: "", categories: "" });

  useEffect(() => {
    getJson<Profile[]>(`${base}/profiles`)
      .then((loaded) => {
        setProfiles(loaded);
        setProfileId((current) => current || loaded[0]?.id || "");
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Unable to load profiles"));
  }, []);

  useEffect(() => {
    if (!profileId) return;
    let cancelled = false;
    Promise.all([
      getJson<Variant[]>(`${base}/profiles/${profileId}/resume-variants`),
      getJson<Family[]>(`${base}/profiles/${profileId}/role-families`),
    ])
      .then(([loadedVariants, loadedFamilies]) => {
        if (cancelled) return;
        setVariants(loadedVariants);
        setFamilies(loadedFamilies);
        setError(null);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Unable to load variants");
      });
    return () => {
      cancelled = true;
    };
  }, [profileId, tick]);

  const create = useCallback(
    async (event: FormEvent) => {
      event.preventDefault();
      const response = await fetch(`${base}/profiles/${profileId}/resume-variants`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: form.name,
          role_family_id: form.familyId || null,
          summary_strategy: form.strategy || null,
          preferred_skill_categories: form.categories.split(",").map((c) => c.trim()).filter(Boolean),
        }),
      });
      if (!response.ok) {
        setError(`Unable to create variant (${response.status})`);
        return;
      }
      setForm({ name: "", familyId: "", strategy: "", categories: "" });
      setTick((value) => value + 1);
    },
    [form, profileId],
  );

  const remove = useCallback(
    async (id: string) => {
      const response = await fetch(`${base}/profiles/${profileId}/resume-variants/${id}`, { method: "DELETE" });
      if (!response.ok) setError(`Unable to delete variant (${response.status})`);
      setTick((value) => value + 1);
    },
    [profileId],
  );

  return (
    <section aria-label="Resume variants">
      <h2>Resume variants</h2>
      {error && <p role="alert">{error}</p>}
      <label htmlFor="variant-profile">Profile</label>{" "}
      <select id="variant-profile" value={profileId} onChange={(e) => setProfileId(e.target.value)}>
        {profiles.map((p) => (
          <option key={p.id} value={p.id}>
            {p.display_name}
          </option>
        ))}
      </select>
      <form onSubmit={(event) => void create(event)} aria-label="New variant">
        <h3>New variant</h3>
        <label htmlFor="v-name">Name</label>{" "}
        <input id="v-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />{" "}
        <label htmlFor="v-family">Role family</label>{" "}
        <select id="v-family" value={form.familyId} onChange={(e) => setForm({ ...form, familyId: e.target.value })}>
          <option value="">None</option>
          {families.map((f) => (
            <option key={f.id} value={f.id}>
              {f.name}
            </option>
          ))}
        </select>{" "}
        <label htmlFor="v-categories">Preferred skill categories (comma separated)</label>{" "}
        <input id="v-categories" value={form.categories} onChange={(e) => setForm({ ...form, categories: e.target.value })} />{" "}
        <label htmlFor="v-strategy">Summary strategy</label>{" "}
        <input id="v-strategy" value={form.strategy} onChange={(e) => setForm({ ...form, strategy: e.target.value })} />{" "}
        <button type="submit">Create variant</button>
      </form>
      {variants.length === 0 ? (
        <p>No variants yet.</p>
      ) : (
        <ul>
          {variants.map((v) => (
            <li key={v.id}>
              <strong>{v.name}</strong>
              {v.role_family_id && ` · ${families.find((f) => f.id === v.role_family_id)?.name ?? "role family"}`}
              {v.preferred_skill_categories.length > 0 && ` · skills: ${v.preferred_skill_categories.join(", ")}`}
              {v.summary_strategy && ` · ${v.summary_strategy}`}{" "}
              <button onClick={() => void remove(v.id)}>Delete</button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
