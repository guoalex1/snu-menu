#!/usr/bin/env python3
"""Daily SNU cafeteria menu email.

Usage:
    python main.py                 scrape today's menu (KST) and email subscribers
    python main.py --dry-run       print the emails instead of sending them
    python main.py --date 2026-09-28
    python main.py print           just print the translated menu, no email

Environment variables (only needed when actually sending):
    GMAIL_ADDRESS, GMAIL_APP_PASSWORD, MY_EMAIL
"""

import argparse
import csv
import os
import re
import socket
import sys
import traceback
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from snumenu import emailer, scrape, translate
from snumenu.glossary import Glossary

ROOT = Path(__file__).parent
SEOUL = ZoneInfo("Asia/Seoul")


def main() -> int:
    args = parse_args()
    socket.setdefaulttimeout(15)  # no network call may hang the run
    load_env(ROOT / ".env")
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    glossary = Glossary.load(ROOT / "glossary.yaml")

    date = args.date or datetime.now(SEOUL).strftime("%Y-%m-%d")
    date_label = datetime.strptime(date, "%Y-%m-%d").strftime(config["date_format"])

    sent_marker = ROOT / ".last_sent"
    sending = args.command == "run" and not args.dry_run
    if (sending and sent_marker.exists()
            and sent_marker.read_text().strip() == date):
        print(f"already sent for {date}; skipping duplicate run", file=sys.stderr)
        return 0
    label_map = config["cafeterias"]

    try:
        restaurants = scrape.parse_menus(scrape.fetch_html(date))
    except Exception:
        notify_me(f"SNU menu: scraping failed for {date}", traceback.format_exc(), args)
        return 1

    if not restaurants:
        notify_me(
            f"SNU menu: zero restaurants parsed for {date}",
            "The page structure may have changed. Check the parser in snumenu/scrape.py.",
            args,
        )
        return 1

    english_names = {ko: english_name(label) for label, ko in label_map.items()}

    if args.command == "print":
        target_names = [r.name for r in restaurants]
    else:
        subscribers = read_subscribers(ROOT / config["subscribers_file"],
                                       list(label_map.values()))
        if not subscribers:
            print("no subscribers; nothing to send", file=sys.stderr)
            return 0
        subscribed = set().union(*subscribers.values())
        target_names = [name for name in label_map.values() if name in subscribed]

    wanted = set(target_names)
    translate.prefetch(
        [dish.name_ko for r in restaurants if r.name in wanted
         for dishes in r.meals.values() for dish in dishes],
        glossary,
    )

    if args.command == "print":
        menu = build_menu(restaurants, target_names, english_names, glossary)
        save_glossary(glossary)
        if menu:
            print(emailer.build_text(menu, date_label))
        else:
            print(f"No menu for {date_label} (weekend or holiday?).")
        return 0

    # One email per distinct cafeteria selection, its subscribers BCC'd together.
    groups: dict[tuple[str, ...], list[str]] = {}
    for email, cafeterias in sorted(subscribers.items()):
        groups.setdefault(cafeterias, []).append(email)

    batches = [
        (menu, recipients)
        for cafeterias, recipients in groups.items()
        if (menu := build_menu(restaurants, cafeterias, english_names, glossary))
    ]
    save_glossary(glossary)

    if not batches:
        if config.get("notify_me_when_empty", True):
            notify_me(
                f"SNU menu: nothing to send for {date}",
                "No menu for any subscribed cafeteria (weekend or holiday?). "
                "No email was sent to subscribers.",
                args,
            )
        return 0

    subject = config["subject_format"].format(date=date_label)

    if args.dry_run:
        for i, (menu, recipients) in enumerate(batches, 1):
            out = ROOT / f"email-{i}.html"
            out.write_text(emailer.build_html(menu, date_label), encoding="utf-8")
            print(f"=== email {i}/{len(batches)} · bcc: {', '.join(recipients)}")
            print(emailer.build_text(menu, date_label))
            print(f"[dry-run] HTML written to {out}\n", file=sys.stderr)
        return 0

    sender, password = gmail_credentials()
    for menu, recipients in batches:
        emailer.send(
            subject,
            emailer.build_text(menu, date_label),
            emailer.build_html(menu, date_label),
            sender, password, to=sender, bcc=recipients,
        )
    sent_marker.write_text(date)
    print(f"sent {len(batches)} email(s) covering {len(subscribers)} subscriber(s)")
    return 0


def read_subscribers(path, offered) -> dict[str, tuple[str, ...]]:
    """Parse the subscribers CSV: one line per person, email first, then
    optionally the cafeterias they want (Korean names, `offered` order).
    An email alone means all cafeterias; "#" lines are comments.
    """
    if not Path(path).exists():
        sys.exit(f"{path} not found — create it (one email per line)")
    subscribers = {}
    for row in csv.reader(Path(path).read_text(encoding="utf-8").splitlines()):
        if not row or row[0].lstrip().startswith("#"):
            continue
        email = row[0].strip().lower()
        if "@" not in email:
            sys.exit(f"{path}: not an email address: {row[0]!r}")
        wanted = [c.strip() for c in row[1:] if c.strip()]
        unknown = sorted(set(wanted) - set(offered))
        if unknown:
            sys.exit(f"{path}: unknown cafeterias for {email}: {', '.join(unknown)}")
        subscribers[email] = tuple(c for c in offered if c in wanted) if wanted \
            else tuple(offered)
    return subscribers


def english_name(label: str) -> str:
    """"Bldg 301 cafeteria (301동식당)" -> "Bldg 301 cafeteria"."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", label) or label


def build_menu(restaurants, wanted_names, english_names, glossary):
    """Keep only the wanted restaurants, in order, with every dish translated."""
    by_name = {r.name: r for r in restaurants}
    menu = []
    for name in wanted_names:
        restaurant = by_name.get(name)
        if restaurant is None or not restaurant.meals:
            continue
        meals = []
        for meal_ko, dishes in restaurant.meals.items():
            rows = []
            for dish in dishes:
                rows.append(
                    emailer.Row(
                        english=translate.translate_dish(dish.name_ko, glossary),
                        name_ko=dish.name_ko,
                        price=dish.price,
                        is_header=dish.is_header,
                    )
                )
            meals.append((meal_ko, rows))
        menu.append(((english_names.get(name, name), restaurant.name), meals))
    return menu


def save_glossary(glossary: Glossary) -> None:
    if glossary.save_if_changed():
        print("glossary.yaml updated with new entries", file=sys.stderr)


def notify_me(subject: str, body: str, args) -> None:
    """Short note to MY_EMAIL only — never to subscribers."""
    my_email = os.environ.get("MY_EMAIL")
    if args.dry_run or args.command == "print" or not my_email:
        print(f"[note to me] {subject}\n{body}", file=sys.stderr)
        return
    sender, password = gmail_credentials()
    emailer.send(subject, body, None, sender, password, to=my_email)


def load_env(path: Path) -> None:
    """Read KEY=VALUE lines from .env; real environment variables take precedence."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def gmail_credentials() -> tuple[str, str]:
    try:
        return os.environ["GMAIL_ADDRESS"], os.environ["GMAIL_APP_PASSWORD"]
    except KeyError as e:
        sys.exit(f"Missing environment variable: {e.args[0]}")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=["run", "print"], default="run")
    parser.add_argument("--date", help="YYYY-MM-DD (default: today in Seoul)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the emails and write email-N.html instead of sending")
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(main())
