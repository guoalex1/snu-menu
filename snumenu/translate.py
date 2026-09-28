"""Translate dish names using the glossary, with a machine-translation fallback.

Order of attempts for a dish name:
  1. exact glossary match on the full name
  2. split into components on separators (&, *, +, comma, OR) and translate each:
     a. exact glossary match on the component
     b. pull out known parenthetical annotations like (뚝), then match the rest
     c. machine-translate what's left; the result is saved to the glossary's
        `unreviewed` section so it can be reviewed later

Anything not confirmed by a human (unreviewed or freshly machine-translated)
is flagged so the email can mark it.
"""

import re
from dataclasses import dataclass
from functools import lru_cache

from .glossary import Glossary

HANGUL = re.compile(r"[가-힣]")

# How separators read in English. OR appears in names like "즉석떡국OR즉석라면".
SEPARATOR_WORDS = {"&": " & ", "+": " & ", ",": " & ", "*": " with ", "OR": " or "}


@dataclass
class Translation:
    english: str
    machine: bool  # True if any part is machine-translated / not yet reviewed


def get_machine_translator():
    """The fallback translator: Korean text -> English text.

    Swap this one function to use Argos Translate, an LLM, etc.
    """
    from deep_translator import GoogleTranslator

    return GoogleTranslator(source="ko", target="en").translate


@lru_cache(maxsize=1)
def _translator():
    return get_machine_translator()


def translate_dish(name_ko: str, glossary: Glossary) -> Translation:
    name_ko = name_ko.strip()

    hit = glossary.lookup(name_ko)
    if hit:
        return Translation(english=hit[0], machine=not hit[1])

    parts = []
    machine = False
    for component, separator in _split(name_ko):
        english, part_machine = _translate_component(component, glossary)
        machine = machine or part_machine
        parts.append(english)
        parts.append(SEPARATOR_WORDS.get(separator, " & "))
    return Translation(english="".join(parts[:-1]), machine=machine)


def _translate_component(component: str, glossary: Glossary) -> tuple[str, bool]:
    hit = glossary.lookup(component)
    if hit:
        return hit[0], not hit[1]

    base, glosses = _extract_annotations(component, glossary.annotations)

    hit = glossary.lookup(base)
    if hit:
        english, reviewed = hit[0], hit[1]
    elif not HANGUL.search(base):
        return component, False  # already Latin/symbols, e.g. "TAKE-OUT"
    else:
        english, reviewed = _machine_translate(base, glossary)

    if glosses:
        english = f"{english} ({'; '.join(glosses)})"
    return english, not reviewed


def _machine_translate(korean: str, glossary: Glossary) -> tuple[str, bool]:
    try:
        english = _translator()(korean)
    except Exception:
        english = None
    if not english:
        return korean, False  # translator down: show Korean (marked), retry next run
    glossary.add_unreviewed(korean, english)
    return english, False


def _extract_annotations(name: str, annotations: dict[str, str]) -> tuple[str, list[str]]:
    """Remove known parenthetical markers, returning (name without them, glosses).

    Unknown parentheticals are left in place; an empty gloss hides the marker.
    """
    glosses = []

    def replace(match):
        content = match.group(1).strip()
        if content not in annotations:
            return match.group(0)
        if annotations[content]:
            glosses.append(annotations[content])
        return ""

    base = re.sub(r"\(([^()]*)\)", replace, name).strip()
    return base or name, glosses


def _split(name: str) -> list[tuple[str, str]]:
    """Split on separators outside parentheses.

    Returns [(component, separator_after)]; the last separator is "".
    """
    parts = []
    current = ""
    depth = 0
    i = 0
    while i < len(name):
        ch = name[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if depth == 0:
            if ch in "&*+,":
                parts.append((current.strip(), ch))
                current = ""
                i += 1
                continue
            if name[i : i + 2] == "OR":
                parts.append((current.strip(), "OR"))
                current = ""
                i += 2
                continue
        current += ch
        i += 1
    parts.append((current.strip(), ""))
    return [(component, sep) for component, sep in parts if component]
