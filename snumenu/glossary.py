"""Load and save glossary.yaml.

Two sections:

    dishes:      Korean -> English. Hand-maintained translations plus every
                 machine translation, cached so each name is translated once.
                 Editing an entry by hand always wins: cached values are
                 never overwritten.
    annotations: parenthetical markers like (뚝) -> English gloss.

Saving always rewrites the file with the same fixed header comments and each
section sorted by Korean key, so git diffs stay minimal and hand-edits are
never reordered unexpectedly.
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

HEADER = """\
# Korean -> English glossary for dish names: hand-maintained translations
# plus cached machine translations (new dishes are added automatically).
# Edit entries freely — whatever is here is used as-is.
#
# annotations: parenthetical markers like (뚝); an empty value hides the marker.
#
# Sections are kept sorted by the Korean key so diffs stay clean.
"""


@dataclass
class Glossary:
    path: Path
    dishes: dict[str, str] = field(default_factory=dict)
    annotations: dict[str, str] = field(default_factory=dict)
    _dirty: bool = False

    @classmethod
    def load(cls, path: str | Path) -> "Glossary":
        path = Path(path)
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls(
            path=path,
            dishes=data.get("dishes") or {},
            annotations=data.get("annotations") or {},
        )

    def lookup(self, korean: str) -> str | None:
        """Exact match first, then case-insensitive (for Latin parts like ICE)."""
        hit = self.dishes.get(korean)
        if hit is not None:
            return hit
        norm = korean.strip().casefold()
        for key, english in self.dishes.items():
            if key.strip().casefold() == norm:
                return english
        return None

    def add(self, korean: str, english: str) -> None:
        self.dishes[korean] = english
        self._dirty = True

    def save_if_changed(self) -> bool:
        """Rewrite the file if new entries were added this run."""
        if not self._dirty:
            return False
        parts = [HEADER]
        for name, mapping in [("dishes", self.dishes), ("annotations", self.annotations)]:
            body = yaml.safe_dump(
                {name: dict(sorted(mapping.items()))},
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
                width=1000,
            )
            parts.append("\n" + body)
        self.path.write_text("".join(parts), encoding="utf-8")
        self._dirty = False
        return True
