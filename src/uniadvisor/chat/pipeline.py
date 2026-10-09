"""One chat message, end to end (spec 5): split -> classify -> extract -> one change card + immediate answers.

Nothing here changes the plan: the change card's Items are applied only after the student confirms (ui.py). Nothing
is logged or stored.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from uniadvisor.chat.answers import answer
from uniadvisor.chat.changes import Item
from uniadvisor.chat.classify import Classifier
from uniadvisor.chat.context import ChatContext
from uniadvisor.chat.extract import extract
from uniadvisor.chat.split import split_requests
from uniadvisor.chat.types import EXAMPLES_VI, OTHER, QUESTION_TYPES

MAX_MESSAGE_CHARS = 1000

HELP_VI = ("Mình chưa hiểu ý em. Mình có thể đổi thông tin để lập lại danh sách hoặc trả lời câu hỏi về danh sách, "
           "ví dụ:\n" + "\n".join(f"- {e}" for e in EXAMPLES_VI))


@dataclass
class Reply:
    items: list[Item] = field(default_factory=list)      # changes for the card (confirm before applying)
    answers: list[str] = field(default_factory=list)     # answers to questions, shown at once
    not_understood: list[str] = field(default_factory=list)
    requests: list[tuple[str, str]] = field(default_factory=list)   # (text, type) as split and classified

    @property
    def help(self) -> str | None:
        if self.not_understood and not self.items and not self.answers:
            return HELP_VI
        return None


def handle(text: str, ctx: ChatContext, classifier: Classifier) -> Reply:
    reply = Reply()
    text = (text or "").strip()[:MAX_MESSAGE_CHARS]
    if not text:
        return reply
    reply.requests = split_requests(text, classifier)
    for piece, rtype in reply.requests:
        if rtype == OTHER:
            reply.not_understood.append(piece)
            continue
        items = extract(piece, rtype, ctx)
        if rtype in QUESTION_TYPES:
            reply.answers += [answer(i, ctx) for i in items]
        else:
            reply.items += items
    if reply.not_understood and (reply.items or reply.answers):
        reply.answers.append("Phần này mình chưa hiểu: " + "; ".join(f"“{t}”" for t in reply.not_understood))
    return reply
