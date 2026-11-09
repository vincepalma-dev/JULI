import pytest

from juli import config, keystore, providers, roles
from juli.local import catalogue

from .conftest import AUTH, fixture_json, serve

LLAMA_REPO = "bartowski/Llama-3.2-1B-Instruct-GGUF"
QWEN_REPO = "unsloth/Qwen3-30B-A3B-GGUF"


def hf_routes(repo: str, info: str, tree: str) -> dict:
    return {
        ("GET", f"/api/models/{repo}"): (200, fixture_json(info), {}),
        ("GET", f"/api/models/{repo}/tree/main"): (200, fixture_json(tree), {}),
    }


# ─── Catalogue ───────────────────────────────────────────────


def test_catalogue_entries_are_complete():
    tags = [m["tag"] for m in catalogue.MODELS]
    assert len(tags) == len(set(tags)) == 21
    allowed_roles = {"planner", "coder", "reviewer", "tester", "docs", "general"}
    for m in catalogue.MODELS:
        assert m["license"] in catalogue.LICENSES
        assert set(m["roles"]) <= allowed_roles
        assert m["size_gb"] > 0 and m["params_b"] > 0 and m["context_max"] >= 32768
    assert catalogue.entry(roles.DEFAULT_MODEL.partition(":")[2]) is not None


def test_llama_and_gemma3_need_acceptance_but_gemma4_is_apache():
    assert catalogue.license_for("llama3.2:3b")["accept"] is True
    assert catalogue.license_for("gemma3:12b")["id"] == "gemma"
    assert catalogue.license_for("gemma4:12b") == {"id": "apache-2.0", **catalogue.LICENSES["apache-2.0"]}
    assert catalogue.license_for("deepseek-r1:8b")["accept"] is False


def test_listing_marks_installed_models_and_their_fit(laptop):
    rows = {m["tag"]: m for m in catalogue.listing(laptop, {"qwen3:8b"}, config.load_settings())}
    assert rows["qwen3:8b"]["installed"] is True
    assert rows["qwen3:8b"]["fit"]["tier"] == "slow"
    assert rows["gpt-oss:120b"]["fit"]["tier"] == "cannot"
    assert rows["gemma3:1b"]["license"]["accepted"] is False


def test_catalogue_route(client, laptop, net):
    net.handler = serve({("GET", "/api/version"): (200, {"version": "0.20.0"}, {}), ("GET", "/api/tags"): (200, fixture_json("ollama_tags.json"), {})})
    data = client.get("/api/local/catalogue", headers=AUTH).json()
    assert data["ollama"]["running"] is True and data["hardware"]["gpu"] is None
    assert next(m for m in data["models"] if m["tag"] == "qwen3:8b")["installed"] is True


# ─── Licenses ────────────────────────────────────────────────


def test_other_tags_of_a_catalogue_model_share_its_license():
    assert catalogue.license_for("qwen3:8b-q8_0")["id"] == "apache-2.0"
    assert catalogue.license_for("llama3.2")["id"] == "llama3.2"


def test_unknown_models_need_acceptance():
    lic = catalogue.license_for("phi4:14b")
    assert lic == {"id": "model:phi4", "name": "the license of phi4", "url": "https://ollama.com/library/phi4", "accept": True}
    assert catalogue.license_for("someone/model:7b")["url"] == "https://ollama.com/someone/model"


def test_accepting_a_license_is_recorded_in_settings():
    settings = config.load_settings()
    assert catalogue.license_needed("gemma3:4b", settings)["id"] == "gemma"
    catalogue.accept_license("gemma")
    settings = config.load_settings()
    assert "accepted_at" in settings["licenses"]["gemma"]
    assert catalogue.license_needed("gemma3:4b", settings) is None
    assert catalogue.license_needed("llama3.2:1b", settings)["id"] == "llama3.2"
    with pytest.raises(ValueError):
        catalogue.accept_license("made-up")


def test_license_route(client):
    assert client.post("/api/local/licenses", json={"license": "llama3.2"}, headers=AUTH).status_code == 200
    assert "llama3.2" in config.load_settings()["licenses"]
    assert client.post("/api/local/licenses", json={"license": "made-up"}, headers=AUTH).status_code == 422
    assert client.post("/api/local/licenses", json={"license": "../x y"}, headers=AUTH).status_code == 422


# ─── Hugging Face GGUF ───────────────────────────────────────


