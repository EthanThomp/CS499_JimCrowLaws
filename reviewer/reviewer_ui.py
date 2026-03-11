#!/usr/bin/env python3
"""
Gradio Reviewer UI for Jim Crow Laws Archive.

Run with:  python reviewer/reviewer_ui.py
Install:   pip install gradio
"""

import json
from pathlib import Path

import gradio as gr

# ─── Configuration ────────────────────────────────────────────────────────────

RESULTS_DIR = Path(__file__).parent.parent / "doc_processing_results"

CATEGORIES = [
    "",
    "education",
    "housing",
    "marriage",
    "public_accommodations",
    "incarceration",
    "voting",
    "labor",
    "other",
]

INSTRUCTIONS = """\
- Choose a file from the dropdown — it loads automatically.
- Entries appear in order of importance: uncertain or flagged ones come first.
- Read the original statute text on the left, then the AI's assessment on the right. Expand **AI Reasoning** to see why the AI reached its conclusion.
- If the AI got it right, just click **Save** — no changes needed.
- If it's wrong, correct **Is Jim Crow?** and/or **Category**, then click **Save**.
- Add a **Research Note** to record your own thoughts for future reference.
- Use **← Prev / Next →** to browse entries, or **Jump to Next Unreviewed** to skip ahead.
- Focus on flagged entries and those marked "Yes" — you don't need to review everything.
"""

# ─── Pure Helper Functions ────────────────────────────────────────────────────


def discover_files() -> list[str]:
    """Return sorted list of *.json filenames in RESULTS_DIR."""
    if not RESULTS_DIR.exists():
        return []
    return [f.name for f in sorted(RESULTS_DIR.glob("*.json"))]


def build_sorted_ids(entries: list) -> list[str]:
    """Sort entry IDs by priority (stable):
    0 = needs_human_review, 1 = is_jim_crow=="yes" (not flagged), 2 = everything else.
    Ambiguous entries always have needs_human_review=True, so they fall into tier 0.
    """
    def _priority(e):
        cls = e.get("classification", {})
        if cls.get("needs_human_review", False):
            return 0
        if cls.get("is_jim_crow") == "yes":
            return 1
        return 2

    return [e["entry_id"] for e in sorted(entries, key=_priority)]


def build_entry_index(entries: list) -> dict:
    """O(1) lookup by entry_id."""
    return {e["entry_id"]: e for e in entries}


def format_confidence(value) -> str:
    """Return e.g. '95% (high)', '60% (medium)', '45% (low)'."""
    try:
        c = float(value or 0.0)
    except (TypeError, ValueError):
        c = 0.0
    pct = int(round(c * 100))
    level = "high" if c >= 0.8 else "medium" if c >= 0.6 else "low"
    return f"{pct}% ({level})"


def compute_progress(entries: list) -> tuple:
    """Return (reviewed_count, total, priority_remaining, priority_total).

    Priority entries: is_jim_crow == "yes" OR needs_human_review == True.
    """
    total = len(entries)
    reviewed_count = sum(1 for e in entries if e.get("reviewed", False))
    priority = [
        e for e in entries
        if e.get("classification", {}).get("is_jim_crow") == "yes"
        or e.get("classification", {}).get("needs_human_review", False)
    ]
    priority_total = len(priority)
    priority_remaining = sum(1 for e in priority if not e.get("reviewed", False))
    return reviewed_count, total, priority_remaining, priority_total


def build_progress_text(entries: list) -> tuple[str, bool]:
    """Return (progress_markdown_text, show_complete_banner)."""
    rc, total, pr, pt = compute_progress(entries)
    overall = f"**{rc} / {total} entries reviewed**"
    if pt == 0:
        priority_str = "No priority entries in this file"
        show_banner = False
    elif pr == 0:
        priority_str = "✅ All priority entries reviewed"
        show_banner = True
    else:
        priority_str = f"⚠ {pr} priority entries remaining"
        show_banner = False
    return f"{overall}  |  {priority_str}", show_banner


def recalculate_statistics(data: dict) -> None:
    """Mutate data['statistics'] and data['human_review_queue'] in place."""
    entries = data.get("entries", [])
    counts: dict[str, int] = {}
    cats: dict[str, int] = {}
    reviewed = 0
    for e in entries:
        cls = e.get("classification", {})
        jc = cls.get("is_jim_crow", "no")
        counts[jc] = counts.get(jc, 0) + 1
        if e.get("reviewed", False):
            reviewed += 1
        cat = cls.get("category")
        if cat:
            cats[cat] = cats.get(cat, 0) + 1
    data["statistics"] = {
        "total_entries": len(entries),
        "jim_crow_count": counts.get("yes", 0),
        "non_jim_crow_count": counts.get("no", 0),
        "ambiguous_count": counts.get("ambiguous", 0),
        "reviewed": reviewed,
        "by_category": cats,
    }
    data["human_review_queue"] = [
        e["entry_id"] for e in entries
        if e.get("classification", {}).get("needs_human_review", False)
        and not e.get("reviewed", False)
    ]


