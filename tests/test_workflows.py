from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_deploy_workflow_runs_from_main_branch() -> None:
    workflow = (ROOT / ".github" / "workflows" / "deploy-cloud-run.yml").read_text()

    assert "branches:\n      - main" in workflow
    assert "branches:\n      - master" not in workflow


def test_scheduled_digest_crons_match_job_conditions() -> None:
    workflow = (ROOT / ".github" / "workflows" / "scheduled-digests.yml").read_text()

    assert 'cron: "17 6 * * 1"' in workflow
    assert "github.event.schedule == '17 6 * * 1'" in workflow
    assert 'cron: "27 6 1 * *"' in workflow
    assert "github.event.schedule == '27 6 1 * *'" in workflow
    assert "github.event.schedule == '0 6 * * 1'" not in workflow
    assert "github.event.schedule == '10 6 1 * *'" not in workflow
