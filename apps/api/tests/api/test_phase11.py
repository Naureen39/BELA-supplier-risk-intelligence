"""Phase 11: packaging checks, the checkpoint downloader, and the demo seed."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

import httpx
import psycopg
import pytest
import yaml
from app.auth.passwords import PasswordService
from app.auth.tokens import TokenService
from app.settings import Settings
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[4]


def _load(name: str, rel: str):  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------- signing key from an env file
def test_signing_key_accepts_escaped_newlines() -> None:
    pem = Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    one_line = pem.replace("\n", "\\n")
    t = TokenService(Settings(jwt_private_key_pem=one_line, data_key="k", cursor_secret="c"))
    assert t is not None


# ---------------------------------------------------------------------------- checkpoint downloader
@pytest.fixture()
def fc():  # type: ignore[no-untyped-def]
    return _load("fetch_checkpoints", "infra/models/fetch_checkpoints.py")


def _client(body: bytes) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=body)))


def test_checkpoint_download_verifies_hash(fc, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    body = b"weights"
    entry = {"name": "m", "url": "https://example.org/m.bin", "dest": "m/m.bin", "sha256": hashlib.sha256(body).hexdigest()}
    assert fc.fetch(entry, tmp_path, _client(body)) == "downloaded"
    assert (tmp_path / "m/m.bin").read_bytes() == body
    assert fc.fetch(entry, tmp_path, _client(b"other")) == "kept"  # verified file is not downloaded again


def test_checkpoint_hash_mismatch_leaves_nothing(fc, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    entry = {"name": "m", "url": "https://example.org/m.bin", "dest": "m.bin", "sha256": "0" * 64}
    with pytest.raises(fc.ChecksumMismatch):
        fc.fetch(entry, tmp_path, _client(b"tampered"))
    assert list(tmp_path.iterdir()) == []


def test_empty_manifest_is_not_an_error(fc, capsys: pytest.CaptureFixture[str]) -> None:  # type: ignore[no-untyped-def]
    assert fc.main([]) == 0
    assert "No checkpoints" in capsys.readouterr().out


# ---------------------------------------------------------------------------- compose file and proxy
def test_compose_stack_is_production_style() -> None:
    c = yaml.safe_load((ROOT / "compose.yaml").read_text())
    svc = c["services"]
    for name, s in svc.items():
        assert s["logging"]["options"]["max-size"], name  # log rotation on every service
    for name in ("db", "valkey", "api", "web", "caddy"):
        s = svc[name]
        assert s["restart"] == "unless-stopped", name
        assert s["deploy"]["resources"]["limits"]["memory"], name
        # API and web carry their health check in the image; the others declare it in the compose file
        assert "healthcheck" in s or name in ("api", "web"), name
    # only the proxy is public; the database and cache are on an internal network
    published = {n for n, s in svc.items() if s.get("ports")}
    assert published == {"caddy", "mailpit"}
    for dockerfile in ("api", "web"):
        assert "HEALTHCHECK" in (ROOT / f"infra/docker/{dockerfile}.Dockerfile").read_text()
    assert svc["mailpit"]["ports"] == ["127.0.0.1:8025:8025"]
    assert c["networks"]["data"]["internal"] is True
    assert set(svc["db"]["networks"]) == {"data"}
    assert svc["api"]["read_only"] is True
    # secrets come from the environment and must be set
    env = svc["api"]["environment"]
    for k in ("JWT_PRIVATE_KEY_PEM", "DATA_KEY", "CURSOR_SECRET"):
        assert ":?" in env[k]
    assert env["COOKIE_SECURE"] == "true"
    assert "app.services.retention" in " ".join(svc["jobs"]["command"])  # the purge job is scheduled
    assert svc["seed"]["profiles"] == ["demo"] and svc["mailpit"]["profiles"] == ["demo"]


def test_caddy_does_not_buffer_the_event_stream() -> None:
    text = (ROOT / "infra/caddy/Caddyfile").read_text()
    assert "flush_interval -1" in text and "handle /api/*" in text


def test_no_secrets_in_packaging_files() -> None:
    for rel in ("compose.yaml", "infra/docker/api.Dockerfile", "infra/docker/web.Dockerfile", "infra/caddy/Caddyfile"):
        assert not re.search(r"BEGIN [A-Z ]*PRIVATE KEY|password\s*[:=]\s*[\"']?[A-Za-z0-9]{12,}", (ROOT / rel).read_text(), re.I), rel


def test_runtime_requirements_cover_pyproject_imports() -> None:
    reqs = (ROOT / "requirements/api.txt").read_text().lower()
    for pkg in ("argon2-cffi", "pyjwt", "pyotp", "psycopg-pool", "redis", "structlog", "zxcvbn", "python-multipart", "pandera"):
        assert pkg in reqs, pkg
    assert "pyjwt" in (ROOT / "pyproject.toml").read_text().lower()


# ---------------------------------------------------------------------------- demo seed
@pytest.fixture()
def seed():  # type: ignore[no-untyped-def]
    return _load("seed_demo", "infra/demo/seed_demo.py")


def test_generated_passwords_are_strong_and_distinct(seed) -> None:  # type: ignore[no-untyped-def]
    pws = {seed.new_password() for _ in range(50)}
    assert len(pws) == 50
    for p in pws:
        assert re.fullmatch(r"([a-z2-9]{4}-){3}[a-z2-9]{4}", p)
        assert PasswordService.problems(p) == []


def test_demo_seed_creates_accounts_once(seed, db_name: str, admin_url: str, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("ARGON_TIME_COST", "1")
    url = admin_url.replace("postgresql+psycopg://", "postgresql://").rsplit("/", 1)[0] + f"/{db_name}"
    passwords = seed.seed_database(url, companies=60, events=120, suppliers=20)
    assert set(passwords) == {a[0] for a in seed.ACCOUNTS}
    with psycopg.connect(url) as conn:
        rows = conn.execute("SELECT email, role, password_hash, tenant_id FROM users ORDER BY email").fetchall()
        assert len(rows) == 6
        for email, role, h, tenant in rows:
            assert h.startswith("$argon2id$") and passwords[email] not in h  # stored hashed
            assert (tenant is None) == (role in ("finance_analyst", "platform_admin"))
        assert conn.execute("SELECT count(*) FROM companies").fetchone()[0] == 60
        assert conn.execute("SELECT count(*) FROM events").fetchone()[0] == 120
    csv_text = seed.SUPPLIER_CSV.read_text()
    assert csv_text.startswith("name,city,state,tier") and len(csv_text.splitlines()) == 21
    with pytest.raises(SystemExit):  # a second run must not duplicate or reset accounts
        seed.seed_database(url, companies=60, events=120, suppliers=20)
    assert json.dumps(passwords) not in (ROOT / "infra/demo/seed_demo.py").read_text()