def entry_to_display_values(data: dict, sorted_ids: list, idx: int) -> tuple:
    """Return a 16-tuple of raw display values for the entry at sorted_ids[idx].

    Index  Field
    -----  -----
    0      entry_id
    1      source_filename
    2      page_number (str)
    3      year (str)
    4      citation
    5      badge HTML
    6      ocr_text
    7      title
    8      confidence (formatted)
    9      summary
    10     keywords (comma-joined)
    11     racial_indicator
    12     reasoning
    13     is_jim_crow  ← dropdown value (str)
    14     category     ← dropdown value (str, "" for None)
    15     reviewer_note
    """
    entries_by_id = build_entry_index(data.get("entries", []))
    if not sorted_ids or not (0 <= idx < len(sorted_ids)):
        return ("", "", "", "", "", "", "", "", "", "", "", "", "", "no", "", "")

    entry = entries_by_id.get(sorted_ids[idx], {})
    cls = entry.get("classification", {})

    # Badge HTML
    if entry.get("reviewed", False):
        badge = (
            '<div style="padding:6px 12px;background:#d1fae5;color:#065f46;'
            'border-radius:6px;font-weight:600;display:inline-block;">'
            "✓ Already Reviewed</div>"
        )
    elif cls.get("needs_human_review", False):
        badge = (
            '<div style="padding:6px 12px;background:#fef3c7;color:#92400e;'
            'border-radius:6px;font-weight:600;display:inline-block;">'
            "⚠ Flagged for Human Review</div>"
        )
    elif cls.get("is_jim_crow") == "yes":
        badge = (
            '<div style="padding:6px 12px;background:#fee2e2;color:#991b1b;'
            'border-radius:6px;font-weight:600;display:inline-block;">'
            "Jim Crow Law</div>"
        )
    else:
        badge = ""

    return (
        entry.get("entry_id", ""),
        entry.get("source_filename", ""),
        str(entry.get("page_number", "")),
        str(entry.get("year") or ""),
        entry.get("citation", ""),
        badge,
        entry.get("ocr_text", ""),
        cls.get("title", ""),
        format_confidence(cls.get("confidence")),
        cls.get("summary", ""),
        ", ".join(cls.get("keywords", [])),
        cls.get("racial_indicator", ""),
        cls.get("reasoning", ""),
        cls.get("is_jim_crow", "no"),
        cls.get("category") or "",
        entry.get("reviewer_note", ""),
    )


def make_display_tuple(data: dict, sorted_ids: list, idx: int) -> tuple:
    """Wrap entry_to_display_values, replacing the raw category string (index 14)
    with a gr.update that also sets interactivity based on is_jim_crow.
    """
    vals = list(entry_to_display_values(data, sorted_ids, idx))
    is_jc = vals[13]
    cat_val = vals[14]
    if is_jc == "no":
        vals[14] = gr.update(interactive=False, value="")
    else:
        vals[14] = gr.update(interactive=True, value=cat_val)
    return tuple(vals)


def _empty_displays() -> tuple:
    """16-tuple of blank/default display values."""
    return (
        "", "", "", "", "", "", "",   # entry_id … ocr_text
        "", "", "", "", "", "",       # title … reasoning
        "no",                         # is_jim_crow
        gr.update(interactive=True, value=""),  # category
        "",                           # reviewer_note
    )


# ─── Event Handlers ───────────────────────────────────────────────────────────

_INIT_STATE = {"file_path": None, "data": None, "sorted_ids": [], "current_idx": 0}


def _pack(display_16: tuple, entries: list, state: dict, status: str) -> tuple:
    """Assemble the full 20-item return tuple that maps to all_outputs."""
    progress_text, show_banner = build_progress_text(entries)
    return (
        *display_16,
        progress_text,
        gr.update(visible=show_banner),
        state,
        status,
    )


def load_file(filename: str, state: dict) -> tuple:
    if not filename or str(filename).startswith("No result"):
        return (
            *_empty_displays(),
            "No file selected.",
            gr.update(visible=False),
            {**_INIT_STATE},
            "No file selected.",
        )

    file_path = RESULTS_DIR / filename
    try:
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return (
            *_empty_displays(),
            "Error loading file.",
            gr.update(visible=False),
            {**_INIT_STATE},
            f"Error: {exc}",
        )

    entries = data.get("entries", [])
    if not entries:
        new_state = {
            "file_path": str(file_path), "data": data,
            "sorted_ids": [], "current_idx": 0,
        }
        return (
            *_empty_displays(),
            "0 / 0 entries reviewed  |  No entries found",
            gr.update(visible=False),
            new_state,
            "No entries found in this file.",
        )

    sorted_ids = build_sorted_ids(entries)
    new_state = {
        "file_path": str(file_path),
        "data": data,
        "sorted_ids": sorted_ids,
        "current_idx": 0,
    }
    display_16 = make_display_tuple(data, sorted_ids, 0)
    n = len(sorted_ids)
    return _pack(display_16, entries, new_state,
                 f"Loaded {n} entries from {filename}. Entry 1 of {n}.")


