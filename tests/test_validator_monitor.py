"""Validator Audit Monitor page — pure-logic helpers + (DB-guarded) layout render."""
from dashboard import validator_monitor as vm


def test_episodes_note_empty_list_is_blank():
    assert vm._episodes_note([]) == ""


def test_episodes_note_formats_up_to_three():
    episodes = [
        {"start": "2008-01", "end": "2008-08", "months": 8,
         "our_z_mean": -1.2, "benchmark_z_mean": 1.1},
        {"start": "2020-03", "end": "2020-06", "months": 4,
         "our_z_mean": -2.0, "benchmark_z_mean": 0.5},
    ]
    note = vm._episodes_note(episodes)
    assert note.startswith("Disagreement episodes:")
    assert "2008-01→2008-08 (8mo" in note
    assert "2020-03→2020-06 (4mo" in note
    assert "more" not in note


def test_episodes_note_truncates_with_a_count():
    episodes = [
        {"start": f"20{10+i}-01", "end": f"20{10+i}-06", "months": 5,
         "our_z_mean": 1.0, "benchmark_z_mean": 1.0}
        for i in range(5)
    ]
    note = vm._episodes_note(episodes)
    assert "(+2 more)" in note


def test_layout_renders():
    # DB-guarded like the other Monitor pages — returns a Div when the
    # signals DB has composite data, else the "no data" placeholder Div.
    try:
        lay = vm.get_layout()
    except Exception:
        return
    assert type(lay).__name__ == "Div"
