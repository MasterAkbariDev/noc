from pathlib import Path

from fastapi.testclient import TestClient

from noc.api.app import create_app
from noc.config import Settings


def make_dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>NOC</title>", encoding="utf-8")
    return dist


def test_spa_index_is_served_at_root(tmp_path: Path) -> None:
    settings = Settings(frontend_dist=make_dist(tmp_path), _env_file=None)
    with TestClient(create_app(settings)) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "<title>NOC</title>" in response.text


def test_health_still_works_with_static_mount(tmp_path: Path) -> None:
    settings = Settings(frontend_dist=make_dist(tmp_path), _env_file=None)
    with TestClient(create_app(settings)) as client:
        assert client.get("/healthz").json() == {"status": "ok"}


def test_no_static_mount_without_dist_dir(tmp_path: Path) -> None:
    settings = Settings(frontend_dist=tmp_path / "missing", _env_file=None)
    with TestClient(create_app(settings)) as client:
        assert client.get("/").status_code == 404
        assert client.get("/healthz").json() == {"status": "ok"}


def test_dashboard_deep_links_fall_back_to_index(tmp_path: Path) -> None:
    settings = Settings(frontend_dist=make_dist(tmp_path), _env_file=None)
    with TestClient(create_app(settings)) as client:
        for path in ("/incidents", "/incidents/3f2c"):
            response = client.get(path)
            assert response.status_code == 200
            assert "<title>NOC</title>" in response.text


def test_unknown_api_paths_and_missing_assets_stay_404(tmp_path: Path) -> None:
    settings = Settings(frontend_dist=make_dist(tmp_path), _env_file=None)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/nope").status_code == 404
        assert client.get("/assets/missing.js").status_code == 404
