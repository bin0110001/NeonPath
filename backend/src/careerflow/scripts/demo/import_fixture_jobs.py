"""
Demo job data import script for CareerFlow.
This script can be used to populate the system with sample job data for testing and demonstrations.
"""

import json
import sys
from pathlib import Path

from sqlalchemy.orm import Session

# Add the backend/src directory to the path so we can import careerflow modules
backend_src_path = Path(__file__).parent.parent.parent / "backend" / "src"
sys.path.insert(0, str(backend_src_path))

from careerflow.application.jobs.service import JobService
from careerflow.infrastructure.database.session import create_database_engine


def load_fixture_jobs(fixture_path: Path) -> list[dict]:
    """Load job fixtures from a JSON file."""
    with open(fixture_path, "r") as f:
        return json.load(f)


def import_fixture_jobs(jobs_data: list[dict]) -> None:
    """Import job data into the database."""
    with Session(create_database_engine()) as session:
        service = JobService(session)
        
        for job_data in jobs_data:
            try:
                # Check if job already exists by canonical_url or title+company
                existing_jobs = session.scalars(
                    select(JobModel).where(
                        (JobModel.canonical_url == job_data.get("canonical_url")) |
                        ((JobModel.title == job_data["title"]) & (JobModel.company == job_data["company"]))
                    )
                ).all()
                
                if existing_jobs:
                    print(f"Job already exists: {job_data['title']} at {job_data['company']}")
                    continue
                
                # Create the job
                job = service.create_job(job_data)
                print(f"Created job: {job.title} at {job.company}")
                
                # Add source record if provided
                if "source" in job_data:
                    source_data = job_data["source"]
                    source_data["job_id"] = job.id
                    service.add_source_record(job.id, source_data)
                    
                # Add requirements if provided
                if "requirements" in job_data:
                    for req_data in job_data["requirements"]:
                        req_data["job_id"] = job.id
                        service.add_requirement(job.id, req_data)
                        
            except Exception as e:
                print(f"Error importing job {job_data.get('title', 'Unknown')}: {e}")
                session.rollback()
                continue
        
        session.commit()


def main():
    """Main function to run the fixture import."""
    if len(sys.argv) < 2:
        print("Usage: python import_fixture_jobs.py <fixture_file.json>")
        sys.exit(1)
    
    fixture_path = Path(sys.argv[1])
    if not fixture_path.exists():
        print(f"Fixture file not found: {fixture_path}")
        sys.exit(1)
    
    print(f"Loading fixture data from: {fixture_path}")
    jobs_data = load_fixture_jobs(fixture_path)
    print(f"Loaded {len(jobs_data)} jobs from fixture")
    
    print("Importing jobs...")
    import_fixture_jobs(jobs_data)
    print("Import completed!")


if __name__ == "__main__":
    # Import here to avoid issues with path modification
    from sqlalchemy import select
    from careerflow.infrastructure.database.models import JobModel
    main()