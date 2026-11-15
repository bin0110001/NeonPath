from __future__ import annotations

import hashlib
import io
import os
import zipfile
from collections.abc import Generator
from pathlib import Path

import pytest
from docx import Document as read_docx
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from careerflow.api.artifacts import get_session as artifacts_session
from careerflow.api.profiles import get_session as profiles_session
from careerflow.api.resume import get_session as resume_session
from careerflow.domain.artifacts.ports import (
    AchievementBlock,
    ContactBlock,
    EducationBlock,
    ExperienceBlock,
    ResumeDocument,
    redact,
    scrub_contact_details,
)
from careerflow.infrastructure.artifacts.registry import RENDERERS
from careerflow.infrastructure.database.models import (
    ApplicationPackageModel,
    Base,
    JobModel,
    ProfileContactModel,
    ProfileModel,
)
from careerflow.main import create_app
from careerflow.seed import seed_session

GOLDEN = Path(__file__).parent.parent / "golden"

DOC = ResumeDocument(
    name="Jordan Lee",
    headline="Principal Software / AI Engineer",
    summary="Builds governed LLM platforms. Reach me at jordan@example.com or +1 (555) 010-0199.",
    contact=ContactBlock("Jordan Lee", "jordan@example.com", "+1 555 010 0199", "Austin, Texas", ("https://example.com/jordan",)),
    skills=("Python", "C#", "Azure"),
    experiences=(ExperienceBlock("Principal Engineer", "Northstar Systems", "2019 - present", "Remote", "Led cloud platforms & <distributed> systems."),),
    achievements=(AchievementBlock("Production AI platform", "Designed a governed LLM platform.", ("Python", "LLM"), True),),
    education=(EducationBlock("Fictional University", "BSc", "Computer Science", "2005 - 2009"),),
    cover_letter_notes=("Mention the platform migration.",),
    target="Principal AI Engineer at Contoso",
)


def text_of(fmt: str, data: bytes) -> str:
    if fmt == "docx":
        return "\n".join(p.text for p in read_docx(io.BytesIO(data)).paragraphs) + "\n"
    if fmt == "pdf":
        return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(data)).pages).strip() + "\n"
    return data.decode("utf-8")


GOLDEN_FILES = {"markdown": "resume.md", "html": "resume.html", "docx": "resume.docx.txt", "pdf": "resume.pdf.txt"}


@pytest.mark.parametrize("fmt", sorted(GOLDEN_FILES))
def test_golden_output(fmt: str) -> None:
    """Rendered output (text content for the binary formats) must match the reviewed golden file.
    Regenerate deliberately with UPDATE_GOLDEN=1 and review the diff."""
    actual = text_of(fmt, RENDERERS[fmt].render(DOC))
    path = GOLDEN / GOLDEN_FILES[fmt]
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN.mkdir(exist_ok=True)
        path.write_text(actual, encoding="utf-8", newline="\n")
    assert actual == path.read_text(encoding="utf-8").replace("\r\n", "\n")


@pytest.mark.parametrize("fmt", sorted(RENDERERS))
def test_rendering_is_deterministic_and_well_formed(fmt: str) -> None:
    renderer = RENDERERS[fmt]
    first, second = renderer.render(DOC), renderer.render(DOC)
    assert first == second and hashlib.sha256(first).digest() == hashlib.sha256(second).digest()
    assert renderer.version and renderer.extension and renderer.content_type
    if fmt == "pdf":
        assert first.startswith(b"%PDF-")
    if fmt == "docx":
        names = zipfile.ZipFile(io.BytesIO(first)).namelist()
        assert "word/document.xml" in names and names == sorted(names)
        assert {i.date_time for i in zipfile.ZipFile(io.BytesIO(first)).infolist()} == {(2000, 1, 1, 0, 0, 0)}


def test_html_escapes_everything() -> None:
    nasty = ResumeDocument(name="<script>alert(1)</script>", summary='"><img src=x onerror=alert(1)>', skills=("<b>x</b>",))
    html = RENDERERS["html"].render(nasty).decode()
    assert "<script>" not in html and "<img" not in html and "<b>x" not in html
    assert "&lt;script&gt;" in html and "&lt;img src=x onerror=alert(1)&gt;" in html


def test_pdf_degrades_non_latin_text_instead_of_failing() -> None:
    doc = ResumeDocument(name="Zoë Łukasz 山田", summary="naïve café 日本語")
    assert text_of("pdf", RENDERERS["pdf"].render(doc)).startswith("Zoë")  # Latin-1 survives, the rest becomes ?
    assert "?" in text_of("pdf", RENDERERS["pdf"].render(doc))
    assert "山田" in RENDERERS["markdown"].render(doc).decode()  # other formats keep full Unicode


