"""Subscribers from a Google Form, read via its response sheet published as CSV.

The form has two questions: the subscriber's email address and a checkbox list
of cafeterias (the labels in config.yaml's `cafeterias:` map). Google Sheets
joins checkbox answers with ", " in a single cell, so labels must not contain
commas, and the cafeteria question must be the last question on the form.

Each new submission by the same email replaces their previous one, so people
resubmit the form to change cafeterias — or submit with nothing checked to
unsubscribe.
"""

import csv
import io
from pathlib import Path

import requests

from .scrape import USER_AGENT


def load_subscribers(source: str, label_map: dict[str, str]) -> dict[str, tuple[str, ...]]:
    """Return {email: cafeteria Korean names, in config order}.

    `source` is the published-CSV URL of the form's response sheet, or a local
    file path (handy for testing).
    """
    if source.startswith("http"):
        resp = requests.get(source, headers={"User-Agent": USER_AGENT}, timeout=30)
        resp.raise_for_status()
        text = resp.text
    else:
        text = Path(source).read_text(encoding="utf-8")
    return parse_subscribers(text, label_map)


def parse_subscribers(csv_text: str, label_map: dict[str, str]) -> dict[str, tuple[str, ...]]:
    rows = list(csv.reader(io.StringIO(csv_text)))
    if len(rows) < 2:
        return {}

    header = [h.strip().lower() for h in rows[0]]
    email_col = next((i for i, h in enumerate(header) if "email" in h), 1)
    choice_col = len(header) - 1  # the cafeteria question is the last column

    subscribers: dict[str, tuple[str, ...]] = {}
    for row in rows[1:]:  # in submission order, so later rows win
        if len(row) <= max(email_col, choice_col):
            continue
        email = row[email_col].strip().lower()
        if "@" not in email:
            continue
        chosen = {c.strip() for c in row[choice_col].split(",")}
        cafeterias = tuple(name for label, name in label_map.items() if label in chosen)
        if cafeterias:
            subscribers[email] = cafeterias
        else:
            subscribers.pop(email, None)  # resubmitted with nothing checked
    return subscribers
