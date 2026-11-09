import pytest

from .conftest import AUTH


@pytest.fixture
def project_id(client):
    return client.post("/api/projects", json={"name": "P"}, headers=AUTH).json()["id"]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"prompt": "", "project_id": "p"},
        {"prompt": "x" * 20001, "project_id": "p"},
        {"prompt": "hi"},  # project_id is required
        {"prompt": "hi", "project_id": "p", "mode": "everything"},
        {"prompt": "hi", "project_id": "p", "max_round": 0},
        {"prompt": "hi", "project_id": "p", "max_round": 51},
        {"prompt": "hi", "project_id": "p", "surprise": True},
    ],
)
def test_task_request_validation(client, body):
    assert client.post("/api/task", json=body, headers=AUTH).status_code == 422


def test_task_for_unknown_project_is_404(client, fake_engine):
    r = client.post("/api/task", json={"prompt": "hi", "project_id": "missing"}, headers=AUTH)
    assert r.status_code == 404


@pytest.mark.parametrize("name", ["", "x" * 101])
def test_project_name_validation(client, name):
    assert client.post("/api/projects", json={"name": name}, headers=AUTH).status_code == 422


def test_unknown_project_is_404(client):
    assert client.get("/api/projects/nope", headers=AUTH).status_code == 404
    assert client.delete("/api/projects/nope", headers=AUTH).status_code == 404
    assert client.put("/api/projects/nope/activate", headers=AUTH).status_code == 404


@pytest.mark.parametrize(
    "agent",
    [
        {"name": "1Bad"},
        {"name": "has space"},
        {"name": "A" * 41},
        {"name": "Ok", "color": "red"},
        {"name": "Ok", "prompt": "x" * 8001},
        {"name": "Ok", "job_title": "x" * 81},
        {"name": "Ok", "icon": "<svg>"},
    ],
)
def test_agent_validation(client, agent):
    assert client.post("/api/settings/agents", json=agent, headers=AUTH).status_code == 422


def test_agent_update_validation(client):
    assert client.put("/api/settings/agents", json={"bad name": {}}, headers=AUTH).status_code == 422
    assert client.put("/api/settings/agents", json={"Coder": {"color": "#12345"}}, headers=AUTH).status_code == 422


def test_agent_conflict_and_missing(client):
    assert client.post("/api/settings/agents", json={"name": "Extra"}, headers=AUTH).status_code == 201
    assert client.post("/api/settings/agents", json={"name": "Extra"}, headers=AUTH).status_code == 409
    assert client.delete("/api/settings/agents/Extra", headers=AUTH).status_code == 204
    assert client.delete("/api/settings/agents/Extra", headers=AUTH).status_code == 404


@pytest.mark.parametrize("keys", [{"Bad-Id": "k"}, {"9lives": "k"}, {"openai": "k" * 501}])
def test_key_validation(client, keys):
    assert client.put("/api/settings/keys", json=keys, headers=AUTH).status_code == 422


def test_key_delete_validates_provider(client):
    assert client.delete("/api/settings/keys/Not-Valid", headers=AUTH).status_code == 422
