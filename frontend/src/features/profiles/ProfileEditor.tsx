import { FormEvent, useCallback, useEffect, useState } from "react";
import { ItemsEditor } from "./ItemsEditor";
import type { Field } from "./fields";
import { type Profile, type SkillRecord, profileApi } from "./api";

const DIMENSIONS = [
  "role_alignment", "seniority_alignment", "technical_alignment", "architecture_alignment", "leadership_alignment",
  "domain_alignment", "location_alignment", "compensation_alignment", "employment_alignment", "interest_alignment",
];
const REMOTE_POLICIES = ["REQUIRED", "PREFERRED", "NEUTRAL", "AVOID", "BLOCK"];

const EXPERIENCE: Field[] = [
  { name: "organization", label: "Organization", type: "text", required: true },
  { name: "title", label: "Title", type: "text", required: true },
  { name: "start_date", label: "Start date", type: "date" },
  { name: "end_date", label: "End date", type: "date" },
  { name: "location", label: "Location", type: "text" },
  { name: "employment_type", label: "Employment type", type: "text" },
  { name: "description", label: "Description", type: "textarea" },
];
const ACHIEVEMENT: Field[] = [
  { name: "title", label: "Title", type: "text", required: true },
  { name: "situation", label: "Situation", type: "textarea" },
  { name: "action", label: "Action", type: "textarea" },
  { name: "result", label: "Result", type: "textarea" },
  { name: "technologies", label: "Technologies", type: "list" },
  { name: "competency_tags", label: "Competency tags", type: "list" },
  { name: "verified", label: "Verified (I can substantiate this)", type: "checkbox" },
];
const EDUCATION: Field[] = [
  { name: "institution", label: "Institution", type: "text", required: true },
  { name: "degree", label: "Degree", type: "text" },
  { name: "field_of_study", label: "Field of study", type: "text" },
  { name: "start_date", label: "Start date", type: "date" },
  { name: "end_date", label: "End date", type: "date" },
  { name: "notes", label: "Notes", type: "textarea" },
];
const PORTFOLIO: Field[] = [
  { name: "name", label: "Name", type: "text", required: true },
  { name: "url", label: "URL", type: "text" },
  { name: "description", label: "Description", type: "textarea" },
  { name: "technologies", label: "Technologies", type: "list" },
  { name: "verified", label: "Verified", type: "checkbox" },
];
const ROLE_FAMILY: Field[] = [
  { name: "name", label: "Name", type: "text", required: true },
  { name: "priority", label: "Priority", type: "number" },
  { name: "enabled", label: "Enabled", type: "checkbox" },
];
const ROLE_TARGET: Field[] = [
  { name: "title_pattern", label: "Title pattern (use * as wildcard)", type: "text" },
  { name: "include_keywords", label: "Include keywords", type: "list" },
  { name: "exclude_keywords", label: "Exclude keywords", type: "list" },
  { name: "target_seniority", label: "Target seniority", type: "list" },
];

function useAsyncError() {
  const [error, setError] = useState<string | null>(null);
  const guard = useCallback(async (work: () => Promise<unknown>) => {
    setError(null);
    try {
      await work();
      return true;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Something went wrong");
      return false;
    }
  }, []);
  return { error, guard, setError };
}

function Overview({ profile, onChanged }: { profile: Profile; onChanged: () => void }) {
  const [form, setForm] = useState({ display_name: profile.display_name, headline: profile.headline ?? "", summary: profile.summary ?? "", timezone: profile.timezone });
  const [contact, setContact] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);
  const { error, guard } = useAsyncError();
  const contactFields = ["full_name", "email", "phone", "city", "region", "country", "website", "linkedin_url", "github_url"];

  useEffect(() => {
    profileApi.contact(profile.id).then((c) => setContact(Object.fromEntries(contactFields.map((f) => [f, String(c?.[f] ?? "")])))).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile.id]);

  async function save(event: FormEvent) {
    event.preventDefault();
    setSaved(false);
    const ok = await guard(async () => {
      await profileApi.update(profile.id, {
        slug: profile.slug,
        display_name: form.display_name,
        headline: form.headline || null,
        summary: form.summary || null,
        timezone: form.timezone,
      });
      await profileApi.saveContact(profile.id, Object.fromEntries(contactFields.map((f) => [f, contact[f] ? contact[f] : null])));
    });
    if (ok) {
      setSaved(true);
      onChanged();
    }
  }

  return (
    <form onSubmit={(event) => void save(event)} aria-label="Overview form">
      <h3>Overview</h3>
      {error && <p role="alert">{error}</p>}
      {saved && <p role="status">Saved.</p>}
      <div><label htmlFor="ov-name">Display name</label> <input id="ov-name" value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} required /></div>
      <div><label htmlFor="ov-headline">Headline</label> <input id="ov-headline" value={form.headline} onChange={(e) => setForm({ ...form, headline: e.target.value })} /></div>
      <div><label htmlFor="ov-summary">Summary</label> <textarea id="ov-summary" rows={3} value={form.summary} onChange={(e) => setForm({ ...form, summary: e.target.value })} /></div>
      <div><label htmlFor="ov-tz">Timezone</label> <input id="ov-tz" value={form.timezone} onChange={(e) => setForm({ ...form, timezone: e.target.value })} /></div>
      <h4>Contact (optional, never shown in public copies)</h4>
      {contactFields.map((f) => (
        <div key={f}>
          <label htmlFor={`ct-${f}`}>{f.replace(/_/g, " ")}</label>{" "}
          <input id={`ct-${f}`} value={contact[f] ?? ""} onChange={(e) => setContact({ ...contact, [f]: e.target.value })} />
        </div>
      ))}
      <button type="submit">Save overview</button>
    </form>
  );
}

