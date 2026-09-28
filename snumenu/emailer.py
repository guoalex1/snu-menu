"""Build the menu email (plain text + HTML) and send it via Gmail SMTP."""

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465  # SSL

MEAL_NAMES = {"아침": "Breakfast", "점심": "Lunch", "저녁": "Dinner"}

FOOTNOTE = "* machine-translated, may be rough"


@dataclass
class Row:
    english: str
    name_ko: str
    price: int | None
    is_header: bool
    machine: bool


# menu structure passed in: [(restaurant_name, [(meal_label_ko, [Row, ...]), ...]), ...]


def meal_label_en(label_ko: str) -> str:
    """"점심 / 저녁" -> "Lunch / Dinner"."""
    parts = [MEAL_NAMES.get(p.strip(), p.strip()) for p in label_ko.split("/")]
    return " / ".join(parts)


def _won(price: int | None) -> str:
    return f"₩{price:,}" if price is not None else ""


def build_text(menu, date_label: str) -> str:
    lines = [f"SNU cafeteria menu — {date_label}", ""]
    any_machine = False
    for restaurant, meals in menu:
        lines.append(f"■ {restaurant}")
        for meal_ko, rows in meals:
            lines.append(f"  {meal_label_en(meal_ko)}")
            for row in rows:
                star = "*" if row.machine else ""
                any_machine = any_machine or row.machine
                price = f" — {_won(row.price)}" if row.price is not None else ""
                if row.is_header:
                    lines.append(f"    〈 {row.english}{star} 〉{price}")
                else:
                    lines.append(f"    {row.english}{star} ({row.name_ko}){price}")
            lines.append("")
    if any_machine:
        lines += [FOOTNOTE, ""]
    return "\n".join(lines)


def build_html(menu, date_label: str) -> str:
    parts = [
        '<div style="max-width:600px;margin:0 auto;padding:16px;'
        "font-family:-apple-system,'Segoe UI',Roboto,'Apple SD Gothic Neo',"
        'sans-serif;color:#222;line-height:1.45">',
        f'<h1 style="font-size:20px;margin:0 0 16px">'
        f"SNU cafeteria menu <span style='font-weight:normal;color:#666'>— {date_label}</span></h1>",
    ]
    any_machine = False
    for restaurant, meals in menu:
        parts.append(
            f'<h2 style="font-size:17px;margin:20px 0 4px;padding-bottom:4px;'
            f'border-bottom:2px solid #333">{restaurant}</h2>'
        )
        for meal_ko, rows in meals:
            parts.append(
                f'<h3 style="font-size:13px;margin:12px 0 4px;color:#888;'
                f'text-transform:uppercase;letter-spacing:1px">{meal_label_en(meal_ko)}</h3>'
            )
            parts.append('<table style="width:100%;border-collapse:collapse">')
            for row in rows:
                star = '<sup style="color:#c00">*</sup>' if row.machine else ""
                any_machine = any_machine or row.machine
                price = _won(row.price)
                if row.is_header:
                    name = (
                        f'<span style="color:#666;font-weight:bold">'
                        f"〈 {row.english}{star} 〉</span>"
                    )
                else:
                    name = (
                        f"{row.english}{star} "
                        f'<span style="font-size:12px;color:#999">{row.name_ko}</span>'
                    )
                parts.append(
                    '<tr style="border-bottom:1px solid #eee">'
                    f'<td style="padding:6px 0">{name}</td>'
                    f'<td style="padding:6px 0 6px 8px;text-align:right;'
                    f'white-space:nowrap;color:#555">{price}</td></tr>'
                )
            parts.append("</table>")
    if any_machine:
        parts.append(f'<p style="font-size:12px;color:#999;margin-top:16px">{FOOTNOTE}</p>')
    parts.append("</div>")
    return "\n".join(parts)


def send(subject: str, text: str, html: str | None, sender: str, password: str,
         to: str, bcc: list[str] = ()) -> None:
    """Send one email. Only `to` appears in the headers; `bcc` stays hidden."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.login(sender, password)
        smtp.send_message(msg, from_addr=sender, to_addrs=[to, *bcc])
