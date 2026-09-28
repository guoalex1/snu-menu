"""Fetch and parse the SNU cafeteria menu page (snumenu.gerosyab.net).

The page is server-rendered. Structure (as of 2026-09):

    div.restaurant
      div.restaurant-name > a[data-resName]     <- restaurant name
      div.meal
        div.meal-type                           <- "아침", "점심", "저녁", "점심 / 저녁", ...
        div.menu
          div.menu-name-with-price (or .menu-name-without-price)
            a[data-menu]                        <- dish name (sometimes plain text, no <a>)
          div.menu-price                        <- optional, plain number in won

Names like "<셀프코너>" in angle brackets are section headers, not dishes.
Ad banners are div.restaurant blocks without a data-resName link; there are
also junk entries whose text is literally "#menuDetailModal". Both are skipped.

We read dish names from the data-menu attribute when present: header names
like "<TAKE-OUT>" appear unescaped in the HTML and get eaten as tags if you
read the anchor's text.
"""

from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup

URL = "https://snumenu.gerosyab.net/ko/menus"
USER_AGENT = (
    "snu-menu-mailer/1.0 (personal daily-menu email; "
    "https://github.com/alexguoxh; one request per day)"
)


@dataclass
class Dish:
    name_ko: str
    price: int | None = None
    is_header: bool = False


@dataclass
class Restaurant:
    name: str
    meals: dict[str, list[Dish]] = field(default_factory=dict)  # meal label -> dishes


def fetch_html(date: str) -> str:
    """Fetch the menu page for a date ("YYYY-MM-DD"). One request per run."""
    resp = requests.get(
        URL, params={"date": date}, headers={"User-Agent": USER_AGENT}, timeout=30
    )
    resp.raise_for_status()
    return resp.text


def parse_menus(html: str) -> list[Restaurant]:
    """Parse the page into a list of Restaurant, in page order."""
    soup = BeautifulSoup(html, "html.parser")
    restaurants = []

    for block in soup.select("div.restaurant"):
        name_link = block.select_one(".restaurant-name a[data-resname]")
        if name_link is None:  # ad banner or other non-restaurant block
            continue
        restaurant = Restaurant(name=name_link["data-resname"].strip())

        for meal in block.select("div.meal"):
            meal_type = meal.select_one(".meal-type")
            if meal_type is None:
                continue
            label = meal_type.get_text(strip=True)
            dishes = [d for d in map(_parse_dish, meal.select("div.menu")) if d]
            if dishes:
                restaurant.meals[label] = dishes

        restaurants.append(restaurant)

    return restaurants


def _parse_dish(menu_div) -> Dish | None:
    name_div = menu_div.select_one(".menu-name-with-price, .menu-name-without-price")
    if name_div is None:
        return None

    link = name_div.select_one("a[data-menu]")
    name = link["data-menu"].strip() if link else name_div.get_text(strip=True)
    if not name or name == "#menuDetailModal":
        return None

    price_div = menu_div.select_one(".menu-price")
    price = None
    if price_div:
        digits = price_div.get_text(strip=True).replace(",", "")
        if digits.isdigit():
            price = int(digits)

    is_header = name.startswith("<") and name.endswith(">")
    if is_header:
        name = name[1:-1].strip()

    return Dish(name_ko=name, price=price, is_header=is_header)
