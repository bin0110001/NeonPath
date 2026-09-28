from sqlalchemy import select
from sqlalchemy.orm import Session

from careerflow.infrastructure.database.models import (
    AchievementModel,
    ExperienceModel,
    ProfileContactModel,
    ProfileModel,
)
from careerflow.infrastructure.database.session import create_database_engine


def seed_demo_data() -> None:
    """Create safe, fictional demo profiles once; never overwrite user data."""
    with Session(create_database_engine()) as session:
        if session.scalar(select(ProfileModel.id).limit(1)) is not None:
            return
        jordan = ProfileModel(
            slug="jordan-lee",
            display_name="Jordan Lee",
            headline="Principal Software / AI Engineer",
            summary="Fictional demo profile for platform architecture and applied AI roles.",
            timezone="America/New_York",
        )
        morgan = ProfileModel(
            slug="morgan-rivera",
            display_name="Morgan Rivera",
            headline="Senior Data Scientist",
            summary="Fictional demo profile for analytics, experimentation, and forecasting roles.",
            timezone="America/Chicago",
        )
        session.add_all([jordan, morgan])
        session.flush()
        session.add_all(
            [
                ProfileContactModel(profile_id=jordan.id, full_name="Jordan Lee"),
                ProfileContactModel(profile_id=morgan.id, full_name="Morgan Rivera"),
                ExperienceModel(
                    profile_id=jordan.id,
                    organization="Northstar Systems",
                    title="Principal Engineer",
                    description="Led cloud platforms, distributed systems, and LLM applications.",
                ),
                ExperienceModel(
                    profile_id=morgan.id,
                    organization="Cedar Analytics",
                    title="Senior Data Scientist",
                    description="Built forecasting and experimentation products using Python and SQL.",
                ),
                AchievementModel(
                    profile_id=jordan.id,
                    title="Production AI platform",
                    action="Designed a governed LLM application platform for product teams.",
                    technologies=["Python", "C#", "Cloud architecture", "LLM applications"],
                    verified=True,
                ),
                AchievementModel(
                    profile_id=morgan.id,
                    title="Forecasting program",
                    action="Improved demand forecasting through experiment design and ML modeling.",
                    technologies=["Python", "SQL", "Machine learning", "Visualization"],
                    verified=True,
                ),
            ]
        )
        session.commit()


if __name__ == "__main__":
    seed_demo_data()
