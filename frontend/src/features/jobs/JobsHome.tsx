import { resolveActive, useActiveProfileId } from "../profiles/activeProfile";
import { useEffect, useState } from "react";
import { Dashboard } from "./Dashboard";
import { ImportJob } from "./ImportJob";
import { type InboxFilters, defaultFilters } from "./inbox";
import { JobList } from "./JobList";
import type { ProfileSummary } from "./types";

const apiUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const STATUSES = ["READY_FOR_REVIEW", "SHORTLISTED", "SAVED", "REJECTED", "ARCHIVED", "APPLIED"];

export function JobsHome() {
  const [profiles, setProfiles] = useState<ProfileSummary[]>([]);
  const [profileId, setProfileId] = useActiveProfileId();
  const [filters, setFilters] = useState<InboxFilters>(defaultFilters);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${apiUrl}/api/v1/profiles`)
      .then((response) => {
        if (!response.ok) throw new Error("Unable to load profiles");
        return response.json() as Promise<ProfileSummary[]>;
      })
      .then((data) => {
        setProfiles(data);
        setProfileId((current) => resolveActive(current, data.map((p) => p.id)));
      })
      .catch((reason: unknown) =>
        setError(reason instanceof Error ? reason.message : "Unable to load profiles"),
      );
  }, [setProfileId]);

  const set = <K extends keyof InboxFilters>(key: K, value: InboxFilters[K]) =>
    setFilters((current) => ({ ...current, [key]: value }));

  if (error) return <div role="alert">Error: {error}</div>;
  if (!profileId) return <p>Create a profile to start reviewing jobs.</p>;

  return (
    <div>
      <div>
        <label htmlFor="inbox-profile">Active profile</label>{" "}
        <select id="inbox-profile" value={profileId} onChange={(e) => setProfileId(e.target.value)}>
          {profiles.map((profile) => (
            <option key={profile.id} value={profile.id}>
              {profile.display_name}
            </option>
          ))}
        </select>
      </div>
      <Dashboard profileId={profileId} onSelectStatus={(status) => set("status", status)} />
      <ImportJob />
      <fieldset>
        <legend>Filters</legend>
        <label htmlFor="f-status">Status</label>{" "}
        <select id="f-status" value={filters.status} onChange={(e) => set("status", e.target.value)}>
          <option value="">Any</option>
          {STATUSES.map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>{" "}
        <label htmlFor="f-score">Min fit %</label>{" "}
        <input
          id="f-score"
          type="number"
          min={0}
          max={100}
          value={filters.minScore}
          onChange={(e) => set("minScore", e.target.value)}
        />{" "}
        <label htmlFor="f-remote">Arrangement filter</label>{" "}
        <select id="f-remote" value={filters.remoteType} onChange={(e) => set("remoteType", e.target.value)}>
          <option value="">Any</option>
          <option>REMOTE</option>
          <option>HYBRID</option>
          <option>ONSITE</option>
        </select>{" "}
        <label htmlFor="f-company">Employer contains</label>{" "}
        <input id="f-company" value={filters.company} onChange={(e) => set("company", e.target.value)} />{" "}
        <label htmlFor="f-location">Place contains</label>{" "}
        <input id="f-location" value={filters.location} onChange={(e) => set("location", e.target.value)} />{" "}
        <label htmlFor="f-sort">Sort by</label>{" "}
        <select
          id="f-sort"
          value={filters.sort}
          onChange={(e) => set("sort", e.target.value as InboxFilters["sort"])}
        >
          <option value="discovered_at">Newest</option>
          <option value="score">Best fit</option>
          <option value="title">Title</option>
        </select>
      </fieldset>
      <JobList key={`${profileId}|${JSON.stringify(filters)}`} profileId={profileId} filters={filters} />
    </div>
  );
}
