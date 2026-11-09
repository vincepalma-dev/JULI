import json
import os

import keyring
import pytest
from keyring.backends.fail import Keyring as FailKeyring

from juli import config, keystore

from .conftest import AUTH


@pytest.fixture
def no_keychain():
    previous = keyring.get_keyring()
    keyring.set_keyring(FailKeyring())
    yield
    keyring.set_keyring(previous)


def test_roundtrip_with_fake_backend(memory_keyring):
    keystore.set_key("openai", "sk-test-abcd1234")
    assert memory_keyring.store[("juli", "openai")] == "sk-test-abcd1234"
    assert keystore.get_key("openai") == "sk-test-abcd1234"
    keystore.delete_key("openai")
    keystore.delete_key("openai")  # deleting twice is fine
    assert keystore.get_key("openai") is None


def test_env_and_dotenv_fallback(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "from-env")
    assert keystore.get_key("openai") == "from-env"
    keystore.ENV_FILE.write_text("ANTHROPIC_API_KEY=from-dotenv\n", encoding="utf-8")
    keystore._dotenv.cache_clear()
    assert keystore.get_key("anthropic") == "from-dotenv"


def test_keychain_wins_over_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "from-env")
    keystore.set_key("openai", "from-keychain")
    assert keystore.get_key("openai") == "from-keychain"


def test_unavailable_keychain(no_keychain, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "from-env")
    assert keystore.get_key("openai") == "from-env"
    with pytest.raises(keystore.KeystoreUnavailable):
        keystore.set_key("openai", "x")


def test_key_hint():
    assert keystore.key_hint("sk-1234567890abcd") == "••••abcd"
    assert keystore.key_hint("short") == "••••"
    assert keystore.key_hint(None) == ""


def test_settings_api_never_returns_keys(client):
    assert client.put("/api/settings/keys", json={"openai": "sk-secret-value-wxyz"}, headers=AUTH).status_code == 200
    body = client.get("/api/settings", headers=AUTH).text
    assert "sk-secret-value" not in body
    assert json.loads(body)["key_hints"]["openai"] == "••••wxyz"
    assert "sk-secret" not in config.settings_path().read_text(encoding="utf-8")


def test_masked_values_are_not_saved(client, memory_keyring):
    client.put("/api/settings/keys", json={"openai": "sk-real-key-1111"}, headers=AUTH)
    client.put("/api/settings/keys", json={"openai": "••••1111"}, headers=AUTH)
    assert memory_keyring.store[("juli", "openai")] == "sk-real-key-1111"


def test_new_provider_is_recorded_and_deletable(client, memory_keyring):
    client.put("/api/settings/keys", json={"mistral": "m-key-123456"}, headers=AUTH)
    assert "mistral" in client.get("/api/settings", headers=AUTH).json()["key_hints"]
    assert client.delete("/api/settings/keys/mistral", headers=AUTH).status_code == 204
    assert ("juli", "mistral") not in memory_keyring.store
    assert "mistral" not in client.get("/api/settings", headers=AUTH).json()["key_hints"]


def test_saving_without_keychain_is_503(client, no_keychain):
    r = client.put("/api/settings/keys", json={"openai": "sk-x-123456"}, headers=AUTH)
    assert r.status_code == 503
    assert ".env" in r.json()["detail"]


def test_server_never_writes_os_environ(client):
    client.put("/api/settings/keys", json={"openai": "sk-env-check-9999"}, headers=AUTH)
    assert "sk-env-check-9999" not in os.environ.values()


# ─── Legacy migration ────────────────────────────────────────


def write_legacy(keys):
    data = {"agents": {"Coder": {"model": "claude"}}, "api_keys": keys, "available_models": ["gpt4"]}
    config.LEGACY_SETTINGS_FILE.write_text(json.dumps(data), encoding="utf-8")


def test_legacy_keys_move_to_keychain(memory_keyring):
    write_legacy({"openai": "sk-legacy-aaaa", "google": ""})
    config.migrate_legacy_settings()

    assert memory_keyring.store == {("juli", "openai"): "sk-legacy-aaaa"}
    legacy = json.loads(config.LEGACY_SETTINGS_FILE.read_text(encoding="utf-8"))
    assert legacy["api_keys"] == {"openai": "", "google": ""}
    new = json.loads(config.settings_path().read_text(encoding="utf-8"))
    assert "api_keys" not in new
    assert new["providers"] == ["openai", "google"]
    assert new["agents"] == {"Coder": {"model": "claude"}}


def test_legacy_left_alone_without_keychain(no_keychain):
    write_legacy({"openai": "sk-legacy-bbbb"})
    config.migrate_legacy_settings()
    legacy = json.loads(config.LEGACY_SETTINGS_FILE.read_text(encoding="utf-8"))
    assert legacy["api_keys"] == {"openai": "sk-legacy-bbbb"}
    assert not config.settings_path().exists()


def test_keys_in_new_settings_file_are_removed(memory_keyring):
    config.settings_path().write_text(
        json.dumps({"agents": {}, "api_keys": {"anthropic": "a-key-cccc"}}), encoding="utf-8"
    )
    config.migrate_legacy_settings()
    assert memory_keyring.store == {("juli", "anthropic"): "a-key-cccc"}
    assert "api_keys" not in json.loads(config.settings_path().read_text(encoding="utf-8"))


def test_settings_write_is_atomic_utf8():
    config.save_settings({"agents": {"Coder": {"prompt": "Señor ✓"}}, "providers": [], "available_models": []})
    assert "Señor ✓" in config.settings_path().read_text(encoding="utf-8")
    assert [p.name for p in config.data_dir().iterdir()] == ["settings.json"]
