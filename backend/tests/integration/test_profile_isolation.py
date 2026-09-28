from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from careerflow.application.profiles.service import ProfileService
from careerflow.infrastructure.database.models import Base


def test_profile_scoped_records_are_isolated() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        service = ProfileService(session)
        first = service.create_profile({"slug": "first", "display_name": "First"})
        second = service.create_profile({"slug": "second", "display_name": "Second"})
        first_experience = service.add_experience(
            first.id, {"organization": "One", "title": "Engineer"}
        )
        service.add_experience(second.id, {"organization": "Two", "title": "Scientist"})

        assert [item.id for item in service.list_experiences(first.id)] == [first_experience.id]

        try:
            service.add_achievement(
                second.id,
                {"title": "Not allowed", "experience_id": first_experience.id},
            )
        except ValueError as error:
            assert str(error) == "experience must belong to the selected profile"
        else:
            raise AssertionError("cross-profile experience should not be accepted")