# --- redaction -------------------------------------------------------------------------------------


def test_redacted_copy_has_no_contact_details_anywhere() -> None:
    public = redact(DOC)
    assert public.redacted and public.contact is None
    for fmt in sorted(RENDERERS):
        text = text_of(fmt, RENDERERS[fmt].render(public))
        for secret in ("jordan@example.com", "555", "example.com/jordan", "Austin"):
            assert secret not in text, (fmt, secret)
    assert "[email removed]" in public.summary and "[phone removed]" in public.summary  # type: ignore[operator]


def test_scrub_contact_details() -> None:
    assert scrub_contact_details(None) is None
    assert scrub_contact_details("mail a.b+c@x-y.org now") == "mail [email removed] now"
    assert scrub_contact_details("call 555-123-4567 or +44 20 7946 0958") == "call [phone removed] or [phone removed]"
    assert scrub_contact_details("see https://x.io/p?q=1 and www.y.com") == "see [link removed] and [link removed]"
    assert scrub_contact_details("2019 - 2024 and 40 teams") == "2019 - 2024 and 40 teams"  # dates/numbers survive
    assert scrub_contact_details("(555) 123-4567") == "[phone removed]"


def test_document_json_round_trip() -> None:
    assert ResumeDocument.from_json(DOC.to_json()) == DOC
    assert ResumeDocument.from_json(redact(DOC).to_json()) == redact(DOC)


# --- service / API -----------------------------------------------------------------------------------


@pytest.fixture
def env() -> Generator[tuple[TestClient, Session]]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = Session(engine)
    seed_session(session)
    app = create_app()
    for dep in (profiles_session, artifacts_session, resume_session):
        app.dependency_overrides[dep] = lambda: session
    yield TestClient(app), session
    session.close()


def ids(session: Session) -> tuple[str, str, str]:
    jordan = session.scalars(select(ProfileModel).where(ProfileModel.slug == "jordan-lee")).one().id
    morgan = session.scalars(select(ProfileModel).where(ProfileModel.slug == "morgan-rivera")).one().id
    job = session.scalars(select(JobModel).where(JobModel.company == "Lumen Robotics")).one().id
    return jordan, morgan, job


def test_versions_increment_per_profile_job_and_format(env: tuple[TestClient, Session]) -> None:
    client, session = env
    jordan, _, job = ids(session)
    url = f"/api/v1/profiles/{jordan}/artifacts"
    v1 = client.post(url, json={"format": "markdown"}).json()
    v2 = client.post(url, json={"format": "markdown"}).json()
    other_format = client.post(url, json={"format": "html"}).json()
    for_job = client.post(url, json={"format": "markdown", "job_id": job}).json()
    assert (v1["version"], v2["version"], other_format["version"], for_job["version"]) == (1, 2, 1, 1)
    assert v1["content_sha256"] == v2["content_sha256"]
    assert [a["version"] for a in client.get(url).json()] == [1, 2, 1, 1][::-1] or len(client.get(url).json()) == 4
    assert len(client.get(url, params={"job_id": job}).json()) == 1
    assert client.get("/api/v1/artifact-formats").json() == ["docx", "html", "markdown", "pdf"]


def test_rerendering_an_old_version_reproduces_it_from_retained_inputs(env: tuple[TestClient, Session]) -> None:
    client, session = env
    jordan, _, _ = ids(session)
    url = f"/api/v1/profiles/{jordan}/artifacts"
    old = client.post(url, json={"format": "docx"}).json()
    # the profile changes afterwards; the old version must still be reproducible from its inputs
    session.get(ProfileContactModel, jordan).full_name = "Changed Name"  # type: ignore[union-attr]
    session.scalars(select(ProfileModel).where(ProfileModel.id == jordan)).one().summary = "A different summary now."
    session.commit()
    new = client.post(url, json={"format": "docx"}).json()
    assert new["content_sha256"] != old["content_sha256"]
    again = client.post(f"{url}/{old['id']}/rerender").json()
    assert again["matches_stored"] is True and again["content_sha256"] == old["content_sha256"] and again["version"] == 1
    assert client.post(f"{url}/{new['id']}/rerender").json()["matches_stored"] is True


