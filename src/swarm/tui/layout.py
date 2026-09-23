"""ASCII two-pane dump: left agent rail + placeholder chat (--once)."""

from __future__ import annotations

from swarm.tui.client import RailSeat, sectioned_seats

CHAT_PLACEHOLDER = (
    "Chat pane — --once lists the rail only; interactive TUI hydrates and sends.\n"
    "This is a placeholder. No messages are invented."
)


def render_scaffold(
    seats: list[RailSeat],
    *,
    selected_id: str | None = None,
    base_url: str = "",
) -> str:
    """Render Herdr-like chrome as text for ``--once`` / CI."""
    selected = _pick_selected(seats, selected_id)
    # Wave 1b: leave room for the kind section label + the seat indent.
    section_labels = [label for label, _ in sectioned_seats(seats)]
    content = [s.name for s in seats] + section_labels + ["AGENTS"]
    rail_width = max(16, *(len(text) + 5 for text in content)) if content else 16
    rail_width = min(rail_width, 30)
    chat_width = 48
    total = rail_width + chat_width + 3

    header = f" Operating Swarm TUI  {base_url}".rstrip()
    lines = [header, "┌" + "─" * rail_width + "┬" + "─" * chat_width + "┐"]

    rail_rows = _rail_rows(seats, selected, rail_width)
    chat_rows = _wrap(CHAT_PLACEHOLDER, chat_width)
    height = max(len(rail_rows), len(chat_rows), 6)
    rail_rows.extend([" " * rail_width] * (height - len(rail_rows)))
    chat_rows.extend([" " * chat_width] * (height - len(chat_rows)))

    for left, right in zip(rail_rows, chat_rows, strict=True):
        lines.append(f"│{left}│{right}│")

    lines.append("└" + "─" * rail_width + "┴" + "─" * chat_width + "┘")
    lines.append(" j/k select · q quit · --once — rail list only")
    # Keep a machine-stable width note for tests without depending on wcwidth.
    _ = total
    return "\n".join(lines) + "\n"


def _pick_selected(seats: list[RailSeat], selected_id: str | None) -> str | None:
    if not seats:
        return None
    if selected_id:
        for seat in seats:
            if seat.id == selected_id:
                return seat.id
    return seats[0].id


def _rail_rows(seats: list[RailSeat], selected: str | None, width: int) -> list[str]:
    rows = [_pad(" AGENTS", width)]
    if not seats:
        rows.append(_pad(" (none — API empty)", width))
        return rows
    # Wave 1b: kind sections CLI / API / Blueprint / Remote, empty omitted.
    for label, group in sectioned_seats(seats):
        rows.append(_pad(f" {label}", width))
        for seat in group:
            mark = ">" if seat.id == selected else " "
            rows.append(_pad(f"  {mark} {seat.name}", width))
    return rows


def _wrap(text: str, width: int) -> list[str]:
    rows = [_pad(" Chat", width)]
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            rows.append(" " * width)
            continue
        current = ""
        for word in words:
            trial = f"{current} {word}".strip()
            if len(trial) + 1 > width:
                rows.append(_pad(" " + current, width))
                current = word
            else:
                current = trial
        if current:
            rows.append(_pad(" " + current, width))
    return rows


def _pad(text: str, width: int) -> str:
    if len(text) >= width:
        return text[:width]
    return text + " " * (width - len(text))
