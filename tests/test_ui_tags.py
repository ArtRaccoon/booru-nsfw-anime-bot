from app.ui.tags import format_full_tags_messages, format_tag_preview, split_tags


def test_preview_returns_max_12_tags():
    tags = " ".join(f"tag_{index}" for index in range(20))

    preview = format_tag_preview(tags)

    assert preview == ", ".join(f"tag_{index}" for index in range(12))


def test_full_tags_include_all_tags():
    tags = "alpha beta gamma"

    messages = format_full_tags_messages(tags)
    combined = "\n".join(messages)

    for tag in split_tags(tags):
        assert tag in combined
    assert "🏷 Все теги: 3" in messages[0]


def test_long_tag_list_is_split_into_multiple_messages():
    tags = " ".join(f"very_long_tag_{index:03d}" for index in range(100))

    messages = format_full_tags_messages(tags, max_length=250)

    assert len(messages) > 1
    assert all(len(message) <= 250 for message in messages)
    assert messages[0].startswith(f"🏷 Все теги 1/{len(messages)}")
    assert messages[-1].startswith(f"🏷 Все теги {len(messages)}/{len(messages)}")
    combined = "\n".join(messages)
    for tag in split_tags(tags):
        assert tag in combined


def test_colon_tags_are_preserved():
    messages = format_full_tags_messages("rating:explicit artist:name")

    assert "rating:explicit" in messages[0]
    assert "artist:name" in messages[0]


def test_underscores_and_parentheses_are_preserved():
    messages = format_full_tags_messages("blue_hair character_(series)")

    assert "blue_hair" in messages[0]
    assert "character_(series)" in messages[0]
