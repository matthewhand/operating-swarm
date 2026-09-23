"""REQ-106 / #768: brand marks by surface + SPA/Django favicon wiring."""

from __future__ import annotations

import json
import struct
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from django.test import Client

REPO = Path(__file__).resolve().parents[2]
BRAND = REPO / "assets" / "brand"
RETIRED = BRAND / "retired"
PUBLIC = REPO / "webui" / "frontend" / "public"
SPA_INDEX = REPO / "webui" / "frontend" / "index.html"
BASE = REPO / "src" / "swarm" / "templates" / "base.html"
LOGIN = REPO / "src" / "swarm" / "templates" / "account" / "login.html"
INCLUDE = REPO / "src" / "swarm" / "templates" / "includes" / "brand_icons.html"
SETTINGS_SHEET = REPO / "webui" / "frontend" / "src" / "components" / "SettingsSheet.tsx"
PINOKIO = REPO / "pinokio.js"
PINOKIO_MENU = REPO / "pinokio" / "menu.js"
HERO_JPG = REPO / "assets" / "images" / "openswarm-project-image.jpg"
OLD_ICO = REPO / "assets" / "images" / "favicon.ico"

MINIMAL_SVG = BRAND / "favicon-minimal.svg"
MINIMAL_MONO_SVG = BRAND / "favicon-minimal-mono.svg"
MINIMAL_DARK_SVG = BRAND / "favicon-minimal-mono-on-dark.svg"
GEOMETRIC_SVG = BRAND / "webui-geometric.svg"
CYBER_SVG = BRAND / "marketing-cyber-swarm.svg"

PNG_SIZES = {
    "favicon-16.png": 16,
    "favicon-32.png": 32,
    "favicon-48.png": 48,
    "apple-touch-icon.png": 180,
    "apple-touch-icon-120.png": 120,
    "apple-touch-icon-152.png": 152,
    "icon-192.png": 192,
    "icon-512.png": 512,
    "favicon-minimal-mono-16.png": 16,
    "favicon-minimal-mono-32.png": 32,
    "favicon-minimal-mono-192.png": 192,
    "favicon-minimal-mono-512.png": 512,
    "favicon-minimal-mono-on-dark-16.png": 16,
    "favicon-minimal-mono-on-dark-32.png": 32,
    "favicon-minimal-mono-on-dark-192.png": 192,
    "favicon-minimal-mono-on-dark-512.png": 512,
    "webui-geometric-32.png": 32,
    "webui-geometric-64.png": 64,
    "webui-geometric-128.png": 128,
    "webui-geometric-256.png": 256,
    "marketing-cyber-swarm.png": 512,
    "marketing-cyber-swarm-256.png": 256,
    "marketing-cyber-swarm-512.png": 512,
    "marketing-cyber-swarm-1024.png": 1024,
}

SPA_COPIES = (
    "favicon.ico",
    "favicon-16.png",
    "favicon-32.png",
    "apple-touch-icon.png",
    "icon-192.png",
    "icon-512.png",
    "manifest.json",
    "favicon-minimal.svg",
    "webui-geometric.svg",
)

ROOT_ICON_URLS = (
    ("/favicon.ico", "image/x-icon", b"\x00\x00\x01\x00"),
    ("/favicon-16.png", "image/png", b"\x89PNG\r\n\x1a\n"),
    ("/favicon-32.png", "image/png", b"\x89PNG\r\n\x1a\n"),
    ("/apple-touch-icon.png", "image/png", b"\x89PNG\r\n\x1a\n"),
    ("/icon-192.png", "image/png", b"\x89PNG\r\n\x1a\n"),
    ("/icon-512.png", "image/png", b"\x89PNG\r\n\x1a\n"),
    ("/favicon-minimal.svg", "image/svg+xml", b"<svg"),
    ("/webui-geometric.svg", "image/svg+xml", b"<svg"),
)


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    return struct.unpack(">II", data[16:24])


def _ico_sizes(path: Path) -> list[tuple[int, int]]:
    data = path.read_bytes()
    assert data[:4] == b"\x00\x00\x01\x00"
    count = int.from_bytes(data[4:6], "little")
    sizes = []
    off = 6
    for _ in range(count):
        w = data[off] or 256
        h = data[off + 1] or 256
        sizes.append((w, h))
        off += 16
    return sizes


def _parse_svg(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    assert "<svg" in text
    ET.fromstring(text)
    assert "shutterstock" not in text.lower()
    return text


def test_hero_banner_jpg_is_not_replaced():
    assert HERO_JPG.is_file()
    assert HERO_JPG.stat().st_size > 50_000


def test_surface_masters_match_768_roles():
    minimal = _parse_svg(MINIMAL_SVG)
    geometric = _parse_svg(GEOMETRIC_SVG)
    cyber = _parse_svg(CYBER_SVG)
    assert "#EBA222" in minimal
    assert "#17212A" in minimal
    assert "#EFAB22" in geometric
    assert "#1D2226" in geometric
    assert "os-honey" in geometric
    assert "#F3BA25" in cyber
    assert "os-cyber-glow" in cyber
    assert (BRAND / "tasters" / "option3-minimal-brand-mark.jpg").is_file()
    assert (BRAND / "tasters" / "option1-geometric-bee.jpg").is_file()
    assert (BRAND / "tasters" / "option2-cyber-swarm-bee.jpg").is_file()


def test_minimal_mono_masters():
    mono = _parse_svg(MINIMAL_MONO_SVG)
    dark = _parse_svg(MINIMAL_DARK_SVG)
    assert "currentColor" in mono
    assert "#FFFFFF" in dark
    assert "#111111" in dark


def test_clipart_487_is_retired_and_unwired():
    assert (RETIRED / "bee-mark.svg").is_file()
    assert (RETIRED / "README.md").is_file()
    assert not (BRAND / "bee-mark.svg").is_file()
    wired = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (SPA_INDEX, BASE, LOGIN, INCLUDE, SETTINGS_SHEET, PINOKIO)
    )
    assert "bee-mark.svg" not in wired
    assert "fa-robot" not in BASE.read_text(encoding="utf-8")


