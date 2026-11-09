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
        {"prompt": "hi", "project_id": "p", "max_cycles": 0},
        {"prompt": "hi", "project_id": "p", "max_cycles": 11},
        {"prompt": "hi", "project_id": "p", "max_round": 15},  # replaced by max_cycles
        {"prompt": "hi", "project_id": "p", "discussion_rounds": 5},
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
        {"name": "Ok", "model": "gpt4"},  # legacy keys are no longer model refs
        {"name": "Ok", "model": "openai: spaced"},
        {"name": "Ok", "role": "boss"},
        {"name": "Ok", "max_tokens": 0},
        {"name": "Ok", "max_tokens": 200_001},
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


def test_unknown_provider_in_model_is_422(client):
    r = client.post("/api/settings/agents", json={"name": "Ok", "model": "nosuch:model"}, headers=AUTH)
    assert r.status_code == 422
    assert client.put("/api/settings/agents", json={"Coder": {"model": "nosuch:m"}}, headers=AUTH).status_code == 422


@pytest.mark.parametrize(
    "body",
    [
        {"budget_usd": 0},
        {"budget_usd": -1},
        {"budget_usd": 10_001},
        {"token_cap": 0},
        {"token_cap": 100_000_001},
        {"allowances": {"openai": 0}},
        {"allowances": {"Bad-Id": 5}},
        {"discussion_rounds": -1},
        {"discussion_rounds": 5},
        {"surprise": 1},
    ],
)
def test_run_settings_validation(client, body):
    assert client.put("/api/settings/run", json=body, headers=AUTH).status_code == 422


@pytest.mark.parametrize("body", [{"action": "maybe"}, {"action": "switch", "model": "not a ref"}, {}])
def test_decision_validation(client, body):
    assert client.post("/api/task/decision", json=body, headers=AUTH).status_code == 422


@pytest.mark.parametrize("body", [{"content": ""}, {"content": "x" * 4001}, {}])
def test_task_message_validation(client, body):
    assert client.post("/api/task/message", json=body, headers=AUTH).status_code == 422


@pytest.mark.parametrize("body", [{"agent": "Coder"}, {"agent": "bad name", "message": "q"}, {"agent": "Coder", "message": ""}])
def test_follow_up_validation(client, body):
    assert client.post("/api/runs/1/chat", json=body, headers=AUTH).status_code == 422
