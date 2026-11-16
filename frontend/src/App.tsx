import { FormEvent, useEffect, useState } from "react";
import { JobsHome } from "./features/jobs/JobsHome";
import { DuplicateReview } from "./features/duplicates/DuplicateReview";
import { IntegrationsPage } from "./features/integrations/IntegrationsPage";
import { Pipeline } from "./features/tracking/Pipeline";
import { ResumeVariants } from "./features/applications/ResumeVariants";
import { AiSettings } from "./features/settings/AiSettings";
import { SearchesPage } from "./features/searches/SearchesPage";
import { TaskList } from "./features/tasks/TaskList";
import { JobDetail } from "./features/jobs/JobDetail";
import { ProfileEditor } from "./features/profiles/ProfileEditor";
import { resolveActive, useActiveProfileId } from "./features/profiles/activeProfile";
import { BrowserRouter as Router, Routes, Route, Navigate } from "react-router-dom";

type Profile = { id: string; slug: string; display_name: string; headline: string | null; summary: string | null; timezone: string };
const apiUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export function App() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [activeId, setActiveId] = useActiveProfileId();
  const selected = profiles.find((p) => p.id === activeId) ?? null;
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState<string>("profiles"); // "profiles" or "jobs"
  const [demoMode, setDemoMode] = useState(false);

  useEffect(() => {
    fetch(`${apiUrl}/api/v1/config`)
      .then((response) => (response.ok ? response.json() : null))
      .then((config: { demo_mode?: boolean } | null) => setDemoMode(config?.demo_mode === true))
      .catch(() => setDemoMode(false));
  }, []);

  async function loadProfiles() {
    try {
      const response = await fetch(`${apiUrl}/api/v1/profiles`);
      if (!response.ok) throw new Error("Unable to load profiles");
      const data: Profile[] = await response.json();
      setProfiles(data);
      setActiveId((current) => resolveActive(current, data.map((p) => p.id)));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load profiles");
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => { void loadProfiles(); }, 0);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- load once on mount
  }, []);

  async function createProfile(event: FormEvent) {
    event.preventDefault();
    const slug = name.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
    if (!slug) return;
    const response = await fetch(`${apiUrl}/api/v1/profiles`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slug, display_name: name }),
    });
    if (!response.ok) {
      setError("Unable to create profile. Names must be unique.");
      return;
    }
    setName("");
    await loadProfiles();
  }

  return (
    <main>
      {demoMode && (
        <div role="status" className="demo-banner">
          Demo mode: all data is fictional and external actions are disabled.
        </div>
      )}
      <h1>CareerFlow</h1>
      <p>Profile-first job discovery and preparation, with people in control.</p>
      {error && <p role="alert">{error}</p>}
      <div className="tab-container">
        <button 
          className={activeTab === "profiles" ? "active" : ""}
          onClick={() => setActiveTab("profiles")}
        >
          Profiles
        </button>
        <button 
          className={activeTab === "jobs" ? "active" : ""}
          onClick={() => setActiveTab("jobs")}
        >
          Jobs
        </button>
        <button
          className={activeTab === "tasks" ? "active" : ""}
          onClick={() => setActiveTab("tasks")}
        >
          Tasks
        </button>
        <button
          className={activeTab === "duplicates" ? "active" : ""}
          onClick={() => setActiveTab("duplicates")}
        >
          Duplicates
        </button>
        <button
          className={activeTab === "searches" ? "active" : ""}
          onClick={() => setActiveTab("searches")}
        >
          Searches
        </button>
        <button
          className={activeTab === "settings" ? "active" : ""}
          onClick={() => setActiveTab("settings")}
        >
          Settings
        </button>
        <button
          className={activeTab === "resume" ? "active" : ""}
          onClick={() => setActiveTab("resume")}
        >
          Resume
        </button>
        <button
          className={activeTab === "pipeline" ? "active" : ""}
          onClick={() => setActiveTab("pipeline")}
        >
          Pipeline
        </button>
        <button
          className={activeTab === "integrations" ? "active" : ""}
          onClick={() => setActiveTab("integrations")}
        >
          Integrations
        </button>
      </div>
      
      <section className="content-area">
        {activeTab === "tasks" ? (
          <TaskList />
        ) : activeTab === "integrations" ? (
          <IntegrationsPage />
        ) : activeTab === "pipeline" ? (
          <Router>
            <Pipeline />
          </Router>
        ) : activeTab === "resume" ? (
          <ResumeVariants />
        ) : activeTab === "settings" ? (
          <AiSettings />
        ) : activeTab === "searches" ? (
          <SearchesPage />
        ) : activeTab === "duplicates" ? (
          <DuplicateReview />
        ) : activeTab === "profiles" ? (
          <section className="profile-layout">
            <aside>
              <h2>Profiles</h2>
              {profiles.map((profile) => (
                <button key={profile.id} aria-pressed={profile.id === activeId} onClick={() => setActiveId(profile.id)}>{profile.display_name}</button>
              ))}
              <form onSubmit={createProfile}>
                <label htmlFor="profile-name">New profile</label>
                <input id="profile-name" value={name} onChange={(event) => setName(event.target.value)} />
                <button type="submit">Create</button>
              </form>
            </aside>
            <section aria-live="polite">
              {selected ? <ProfileEditor key={selected.id} profile={{ ...selected, slug: selected.slug ?? "", timezone: selected.timezone ?? "UTC" }} onChanged={() => void loadProfiles()} /> : <p>No profiles yet.</p>}
            </section>
          </section>
        ) : (
          <Router>
            <Routes>
              <Route path="/" element={<JobsHome />} />
              <Route path="/jobs/:jobId" element={<JobDetail />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Router>
        )}
      </section>
    </main>
  );
}
