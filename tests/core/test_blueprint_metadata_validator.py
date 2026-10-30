"""Tests for blueprint metadata validation."""

from swarm.core.blueprint_discovery import (
    discover_blueprints,
    validate_blueprint_metadata,
)


def test_validate_blueprint_metadata_valid_full():
    valid_meta = {
        "name": "valid_blueprint",
        "title": "Valid Blueprint",
        "description": "A blueprint that satisfies all schema requirements.",
        "version": "1.0.0",
        "author": "Test Author",
        "category": "orchestration",
        "tags": ["test", "valid"],
    }
    issues = validate_blueprint_metadata(valid_meta, blueprint_key="valid_blueprint")
    assert issues == []


def test_validate_blueprint_metadata_minimal_valid():
    minimal_meta = {
        "name": "minimal_bp",
        "description": "Just enough metadata to be valid.",
    }
    issues = validate_blueprint_metadata(minimal_meta)
    assert issues == []


def test_validate_blueprint_metadata_non_dict():
    issues = validate_blueprint_metadata("not a dict")  # type: ignore[arg-type]
    assert len(issues) == 1
    assert "must be a dictionary" in issues[0]


def test_validate_blueprint_metadata_missing_name():
    issues = validate_blueprint_metadata({"description": "Missing name"}, blueprint_key="test_key")
    assert any("missing required 'name'" in err for err in issues)


def test_validate_blueprint_metadata_non_string_name():
    issues = validate_blueprint_metadata({"name": 123, "description": "Integer name"})
    assert any("must be a string" in err for err in issues)


def test_validate_blueprint_metadata_invalid_name_slug():
    invalid_names = [
        "PascalCaseBlueprint",
        "Chuck's Angels",
        "name with spaces",
        "UPPERCASE",
        "-leading-hyphen",
        "_leading_underscore",
    ]
    for bad_name in invalid_names:
        issues = validate_blueprint_metadata({"name": bad_name, "description": "Test description"})
        assert any("model-id format" in err for err in issues), f"Expected error for bad name: {bad_name}"


def test_validate_blueprint_metadata_missing_or_empty_description():
    issues_missing = validate_blueprint_metadata({"name": "valid_name"})
    assert any("missing valid 'description'" in err for err in issues_missing)

    issues_empty = validate_blueprint_metadata({"name": "valid_name", "description": "   "})
    assert any("missing valid 'description'" in err for err in issues_empty)


def test_validate_blueprint_metadata_invalid_category_or_version():
    issues_cat_empty = validate_blueprint_metadata(
        {"name": "valid_name", "description": "Valid desc", "category": "   "}
    )
    assert any("category must be a non-empty string" in err for err in issues_cat_empty)

    issues_ver_type = validate_blueprint_metadata(
        {"name": "valid_name", "description": "Valid desc", "version": 1.0}  # type: ignore[dict-item]
    )
    assert any("version must be a string" in err for err in issues_ver_type)


def test_builtin_blueprints_satisfy_metadata_validator():
    """Verify all built-in blueprints pass metadata validation without any issues."""
    discovered = discover_blueprints("src/swarm/blueprints")
    assert len(discovered) > 0

    all_issues: dict[str, list[str]] = {}
    for key, bp_info in discovered.items():
        meta = bp_info.get("metadata", {})
        issues = validate_blueprint_metadata(meta, blueprint_key=key)
        if issues:
            all_issues[key] = issues

    assert all_issues == {}, f"Built-in blueprints had metadata validation issues: {all_issues}"
