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
    """The fallback translator: a batch of Korean names -> English, in order.

    The Claude CLI translates the whole batch in one call with by far the
    best quality for dish names; when it's unavailable, DeepL (if
    DEEPL_API_KEY is set) then Google translate one name at a time. Swap
    this one function to use Argos Translate, another LLM, etc.
    """

    def translate_batch(names: list[str]) -> list[str | None]:
        for service in (_claude_batch, _deepl_batch, _google_each):
            try:
                return service(names)
            except Exception:
                continue
        return [None] * len(names)

    return translate_batch


def _claude_batch(names: list[str]) -> list[str]:
    import json
    import subprocess

    prompt = (
        "Translate each Korean cafeteria dish name to natural English that a "
        "foreigner at a Korean university would understand. Keep well-known "
        "Korean dish names romanized with a short parenthetical gloss, e.g. "
        "김치찌개 -> Kimchi-jjigae (kimchi stew). Reply with ONLY a JSON array "
        "of the translations, same order and length as the input:\n"
        + json.dumps(names, ensure_ascii=False)
    )
    result = subprocess.run(
        ["claude", "-p", prompt], capture_output=True, text=True, timeout=300
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip()[:200])
    text = result.stdout
    translations = json.loads(text[text.index("[") : text.rindex("]") + 1])
    if len(translations) != len(names):
        raise RuntimeError("translation count mismatch")
    return [str(t) for t in translations]


def _deepl_batch(names: list[str]) -> list[str]:
    # direct REST call: the deep-translator wrapper predates DeepL's Korean
    # support, and the API translates the whole batch in one request anyway
    import os

    import requests

    key = os.environ["DEEPL_API_KEY"]  # unset -> KeyError -> next service
    host = "api-free.deepl.com" if key.endswith(":fx") else "api.deepl.com"
    resp = requests.post(
        f"https://{host}/v2/translate",
        headers={"Authorization": f"DeepL-Auth-Key {key}"},
        json={"text": names, "source_lang": "KO", "target_lang": "EN-US"},
        timeout=30,
    )
    resp.raise_for_status()
    translations = [t["text"] for t in resp.json()["translations"]]
    if len(translations) != len(names):
        raise RuntimeError("translation count mismatch")
    return translations


def _google_each(names: list[str]) -> list[str]:
    from deep_translator import GoogleTranslator

    google = GoogleTranslator(source="ko", target="en").translate
    return [google(name) for name in names]


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


_failures = 0  # consecutive; after 3, stop trying for the rest of the run


def prefetch(dish_names: list[str], glossary: Glossary) -> None:
    """Machine-translate every unknown component in one batch, up front.

    One call for the whole page beats one per dish, especially for the
    LLM-based translator. translate_dish then finds everything in the
    glossary; any stragglers still fall back to _machine_translate.
    """
    global _failures
    unknown: list[str] = []
    for name in dish_names:
        name = name.strip()
        if glossary.lookup(name):
            continue
        for component, _ in _split(name):
            if glossary.lookup(component):
                continue
            base, _ = _extract_annotations(component, glossary.annotations)
            if HANGUL.search(base) and not glossary.lookup(base) and base not in unknown:
                unknown.append(base)
    if not unknown:
        return
    try:
        translations = _translator()(unknown)
    except Exception:
        _failures += 1
        return
    for korean, english in zip(unknown, translations):
        if english and english.strip() and english.strip() != korean:
            glossary.add_unreviewed(korean, english.strip())


def _machine_translate(korean: str, glossary: Glossary) -> tuple[str, bool]:
    global _failures
    english = None
    if _failures < 3:
        try:
            english = _translator()([korean])[0]
        except Exception:
            english = None
        _failures = 0 if english else _failures + 1
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
            thousands_sep = (  # the comma in prices like "2,000원"
                ch == ","
                and current[-1:].isdigit()
                and name[i + 1 : i + 2].isdigit()
            )
            if ch in "&*+," and not thousands_sep:
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
