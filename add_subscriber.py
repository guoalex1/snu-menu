#!/usr/bin/env python3
"""Interactively add (or update) a subscriber in subscribers.csv.

    python add_subscriber.py

Asks for an email, shows the cafeterias from config.yaml, and writes the
choice to the subscribers file. Picking nothing means all cafeterias.
Re-adding an existing email replaces their line.
"""

import csv
import io
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).parent


def main() -> None:
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    cafeterias = list(config["cafeterias"].items())  # [(label, korean name)]
    csv_path = ROOT / config["subscribers_file"]

    email = input("Email: ").strip().lower()
    if "@" not in email:
        sys.exit("That doesn't look like an email address.")

    print()
    for i, (label, _) in enumerate(cafeterias, 1):
        print(f"  {i}. {label}")
    raw = input("\nSubscribe to which? (e.g. '1 3', or Enter for all): ").strip()

    if raw:
        try:
            picks = sorted({int(token) for token in raw.replace(",", " ").split()})
        except ValueError:
            sys.exit("Numbers only, e.g. '1 3'.")
        if not all(1 <= p <= len(cafeterias) for p in picks):
            sys.exit(f"Pick numbers between 1 and {len(cafeterias)}.")
        chosen = [cafeterias[p - 1][1] for p in picks]
    else:
        chosen = []  # email alone means all cafeterias

    buffer = io.StringIO()
    csv.writer(buffer).writerow([email, *chosen])
    new_line = buffer.getvalue().strip()

    lines = []
    replaced = False
    if csv_path.exists():
        for line in csv_path.read_text(encoding="utf-8").splitlines():
            row = next(csv.reader([line]), None)
            if row and row[0].strip().lower() == email:
                line, replaced = new_line, True
            lines.append(line)
    if not replaced:
        lines.append(new_line)
    csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    summary = ", ".join(chosen) if chosen else "all cafeterias"
    print(f"\n{'Updated' if replaced else 'Added'} {email} → {summary}")


if __name__ == "__main__":
    main()
