"""Deploy env parsing: CORS list, blank-as-unset, and Assist's loopback URL.

    cd backend && pytest tests/test_deploy_env.py -v
"""
import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ci")

from server import _env, cors_allow_origins  # noqa: E402
from assist.tools import _self_base_url  # noqa: E402


def test_cors_strips_spaces_and_keeps_both_site_origins(monkeypatch):
    monkeypatch.setenv(
        "CORS_ORIGINS",
        " https://thecalibrationcrew.us, https://www.thecalibrationcrew.us ",
    )
    assert cors_allow_origins() == [
        "https://thecalibrationcrew.us",
        "https://www.thecalibrationcrew.us",
    ]


def test_cors_blank_matches_the_wildcard_default(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", " , ")
    assert cors_allow_origins() == ["*"]


def test_blank_env_uses_the_documented_default(monkeypatch):
    monkeypatch.setenv("OWNER_EMAIL", "  ")
    assert _env("OWNER_EMAIL", "caleb@thecalibrationcrew.us") == "caleb@thecalibrationcrew.us"


def test_assist_loopback_uses_port_when_override_is_blank(monkeypatch):
    monkeypatch.setenv("ASSIST_SELF_BASE_URL", " ")
    monkeypatch.setenv("PORT", "10000")
    assert _self_base_url() == "http://127.0.0.1:10000"


def test_assist_loopback_defaults_to_8001(monkeypatch):
    monkeypatch.delenv("ASSIST_SELF_BASE_URL", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    assert _self_base_url() == "http://127.0.0.1:8001"


def test_assist_explicit_base_url_wins_over_port(monkeypatch):
    monkeypatch.setenv("ASSIST_SELF_BASE_URL", "https://api.thecalibrationcrew.us/")
    monkeypatch.setenv("PORT", "10000")
    assert _self_base_url() == "https://api.thecalibrationcrew.us"


def test_blank_assist_model_uses_gemini_flash(monkeypatch):
    import assist.agent as agent
    monkeypatch.setenv("ASSIST_MODEL", " ")
    reloaded = importlib.reload(agent)
    assert reloaded.ASSIST_MODEL == "gemini-2.5-flash"
    monkeypatch.undo()
    importlib.reload(agent)
