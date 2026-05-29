from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_postgres_compose_uses_external_network_and_persistent_disk():
    compose = yaml.safe_load((REPO_ROOT / "docker-compose.db.yml").read_text())

    assert compose["networks"]["postgres_network"] == {
        "external": True,
        "name": "postgres_network",
    }
    assert "/data/postgres_data:/var/lib/postgresql/data" in compose["services"][
        "postgres"
    ]["volumes"]


def test_deploy_workflow_reuses_existing_postgres_container():
    workflow = yaml.safe_load((REPO_ROOT / ".github/workflows/deploy.yml").read_text())
    deploy_steps = workflow["jobs"]["deploy"]["steps"]
    deploy_script = next(
        step["run"] for step in deploy_steps if step.get("name") == "Deploy locally"
    )

    assert "POSTGRES_CONTAINER=postgres_db" in deploy_script
    assert 'docker container inspect "$POSTGRES_CONTAINER"' in deploy_script
    assert 'docker start "$POSTGRES_CONTAINER"' in deploy_script
    assert "POSTGRES_NETWORK=postgres_network" in deploy_script
    assert 'docker network inspect "$POSTGRES_NETWORK"' in deploy_script
    assert 'docker network create "$POSTGRES_NETWORK"' in deploy_script
    assert "pg_isready -U postgres -d mono_db" in deploy_script
    assert "SHOW data_directory;" in deploy_script
    assert "/data/postgres_data" in deploy_script
    assert "/var/lib/postgresql/data" in deploy_script