function Skills({ profileId }: { profileId: string }) {
  const [skills, setSkills] = useState<SkillRecord[]>([]);
  const [form, setForm] = useState({ name: "", category: "", years: "", aliases: "", verified: false });
  const [tick, setTick] = useState(0);
  const { error, guard } = useAsyncError();

  useEffect(() => {
    let cancelled = false;
    profileApi.skills(profileId).then((s) => !cancelled && setSkills(s)).catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [profileId, tick]);

  async function add(event: FormEvent) {
    event.preventDefault();
    const ok = await guard(() =>
      profileApi.addSkill(profileId, {
        canonical_name: form.name, category: form.category || null, years_experience: form.years ? Number(form.years) : null,
        aliases: form.aliases.split(",").map((a) => a.trim()).filter(Boolean), verified: form.verified,
      }),
    );
    if (ok) {
      setForm({ name: "", category: "", years: "", aliases: "", verified: false });
      setTick((v) => v + 1);
    }
  }
  const act = async (work: () => Promise<unknown>) => {
    await guard(work);
    setTick((v) => v + 1);
  };

  return (
    <section aria-label="Skills">
      <h3>Skills</h3>
      {error && <p role="alert">{error}</p>}
      {skills.length === 0 ? <p>None yet.</p> : (
        <ul>
          {skills.map((s) => (
            <li key={s.skill_id}>
              <strong>{s.canonical_name}</strong>
              {s.category && ` (${s.category})`}
              {s.years_experience != null && ` · ${s.years_experience} yrs`}
              {s.verified && " · verified"}
              <div>
                Aliases:{" "}
                {s.aliases.length === 0 ? "none" : s.aliases.map((a) => (
                  <span key={a}>
                    {a} <button aria-label={`Remove alias ${a}`} onClick={() => void act(() => profileApi.removeAlias(profileId, s.skill_id, a))}>×</button>{" "}
                  </span>
                ))}
                <AliasAdder onAdd={(alias) => act(() => profileApi.addAlias(profileId, s.skill_id, alias))} label={s.canonical_name} />
              </div>
              <button onClick={() => void act(() => profileApi.saveSkill(profileId, s.skill_id, { verified: !s.verified }))}>
                {s.verified ? "Mark unverified" : "Mark verified"}
              </button>{" "}
              <button onClick={() => void act(() => profileApi.deleteSkill(profileId, s.skill_id))}>Remove</button>
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={(event) => void add(event)} aria-label="Add skill">
        <label htmlFor="sk-name">Skill</label> <input id="sk-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />{" "}
        <label htmlFor="sk-cat">Category</label> <input id="sk-cat" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} />{" "}
        <label htmlFor="sk-years">Years</label> <input id="sk-years" type="number" value={form.years} onChange={(e) => setForm({ ...form, years: e.target.value })} />{" "}
        <label htmlFor="sk-aliases">Aliases (comma separated)</label> <input id="sk-aliases" value={form.aliases} onChange={(e) => setForm({ ...form, aliases: e.target.value })} />{" "}
        <label><input type="checkbox" checked={form.verified} onChange={(e) => setForm({ ...form, verified: e.target.checked })} /> Verified</label>{" "}
        <button type="submit">Add skill</button>
      </form>
    </section>
  );
}

function AliasAdder({ onAdd, label }: { onAdd: (alias: string) => Promise<void>; label: string }) {
  const [value, setValue] = useState("");
  return (
    <span>
      <input aria-label={`New alias for ${label}`} value={value} onChange={(e) => setValue(e.target.value)} />{" "}
      <button type="button" disabled={!value.trim()} onClick={() => void onAdd(value.trim()).then(() => setValue(""))}>Add alias</button>
    </span>
  );
}

function SearchPreferences({ profileId }: { profileId: string }) {
  const [form, setForm] = useState<Record<string, string | boolean>>({ remote_preference: "NEUTRAL" });
  const [saved, setSaved] = useState(false);
  const { error, guard } = useAsyncError();
  const lists = ["allowed_countries", "allowed_regions", "allowed_cities", "employment_types", "excluded_companies", "preferred_companies", "excluded_industries", "preferred_industries"];
  const numbers = ["minimum_base_salary", "minimum_total_comp", "travel_percentage_max"];

  useEffect(() => {
    let cancelled = false;
    profileApi.searchPreferences(profileId).then((prefs) => {
      if (cancelled || !prefs) return;
      const next: Record<string, string | boolean> = { remote_preference: String(prefs.remote_preference ?? "NEUTRAL"), relocation_allowed: Boolean(prefs.relocation_allowed), currency: String(prefs.currency ?? "") };
      for (const l of lists) next[l] = Array.isArray(prefs[l]) ? (prefs[l] as string[]).join(", ") : "";
      for (const n of numbers) next[n] = prefs[n] == null ? "" : String(prefs[n]);
      setForm(next);
    }).catch(() => undefined);
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profileId]);

  async function save(event: FormEvent) {
    event.preventDefault();
    setSaved(false);
    const payload: Record<string, unknown> = { remote_preference: form.remote_preference, relocation_allowed: Boolean(form.relocation_allowed), currency: form.currency || null };
    for (const l of lists) payload[l] = String(form[l] ?? "").split(",").map((s) => s.trim()).filter(Boolean);
    for (const n of numbers) payload[n] = form[n] ? Number(form[n]) : null;
    if (await guard(() => profileApi.saveSearchPreferences(profileId, payload))) setSaved(true);
  }

  return (
    <form onSubmit={(event) => void save(event)} aria-label="Search preferences form">
      <h3>Search preferences</h3>
      {error && <p role="alert">{error}</p>}
      {saved && <p role="status">Saved. Evaluations for this profile will be refreshed.</p>}
      <div>
        <label htmlFor="sp-remote">Remote work</label>{" "}
        <select id="sp-remote" value={String(form.remote_preference)} onChange={(e) => setForm({ ...form, remote_preference: e.target.value })}>
          {REMOTE_POLICIES.map((p) => <option key={p}>{p}</option>)}
        </select>
      </div>
      {numbers.map((n) => (
        <div key={n}><label htmlFor={`sp-${n}`}>{n.replace(/_/g, " ")}</label> <input id={`sp-${n}`} type="number" value={String(form[n] ?? "")} onChange={(e) => setForm({ ...form, [n]: e.target.value })} /></div>
      ))}
      <div><label htmlFor="sp-currency">currency</label> <input id="sp-currency" maxLength={3} value={String(form.currency ?? "")} onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })} /></div>
      <div><label><input type="checkbox" checked={Boolean(form.relocation_allowed)} onChange={(e) => setForm({ ...form, relocation_allowed: e.target.checked })} /> Relocation allowed</label></div>
      {lists.map((l) => (
        <div key={l}><label htmlFor={`sp-${l}`}>{l.replace(/_/g, " ")}</label> <input id={`sp-${l}`} value={String(form[l] ?? "")} onChange={(e) => setForm({ ...form, [l]: e.target.value })} /> <small>comma separated</small></div>
      ))}
      <button type="submit">Save search preferences</button>
    </form>
  );
}

function Scoring({ profileId }: { profileId: string }) {
  const [weights, setWeights] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);
  const { error, guard } = useAsyncError();

  useEffect(() => {
    let cancelled = false;
    profileApi.scoring(profileId).then((s) => !cancelled && setWeights(Object.fromEntries(Object.entries(s?.weights ?? {}).map(([k, v]) => [k, String(v)])))).catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [profileId]);

  async function save(event: FormEvent) {
    event.preventDefault();
    setSaved(false);
    const payload = Object.fromEntries(Object.entries(weights).filter(([, v]) => v !== "").map(([k, v]) => [k, Number(v)]));
    if (await guard(() => profileApi.saveScoring(profileId, payload))) setSaved(true);
  }

  return (
    <form onSubmit={(event) => void save(event)} aria-label="Scoring form">
      <h3>Scoring weights</h3>
      <p>Leave a dimension empty to use the default. Dimensions without a signal for a job are skipped and the weights renormalised.</p>
      {error && <p role="alert">{error}</p>}
      {saved && <p role="status">Saved.</p>}
      {DIMENSIONS.map((d) => (
        <div key={d}>
          <label htmlFor={`w-${d}`}>{d.replace(/_/g, " ")}</label>{" "}
          <input id={`w-${d}`} type="number" step="0.01" min="0" value={weights[d] ?? ""} onChange={(e) => setWeights({ ...weights, [d]: e.target.value })} />
        </div>
      ))}
      <button type="submit">Save scoring</button>
    </form>
  );
}

function ExportImport({ profile, onImported }: { profile: Profile; onImported: () => void }) {
  const [text, setText] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const { error, guard } = useAsyncError();

  async function exportNow() {
    await guard(async () => {
      const data = await profileApi.exportProfile(profile.id);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `${profile.slug}-export.json`;
      link.click();
      URL.revokeObjectURL(link.href);
      setMessage(`Exported ${profile.display_name}.`);
    });
  }
  async function importNow() {
    setMessage(null);
    const ok = await guard(async () => {
      const created = await profileApi.importProfile(JSON.parse(text) as Record<string, unknown>);
      setMessage(`Imported as ${created.display_name}.`);
    });
    if (ok) {
      setText("");
      onImported();
    }
  }
  return (
    <section aria-label="Export and import">
      <h3>Export / import</h3>
      <p>Exports include every record of this profile (a versioned JSON file). Importing creates a new profile; its slug must be unique.</p>
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
      <button onClick={() => void exportNow()}>Export {profile.display_name}</button>
      <div>
        <label htmlFor="import-json">Paste an export to import</label><br />
        <textarea id="import-json" rows={5} value={text} onChange={(e) => setText(e.target.value)} />
      </div>
      <button disabled={!text.trim()} onClick={() => void importNow()}>Import</button>
    </section>
  );
}

const TABS = ["Overview", "Experience", "Achievements", "Skills", "Education", "Role targets", "Search preferences", "Scoring", "Portfolio", "Export / import"] as const;

export function ProfileEditor({ profile, onChanged }: { profile: Profile; onChanged: () => void }) {
  const [tab, setTab] = useState<(typeof TABS)[number]>("Overview");
  const id = profile.id;
  return (
    <section aria-label={`Editing ${profile.display_name}`}>
      <h2>{profile.display_name}</h2>
      <div role="tablist" aria-label="Profile sections">
        {TABS.map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}>{t}</button>
        ))}
      </div>
      {tab === "Overview" && <Overview key={id} profile={profile} onChanged={onChanged} />}
      {tab === "Experience" && <ItemsEditor key={id} profileId={id} kind="experiences" title="Experience" fields={EXPERIENCE} summary={(r) => `${String(r.title)} at ${String(r.organization)}`} />}
      {tab === "Achievements" && <ItemsEditor key={id} profileId={id} kind="achievements" title="Achievements" fields={ACHIEVEMENT} summary={(r) => `${String(r.title)}${r.verified ? " ✓ verified" : ""}`} />}
      {tab === "Skills" && <Skills key={id} profileId={id} />}
      {tab === "Education" && <ItemsEditor key={id} profileId={id} kind="education" title="Education" fields={EDUCATION} summary={(r) => `${String(r.institution)}${r.degree ? `: ${String(r.degree)}` : ""}`} />}
      {tab === "Role targets" && (
        <>
          <ItemsEditor key={`${id}-f`} profileId={id} kind="role-families" title="Role families" fields={ROLE_FAMILY} summary={(r) => `${String(r.name)}${r.enabled ? "" : " (disabled)"}`} />
          <ItemsEditor key={`${id}-t`} profileId={id} kind="role-targets" title="Role targets" fields={ROLE_TARGET} summary={(r) => String(r.title_pattern ?? "(any title)")} />
        </>
      )}
      {tab === "Search preferences" && <SearchPreferences key={id} profileId={id} />}
      {tab === "Scoring" && <Scoring key={id} profileId={id} />}
      {tab === "Portfolio" && <ItemsEditor key={id} profileId={id} kind="portfolio" title="Portfolio" fields={PORTFOLIO} summary={(r) => String(r.name)} />}
      {tab === "Export / import" && <ExportImport key={id} profile={profile} onImported={onChanged} />}
    </section>
  );
}
