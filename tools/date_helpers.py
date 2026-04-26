"""
MeetingMind — Date Calculation Helpers
Provides reliable date parsing to prevent agent calculation errors.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
from google.adk.tools.tool_context import ToolContext


def parse_relative_date(
    tool_context: ToolContext, date_string: str, reference_date: Optional[str] = None
) -> dict:
    """Parse relative date strings like 'Monday', 'tomorrow', 'next week' into absolute YYYY-MM-DD format.

    Args:
        tool_context: ADK tool context.
        date_string: Relative date like "Monday", "tomorrow", "next week", "April 10th"
        reference_date: Optional reference date in YYYY-MM-DD format. Defaults to today.

    Returns:
        dict with absolute date in YYYY-MM-DD format.
    """
    try:
        if reference_date:
            ref = datetime.strptime(reference_date, "%Y-%m-%d")
        else:
            ref = datetime.now()

        date_lower = date_string.lower().strip()

        # Handle "tomorrow"
        if date_lower == "tomorrow":
            target = ref + timedelta(days=1)
            return {
                "status": "success",
                "date": target.strftime("%Y-%m-%d"),
                "day_of_week": target.strftime("%A"),
                "formatted": target.strftime("%B %d, %Y"),
            }

        # Handle "today"
        if date_lower == "today":
            return {
                "status": "success",
                "date": ref.strftime("%Y-%m-%d"),
                "day_of_week": ref.strftime("%A"),
                "formatted": ref.strftime("%B %d, %Y"),
            }

        # Handle "next week"
        if "next week" in date_lower:
            target = ref + timedelta(days=7)
            return {
                "status": "success",
                "date": target.strftime("%Y-%m-%d"),
                "day_of_week": target.strftime("%A"),
                "formatted": target.strftime("%B %d, %Y"),
            }

        # Handle day of week names (Monday, Tuesday, etc.)
        weekdays = {
            "monday": 0,
            "mon": 0,
            "tuesday": 1,
            "tue": 1,
            "tues": 1,
            "wednesday": 2,
            "wed": 2,
            "thursday": 3,
            "thu": 3,
            "thur": 3,
            "thurs": 3,
            "friday": 4,
            "fri": 4,
            "saturday": 5,
            "sat": 5,
            "sunday": 6,
            "sun": 6,
        }

        # Remove "next" and "this" prefixes
        day_name = date_lower.replace("next ", "").replace("this ", "").strip()

        if day_name in weekdays:
            target_weekday = weekdays[day_name]
            current_weekday = ref.weekday()

            # Calculate days until target weekday
            days_ahead = target_weekday - current_weekday
            if days_ahead <= 0:  # Target day already happened this week
                days_ahead += 7

            target = ref + timedelta(days=days_ahead)

            logging.info(
                f"📅 Date calculation: '{date_string}' → {target.strftime('%A, %B %d, %Y')}"
            )

            return {
                "status": "success",
                "date": target.strftime("%Y-%m-%d"),
                "day_of_week": target.strftime("%A"),
                "formatted": target.strftime("%B %d, %Y"),
            }

        # Handle month names (e.g., "April 10th", "April 10")
        try:
            # Try parsing various date formats
            for fmt in ["%B %d", "%B %dst", "%B %dnd", "%B %drd", "%B %dth", "%b %d"]:
                try:
                    parsed = datetime.strptime(date_lower, fmt)
                    # Add year (use 2026 by default)
                    target = parsed.replace(year=ref.year)
                    # If date is in the past, use next year
                    if target < ref:
                        target = target.replace(year=ref.year + 1)

                    return {
                        "status": "success",
                        "date": target.strftime("%Y-%m-%d"),
                        "day_of_week": target.strftime("%A"),
                        "formatted": target.strftime("%B %d, %Y"),
                    }
                except ValueError:
                    continue
        except Exception:
            pass

        # If we get here, couldn't parse
        return {
            "status": "error",
            "message": f"Could not parse date: '{date_string}'. Try formats like 'Monday', 'tomorrow', 'April 10th'",
        }

    except Exception as e:
        logging.error(f"Error parsing date: {e}")
        return {"status": "error", "message": str(e)}
