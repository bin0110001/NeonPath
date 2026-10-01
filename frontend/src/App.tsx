import { FormEvent, useEffect, useState } from "react";
import { JobList } from "./features/jobs/JobList";
import { JobDetail } from "./features/jobs/JobDetail";
import { BrowserRouter as Router, Routes, Route, Navigate } from "react-router-dom";

type Profile = { id: string; display_name: string; headline: string | null; summary: string | null };
const apiUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export function App() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [selected, setSelected] = useState<Profile | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState<string>("profiles"); // "profiles" or "jobs"

  async function loadProfiles() {
    try {
      const response = await fetch(`${apiUrl}/api/v1/profiles`);
      if (!response.ok) throw new Error("Unable to load profiles");
      const data: Profile[] = await response.json();
      setProfiles(data);
      setSelected((current) => current ?? data[0] ?? null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load profiles");
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => { void loadProfiles(); }, 0);
    return () => window.clearTimeout(timer);
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
      </div>
      
      <section className="content-area">
        {activeTab === "profiles" ? (
          <section className="profile-layout">
            <aside>
              <h2>Profiles</h2>
              {profiles.map((profile) => (
                <button key={profile.id} onClick={() => setSelected(profile)}>{profile.display_name}</button>
              ))}
              <form onSubmit={createProfile}>
                <label htmlFor="profile-name">New profile</label>
                <input id="profile-name" value={name} onChange={(event) => setName(event.target.value)} />
                <button type="submit">Create</button>
              </form>
            </aside>
            <section aria-live="polite">
              {selected ? <><h2>{selected.display_name}</h2><h3>{selected.headline}</h3><p>{selected.summary ?? "No summary yet."}</p></> : <p>No profiles yet.</p>}
            </section>
          </section>
        ) : (
          <Router>
            <Routes>
              <Route path="/" element={<JobList />} />
              <Route path="/jobs/:jobId" element={<JobDetail />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Router>
        )}
      </section>
    </main>
  );
}
