from fastapi.testclient import TestClient

from app.core.enums import JobType, OutputFormat
from app.main import app
from app.services.job_store import job_service


def test_job_status_includes_progress_fields(tmp_path):
    client = TestClient(app)

    job_service._jobs = {}
    job = job_service.create_job(
        job_type=JobType.PDF,
        output_format=OutputFormat.PDF,
        input_path=tmp_path / "input.pdf",
    )

    response = client.get(f"/api/v1/jobs/{job.id}")
    assert response.status_code == 200

    data = response.json()
    assert data["progress_current"] == 0
    assert data["progress_total"] is None
    assert data["progress_stage"] is None
