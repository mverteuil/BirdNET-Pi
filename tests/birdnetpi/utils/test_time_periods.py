"""Tests for time period calculation utilities."""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
import pytz

from birdnetpi.utils.time_periods import (
    PeriodType,
    calculate_period_boundaries,
    get_current_season,
    get_period_label,
    period_to_days,
)


class TestPeriodType:
    """Test the PeriodType enum."""

    def test_period_type_values(self) -> None:
        """Should have expected enum values for all period types."""
        assert PeriodType.DAY.value == "day"
        assert PeriodType.WEEK.value == "week"
        assert PeriodType.MONTH.value == "month"
        assert PeriodType.SEASON.value == "season"
        assert PeriodType.YEAR.value == "year"
        assert PeriodType.HISTORICAL.value == "historical"

    def test_period_type_default_alias(self) -> None:
        """Should have DEFAULT as an alias for DAY."""
        assert PeriodType.DEFAULT == PeriodType.DAY
        assert PeriodType.DEFAULT.value == "day"

    def test_period_type_from_string(self) -> None:
        """Should create PeriodType from string values."""
        assert PeriodType("day") == PeriodType.DAY
        assert PeriodType("week") == PeriodType.WEEK
        assert PeriodType("month") == PeriodType.MONTH

    def test_period_type_invalid_string(self) -> None:
        """Should raise ValueError for invalid string values."""
        with pytest.raises(ValueError):
            PeriodType("invalid")


