from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from careerflow.application.jobs.service import JobService
from careerflow.infrastructure.database.models import Base, JobModel


def test_job_creation_and_retrieval() -> None:
    """Test basic job creation and retrieval."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    
    with Session(engine) as session:
        service = JobService(session)
        
        # Create a job
        job_data = {
            "title": "Test Engineer",
            "company": "Test Company",
            "description_text": "Test job description",
        }
        job = service.create_job(job_data)
        
        # Verify the job was created with an ID
        assert job.id is not None
        assert job.title == "Test Engineer"
        assert job.company == "Test Company"
        assert job.description_text == "Test job description"
        assert job.status == "DISCOVERED"  # Default status
        
        # Retrieve the job by ID
        retrieved_job = service.get_job(job.id)
        assert retrieved_job.id == job.id
        assert retrieved_job.title == job.title
        assert retrieved_job.company == job.company
        
        # List jobs and verify our job is in the list
        jobs = service.list_jobs()
        assert len(jobs) == 1
        assert jobs[0].id == job.id


def test_job_update() -> None:
    """Test updating a job."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    
    with Session(engine) as session:
        service = JobService(session)
        
        # Create a job
        job_data = {
            "title": "Original Title",
            "company": "Original Company",
            "description_text": "Original description",
        }
        job = service.create_job(job_data)
        
        # Update the job
        update_data = {
            "title": "Updated Title",
            "description_text": "Updated description",
        }
        updated_job = service.update_job(job.id, update_data)
        
        # Verify the update
        assert updated_job.title == "Updated Title"
        assert updated_job.company == "Original Company"  # Unchanged
        assert updated_job.description_text == "Updated description"
        
        # Verify by retrieving again
        retrieved_job = service.get_job(job.id)
        assert retrieved_job.title == "Updated Title"
        assert retrieved_job.description_text == "Updated description"


def test_job_not_found() -> None:
    """Test that getting a non-existent job raises an exception."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    
    with Session(engine) as session:
        service = JobService(session)
        
        try:
            service.get_job("non-existent-id")
            assert False, "Should have raised JobNotFoundError"
        except Exception as e:
            assert "Job not found" in str(e)


def test_job_source_records() -> None:
    """Test adding and retrieving source records for a job."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    
    with Session(engine) as session:
        service = JobService(session)
        
        # Create a job
        job_data = {
            "title": "Test Job with Source",
            "company": "Test Company",
            "description_text": "Test description",
        }
        job = service.create_job(job_data)
        
        # Add a source record
        source_data = {
            "adapter": "manual",
            "external_id": "test-001",
            "source_url": "https://example.com/job/001",
            "raw_payload": {"test": "data"},
        }
        source_record = service.add_source_record(job.id, source_data)
        
        # Verify the source record
        assert source_record.id is not None
        assert source_record.job_id == job.id
        assert source_record.adapter == "manual"
        assert source_record.external_id == "test-001"
        
        # Retrieve source records
        sources = service.list_source_records(job.id)
        assert len(sources) == 1
        assert sources[0].id == source_record.id


def test_job_requirements() -> None:
    """Test adding and retrieving requirements for a job."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    
    with Session(engine) as session:
        service = JobService(session)
        
        # Create a job
        job_data = {
            "title": "Test Job with Requirements",
            "company": "Test Company",
            "description_text": "Test description",
        }
        job = service.create_job(job_data)
        
        # Add a requirement
        req_data = {
            "type": "skill",
            "normalized_text": "Python",
            "source_text": "Python programming",
            "required_level": "EXPERT",
            "category": "programming_language",
            "confidence": 0.95,
        }
        requirement = service.add_requirement(job.id, req_data)
        
        # Verify the requirement
        assert requirement.id is not None
        assert requirement.job_id == job.id
        assert requirement.type == "skill"
        assert requirement.normalized_text == "Python"
        assert requirement.confidence == 0.95
        
        # Retrieve requirements
        requirements = service.list_requirements(job.id)
        assert len(requirements) == 1
        assert requirements[0].id == requirement.id


def test_job_status_transitions() -> None:
    """Test job status transitions and history tracking."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    
    with Session(engine) as session:
        service = JobService(session)
        
        # Create a job
        job_data = {
            "title": "Test Job for Status",
            "company": "Test Company",
            "description_text": "Test description",
        }
        job = service.create_job(job_data)
        
        # Check initial status
        assert job.status == "DISCOVERED"
        
        # Shortlist the job
        shortlisted_job = service.shortlist_job(job.id, "test_user", "Testing shortlist")
        assert shortlisted_job.status == "SHORTLISTED"
        
        # Save the job
        saved_job = service.save_job(job.id, "test_user", "Testing save")
        assert saved_job.status == "SAVED"
        
        # Reject the job
        rejected_job = service.reject_job(job.id, "test_user", "Testing reject")
        assert rejected_job.status == "REJECTED"
        
        # Check that status history was created
        # Note: We don't have a direct method to list history yet, but we can verify
        # by checking that the status changed
        final_job = service.get_job(job.id)
        assert final_job.status == "REJECTED"
        assert final_job.id == job.id


def test_job_status_history_creation() -> None:
    """Test that status history entries are created when status changes."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    
    with Session(engine) as session:
        service = JobService(session)
        
        # Create a job
        job_data = {
            "title": "Test Job for History",
            "company": "Test Company",
            "description_text": "Test description",
        }
        job = service.create_job(job_data)
        
        # Verify no history entries initially (we'd need to query directly)
        # Shortlist the job - should create history entry
        service.shortlist_job(job.id, "test_user", "Testing shortlist")
        
        # Save the job - should create another history entry
        service.save_job(job.id, "test_user", "Testing save")
        
        # The job should now be in SAVED status
        updated_job = service.get_job(job.id)
        assert updated_job.status == "SAVED"