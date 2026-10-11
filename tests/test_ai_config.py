"""Setting up the AI model from the app: who may, what is kept, what is refused."""
from __future__ import annotations

import pytest

from helpers import create_user, load_app, setup_admin, sign_in
from test_llm import FakeModel

KEY = "sk-test-key-do-not-leak-123"


@pytest.fixture
def env(tmp_path):
    model = FakeModel()
    (tmp_path / "data").mkdir()
    appm = load_app(tmp_path / "data")          # no AI settings in the environment
    admin, _ = setup_admin(appm)
    yield appm, admin, model, tmp_path
    model.close()


def body(model, **over):
    return {"url": model.url, "model": "test-model", **over}


def test_nothing_is_set_up_to_begin_with(env):
    _, admin, _, _ = env
    assert admin.get("/api/v1/ai/status").json() == {"configured": False, "model": None, "source": "none"}
    assert admin.post("/api/v1/ai/test").status_code == 400


def test_try_then_save_then_use(env):
    _, admin, model, _ = env
    tried = admin.post("/api/v1/ai/test", json=body(model))
    assert tried.status_code == 200 and tried.json()["result"]["summary"]
    assert admin.get("/api/v1/ai/status").json()["configured"] is False        # trying does not save
    assert admin.put("/api/v1/ai/config", json=body(model)).status_code == 200
    assert admin.get("/api/v1/ai/status").json() == {"configured": True, "model": "test-model", "source": "saved"}
    assert admin.post("/api/v1/ai/test").json()["ok"] is True                  # the saved settings work too
    cfg = admin.get("/api/v1/ai/config").json()
    assert cfg["url"] == model.url and cfg["editable"] is True and cfg["has_key"] is False


def test_the_key_is_encrypted_never_returned_and_only_sent_to_its_own_address(env):
    _, admin, model, tmp_path = env
    other = FakeModel()
    try:
        assert admin.put("/api/v1/ai/config", json=body(model, api_key=KEY)).status_code == 200
        cfg = admin.get("/api/v1/ai/config")
        assert cfg.json()["has_key"] is True and KEY not in cfg.text and KEY not in admin.get("/api/v1/ai/status").text
        assert all(KEY.encode() not in f.read_bytes() for f in (tmp_path / "data").rglob("*") if f.is_file())
        admin.post("/api/v1/ai/test")
        assert model.auth[-1] == f"Bearer {KEY}"
        # Saving the same address again without a key keeps it; a different address does not inherit it.
        admin.put("/api/v1/ai/config", json=body(model))
        assert admin.get("/api/v1/ai/config").json()["has_key"] is True
        admin.post("/api/v1/ai/test", json={"url": other.url, "model": "m"})
        assert other.auth[-1] is None
        admin.put("/api/v1/ai/config", json={"url": other.url, "model": "m"})
        assert admin.get("/api/v1/ai/config").json()["has_key"] is False
    finally:
        other.close()


def test_addresses_outside_your_network_are_refused(env):
    _, admin, _, _ = env
    for url in ("http://8.8.8.8/v1/chat/completions", "https://api.example.com/v1/chat/completions", "ftp://192.168.1.2/x", "http://user:pw@192.168.1.2/x"):
        r = admin.put("/api/v1/ai/config", json={"url": url, "model": "m"})
        assert r.status_code == 400, url
        assert admin.post("/api/v1/ai/test", json={"url": url, "model": "m"}).status_code == 400, url
    assert admin.get("/api/v1/ai/status").json()["configured"] is False


def test_a_model_that_is_down_or_wrong_is_explained(env):
    _, admin, _, _ = env
    r = admin.post("/api/v1/ai/test", json={"url": "http://127.0.0.1:9/v1/chat/completions", "model": "m"})
    assert r.status_code == 502 and r.json()["detail"]["code"] == "ai_unreachable"
    bad = FakeModel(reply="not json at all")
    try:
        r = admin.post("/api/v1/ai/test", json=body(bad))
        assert r.status_code == 502 and r.json()["detail"]["code"] == "ai_bad_reply"
    finally:
        bad.close()


def test_only_administrators_change_it(env):
    appm, admin, model, _ = env
    create_user(admin, "cara")
    cara = sign_in(appm, "cara")
    assert cara.get("/api/v1/ai/status").status_code == 200
    assert cara.get("/api/v1/ai/config").status_code == 403
    assert cara.put("/api/v1/ai/config", json=body(model)).status_code == 403
    assert cara.delete("/api/v1/ai/config").status_code == 403
    assert cara.post("/api/v1/ai/test", json=body(model)).status_code == 403
    admin.put("/api/v1/ai/config", json=body(model))
    assert cara.post("/api/v1/ai/test").status_code == 200                      # anyone may test what is saved


def test_clearing_turns_it_off(env):
    _, admin, model, _ = env
    admin.put("/api/v1/ai/config", json=body(model, api_key=KEY))
    assert admin.delete("/api/v1/ai/config").status_code == 204
    assert admin.get("/api/v1/ai/status").json()["configured"] is False


def test_server_environment_wins_and_cannot_be_overwritten(tmp_path):
    model = FakeModel()
    try:
        (tmp_path / "data").mkdir()
        appm = load_app(tmp_path / "data", ENVELIQ_LLM_URL=model.url, ENVELIQ_LLM_MODEL="env-model")
        admin, _ = setup_admin(appm)
        assert admin.get("/api/v1/ai/status").json()["source"] == "environment"
        assert admin.get("/api/v1/ai/config").json()["editable"] is False
        assert admin.get("/api/v1/ai/config").json()["env_vars"] == ["ENVELIQ_LLM_URL", "ENVELIQ_LLM_MODEL"]
        assert admin.put("/api/v1/ai/config", json=body(model)).status_code == 409
        assert admin.delete("/api/v1/ai/config").status_code == 409
        assert admin.post("/api/v1/ai/test").status_code == 200
    finally:
        model.close()


def test_the_key_is_not_in_the_vault_file_as_plain_text(env):
    appm, admin, model, tmp_path = env
    admin.put("/api/v1/ai/config", json=body(model, api_key=KEY))
    scan = appm.vault.plaintext_scan([KEY])
    assert not any(scan.values())
