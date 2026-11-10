"""Name perturbations that mimic regulator, ERP, and filing variation (plan section 5.4)."""

from __future__ import annotations

import random
import re
from collections.abc import Callable

_SUFFIX_VARIANTS = {
    "inc": ["INC", "INC.", "INCORPORATED", "Inc"],
    "incorporated": ["INC", "INC.", "Incorporated"],
    "llc": ["LLC", "L.L.C.", "LLC."],
    "corp": ["CORP", "CORP.", "CORPORATION", "Corp"],
    "corporation": ["CORP", "CORP.", "CORPORATION"],
    "co": ["CO", "CO.", "COMPANY"],
    "company": ["CO", "CO.", "COMPANY"],
    "ltd": ["LTD", "LTD.", "LIMITED"],
}
_ABBREV = {
    "international": "INTL", "manufacturing": "MFG", "company": "CO", "group": "GRP",
    "industries": "IND", "technologies": "TECH", "services": "SVCS", "laboratories": "LABS",
}
_KEYBOARD = {
    "a": "qs", "b": "vn", "c": "xv", "d": "sf", "e": "wr", "f": "dg", "g": "fh", "h": "gj",
    "i": "uo", "j": "hk", "k": "jl", "l": "k", "m": "n", "n": "bm", "o": "ip", "p": "o",
    "q": "wa", "r": "et", "s": "ad", "t": "ry", "u": "yi", "v": "cb", "w": "qe", "x": "zc",
    "y": "tu", "z": "x",
}
_STATE_NAMES = {"OH": "OHIO", "TX": "TEXAS", "PA": "PENNSYLVANIA", "CA": "CALIFORNIA",
                "MI": "MICHIGAN", "NY": "NEW YORK", "TN": "TENNESSEE", "NV": "NEVADA"}

Perturbation = Callable[[str, random.Random, str | None], str]


def _tokens(name: str) -> list[str]:
    return name.split()


def suffix_change(name: str, rng: random.Random, state: str | None = None) -> str:
    toks = _tokens(name)
    if not toks:
        return name
    last = re.sub(r"[.,]", "", toks[-1]).casefold()
    if last in _SUFFIX_VARIANTS:
        toks[-1] = rng.choice(_SUFFIX_VARIANTS[last])
    else:
        toks.append(rng.choice(["INC", "LLC", "CORP", "CO"]))
    return " ".join(toks)


def drop_suffix(name: str, rng: random.Random, state: str | None = None) -> str:
    toks = _tokens(name)
    if len(toks) > 1 and re.sub(r"[.,]", "", toks[-1]).casefold() in _SUFFIX_VARIANTS:
        toks = toks[:-1]
    return " ".join(toks).rstrip(",")


def leading_the(name: str, rng: random.Random, state: str | None = None) -> str:
    return name if name.casefold().startswith("the ") else f"THE {name}"


def punctuation_case(name: str, rng: random.Random, state: str | None = None) -> str:
    out = name.upper() if rng.random() < 0.6 else name.lower()
    return out.replace(",", "") if rng.random() < 0.5 else out.replace(" ", "  ", 1)


def abbreviate(name: str, rng: random.Random, state: str | None = None) -> str:
    toks = [_ABBREV.get(t.casefold(), t) for t in _tokens(name)]
    return " ".join(toks)


def typo(name: str, rng: random.Random, state: str | None = None) -> str:
    letters = [i for i, ch in enumerate(name) if ch.casefold() in _KEYBOARD]
    if len(letters) < 4:
        return name
    i = rng.choice(letters[1:])
    mode = rng.choice(["adjacent", "drop", "double"])
    ch = name[i]
    if mode == "adjacent":
        repl = rng.choice(_KEYBOARD[ch.casefold()])
        return name[:i] + (repl.upper() if ch.isupper() else repl) + name[i + 1 :]
    if mode == "drop":
        return name[:i] + name[i + 1 :]
    return name[:i] + ch + name[i:]


def token_swap(name: str, rng: random.Random, state: str | None = None) -> str:
    toks = _tokens(name)
    if len(toks) < 3:
        return name
    i = rng.randrange(len(toks) - 1)
    toks[i], toks[i + 1] = toks[i + 1], toks[i]
    return " ".join(toks)


def truncate(name: str, rng: random.Random, state: str | None = None) -> str:
    toks = _tokens(name)
    return " ".join(toks[: max(2, len(toks) - 1)]) if len(toks) > 2 else name


def location_suffix(name: str, rng: random.Random, state: str | None = None) -> str:
    place = _STATE_NAMES.get(state or "", None)
    return f"{name} OF {place}" if place else name


def plant_suffix(name: str, rng: random.Random, state: str | None = None) -> str:
    return f"{name} {rng.choice(['PLANT', 'FACILITY', 'MILL', 'DC', 'WAREHOUSE'])} {rng.randint(1, 12)}"


def trailing_code(name: str, rng: random.Random, state: str | None = None) -> str:
    return f"{name} #{rng.randint(100, 9999)}"


PERTURBATIONS: dict[str, Perturbation] = {
    "suffix_change": suffix_change, "drop_suffix": drop_suffix, "leading_the": leading_the,
    "punctuation_case": punctuation_case, "abbreviate": abbreviate, "typo": typo,
    "token_swap": token_swap, "truncate": truncate, "location_suffix": location_suffix,
    "plant_suffix": plant_suffix, "trailing_code": trailing_code,
}


def perturb_name(
    name: str, rng: random.Random, state: str | None = None, max_ops: int = 2
) -> tuple[str, list[str]]:
    """Apply 1 to `max_ops` random perturbations. Returns (variant, operation names)."""
    ops = rng.sample(sorted(PERTURBATIONS), k=rng.randint(1, max_ops))
    out = name
    for op in ops:
        out = PERTURBATIONS[op](out, rng, state)
    return out.strip() or name, ops
