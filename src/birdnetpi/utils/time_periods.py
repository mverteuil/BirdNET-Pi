"""Time period calculation utilities.

This module provides centralized functions for calculating time period boundaries
used throughout the application for filtering and aggregating detection data.
"""

from calendar import monthrange
from datetime import UTC, datetime, timedelta
from enum import Enum

import pytz


class PeriodType(str, Enum):
    """Time period types for detection filtering."""

    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    SEASON = "season"
    YEAR = "year"
    HISTORICAL = "historical"

    # Default period when invalid value is provided (alias to DAY)
    DEFAULT = DAY


def calculate_period_boundaries(
    period: PeriodType | str, now: datetime | None = None, timezone: str = "UTC"
) -> tuple[datetime, datetime]:
    """Calculate start and end datetime boundaries for a given period.

    Args:
        period: Time period (day, week, month, season, year, historical)
        now: Reference datetime (defaults to current UTC time)
        timezone: Timezone string for local time calculations

    Returns:
        Tuple of (start_datetime, end_datetime) with timezone info
    """
    if now is None:
        now = datetime.now(UTC)

    # Ensure now has timezone info
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    # Convert to local timezone if specified
    if timezone != "UTC":
        tz = pytz.timezone(timezone)
        now_local = now.astimezone(tz)
    else:
        now_local = now

    # Convert string to enum if needed
    if isinstance(period, str):
        try:
            period = PeriodType(period.lower())
        except ValueError:
            period = PeriodType.DEFAULT

    # Use dispatch dictionary to reduce complexity
    period_handlers = {
        PeriodType.DAY: _calculate_day_boundaries,
        PeriodType.WEEK: _calculate_week_boundaries,
        PeriodType.MONTH: _calculate_month_boundaries,
        PeriodType.SEASON: _calculate_season_boundaries,
        PeriodType.YEAR: _calculate_year_boundaries,
        PeriodType.HISTORICAL: _calculate_historical_boundaries,
    }

    handler = period_handlers.get(period, _calculate_day_boundaries)
    return handler(now_local)


def _calculate_day_boundaries(now_local: datetime) -> tuple[datetime, datetime]:
    """Calculate today's boundaries (00:00 to 24:00 local time)."""
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    return start_local, end_local


def _calculate_week_boundaries(now_local: datetime) -> tuple[datetime, datetime]:
    """Calculate this week's boundaries (Monday 00:00 to Sunday 24:00 local time)."""
    days_since_monday = now_local.weekday()
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    start_local = start_local - timedelta(days=days_since_monday)
    end_local = start_local + timedelta(days=7)
    return start_local, end_local


def _calculate_month_boundaries(now_local: datetime) -> tuple[datetime, datetime]:
    """Calculate this month's boundaries (1st 00:00 to last day 24:00 local time)."""
    start_local = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # Last day of current month
    last_day = monthrange(now_local.year, now_local.month)[1]
    end_local = start_local.replace(day=last_day) + timedelta(days=1)
    return start_local, end_local


def _calculate_season_boundaries(now_local: datetime) -> tuple[datetime, datetime]:
    """Calculate seasonal boundaries based on meteorological seasons.

    Meteorological seasons:
    - Spring: March 1 - May 31
    - Summer: June 1 - August 31
    - Fall: September 1 - November 30
    - Winter: December 1 - February 28/29
    """
    month = now_local.month
    year = now_local.year

    if month in [3, 4, 5]:  # Spring
        start_local = now_local.replace(
            year=year, month=3, day=1, hour=0, minute=0, second=0, microsecond=0
        )
        end_local = now_local.replace(
            year=year, month=6, day=1, hour=0, minute=0, second=0, microsecond=0
        )
    elif month in [6, 7, 8]:  # Summer
        start_local = now_local.replace(
            year=year, month=6, day=1, hour=0, minute=0, second=0, microsecond=0
        )
        end_local = now_local.replace(
            year=year, month=9, day=1, hour=0, minute=0, second=0, microsecond=0
        )
    elif month in [9, 10, 11]:  # Fall
        start_local = now_local.replace(
            year=year, month=9, day=1, hour=0, minute=0, second=0, microsecond=0
        )
        end_local = now_local.replace(
            year=year, month=12, day=1, hour=0, minute=0, second=0, microsecond=0
        )
    else:  # Winter (Dec-Feb)
        if month == 12:
            start_local = now_local.replace(
                year=year, month=12, day=1, hour=0, minute=0, second=0, microsecond=0
            )
            end_local = now_local.replace(
                year=year + 1, month=3, day=1, hour=0, minute=0, second=0, microsecond=0
            )
        else:  # Jan or Feb
            start_local = now_local.replace(
                year=year - 1, month=12, day=1, hour=0, minute=0, second=0, microsecond=0
            )
            end_local = now_local.replace(
                year=year, month=3, day=1, hour=0, minute=0, second=0, microsecond=0
            )

    return start_local, end_local


def _calculate_year_boundaries(now_local: datetime) -> tuple[datetime, datetime]:
    """Calculate this year's boundaries (Jan 1 00:00 to Dec 31 24:00 local time)."""
    start_local = now_local.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local.replace(year=start_local.year + 1)
    return start_local, end_local


def _calculate_historical_boundaries(now_local: datetime) -> tuple[datetime, datetime]:
    """Calculate boundaries for all historical data (no filtering)."""
    # Use very old and very future dates with the same timezone
    start_local = datetime.min.replace(tzinfo=now_local.tzinfo)
    end_local = datetime.max.replace(tzinfo=now_local.tzinfo)
    return start_local, end_local


def period_to_days(period: PeriodType | str) -> int | None:
    """Convert a period type to approximate number of days.

    Args:
        period: Time period type

    Returns:
        Number of days for the period, or None for historical
    """
    # Convert string to enum if needed
    if isinstance(period, str):
        try:
            period = PeriodType(period.lower())
        except ValueError:
            period = PeriodType.DEFAULT

    period_map = {
        PeriodType.DAY: 1,
        PeriodType.WEEK: 7,
        PeriodType.MONTH: 30,
        PeriodType.SEASON: 90,
        PeriodType.YEAR: 365,
        PeriodType.HISTORICAL: None,
    }
    return period_map.get(period)


def get_period_label(period: PeriodType | str) -> str:
    """Get human-readable label for a period.

    Args:
        period: Time period type

    Returns:
        Human-readable period label
    """
    # Convert string to enum if needed
    if isinstance(period, str):
        try:
            period = PeriodType(period.lower())
        except ValueError:
            period = PeriodType.DEFAULT

    labels = {
        PeriodType.DAY: "Today",
        PeriodType.WEEK: "This Week",
        PeriodType.MONTH: "This Month",
        PeriodType.SEASON: "This Season",
        PeriodType.YEAR: "This Year",
        PeriodType.HISTORICAL: "All Time",
    }
    return labels.get(period, period.value.capitalize())


def get_current_season(now: datetime | None = None) -> str:
    """Get the current meteorological season name.

    Args:
        now: Reference datetime (defaults to current UTC time)

    Returns:
        Season name (Spring, Summer, Fall, Winter)
    """
    if now is None:
        now = datetime.now(UTC)

    month = now.month
    if month in [3, 4, 5]:
        return "Spring"
    elif month in [6, 7, 8]:
        return "Summer"
    elif month in [9, 10, 11]:
        return "Fall"
    else:
        return "Winter"
