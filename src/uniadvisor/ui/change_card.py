"""What a change card asks, without Streamlit: the number ranges of the boxes and the question for each open
parameter. The Streamlit card (adjust.py) and the web API (api/views.py) share them."""

from __future__ import annotations

from uniadvisor.chat.changes import Item
from uniadvisor.ui.state import MAX_CUTOFF_SHIFT

# kind of change -> (lowest, highest, step) of its number box
NUMBER_RANGES = {"set_score": (0.0, 10.0, 0.25), "set_extra": (0.0, 10.0, 0.25), "set_budget": (1.0, 1000.0, 5.0),
                 "set_own_score": (0.0, 100.0, 0.05), "set_cutoff_shift": (-MAX_CUTOFF_SHIFT, MAX_CUTOFF_SHIFT, 0.25)}
DEFAULT_RANGE = (0.0, 1000.0, 1.0)


def param_label(item: Item, param: str) -> str:
    if item.kind == "set_cutoff_shift" and param == "value":
        return "Cao hơn bao nhiêu điểm? (thấp hơn: nhập số âm)"
    return {"school": "Trường nào?", "subject": "Môn nào?", "value": "Bao nhiêu?", "index": "Hướng học nào?",
            "code": "Ngành nào?", "new": "Ngành gần nào?", "target": "Đưa lại gì?"}.get(param, param)
