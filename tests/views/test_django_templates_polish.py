"""Unit tests for Django template polish and extension blocks."""

from __future__ import annotations

from pathlib import Path
from django.template import Context, Template

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = ROOT / "src" / "swarm" / "templates"


def test_base_html_has_extra_head_and_extra_js_blocks():
    base_html = (TEMPLATES_DIR / "base.html").read_text(encoding="utf-8")
    assert "{% block extra_head %}{% endblock %}" in base_html
    assert "{% block extra_js %}{% endblock %}" in base_html


def test_profiles_html_uses_bootstrap_table_classes():
    profiles_html = (TEMPLATES_DIR / "profiles.html").read_text(encoding="utf-8")
    assert "class=\"prof-table table table-dark table-hover mb-0\"" in profiles_html


def test_child_template_can_override_extra_head_and_extra_js():
    child_template_src = """
    {% extends "base.html" %}
    {% block extra_head %}<meta name="test-extra-head" content="ok">{% endblock %}
    {% block content %}<div>Test Content</div>{% endblock %}
    {% block extra_js %}<script>console.log('test-extra-js');</script>{% endblock %}
    """
    t = Template(child_template_src)
    rendered = t.render(Context({"request": type("Req", (), {"path": "/"})()}))
    assert '<meta name="test-extra-head" content="ok">' in rendered
    assert "<div>Test Content</div>" in rendered
    assert "<script>console.log('test-extra-js');</script>" in rendered
