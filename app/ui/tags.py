"""Helpers for compact tag previews and full tag messages."""

TELEGRAM_SAFE_MESSAGE_LENGTH = 3900
DEFAULT_PREVIEW_LIMIT = 12


def split_tags(tags: str) -> list[str]:
    """Split a booru tag string into individual tags.

    Booru providers in this project store tags as whitespace-separated values, while
    display text joins them with commas. Accept both separators so helpers are safe
    to use with provider data and already-formatted strings.
    """
    return [tag for tag in tags.replace(",", " ").split() if tag]


def format_tag_preview(tags: str, limit: int = DEFAULT_PREVIEW_LIMIT) -> str:
    """Return a compact comma-separated tag preview."""
    preview = split_tags(tags)[:limit]
    return ", ".join(preview) or "—"


def _full_tags_header(count: int, part: int | None = None, total: int | None = None) -> str:
    if part is not None and total is not None:
        return f"🏷 Все теги {part}/{total}: {count}"
    return f"🏷 Все теги: {count}"


def _split_tag_lines(tag_list: list[str], content_limit: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    for tag in tag_list:
        candidate = tag if not current else f"{current}, {tag}"
        if len(candidate) <= content_limit or not current:
            current = candidate
            continue
        chunks.append(current)
        current = tag
    if current or not chunks:
        chunks.append(current)
    return chunks


def format_full_tags_messages(
    tags: str, max_length: int = TELEGRAM_SAFE_MESSAGE_LENGTH
) -> list[str]:
    """Format all tags for Telegram, splitting messages before max_length.

    The output is plain text: no Markdown/HTML parse mode is required, so tag
    symbols such as underscores, colons, and parentheses are preserved exactly.
    """
    tag_list = split_tags(tags)
    count = len(tag_list)
    all_tags = ", ".join(tag_list) or "—"
    header = _full_tags_header(count)
    single_message = f"{header}\n\n`{all_tags}`"
    if len(single_message) <= max_length:
        return [single_message]

    # Reserve enough space for a split header, blank line, and literal backticks.
    content_limit = max(1, max_length - len(_full_tags_header(count, 999, 999)) - 4)
    chunks = _split_tag_lines(tag_list, content_limit)
    total = len(chunks)

    # If the actual total has more digits than the estimate, split once more with
    # the precise header length.
    content_limit = max(1, max_length - len(_full_tags_header(count, total, total)) - 4)
    chunks = _split_tag_lines(tag_list, content_limit)
    total = len(chunks)

    return [
        f"{_full_tags_header(count, index, total)}\n\n`{chunk}`"
        for index, chunk in enumerate(chunks, start=1)
    ]
