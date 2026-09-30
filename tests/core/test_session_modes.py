from swarm.core.session_modes import (
    apply_session_mode,
    cycle_session_mode,
    normalize_session_mode,
)


def test_cycle_is_default_plan_auto_edit():
    assert cycle_session_mode("default") == "plan"
    assert cycle_session_mode("plan") == "auto-edit"
    assert cycle_session_mode("auto-edit") == "default"
    assert "always" not in cycle_session_mode("auto-edit")


def test_aliases_and_wrap():
    assert normalize_session_mode("acceptEdits") == "auto-edit"
    assert apply_session_mode("hi", "default") == "hi"
    plan = apply_session_mode("hi", "plan")
    assert plan.startswith("[Operating Swarm session mode: plan]")
    assert plan.endswith("hi")
    assert "Do not edit files" in plan
    auto = apply_session_mode("hi", "auto-edit")
    assert "auto-edit" in auto
    assert "always-approve" in auto
    assert apply_session_mode("  ", "plan") == "  "