@pytest.mark.parametrize(
    "path, quant",
    [
        ("Llama-3.2-1B-Instruct-Q4_K_M.gguf", "Q4_K_M"),
        ("Llama-3.2-1B-Instruct-IQ4_XS.gguf", "IQ4_XS"),
        ("Llama-3.2-1B-Instruct-Q4_0_4_4.gguf", "Q4_0_4_4"),
        ("Llama-3.2-1B-Instruct-f16.gguf", "F16"),
        ("Qwen3-30B-A3B-UD-Q4_K_XL.gguf", "UD-Q4_K_XL"),
        ("BF16/Qwen3-30B-A3B-BF16-00001-of-00002.gguf", "BF16"),
        ("model-q8_0.gguf", "Q8_0"),
        ("Qwen3-8B.gguf", None),
    ],
)
def test_quant_of(path, quant):
    assert catalogue.quant_of(path) == quant


def test_parse_ggufs_lists_each_quant_smallest_first():
    groups = catalogue.parse_ggufs(fixture_json("hf_tree_llama.json"))
    assert len(groups) == 18  # the .imatrix and README aren't models
    assert groups[0]["quant"] == "IQ3_M" and groups[-1]["quant"] == "F16"
    assert [g["size_bytes"] for g in groups] == sorted(g["size_bytes"] for g in groups)


def test_parse_ggufs_sums_shards_and_skips_vision_projectors():
    tree = fixture_json("hf_tree_qwen_moe.json") + [{"type": "file", "path": "mmproj-F16.gguf", "size": 800}]
    groups = {g["quant"]: g for g in catalogue.parse_ggufs(tree)}
    assert groups["BF16"]["size_bytes"] == 49_693_950_144 + 11_401_853_280
    assert len(groups["BF16"]["files"]) == 2
    assert set(groups) == {"BF16", "IQ4_XS", "Q4_K_M", "UD-Q4_K_XL", "Q8_0"}


def test_hf_models_fit_each_quant(net, laptop):
    net.handler = serve(hf_routes(LLAMA_REPO, "hf_model_llama.json", "hf_tree_llama.json"))
    found = catalogue.hf_models(LLAMA_REPO, laptop, {"hf.co/bartowski/Llama-3.2-1B-Instruct-GGUF:Q4_K_M"}, config.load_settings())
    assert found["license"]["id"] == "llama3.2" and found["license"]["accepted"] is False
    q4 = next(m for m in found["models"] if m["quant"] == "Q4_K_M")
    assert q4["tag"] == f"hf.co/{LLAMA_REPO}:Q4_K_M"
    assert q4["installed"] is True
    assert q4["params_b"] == pytest.approx(1.24, abs=0.01)  # from the repo's GGUF metadata
    assert q4["context_max"] == 131072
    assert q4["fit"]["tier"] == "slow"
    assert net.requests[1].url.params["recursive"] == "true"


def test_hf_estimates_params_without_gguf_metadata(net, laptop):
    info = {k: v for k, v in fixture_json("hf_model_qwen_moe.json").items() if k != "gguf"}
    net.handler = serve({**hf_routes(QWEN_REPO, "hf_model_qwen_moe.json", "hf_tree_qwen_moe.json"), ("GET", f"/api/models/{QWEN_REPO}"): (200, info, {})})
    found = catalogue.hf_models(QWEN_REPO, laptop, set(), config.load_settings())
    q8 = next(m for m in found["models"] if m["quant"] == "Q8_0")
    assert q8["params_b"] == pytest.approx(32.48 * 8 / 8.5, abs=0.1)
    assert found["license"]["accept"] is False  # apache-2.0
    assert next(m for m in found["models"] if m["quant"] == "BF16")["fit"]["tier"] == "cannot"


def test_gated_and_unknown_licenses_need_acceptance():
    gated = catalogue.hf_license("meta-llama/Llama-3.2-1B", fixture_json("hf_model_gated.json"))
    assert gated["id"] == "hf:meta-llama/Llama-3.2-1B" and gated["gated"] is True and gated["accept"] is True
    other = catalogue.hf_license("a/b", {"cardData": {"license": "other", "license_link": "https://example.com/terms"}})
    assert other == {"id": "hf:a/b", "name": "other", "url": "https://example.com/terms", "accept": True, "gated": False}
    assert catalogue.hf_license("a/b", {})["name"] == "unknown terms"


def test_hf_license_is_looked_up_for_pulls(net):
    net.handler = serve(hf_routes(LLAMA_REPO, "hf_model_llama.json", "hf_tree_llama.json"))
    assert catalogue.license_for(f"hf.co/{LLAMA_REPO}:Q4_K_M")["id"] == "llama3.2"