def navigate(direction: str, state: dict) -> tuple:
    data = state.get("data")
    sorted_ids = state.get("sorted_ids", [])
    idx = state.get("current_idx", 0)

    if not data or not sorted_ids:
        return (
            *_empty_displays(),
            "No file loaded.",
            gr.update(visible=False),
            state,
            "No file loaded.",
        )

    n = len(sorted_ids)
    entries_by_id = build_entry_index(data.get("entries", []))

    if direction == "prev":
        new_idx = max(0, idx - 1)
        status = f"Entry {new_idx + 1} of {n}."

    elif direction == "next":
        new_idx = min(n - 1, idx + 1)
        status = f"Entry {new_idx + 1} of {n}."

    elif direction == "unreviewed":
        new_idx = None
        # Search forward from idx + 1
        for i in range(idx + 1, n):
            if not entries_by_id.get(sorted_ids[i], {}).get("reviewed", False):
                new_idx = i
                break
        # Wrap around from beginning if nothing found ahead
        if new_idx is None:
            for i in range(0, idx):
                if not entries_by_id.get(sorted_ids[i], {}).get("reviewed", False):
                    new_idx = i
                    break
        if new_idx is None:
            new_idx = idx
            status = "All entries reviewed."
        else:
            status = f"Entry {new_idx + 1} of {n} (next unreviewed)."

    else:
        new_idx = idx
        status = f"Entry {new_idx + 1} of {n}."

    state["current_idx"] = new_idx
    display_16 = make_display_tuple(data, sorted_ids, new_idx)
    return _pack(display_16, data.get("entries", []), state, status)


def save_review(
    is_jim_crow: str,
    category: str,
    reviewer_note: str,
    state: dict,
) -> tuple:
    data = state.get("data")
    sorted_ids = state.get("sorted_ids", [])
    idx = state.get("current_idx", 0)
    file_path = state.get("file_path")

    if not data or not sorted_ids or not file_path:
        return (
            *_empty_displays(),
            "No file loaded.",
            gr.update(visible=False),
            state,
            "No file loaded.",
        )

    entry_id = sorted_ids[idx]
    entries_by_id = build_entry_index(data.get("entries", []))
    entry = entries_by_id.get(entry_id)
    if not entry:
        return (
            *_empty_displays(),
            "Error.",
            gr.update(visible=False),
            state,
            "Entry not found.",
        )

    # Force category to None when is_jim_crow is "no"
    effective_category = None if is_jim_crow == "no" else (category or None)

    # Mutate entry in place
    entry["classification"]["is_jim_crow"] = is_jim_crow
    entry["classification"]["category"] = effective_category
    entry["classification"]["needs_human_review"] = False
    entry["reviewer_note"] = reviewer_note
    entry["reviewed"] = True

    recalculate_statistics(data)

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        status = "Saved."
    except OSError as exc:
        status = f"Error saving: {exc}"

    entries = data.get("entries", [])
    display_16 = make_display_tuple(data, sorted_ids, idx)
    return _pack(display_16, entries, state, status)


def toggle_category_interactivity(is_jim_crow: str):
    """Disable + clear category when 'no'; re-enable (without restoring) otherwise."""
    if is_jim_crow == "no":
        return gr.update(interactive=False, value="")
    return gr.update(interactive=True)


# ─── UI Layout ────────────────────────────────────────────────────────────────


