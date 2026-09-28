"""Load and save glossary.yaml.

The file has three sections:

    dishes:      Korean -> English, reviewed by a human. One line per dish.
    unreviewed:  Korean -> English, machine-translated. To review an entry,
                 fix the English and move the line up into `dishes:`.
    annotations: parenthetical markers like (뚝) -> English gloss.

Saving always rewrites the file with the same fixed header comments and each
section sorted by Korean key, so git diffs stay minimal and hand-edits are
never reordered unexpectedly.
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

HEADER = """\
# Korean -> English glossary for dish names. Hand-edited; see README.
#
# dishes:      reviewed translations (trusted, shown without a footnote marker)
# unreviewed:  machine translations added automatically by each run.
#              To review: fix the English, then move the line into `dishes:`.
# annotations: parenthetical markers like (뚝); an empty value hides the marker.
#
# Sections are kept sorted by the Korean key so diffs stay clean.
"""


@dataclass
class Glossary:
    path: Path
    dishes: dict[str, str] = field(default_factory=dict)
    unreviewed: dict[str, str] = field(default_factory=dict)
    annotations: dict[str, str] = field(default_factory=dict)
    _dirty: bool = False

    @classmethod
    def load(cls, path: str | Path) -> "Glossary":
        path = Path(path)
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls(
            path=path,
            dishes=data.get("dishes") or {},
            unreviewed=data.get("unreviewed") or {},
            annotations=data.get("annotations") or {},
        )

    def lookup(self, korean: str) -> tuple[str, bool] | None:
        """Return (english, reviewed) for an exact match, else None."""
        if korean in self.dishes:
            return self.dishes[korean], True
        if korean in self.unreviewed:
            return self.unreviewed[korean], False
        return None

    def add_unreviewed(self, korean: str, english: str) -> None:
        self.unreviewed[korean] = english
        self._dirty = True

    def save_if_changed(self) -> bool:
        """Rewrite the file if new entries were added this run."""
        if not self._dirty:
            return False
        sections = [
            ("dishes", self.dishes),
            ("unreviewed", self.unreviewed),
            ("annotations", self.annotations),
        ]
        parts = [HEADER]
        for name, mapping in sections:
            body = yaml.safe_dump(
                {name: dict(sorted(mapping.items()))} if mapping else {name: {}},
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
                width=1000,
            )
            parts.append("\n" + body)
        self.path.write_text("".join(parts), encoding="utf-8")
        self._dirty = False
        return True
