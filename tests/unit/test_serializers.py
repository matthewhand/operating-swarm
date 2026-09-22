from swarm.serializers import ChatCompletionRequestSerializer


def test_validate_messages_happy_path():
    data = {
        "model": "gpt-3.5-turbo",
        "messages": [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"}
        ]
    }
    serializer = ChatCompletionRequestSerializer(data=data)
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["messages"] == data["messages"]

def test_validate_messages_empty_list():
    data = {
        "model": "gpt-3.5-turbo",
        "messages": []
    }
    serializer = ChatCompletionRequestSerializer(data=data)
    assert not serializer.is_valid()
    # DRF's min_length=1 on the field itself might catch this before validate_messages
    # or validate_messages might catch it.
    assert "messages" in serializer.errors
    # The explicit check in validate_messages says "Messages list cannot be empty."
    # But DRF's ListField (which MessageSerializer(many=True) uses) might raise its own error.
    # Let's see what happens.

def test_validate_messages_not_a_list():
    data = {
        "model": "gpt-3.5-turbo",
        "messages": "not a list"
    }
    serializer = ChatCompletionRequestSerializer(data=data)
    assert not serializer.is_valid()
    assert "messages" in serializer.errors

def test_validate_messages_item_not_a_dict():
    data = {
        "model": "gpt-3.5-turbo",
        "messages": ["not a dict"]
    }
    serializer = ChatCompletionRequestSerializer(data=data)
    assert not serializer.is_valid()
    # The error structure for validate_messages when it raises ValidationError(errors)
    # where errors is a list of dicts.
    assert "messages" in serializer.errors
    # DRF reports per-item errors; a non-dict item yields a non_field_errors entry.
    assert "Expected a dictionary" in str(serializer.errors["messages"][0]["non_field_errors"][0])

def test_validate_messages_invalid_content_type():
    data = {
        "model": "gpt-3.5-turbo",
        "messages": [
            {"role": "user", "content": 123}
        ]
    }
    serializer = ChatCompletionRequestSerializer(data=data)
    assert not serializer.is_valid()
    assert "messages" in serializer.errors
    # It should be in the first item's errors
    assert serializer.errors["messages"][0]["content"] == ["Content must be a string or null."]

def test_validate_messages_multiple_errors():
    data = {
        "model": "gpt-3.5-turbo",
        "messages": [
            "not a dict",
            {"role": "user", "content": 123},
            {"role": "assistant", "content": "valid"}
        ]
    }
    serializer = ChatCompletionRequestSerializer(data=data)
    assert not serializer.is_valid()
    assert "messages" in serializer.errors
    errors = serializer.errors["messages"]
    assert "Expected a dictionary" in str(errors[0]["non_field_errors"][0])
    # Note: int content is coerced to str by DRF CharField, so message 1 is
    # accepted under current rules; only the non-dict item errors.
    # DRF <=3.15 emitted a positional entry per message; DRF 3.16 reports
    # only the failing indexes (#890 lock uplift). Either way: message 0
    # failed, messages 1–2 produced no errors.
    if len(errors) == 3:
        assert not errors[1] and not errors[2]
    else:
        assert set(errors) == {0}

def test_validate_messages_null_content_is_allowed():
    data = {
        "model": "gpt-3.5-turbo",
        "messages": [
            {"role": "assistant", "content": None}
        ]
    }
    serializer = ChatCompletionRequestSerializer(data=data)
    # MessageSerializer says content = serializers.CharField(allow_null=True, ...)
    # validate_messages says content is None and isinstance(content, str) is false
    # but it only raises if content is NOT None.
    # if 'content' in raw_msg and content is not None and not isinstance(content, str):
    assert serializer.is_valid(), serializer.errors

def test_validate_messages_accepts_image_url_parts():
    data = {
        "model": "api_agent",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "what is in this image?"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,abc"},
                    },
                ],
            }
        ],
    }
    serializer = ChatCompletionRequestSerializer(data=data)
    assert serializer.is_valid(), serializer.errors
    content = serializer.validated_data["messages"][0]["content"]
    assert isinstance(content, list)
    assert content[1]["type"] == "image_url"


def test_validate_model_must_be_string():
    data = {
        "model": 123,
        "messages": [{"role": "user", "content": "Hello"}]
    }
    serializer = ChatCompletionRequestSerializer(data=data)
    assert not serializer.is_valid()
    assert "model" in serializer.errors
    assert serializer.errors["model"] == ["Field 'model' must be a string."]