def test_raster_checklist_and_png_dimensions():
    for name, size in PNG_SIZES.items():
        path = BRAND / name
        assert path.is_file(), name
        width, height = _png_size(path)
        assert (width, height) == (size, size), f"{name}: {width}x{height}"


def test_favicon_ico_is_16_32_48():
    ico = BRAND / "favicon.ico"
    assert ico.is_file()
    assert set(_ico_sizes(ico)) == {(16, 16), (32, 32), (48, 48)}
    assert OLD_ICO.read_bytes() == ico.read_bytes()


def test_spa_public_copies_match_brand():
    for name in SPA_COPIES:
        src = BRAND / name
        dest = PUBLIC / name
        assert src.is_file(), name
        assert dest.is_file(), name
        assert src.read_bytes() == dest.read_bytes(), name


def test_manifest_lists_pwa_colour_icons():
    manifest = json.loads((BRAND / "manifest.json").read_text(encoding="utf-8"))
    srcs = {icon["src"] for icon in manifest["icons"]}
    assert "/icon-192.png" in srcs
    assert "/icon-512.png" in srcs
    assert manifest["theme_color"] == "#111111"
    assert manifest["background_color"] == "#17212A"


def test_html_heads_reference_brand_icons():
    spa = SPA_INDEX.read_text(encoding="utf-8")
    include = INCLUDE.read_text(encoding="utf-8")
    base = BASE.read_text(encoding="utf-8")
    login = LOGIN.read_text(encoding="utf-8")
    assert 'rel="icon" href="/favicon.ico"' in spa
    assert 'href="/favicon-16.png"' in spa
    assert 'href="/favicon-32.png"' in spa
    assert 'rel="apple-touch-icon" href="/apple-touch-icon.png"' in spa
    assert 'rel="manifest" href="/manifest.json"' in spa
    assert "includes/brand_icons.html" in base
    assert "includes/brand_icons.html" in login
    assert "brand/favicon.ico" in include
    assert "brand/apple-touch-icon.png" in include
    assert "brand/manifest.json" in include


def test_webui_chrome_uses_geometric_mark():
    base = BASE.read_text(encoding="utf-8")
    login = LOGIN.read_text(encoding="utf-8")
    settings = SETTINGS_SHEET.read_text(encoding="utf-8")
    assert "brand/webui-geometric.svg" in base
    assert "brand/webui-geometric.svg" in login
    assert "/webui-geometric.svg" in settings


def test_pinokio_uses_minimal_mark():
    assert PINOKIO.is_file()
    text = PINOKIO_MENU.read_text(encoding="utf-8")
    assert "assets/brand/favicon-minimal.svg" in text
    assert "rest_mode/svg/logo.svg" not in text
    assert "assets/brand/bee-mark.svg" not in text


@pytest.mark.django_db
def test_root_icon_urls_are_not_html(client: Client):
    for url, ctype, magic in ROOT_ICON_URLS:
        response = client.get(url)
        assert response.status_code == 200, url
        assert ctype in response["Content-Type"], url
        assert response.content.startswith(magic), url
        assert b"<html" not in response.content[:200].lower()
        assert getattr(response, "streaming", False) is False

    manifest = client.get("/manifest.json")
    assert manifest.status_code == 200
    assert "manifest" in manifest["Content-Type"] or "json" in manifest["Content-Type"]
    body = json.loads(manifest.content)
    # REQ-862 identity: the served PWA manifest carries the Operating Swarm
    # name, matching the UI templates and the SPA copy (#311 rename).
    assert body["name"] == "Operating Swarm"


def test_django_static_finder_resolves_brand_icons():
    """Operator {% static 'brand/…' %} is backed by STATICFILES_DIRS prefix.

    The Django test client does not mount staticfiles; collectstatic / runserver
    do. Finder resolution is the contract.
    """
    from django.contrib.staticfiles import finders

    ico = finders.find("brand/favicon.ico")
    png = finders.find("brand/favicon-16.png")
    geo = finders.find("brand/webui-geometric.svg")
    assert ico and Path(ico).read_bytes() == (BRAND / "favicon.ico").read_bytes()
    assert png and Path(png).read_bytes() == (BRAND / "favicon-16.png").read_bytes()
    assert geo and Path(geo).read_bytes() == GEOMETRIC_SVG.read_bytes()


@pytest.mark.django_db
def test_operator_and_login_html_link_static_brand(client: Client):
    login = client.get("/login/")
    assert login.status_code == 200
    html = login.content.decode("utf-8")
    assert "brand/favicon.ico" in html
    assert "brand/apple-touch-icon.png" in html
    assert "brand/manifest.json" in html
    assert "brand/webui-geometric.svg" in html
