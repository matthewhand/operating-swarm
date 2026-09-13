from swarm.core.model_text import (
    error_body_message,
    is_usable_model_text,
    sanitize_model_text,
)


def test_strips_unused50_spam():
    raw = "REST plan:\nFor<unused50><unused50><unused50>\n\nhi"
    assert sanitize_model_text(raw) == "REST plan:\nFor\n\nhi"


def test_empty_after_only_specials():
    assert sanitize_model_text("<unused50><unused50>") == ""
    assert sanitize_model_text("") == ""
    assert sanitize_model_text(None) == ""


def test_strips_ansi_and_esc_stripped_csi():
    raw = (
        "REST plan: anlı\x1b[13;28;13;1;0;1_"
        "\x1b[13;28;13;0;0;1_"
        "[13;28;13;1;0;1_[13;28;13;0;0;1_"
        "(no CLI agents configured — add a 'cli_agents' block; see docs/CLI_FUSION.md)"
    )
    cleaned = sanitize_model_text(raw)
    assert "13;28" not in cleaned
    assert "\x1b" not in cleaned
    assert "no CLI agents configured" in cleaned
    assert not is_usable_model_text("anlı[13;28;13;1;0;1_")
    assert is_usable_model_text("[rest-plan] solo")


def test_error_body_message_full_body_extracts_message():
    raw = '{"error": {"message": "Invalid model name passed in model=auxiliary."}}'
    assert error_body_message(raw) == "Invalid model name passed in model=auxiliary."


def test_error_body_message_string_error():
    assert error_body_message('{"error": "boom"}') == "boom"


def test_error_body_message_heads_flagged():
    # Truncated heads a dying upstream leaks; never a real reply.
    assert error_body_message("{") is not None
    assert error_body_message('{"') is not None
    assert error_body_message('{"error') is not None
    assert error_body_message("{}") is not None


def test_error_body_message_ignores_real_replies():
    assert error_body_message("ok") is None
    assert error_body_message("BP reply") is None
    assert error_body_message('{"answer": 42}') is None
    assert error_body_message("") is None
    assert error_body_message(None) is None
    assert error_body_message(123) is None