@pytest.mark.parametrize(("fmt", "content_type", "ext"), [
    ("markdown", "text/markdown", "md"), ("html", "text/html", "html"), ("pdf", "application/pdf", "pdf"),
    ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "docx"),
])  # fmt: skip
def test_download_headers_and_bytes(env: tuple[TestClient, Session], fmt: str, content_type: str, ext: str) -> None:
    client, session = env
    jordan, _, _ = ids(session)
    made = client.post(f"/api/v1/profiles/{jordan}/artifacts", json={"format": fmt}).json()
    response = client.get(f"/api/v1/profiles/{jordan}/artifacts/{made['id']}/download")
    assert response.status_code == 200 and response.headers["content-type"].startswith(content_type)
    assert response.headers["content-disposition"] == f'attachment; filename="resume-v1.{ext}"'
    assert response.headers["x-content-type-options"] == "nosniff"
    assert hashlib.sha256(response.content).hexdigest() == made["content_sha256"]


def test_public_mode_removes_contact_details_from_the_download(env: tuple[TestClient, Session]) -> None:
    client, session = env
    jordan, _, _ = ids(session)
    contact = session.get(ProfileContactModel, jordan)
    assert contact is not None
    contact.email, contact.phone, contact.city = "jordan@example.com", "+1 555 010 0199", "Austin"
    session.commit()
    url = f"/api/v1/profiles/{jordan}/artifacts"
    private = client.post(url, json={"format": "markdown"}).json()
    public = client.post(url, json={"format": "markdown", "redacted": True}).json()
    assert public["redacted"] and not private["redacted"]
    private_text = client.get(f"{url}/{private['id']}/download").text
    public_resp = client.get(f"{url}/{public['id']}/download")
    assert "jordan@example.com" in private_text and "Austin" in private_text
    assert "jordan@example.com" not in public_resp.text and "555" not in public_resp.text and "Austin" not in public_resp.text
    assert "-public.md" in public_resp.headers["content-disposition"]


def test_document_uses_the_approved_package_and_never_invents_facts(env: tuple[TestClient, Session]) -> None:
    client, session = env
    jordan, _, job = ids(session)
    from careerflow.infrastructure.database.models import AchievementModel

    achievement = session.scalars(select(AchievementModel).where(AchievementModel.profile_id == jordan)).first()
    assert achievement is not None
    client.put(f"/api/v1/profiles/{jordan}/packages/by-job/{job}", json={"summary_suggestion": "Draft summary", "cover_letter_notes": ["Mention X"], "recommended_achievement_ids": [achievement.id]})
    draft = client.post(f"/api/v1/profiles/{jordan}/artifacts", json={"format": "markdown", "job_id": job, "include_cover_letter_notes": True})
    text = client.get(f"/api/v1/profiles/{jordan}/artifacts/{draft.json()['id']}/download").text
    assert "Draft summary" not in text and "Mention X" not in text  # only an APPROVED package may shape the document
    package = session.scalars(select(ApplicationPackageModel)).one()
    package.status = "APPROVED"
    session.commit()
    approved = client.post(f"/api/v1/profiles/{jordan}/artifacts", json={"format": "markdown", "job_id": job, "include_cover_letter_notes": True}).json()
    text = client.get(f"/api/v1/profiles/{jordan}/artifacts/{approved['id']}/download").text
    assert "Draft summary" in text and "Mention X" in text and "Prepared for: Principal AI Platform Engineer at Lumen Robotics" in text
    assert approved["kind"] == "resume_with_cover_notes"


def test_artifacts_are_isolated_between_profiles(env: tuple[TestClient, Session]) -> None:
    client, session = env
    jordan, morgan, _ = ids(session)
    made = client.post(f"/api/v1/profiles/{jordan}/artifacts", json={"format": "pdf"}).json()
    base = f"/api/v1/profiles/{morgan}/artifacts"
    assert client.get(base).json() == []
    assert client.get(f"{base}/{made['id']}").status_code == 404
    assert client.get(f"{base}/{made['id']}/download").status_code == 404
    assert client.post(f"{base}/{made['id']}/rerender").status_code == 404


def test_validation_errors(env: tuple[TestClient, Session]) -> None:
    client, session = env
    jordan, _, _ = ids(session)
    url = f"/api/v1/profiles/{jordan}/artifacts"
    assert client.post(url, json={"format": "rtf"}).status_code == 422
    assert client.post(url, json={"format": "pdf", "job_id": "nope"}).status_code == 404
    assert client.post("/api/v1/profiles/nope/artifacts", json={"format": "pdf"}).status_code == 404
    assert client.get(f"{url}/nope").status_code == 404