class TestCalculatePeriodBoundaries:
    """Test calculate_period_boundaries function."""

    def test_day_boundaries_utc(self) -> None:
        """Should calculate correct day boundaries in UTC."""
        now = datetime(2024, 3, 15, 14, 30, 0, tzinfo=UTC)
        start, end = calculate_period_boundaries(PeriodType.DAY, now, "UTC")

        assert start == datetime(2024, 3, 15, 0, 0, 0, tzinfo=UTC)
        assert end == datetime(2024, 3, 16, 0, 0, 0, tzinfo=UTC)

    def test_day_boundaries_with_timezone(self) -> None:
        """Should calculate correct day boundaries with specific timezone."""
        now = datetime(2024, 3, 15, 14, 30, 0, tzinfo=UTC)
        start, end = calculate_period_boundaries(PeriodType.DAY, now, "America/New_York")

        # Should be in New York timezone
        ny_tz = pytz.timezone("America/New_York")
        expected_start = ny_tz.localize(datetime(2024, 3, 15, 0, 0, 0))

        # Compare as UTC to avoid DST issues
        assert start.astimezone(UTC).date() == expected_start.astimezone(UTC).date()
        assert (end - start).total_seconds() == 86400  # Exactly 24 hours

    def test_week_boundaries(self) -> None:
        """Should calculate week boundaries from Monday to Sunday."""
        # Test with a Wednesday
        now = datetime(2024, 3, 13, 14, 30, 0, tzinfo=UTC)  # Wednesday
        start, end = calculate_period_boundaries(PeriodType.WEEK, now, "UTC")

        assert start == datetime(2024, 3, 11, 0, 0, 0, tzinfo=UTC)  # Monday
        assert end == datetime(2024, 3, 18, 0, 0, 0, tzinfo=UTC)  # Next Monday
        assert start.weekday() == 0  # Monday
        assert (end - start).days == 7

    def test_month_boundaries(self) -> None:
        """Should calculate correct month boundaries."""
        now = datetime(2024, 3, 15, 14, 30, 0, tzinfo=UTC)
        start, end = calculate_period_boundaries(PeriodType.MONTH, now, "UTC")

        assert start == datetime(2024, 3, 1, 0, 0, 0, tzinfo=UTC)
        assert end == datetime(2024, 4, 1, 0, 0, 0, tzinfo=UTC)

    def test_month_boundaries_february(self) -> None:
        """Should handle February boundaries correctly for leap and non-leap years."""
        # Non-leap year
        now = datetime(2023, 2, 15, 14, 30, 0, tzinfo=UTC)
        start, end = calculate_period_boundaries(PeriodType.MONTH, now, "UTC")
        assert start == datetime(2023, 2, 1, 0, 0, 0, tzinfo=UTC)
        assert end == datetime(2023, 3, 1, 0, 0, 0, tzinfo=UTC)

        # Leap year
        now = datetime(2024, 2, 15, 14, 30, 0, tzinfo=UTC)
        start, end = calculate_period_boundaries(PeriodType.MONTH, now, "UTC")
        assert start == datetime(2024, 2, 1, 0, 0, 0, tzinfo=UTC)
        assert end == datetime(2024, 3, 1, 0, 0, 0, tzinfo=UTC)

    def test_season_boundaries_spring(self) -> None:
        """Should calculate spring season boundaries (Mar-May)."""
        now = datetime(2024, 4, 15, 14, 30, 0, tzinfo=UTC)
        start, end = calculate_period_boundaries(PeriodType.SEASON, now, "UTC")

        assert start == datetime(2024, 3, 1, 0, 0, 0, tzinfo=UTC)
        assert end == datetime(2024, 6, 1, 0, 0, 0, tzinfo=UTC)

    def test_season_boundaries_summer(self) -> None:
        """Should calculate summer season boundaries (Jun-Aug)."""
        now = datetime(2024, 7, 15, 14, 30, 0, tzinfo=UTC)
        start, end = calculate_period_boundaries(PeriodType.SEASON, now, "UTC")

        assert start == datetime(2024, 6, 1, 0, 0, 0, tzinfo=UTC)
        assert end == datetime(2024, 9, 1, 0, 0, 0, tzinfo=UTC)

    def test_season_boundaries_fall(self) -> None:
        """Should calculate fall season boundaries (Sep-Nov)."""
        now = datetime(2024, 10, 15, 14, 30, 0, tzinfo=UTC)
        start, end = calculate_period_boundaries(PeriodType.SEASON, now, "UTC")

        assert start == datetime(2024, 9, 1, 0, 0, 0, tzinfo=UTC)
        assert end == datetime(2024, 12, 1, 0, 0, 0, tzinfo=UTC)

    def test_season_boundaries_winter_december(self) -> None:
        """Should calculate winter boundaries when starting in December."""
        now = datetime(2024, 12, 15, 14, 30, 0, tzinfo=UTC)
        start, end = calculate_period_boundaries(PeriodType.SEASON, now, "UTC")

        assert start == datetime(2024, 12, 1, 0, 0, 0, tzinfo=UTC)
        assert end == datetime(2025, 3, 1, 0, 0, 0, tzinfo=UTC)

    def test_season_boundaries_winter_january(self) -> None:
        """Should calculate winter boundaries when in January."""
        now = datetime(2024, 1, 15, 14, 30, 0, tzinfo=UTC)
        start, end = calculate_period_boundaries(PeriodType.SEASON, now, "UTC")

        assert start == datetime(2023, 12, 1, 0, 0, 0, tzinfo=UTC)
        assert end == datetime(2024, 3, 1, 0, 0, 0, tzinfo=UTC)

    def test_year_boundaries(self) -> None:
        """Should calculate correct year boundaries."""
        now = datetime(2024, 6, 15, 14, 30, 0, tzinfo=UTC)
        start, end = calculate_period_boundaries(PeriodType.YEAR, now, "UTC")

        assert start == datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        assert end == datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)

    def test_historical_boundaries(self) -> None:
        """Should return min/max datetime for historical period."""
        now = datetime(2024, 3, 15, 14, 30, 0, tzinfo=UTC)
        start, end = calculate_period_boundaries(PeriodType.HISTORICAL, now, "UTC")

        # Should return very old and very future dates
        assert start.year == datetime.min.year
        assert end.year == datetime.max.year
        assert start.tzinfo == UTC
        assert end.tzinfo == UTC

    def test_string_period_type(self) -> None:
        """Should convert string period types to enum."""
        now = datetime(2024, 3, 15, 14, 30, 0, tzinfo=UTC)

        # Test with string
        start, end = calculate_period_boundaries("day", now, "UTC")
        assert start == datetime(2024, 3, 15, 0, 0, 0, tzinfo=UTC)
        assert end == datetime(2024, 3, 16, 0, 0, 0, tzinfo=UTC)

    def test_invalid_period_type_uses_default(self) -> None:
        """Should fall back to DAY for invalid period type."""
        now = datetime(2024, 3, 15, 14, 30, 0, tzinfo=UTC)

        # Invalid period should use DEFAULT (DAY)
        start, end = calculate_period_boundaries("invalid", now, "UTC")
        assert start == datetime(2024, 3, 15, 0, 0, 0, tzinfo=UTC)
        assert end == datetime(2024, 3, 16, 0, 0, 0, tzinfo=UTC)

    def test_no_timezone_info_adds_utc(self) -> None:
        """Should add UTC timezone to naive datetime."""
        now = datetime(2024, 3, 15, 14, 30, 0)  # No timezone
        start, end = calculate_period_boundaries(PeriodType.DAY, now, "UTC")

        assert start.tzinfo == UTC
        assert end.tzinfo == UTC

    @patch("birdnetpi.utils.time_periods.datetime", autospec=True)
    def test_default_now_uses_current_time(self, mock_datetime: object) -> None:
        """Should use current time when now parameter is None."""
        mock_now = datetime(2024, 3, 15, 14, 30, 0, tzinfo=UTC)
        mock_datetime.now.return_value = mock_now  # type: ignore[attr-defined]
        mock_datetime.min = datetime.min  # type: ignore[attr-defined]
        mock_datetime.max = datetime.max  # type: ignore[attr-defined]

        start, end = calculate_period_boundaries(PeriodType.DAY, None, "UTC")

        # Should use the mocked current time
        assert start == datetime(2024, 3, 15, 0, 0, 0, tzinfo=UTC)
        assert end == datetime(2024, 3, 16, 0, 0, 0, tzinfo=UTC)


