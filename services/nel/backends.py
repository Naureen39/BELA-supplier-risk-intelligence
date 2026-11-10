"""Mention detection and linking backends for the nel service.

`GazetteerBackend` is a deterministic development and test backend (longest match against a name
list). It is not BELA and must never be used for reported results.

The BELA backend is loaded with `NEL_BACKEND=module:factory`. The factory returns an object with
`link(texts: list[str], lang: list[str]) -> list[list[dict]]`, where each dict has start, end,
surface, qid, md_score, el_score, and candidates (top 10 of {qid, score}). Spike A (ADR-001)
decides how BELA, or the community wrapper, is adapted to this interface.
"""

from __future__ import annotations

import importlib
import os
import re
from collections.abc import Sequence
from typing import Any, Protocol


class LinkBackend(Protocol):
    model_version: str

    def link(self, texts: Sequence[str], langs: Sequence[str]) -> list[list[dict[str, Any]]]: ...


class GazetteerBackend:
    model_version = "gazetteer-dev"

    def __init__(self, names_to_qid: dict[str, str]) -> None:
        self._names = sorted(names_to_qid.items(), key=lambda kv: -len(kv[0]))

    def link(self, texts: Sequence[str], langs: Sequence[str]) -> list[list[dict[str, Any]]]:
        out = []
        for text in texts:
            found: list[dict[str, Any]] = []
            taken: list[tuple[int, int]] = []
            for name, qid in self._names:
                for m in re.finditer(re.escape(name), text):
                    span = (m.start(), m.end())
                    if any(span[0] < b and a < span[1] for a, b in taken):
                        continue
                    taken.append(span)
                    found.append({"start": span[0], "end": span[1], "surface": name, "qid": qid,
                                  "md_score": 0.99, "el_score": 0.99,
                                  "candidates": [{"qid": qid, "score": 0.99}]})
            out.append(sorted(found, key=lambda d: d["start"]))
        return out


def load_backend() -> LinkBackend:
    spec = os.environ.get("NEL_BACKEND", "")
    if not spec:
        return GazetteerBackend({})
    module_name, _, factory = spec.partition(":")
    backend: LinkBackend = getattr(importlib.import_module(module_name), factory)()
    return backend
