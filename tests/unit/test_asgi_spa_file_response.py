"""Lock: SPA HTML/assets must not use Django FileResponse on ASGI (#425)."""

from pathlib import Path

from django.http import HttpResponse
from django.test import override_settings

from swarm.views.web_views import asgi_file_response

ROOT = Path(__file__).resolve().parents[2]


def test_asgi_file_response_is_buffered_not_streaming(tmp_path):
    path = tmp_path / "index.html"
    path.write_text("<div id='root'></div>", encoding="utf-8")
    response = asgi_file_response(path, "text/html")
    assert isinstance(response, HttpResponse)
    assert getattr(response, "streaming", False) is False
    assert b"root" in response.content


def test_spa_views_and_urls_do_not_use_fileresponse():
    web_views = (ROOT / "src/swarm/views/web_views.py").read_text(encoding="utf-8")
    urls = (ROOT / "src/swarm/urls.py").read_text(encoding="utf-8")
    assert "return FileResponse" not in web_views
    assert "FileResponse(" not in urls
    assert "asgi_file_response" in web_views
    # #714: the ASGI-safe serving helper lives in web_views; routing modules
    # consume the views (spa_asset_view / spa_fallback_view), not the helper.
    assert "spa_asset_view" in urls
    assert "spa_fallback_view" in urls
    assert "django.views.static import serve" not in urls.split("SPA Fallback")[-1]


@override_settings(DEBUG=True)
def test_index_and_chat_are_not_streaming_when_dist_exists(client):
    dist = ROOT / "webui/frontend/dist/index.html"
    if not dist.is_file():
        return
    for path in ("/", "/chat"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert getattr(response, "streaming", False) is False, path
        assert b"root" in response.content, path
