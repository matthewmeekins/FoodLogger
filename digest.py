"""
Telegram digest module for Food Log.

Sends daily and weekly nutrition summaries to a Telegram bot.
Requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env.
"""

import os
from datetime import date, timedelta
from typing import Optional

import httpx
from dotenv import load_dotenv

import database

load_dotenv()

_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

MEAL_ICONS = {
    "breakfast": "🍳",
    "lunch": "🥗",
    "dinner": "🍽",
    "snack": "🍎",
}

CAL_TARGET = 2000  # used for the calorie progress bar


# ---------------------------------------------------------------------------
# Core send helper
# ---------------------------------------------------------------------------

def send_telegram(text: str) -> dict:
    """
    POST a Markdown message to the configured Telegram chat.
    Returns the Telegram API response dict.
    Raises RuntimeError if credentials are missing or request fails.
    """
    if not _BOT_TOKEN or not _CHAT_ID:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in .env"
        )

    url = _TELEGRAM_API.format(token=_BOT_TOKEN)
    payload = {
        "chat_id": _CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
    }

    try:
        resp = httpx.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(
            f"Telegram API error {exc.response.status_code}: {exc.response.text}"
        ) from exc


# ---------------------------------------------------------------------------
# Bar chart helper
# ---------------------------------------------------------------------------

def _cal_bar(calories: int, target: int = CAL_TARGET, width: int = 10) -> str:
    """Return a Unicode block progress bar, e.g. '███████░░░'."""
    if target <= 0:
        return "░" * width
    filled = min(width, round(calories / target * width))
    return "█" * filled + "░" * (width - filled)


def _fmt(value: Optional[float], decimals: int = 0) -> str:
    if value is None:
        return "—"
    if decimals == 0:
        return f"{int(round(value)):,}"
    return f"{round(value, decimals)}"


# ---------------------------------------------------------------------------
# Message builders
# ---------------------------------------------------------------------------

def build_daily_message(date_str: Optional[str] = None, user_id: Optional[int] = None) -> str:
    """Build a Markdown daily digest for the given date (defaults to today)."""
    if date_str is None:
        date_str = date.today().isoformat()

    if user_id is None:
        raise RuntimeError("user_id is required for digest queries")

    entries = database.get_entries_for_date(date_str, user_id)

    # Pretty date
    d = date.fromisoformat(date_str)
    pretty_date = d.strftime("%A, %B %-d, %Y")

    if not entries:
        return (
            f"📊 *Food Log — {pretty_date}*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "_No entries logged today._"
        )

    total_cal = sum(e.get("calories") or 0 for e in entries)
    total_protein = sum(e.get("protein_g") or 0 for e in entries)
    total_carbs = sum(e.get("carbs_g") or 0 for e in entries)
    total_fat = sum(e.get("fat_g") or 0 for e in entries)

    bar = _cal_bar(total_cal)

    # Group by meal
    meals: dict[str, list] = {}
    for e in entries:
        meal = e.get("meal") or "other"
        meals.setdefault(meal, []).append(e)

    meal_order = ["breakfast", "lunch", "dinner", "snack", "other"]
    meal_lines = []
    for meal in meal_order:
        if meal not in meals:
            continue
        icon = MEAL_ICONS.get(meal, "🍴")
        meal_cal = sum(e.get("calories") or 0 for e in meals[meal])
        meal_lines.append(f"{icon} {meal.title():<10} {_fmt(meal_cal)} cal")

    meal_section = "\n".join(meal_lines) if meal_lines else "_No meals recorded._"

    lines = [
        f"📊 *Food Log — {pretty_date}*",
        "━━━━━━━━━━━━━━━━━━━━",
        f"🔥 Calories: *{_fmt(total_cal)}* / {_fmt(CAL_TARGET)}",
        f"`{bar}`",
        "",
        f"🥩 Protein:  {_fmt(total_protein)}g",
        f"🍞 Carbs:    {_fmt(total_carbs)}g",
        f"🧈 Fat:       {_fmt(total_fat)}g",
        "",
        meal_section,
    ]
    return "\n".join(lines)


def build_weekly_message(start_date: Optional[str] = None, user_id: Optional[int] = None) -> str:
    """Build a Markdown weekly digest for the 7-day window starting at start_date."""
    if start_date is None:
        start_date = (date.today() - timedelta(days=6)).isoformat()

    if user_id is None:
        raise RuntimeError("user_id is required for digest queries")

    summary = database.get_weekly_summary(start_date, user_id)
    days = summary["days"]
    totals = summary["totals"]
    averages = summary["averages"]
    active = summary["active_days"]

    start = date.fromisoformat(summary["start_date"])
    end = date.fromisoformat(summary["end_date"])
    period = f"{start.strftime('%b %-d')} – {end.strftime('%b %-d, %Y')}"

    if active == 0:
        return (
            f"📅 *Week of {period}*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "_No entries logged this week._"
        )

    # Day rows with mini bar
    day_lines = []
    max_cal = max((d["total_calories"] or 0) for d in days)
    for d in days:
        day_label = date.fromisoformat(d["date"]).strftime("%a")
        cal = d["total_calories"]
        if cal is None:
            day_lines.append(f"{day_label} {'—':>4}  _(no entries)_")
        else:
            bar_width = 8
            filled = round(cal / max_cal * bar_width) if max_cal > 0 else 0
            bar = "█" * filled + "░" * (bar_width - filled)
            day_lines.append(f"`{day_label} {bar}` {_fmt(cal):>5} cal")

    day_section = "\n".join(day_lines)

    avg_cal = averages.get("calories")
    avg_p = averages.get("protein_g")
    avg_c = averages.get("carbs_g")
    avg_f = averages.get("fat_g")

    lines = [
        f"📅 *Week of {period}*",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Total: *{_fmt(totals['calories'])} cal*  |  Avg: {_fmt(avg_cal)}/day  |  {active}/7 days logged",
        "",
        day_section,
        "",
        f"Avg macros/day: {_fmt(avg_p)}g P · {_fmt(avg_c)}g C · {_fmt(avg_f)}g F",
    ]
    return "\n".join(lines)
