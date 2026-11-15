export const PAGE_SIZE = 10;

export interface InboxFilters {
  status: string;
  minScore: string;
  remoteType: string;
  company: string;
  location: string;
  sort: "discovered_at" | "score" | "title";
}

export const defaultFilters: InboxFilters = {
  status: "",
  minScore: "",
  remoteType: "",
  company: "",
  location: "",
  sort: "discovered_at",
};

export function buildJobsQuery(profileId: string, filters: InboxFilters, page: number): string {
  const params = new URLSearchParams({ profile_id: profileId, sort: filters.sort });
  if (filters.status) params.set("status", filters.status);
  if (filters.minScore) params.set("min_score", String(Number(filters.minScore) / 100));
  if (filters.remoteType) params.set("remote_type", filters.remoteType);
  if (filters.company) params.set("company", filters.company);
  if (filters.location) params.set("location", filters.location);
  params.set("limit", String(PAGE_SIZE));
  params.set("offset", String(page * PAGE_SIZE));
  return params.toString();
}