def test_hf_errors(net, laptop):
    net.handler = lambda req: (404, {"error": "Repository not found"}, {})
    with pytest.raises(providers.ProviderError, match="not found"):
        catalogue.hf_models("nobody/nothing", laptop, set(), {})
    net.handler = None
    with pytest.raises(providers.ProviderError, match="can't reach Hugging Face"):
        catalogue.hf_models("nobody/nothing", laptop, set(), {})


def test_hf_route(client, net, laptop):
    net.handler = serve(hf_routes(LLAMA_REPO, "hf_model_llama.json", "hf_tree_llama.json"))
    r = client.get("/api/local/hf", params={"repo": LLAMA_REPO}, headers=AUTH)
    assert r.status_code == 200 and len(r.json()["models"]) == 18
    assert client.get("/api/local/hf", params={"repo": "../etc/passwd"}, headers=AUTH).status_code == 422
    net.handler = None
    assert client.get("/api/local/hf", params={"repo": "a/b"}, headers=AUTH).status_code == 502


# ─── OpenAI-compatible endpoints ─────────────────────────────

MODELS_LIST = {"object": "list", "data": [{"id": "qwen3-8b", "object": "model", "created": 1, "owned_by": "me"}]}


def test_add_a_local_endpoint_tests_it_and_lists_models(client, net):
    net.handler = lambda req: (200, MODELS_LIST, {})
    r = client.post("/api/providers/endpoints", json={"id": "lmstudio", "label": "LM Studio", "base_url": "http://localhost:1234/v1/"}, headers=AUTH)
    assert r.status_code == 201
    body = r.json()
    assert body["local"] is True and body["key"] is False
    assert body["health"]["status"] == "ok" and body["health"]["models"] == ["qwen3-8b"]
    assert str(net.requests[0].url) == "http://localhost:1234/v1/models"
    assert config.load_settings()["endpoints"]["lmstudio"]["base_url"] == "http://localhost:1234/v1"
    listed = {p["id"]: p for p in client.get("/api/providers", headers=AUTH).json()}
    assert listed["lmstudio"]["local"] is True
    assert providers.is_local("lmstudio:qwen3-8b", config.load_settings()["endpoints"])


def test_endpoint_keys_go_to_the_keychain(client, net, memory_keyring):
    net.handler = lambda req: (200, MODELS_LIST, {})
    key = "sk-test-not-a-real-key-1234"
    r = client.post("/api/providers/endpoints", json={"id": "myhost", "label": "Mine", "base_url": "https://llm.example.com/v1", "key": key}, headers=AUTH)
    assert r.status_code == 201 and r.json()["key"] is True
    assert keystore.get_key("myhost") == key
    assert key not in config.settings_path().read_text(encoding="utf-8")
    assert net.requests[0].headers["authorization"] == f"Bearer {key}"


@pytest.mark.parametrize(
    "endpoint_id, base_url",
    [
        ("openai", "https://api.openai.com/v1"),  # a built-in provider
        ("remote", "http://llm.example.com/v1"),  # plain http off the LAN
        ("creds", "https://user:pw@example.com/v1"),
        ("weird", "ftp://localhost/v1"),
    ],
)
def test_bad_endpoints_are_rejected(client, endpoint_id, base_url):
    r = client.post("/api/providers/endpoints", json={"id": endpoint_id, "label": "x", "base_url": base_url}, headers=AUTH)
    assert r.status_code == 422


def test_remove_an_endpoint(client, net, memory_keyring):
    net.handler = lambda req: (200, MODELS_LIST, {})
    client.post("/api/providers/endpoints", json={"id": "box", "label": "Box", "base_url": "http://192.168.1.20:8080/v1", "key": "not-a-real-key-5678"}, headers=AUTH)
    client.put("/api/settings/agents", json={"Coder": {"model": "box:qwen3-8b"}}, headers=AUTH)
    assert client.delete("/api/providers/endpoints/box", headers=AUTH).status_code == 409  # in use
    client.put("/api/settings/agents", json={"Coder": {"model": "ollama:qwen3:8b"}}, headers=AUTH)
    assert client.delete("/api/providers/endpoints/box", headers=AUTH).status_code == 204
    assert keystore.get_key("box") is None
    assert "box" not in config.load_settings()["endpoints"]
    assert client.delete("/api/providers/endpoints/box", headers=AUTH).status_code == 404