def build_ui() -> gr.Blocks:
    initial_files = discover_files()
    file_choices = initial_files or ["No result files found in doc_processing_results/"]

    with gr.Blocks(title="Jim Crow Laws Archive — Reviewer") as demo:

        state = gr.State({
            "file_path": None,
            "data": None,
            "sorted_ids": [],
            "current_idx": 0,
        })

        gr.Markdown(
            "# Jim Crow Laws Archive — Human Reviewer UI\n"
        )

        # ── File selection ────────────────────────────────────────────────────
        with gr.Row():
            file_dropdown = gr.Dropdown(
                choices=file_choices,
                label="Select Result File",
                scale=4,
            )
            refresh_btn = gr.Button("Refresh File List", scale=1)

        # ── Progress ──────────────────────────────────────────────────────────
        progress_md = gr.Markdown("No file selected.")
        complete_banner = gr.HTML(
            value=(
                '<div style="padding:12px 16px;background:#d1fae5;color:#065f46;'
                'border-radius:8px;font-weight:700;font-size:1.05em;text-align:center;">'
                "✅ All priority entries reviewed — this file is complete!</div>"
            ),
            visible=False,
        )

        # ── Instructions ──────────────────────────────────────────────────────
        with gr.Accordion("Reviewer Instructions:", open=True):
            gr.Markdown(INSTRUCTIONS)

        # ── Main workspace ────────────────────────────────────────────────────
        with gr.Row():

            # LEFT — OCR content
            with gr.Column(scale=3):
                with gr.Row():
                    entry_id_box = gr.Textbox(
                        label="Entry ID", interactive=False, scale=3
                    )
                    source_file_box = gr.Textbox(
                        label="Source File", interactive=False, scale=3
                    )
                    page_box = gr.Textbox(
                        label="Page", interactive=False, scale=1
                    )
                    year_box = gr.Textbox(
                        label="Year", interactive=False, scale=1
                    )
                citation_box = gr.Textbox(label="Citation", interactive=False)
                badge_html = gr.HTML("")
                ocr_text_box = gr.Textbox(
                    label="OCR Text",
                    lines=18,
                    interactive=False,
                    show_label=True,
                    buttons=["copy"],
                )
                with gr.Accordion("AI Reasoning", open=False):
                    reasoning_box = gr.Textbox(
                        label="Reasoning", lines=6, interactive=False
                    )

            # RIGHT — Classification & Review
            with gr.Column(scale=2):
                with gr.Group():
                    gr.Markdown("### AI Classification")
                    with gr.Row():
                        title_box = gr.Textbox(
                            label="Title", interactive=False, scale=3
                        )
                        confidence_box = gr.Textbox(
                            label="Confidence", interactive=False, scale=1
                        )
                    summary_box = gr.Textbox(
                        label="Summary", lines=3, interactive=False
                    )
                    keywords_box = gr.Textbox(label="Keywords", interactive=False)
                    racial_indicator_box = gr.Textbox(
                        label="Racial Indicator", interactive=False
                    )

                with gr.Group():
                    gr.Markdown("### Your Review")
                    is_jim_crow_dd = gr.Dropdown(
                        choices=["yes", "no", "ambiguous"],
                        label="Is Jim Crow?",
                        value="no",
                    )
                    category_dd = gr.Dropdown(
                        choices=CATEGORIES,
                        label="Category",
                        value="",
                    )
                    reviewer_note_box = gr.Textbox(
                        label="Research Notes",
                        lines=3,
                        placeholder="Your own notes for future reference (ambiguity, context, questions, etc.)...",
                    )

                save_btn = gr.Button("Save Review", variant="primary")

                with gr.Row():
                    prev_btn = gr.Button("← Prev")
                    next_btn = gr.Button("Next →")
                    jump_btn = gr.Button("Jump to Next Unreviewed")

        status_msg = gr.Markdown("")

        # ── Output list — order MUST match _pack() return tuple ───────────────
        all_outputs = [
            # display_16
            entry_id_box, source_file_box, page_box, year_box,
            citation_box, badge_html, ocr_text_box,
            title_box, confidence_box, summary_box,
            keywords_box, racial_indicator_box, reasoning_box,
            is_jim_crow_dd, category_dd, reviewer_note_box,
            # progress + state
            progress_md, complete_banner,
            state, status_msg,
        ]

        # ── Event wiring ──────────────────────────────────────────────────────

        def _refresh():
            files = discover_files()
            choices = files or ["No result files found in doc_processing_results/"]
            return gr.update(choices=choices, value=None)

        refresh_btn.click(fn=_refresh, outputs=[file_dropdown])

        file_dropdown.change(
            fn=load_file,
            inputs=[file_dropdown, state],
            outputs=all_outputs,
        )

        save_btn.click(
            fn=save_review,
            inputs=[is_jim_crow_dd, category_dd, reviewer_note_box, state],
            outputs=all_outputs,
        )

        prev_btn.click(
            fn=lambda s: navigate("prev", s),
            inputs=[state],
            outputs=all_outputs,
        )
        next_btn.click(
            fn=lambda s: navigate("next", s),
            inputs=[state],
            outputs=all_outputs,
        )
        jump_btn.click(
            fn=lambda s: navigate("unreviewed", s),
            inputs=[state],
            outputs=all_outputs,
        )

        is_jim_crow_dd.change(
            fn=toggle_category_interactivity,
            inputs=[is_jim_crow_dd],
            outputs=[category_dd],
        )

    return demo


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    demo = build_ui()
    demo.launch()