class TestPeriodToDays:
    """Test period_to_days function."""

    def test_period_to_days_mapping(self) -> None:
        """Should map periods to correct number of days."""
        assert period_to_days(PeriodType.DAY) == 1
        assert period_to_days(PeriodType.WEEK) == 7
        assert period_to_days(PeriodType.MONTH) == 30
        assert period_to_days(PeriodType.SEASON) == 90
        assert period_to_days(PeriodType.YEAR) == 365
        assert period_to_days(PeriodType.HISTORICAL) is None

    def test_period_to_days_with_string(self) -> None:
        """Should convert string period to days."""
        assert period_to_days("day") == 1
        assert period_to_days("week") == 7
        assert period_to_days("month") == 30

    def test_period_to_days_invalid_uses_default(self) -> None:
        """Should use DEFAULT (1 day) for invalid period."""
        assert period_to_days("invalid") == 1  # DEFAULT is DAY = 1


class TestGetPeriodLabel:
    """Test get_period_label function."""

    def test_period_labels(self) -> None:
        """Should return correct human-readable labels for periods."""
        assert get_period_label(PeriodType.DAY) == "Today"
        assert get_period_label(PeriodType.WEEK) == "This Week"
        assert get_period_label(PeriodType.MONTH) == "This Month"
        assert get_period_label(PeriodType.SEASON) == "This Season"
        assert get_period_label(PeriodType.YEAR) == "This Year"
        assert get_period_label(PeriodType.HISTORICAL) == "All Time"

    def test_period_label_with_string(self) -> None:
        """Should handle string input for period labels."""
        assert get_period_label("day") == "Today"
        assert get_period_label("week") == "This Week"
        assert get_period_label("historical") == "All Time"

    def test_period_label_invalid_uses_default(self) -> None:
        """Should use DEFAULT label for invalid period."""
        assert get_period_label("invalid") == "Today"  # DEFAULT is DAY


class TestGetCurrentSeason:
    """Test get_current_season function."""

    def test_spring_months(self) -> None:
        """Should detect spring season for March through May."""
        assert get_current_season(datetime(2024, 3, 1)) == "Spring"
        assert get_current_season(datetime(2024, 4, 15)) == "Spring"
        assert get_current_season(datetime(2024, 5, 31)) == "Spring"

    def test_summer_months(self) -> None:
        """Should detect summer season for June through August."""
        assert get_current_season(datetime(2024, 6, 1)) == "Summer"
        assert get_current_season(datetime(2024, 7, 15)) == "Summer"
        assert get_current_season(datetime(2024, 8, 31)) == "Summer"

    def test_fall_months(self) -> None:
        """Should detect fall season for September through November."""
        assert get_current_season(datetime(2024, 9, 1)) == "Fall"
        assert get_current_season(datetime(2024, 10, 15)) == "Fall"
        assert get_current_season(datetime(2024, 11, 30)) == "Fall"

    def test_winter_months(self) -> None:
        """Should detect winter season for December through February."""
        assert get_current_season(datetime(2024, 12, 1)) == "Winter"
        assert get_current_season(datetime(2024, 1, 15)) == "Winter"
        assert get_current_season(datetime(2024, 2, 28)) == "Winter"

    @patch("birdnetpi.utils.time_periods.datetime", autospec=True)
    def test_current_season_default_now(self, mock_datetime: object) -> None:
        """Should use current time when None is passed."""
        mock_now = datetime(2024, 7, 15, tzinfo=UTC)
        mock_datetime.now.return_value = mock_now  # type: ignore[attr-defined]

        assert get_current_season(None) == "Summer"


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_leap_year_february(self) -> None:
        """Should handle leap year February boundaries correctly."""
        # February 29, 2024 (leap year)
        now = datetime(2024, 2, 29, 12, 0, 0, tzinfo=UTC)
        start, end = calculate_period_boundaries(PeriodType.MONTH, now, "UTC")

        assert start == datetime(2024, 2, 1, 0, 0, 0, tzinfo=UTC)
        assert end == datetime(2024, 3, 1, 0, 0, 0, tzinfo=UTC)

    def test_daylight_saving_transition(self) -> None:
        """Should maintain 24-hour day during DST transitions."""
        # March 10, 2024 - Spring forward (DST starts)
        now = datetime(2024, 3, 10, 12, 0, 0, tzinfo=UTC)
        start, end = calculate_period_boundaries(PeriodType.DAY, now, "America/New_York")

        # Should still be exactly 24 hours apart despite DST
        duration = (end - start).total_seconds()
        assert duration == 86400  # 24 hours in seconds

    def test_year_boundary_crossing(self) -> None:
        """Should handle periods that cross year boundaries."""
        # December week that crosses into January
        now = datetime(2024, 12, 30, 12, 0, 0, tzinfo=UTC)  # Monday
        start, end = calculate_period_boundaries(PeriodType.WEEK, now, "UTC")

        assert start.year == 2024
        assert end.year == 2025
        assert (end - start).days == 7

    def test_all_period_types_have_handlers(self) -> None:
        """Should have handlers for all PeriodType enum values."""
        now = datetime(2024, 3, 15, 14, 30, 0, tzinfo=UTC)

        for period in PeriodType:
            # Should not raise any exceptions
            start, end = calculate_period_boundaries(period, now, "UTC")
            assert isinstance(start, datetime)
            assert isinstance(end, datetime)
            assert start < end  # Start should always be before end
