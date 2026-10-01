import { useEffect, useState } from "react";

const apiUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

// Mock data function - moved to top to avoid temporal dead zone issues
const getMockJobs = () => {
  return [
    {
      "id": "1",
      "title": "Principal AI Engineer",
      "company": "TechInnovate Inc.",
      "company_domain": "techinnovate.com",
      "description_text": "We are seeking a Principal AI Engineer to lead our AI initiatives and drive innovation in machine learning and artificial intelligence. The ideal candidate will have deep expertise in LLMs, MLOps, and AI system architecture.",
      "description_html": "<p>We are seeking a Principal AI Engineer to lead our AI initiatives and drive innovation in machine learning and artificial intelligence. The ideal candidate will have deep expertise in LLMs, MLOps, and AI system architecture.</p>",
      "location_text": "San Francisco, CA (Remote)",
      "remote_type": "REMOTE",
      "employment_type": "FULL_TIME",
      "salary_min": 180000,
      "salary_max": 250000,
      "salary_currency": "USD",
      "salary_period": "YEAR",
      "canonical_url": "https://techinnovate.com/careers/principal-ai-engineer",
      "discovered_at": "2026-09-30T10:00:00Z",
      "requirements": [
        {
          "type": "skill",
          "normalized_text": "Python",
          "source_text": "Python programming",
          "required_level": "EXPERT",
          "category": "programming_language",
          "confidence": 0.95
        },
        {
          "type": "skill",
          "normalized_text": "Machine Learning",
          "source_text": "Machine Learning and Deep Learning",
          "required_level": "EXPERT",
          "category": "technical_skill",
          "confidence": 0.9
        }
      ],
      "sources": [
        {
          "adapter": "manual",
          "external_id": "principal-ai-engineer-001",
          "source_url": "https://techinnovate.com/careers/principal-ai-engineer",
          "discovered_at": "2026-09-30T10:00:00Z"
        }
      ]
    },
    {
      "id": "2",
      "title": "Senior Data Scientist",
      "company": "DataDriven Solutions",
      "company_domain": "datadrivensolutions.com",
      "description_text": "Join our analytics team as a Senior Data Scientist to build predictive models and derive insights from complex datasets. You'll work with Python, SQL, and modern ML frameworks to solve business problems.",
      "description_html": "<p>Join our analytics team as a Senior Data Scientist to build predictive models and derive insights from complex datasets. You'll work with Python, SQL, and modern ML frameworks to solve business problems.</p>",
      "location_text": "New York, NY (Hybrid)",
      "remote_type": "HYBRID",
      "employment_type": "FULL_TIME",
      "salary_min": 120000,
      "salary_max": 160000,
      "salary_currency": "USD",
      "salary_period": "YEAR",
      "canonical_url": "https://datadrivensolutions.com/jobs/senior-data-scientist",
      "discovered_at": "2026-09-30T11:00:00Z",
      "requirements": [
        {
          "type": "skill",
          "normalized_text": "Python",
          "source_text": "Python programming",
          "required_level": "EXPERT",
          "category": "programming_language",
          "confidence": 0.9
        },
        {
          "type": "skill",
          "normalized_text": "SQL",
          "source_text": "SQL and database querying",
          "required_level": "EXPERT",
          "category": "programming_language",
          "confidence": 0.85
        }
      ],
      "sources": [
        {
          "adapter": "manual",
          "external_id": "senior-data-scientist-002",
          "source_url": "https://datadrivensolutions.com/jobs/senior-data-scientist",
          "discovered_at": "2026-09-30T11:00:00Z"
        }
      ]
    }
  ];
};

export function JobList() {
  const [jobs, setJobs] = useState<Array<any>>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchJobs() {
      try {
        setLoading(true);
        const response = await fetch(`${apiUrl}/api/v1/jobs`);
        if (!response.ok) {
          // If API is not available, show mock data for demo
          setJobs(getMockJobs());
          setError("Using mock data - API not available");
        } else {
          const data = await response.json();
          setJobs(data);
        }
      } catch (err) {
        // If API is not available, show mock data for demo
        setJobs(getMockJobs());
        setError("Using mock data - API not available");
      } finally {
        setLoading(false);
      }
    }

    fetchJobs();
  }, []);

  if (loading) return <div>Loading jobs...</div>;
  if (error) return <div role="alert">Error: {error}</div>;

  return (
    <div>
      <h2>Job Listings</h2>
      {jobs.length === 0 ? (
        <p>No jobs found.</p>
      ) : (
        <ul>
          {jobs.map((job) => (
            <li key={job.id}>
              <h3>{job.title}</h3>
              <p><strong>Company:</strong> {job.company}</p>
              <p><strong>Location:</strong> {job.location_text || "Not specified"}</p>
              {job.remote_type && (
                <p><strong>Remote:</strong> {job.remote_type}</p>
              )}
              {job.salary_min && job.salary_max && job.salary_currency && (
                <p><strong>Salary:</strong> {job.salary_currency} {job.salary_min} - {job.salary_max} {job.salary_period}</p>
              )}
              <p><strong>Discovered:</strong> {new Date(job.discovered_at).toLocaleDateString()}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}