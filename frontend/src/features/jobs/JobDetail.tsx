import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import type { Job, JobEvaluation, JobRequirement, JobSource } from "./types";

// For demo, a fixed profile ID; this would come from auth/profile selection in a real app.
const profileId = "demo-profile-id";

const apiUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export function JobDetail() {
  const { jobId } = useParams();
  const navigate = useNavigate();
  const [job, setJob] = useState<Job | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [evaluation, setEvaluation] = useState<JobEvaluation | null>(null);
  const [evalLoading, setEvalLoading] = useState<boolean>(false);
  const [evalError, setEvalError] = useState<string | null>(null);

  // Mock data function - moved to top to avoid temporal dead zone issues
  const getMockJobById = (id: string) => {
    const mockJobs = [
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
          },
          {
            "type": "experience",
            "normalized_text": "LLM Applications",
            "source_text": "Experience building LLM applications and systems",
            "required_level": "ADVANCED",
            "category": "experience",
            "confidence": 0.85
          },
          {
            "type": "education",
            "normalized_text": "Master's in Computer Science",
            "source_text": "MS or PhD in Computer Science or related field",
            "required_level": "PREFERRED",
            "category": "education",
            "confidence": 0.7
          }
        ],
        "sources": [
          {
            "id": "src-1",
            "job_id": "1",
            "adapter": "manual",
            "external_id": "principal-ai-engineer-001",
            "source_url": "https://techinnovate.com/careers/principal-ai-engineer",
            "raw_payload": {
              "title": "Principal AI Engineer",
              "company": "TechInnovate Inc.",
              "description": "We are seeking a Principal AI Engineer to lead our AI initiatives and drive innovation in machine learning and artificial intelligence."
            },
            "discovered_at": "2026-09-30T10:00:00Z",
            "last_seen_at": "2026-09-30T10:00:00Z"
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
          },
          {
            "type": "skill",
            "normalized_text": "Statistical Analysis",
            "source_text": "Statistical modeling and analysis",
            "required_level": "ADVANCED",
            "category": "analytical_skill",
            "confidence": 0.8
          },
          {
            "type": "experience",
            "normalized_text": "Machine Learning",
            "source_text": "Applied machine learning in business contexts",
            "required_level": "ADVANCED",
            "category": "experience",
            "confidence": 0.75
          }
        ],
        "sources": [
          {
            "id": "src-2",
            "job_id": "2",
            "adapter": "manual",
            "external_id": "senior-data-scientist-002",
            "source_url": "https://datadrivensolutions.com/jobs/senior-data-scientist",
            "raw_payload": {
              "title": "Senior Data Scientist",
              "company": "DataDriven Solutions",
              "description": "Join our analytics team as a Senior Data Scientist to build predictive models and derive insights from complex datasets."
            },
            "discovered_at": "2026-09-30T11:00:00Z",
            "last_seen_at": "2026-09-30T11:00:00Z"
          }
        ]
      }
    ];
    
    return mockJobs.find(job => job.id === id) || null;
  };

  useEffect(() => {
    async function fetchJob() {
      if (!jobId) return;
      
      try {
        setLoading(true);
        const response = await fetch(`${apiUrl}/api/v1/jobs/${jobId}`);
        if (!response.ok) {
          // If API is not available or job not found, show mock data for demo
          const mockJob = getMockJobById(jobId);
          if (mockJob) {
            setJob(mockJob);
            setError("Using mock data - API not available");
          } else {
            setError("Job not found");
          }
        } else {
          const data = await response.json();
          setJob(data);
        }
      } catch {
        // If API is not available, show mock data for demo
        const mockJob = getMockJobById(jobId);
        if (mockJob) {
          setJob(mockJob);
          setError("Using mock data - API not available");
        } else {
          setError("Job not found");
        }
      } finally {
        setLoading(false);
      }
    }

    // Also fetch evaluation if we have a profile ID
    async function fetchEvaluation() {
      if (!jobId || !profileId) return;
      
      try {
        setEvalLoading(true);
        const response = await fetch(`${apiUrl}/api/v1/jobs/${jobId}/evaluations/latest?profile_id=${profileId}`);
        if (!response.ok) {
          // No evaluation found or error
          setEvalError("No evaluation found or unable to fetch");
        } else {
          const data = await response.json();
          setEvaluation(data);
        }
      } catch {
        setEvalError("Failed to fetch evaluation");
      } finally {
        setEvalLoading(false);
      }
    }

    fetchJob();
    fetchEvaluation();
  }, [jobId]);

  const handleJobAction = (action: string) => {
    if (!jobId) return;
    
    // For now, just simulate the action and go back to job list
    // In a real implementation, this would call the API
    alert(`${action.charAt(0).toUpperCase() + action.slice(1)} job action simulated`);
    navigate(-1); // Go back to previous page
  };

  const handleEvaluateJob = async () => {
    if (!jobId || !profileId) return;
    
    try {
      setEvalLoading(true);
      setEvalError(null);
      const response = await fetch(`${apiUrl}/api/v1/jobs/${jobId}/evaluations`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ profile_id: profileId }),
      });
      
      if (!response.ok) {
        throw new Error(`Failed to evaluate job: ${response.status}`);
      }
      
      const data = await response.json();
      setEvaluation(data);
    } catch {
      setEvalError("Failed to evaluate job");
    } finally {
      setEvalLoading(false);
    }
  };

  if (loading) return <div>Loading job details...</div>;
  if (error) return <div role="alert">Error: {error}</div>;
  if (!job) return <div>No job found.</div>;

  return (
    <div>
      <h2>Job Details</h2>
      <div className="job-detail">
        <div className="job-header">
          <h1>{job.title}</h1>
          <div className="job-meta">
            <span><strong>Company:</strong> {job.company}</span>
            <span><strong>Location:</strong> {job.location_text || "Not specified"}</span>
            {job.remote_type && (
              <span><strong>Remote:</strong> {job.remote_type}</span>
            )}
          </div>
          {job.salary_min && job.salary_max && job.salary_currency && (
            <div className="salary">
              <strong>Salary:</strong> {job.salary_currency} {job.salary_min} - {job.salary_max} {job.salary_period}
            </div>
          )}
        </div>
        
        {job.description_html && (
          <div className="job-description" dangerouslySetInnerHTML={{ __html: job.description_html }} />
        )}
        
        {!job.description_html && job.description_text && (
          <div className="job-description">
            <h3>Description</h3>
            <p>{job.description_text}</p>
          </div>
        )}
        
        {/* Requirements */}
        {job.requirements && job.requirements.length > 0 && (
          <div className="job-section">
            <h3>Requirements</h3>
            <ul>
              {job.requirements.map((req: JobRequirement, index: number) => (
                <li key={index}>
                  <strong>{req.type}:</strong> {req.normalized_text} 
                  {req.required_level && ` (${req.required_level})`}
                </li>
              ))}
            </ul>
          </div>
        )}
        
        {/* Source Information */}
        {job.sources && job.sources.length > 0 && (
          <div className="job-section">
            <h3>Source Information</h3>
            <p><strong>Discovered:</strong> {new Date(job.discovered_at).toLocaleDateString()}</p>
            {job.sources.map((source: JobSource, index: number) => (
              <div key={index} className="source-item">
                <strong>Source:</strong> {source.adapter} 
                {source.external_id && ` (ID: ${source.external_id})`}
                {source.source_url && (
                  <a href={source.source_url} target="_blank" rel="noopener noreferrer">
                    View Original
                  </a>
                )}
              </div>
            ))}
          </div>
        )}
        
        {/* Evaluation Information */}
        {evaluation && (
          <div className="job-section">
            <h3>Evaluation</h3>
            <div className="evaluation-content">
              <div className="evaluation-score">
                <strong>Overall Score:</strong> {(evaluation.overall_score * 100).toFixed(0)}%
                <span className="evaluation-confidence">(Confidence: {(evaluation.confidence || 0.85) * 100}.0%)</span>
              </div>
              
              {evaluation.explanation && (
                <p className="evaluation-explanation"><strong>Explanation:</strong> {evaluation.explanation}</p>
              )}
              
              {evaluation.strengths && evaluation.strengths.length > 0 && (
                <div className="evaluation-strengths">
                  <strong>Strengths:</strong>
                  <ul>
                    {evaluation.strengths.map((strength: string, index: number) => (
                      <li key={index}>{strength}</li>
                    ))}
                  </ul>
                </div>
              )}
              
              {evaluation.gaps && evaluation.gaps.length > 0 && (
                <div className="evaluation-gaps">
                  <strong>Gaps:</strong>
                  <ul>
                    {evaluation.gaps.map((gap: string, index: number) => (
                      <li key={index}>{gap}</li>
                    ))}
                  </ul>
                </div>
              )}
              
              {evaluation.blockers && evaluation.blockers.length > 0 && (
                <div className="evaluation-blockers">
                  <strong>Blockers:</strong>
                  <ul>
                    {evaluation.blockers.map((blocker: string, index: number) => (
                      <li key={index}>{blocker}</li>
                    ))}
                  </ul>
                </div>
              )}
              
              {evaluation.dimension_scores_json && Object.keys(evaluation.dimension_scores_json).length > 0 && (
                <div className="evaluation-dimensions">
                  <strong>Dimension Scores:</strong>
                  <ul>
                    {Object.entries(evaluation.dimension_scores_json).map(([dimension, score], index: number) => (
                      <li key={index}>
                        <strong>{dimension}:</strong> {(Number(score) * 100).toFixed(0)}%
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        )}
        
        {/* Evaluate Button */}
        {!evaluation && !evalLoading && (
          <div className="job-section">
            <button 
              className="btn-info"
              onClick={handleEvaluateJob}
              disabled={evalLoading}
            >
              {evalLoading ? "Evaluating..." : "Evaluate Job"}
            </button>
          </div>
        )}
        
        {evalError && (
          <div className="job-section evaluation-error">
            <strong>Evaluation Error:</strong> {evalError}
          </div>
        )}
        
        {/* Workflow Actions */}
        <div className="job-actions">
          <button 
            className="btn-primary"
            onClick={() => handleJobAction('shortlist')}
          >
            Shortlist
          </button>
          <button 
            className="btn-secondary"
            onClick={() => handleJobAction('save')}
          >
            Save
          </button>
          <button 
            className="btn-danger"
            onClick={() => handleJobAction('reject')}
          >
            Reject
          </button>
        </div>
      </div>
    </div>
  );
}