"""Tests for time period calculation utilities - Refactored with parameterization."""

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

    @pytest.mark.parametrize(
        "period_type, expected_value",
        [
            (PeriodType.DAY, "day"),
            (PeriodType.WEEK, "week"),
            (PeriodType.MONTH, "month"),
            (PeriodType.SEASON, "season"),
            (PeriodType.YEAR, "year"),
            (PeriodType.HISTORICAL, "historical"),
        ],
        ids=["day", "week", "month", "season", "year", "historical"],
    )
    def test_period_type_values(self, period_type, expected_value) -> None:
        """Should have expected enum values for all period types."""
        assert period_type.value == expected_value

    def test_period_type_default_alias(self) -> None:
        """Should have DEFAULT as an alias for DAY."""
        assert PeriodType.DEFAULT == PeriodType.DAY
        assert PeriodType.DEFAULT.value == "day"

    @pytest.mark.parametrize(
        "string_value, expected_period",
        [
            ("day", PeriodType.DAY),
            ("week", PeriodType.WEEK),
            ("month", PeriodType.MONTH),
        ],
        ids=["day", "week", "month"],
    )
    def test_period_type_from_string(self, string_value, expected_period) -> None:
        """Should create PeriodType from string values."""
        assert PeriodType(string_value) == expected_period

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

    @pytest.mark.parametrize(
        "year, month, expected_end_month",
        [
            (2023, 2, 3),  # Non-leap year February
            (2024, 2, 3),  # Leap year February
        ],
        ids=["non-leap-year", "leap-year"],
    )
    def test_month_boundaries_february(self, year, month, expected_end_month) -> None:
        """Should handle February boundaries correctly for leap and non-leap years."""
        now = datetime(year, month, 15, 14, 30, 0, tzinfo=UTC)
        start, end = calculate_period_boundaries(PeriodType.MONTH, now, "UTC")

        assert start == datetime(year, month, 1, 0, 0, 0, tzinfo=UTC)
        assert end == datetime(year, expected_end_month, 1, 0, 0, 0, tzinfo=UTC)

    @pytest.mark.parametrize(
        "test_month, season_name, expected_start_month, expected_end_month",
        [
            pytest.param(4, "spring", 3, 6, id="spring-april"),
            pytest.param(7, "summer", 6, 9, id="summer-july"),
            pytest.param(10, "fall", 9, 12, id="fall-october"),
            pytest.param(12, "winter", 12, 3, id="winter-december"),
            pytest.param(1, "winter", 12, 3, id="winter-january"),
        ],
    )
    def test_season_boundaries(
        self, test_month, season_name, expected_start_month, expected_end_month
    ) -> None:
        """Should calculate correct season boundaries for all seasons."""
        # Determine the year for start/end based on the season
        test_year = 2024
        if test_month == 12 and expected_end_month == 3:
            # Winter December case
            start_year = test_year
            end_year = test_year + 1
        elif test_month == 1 and expected_start_month == 12:
            # Winter January case
            start_year = test_year - 1
            end_year = test_year
        else:
            start_year = end_year = test_year

        now = datetime(test_year, test_month, 15, 14, 30, 0, tzinfo=UTC)
        start, end = calculate_period_boundaries(PeriodType.SEASON, now, "UTC")

        assert start == datetime(start_year, expected_start_month, 1, 0, 0, 0, tzinfo=UTC)
        assert end == datetime(end_year, expected_end_month, 1, 0, 0, 0, tzinfo=UTC)

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

    @pytest.mark.parametrize(
        "period, expected_days",
        [
            (PeriodType.DAY, 1),
            (PeriodType.WEEK, 7),
            (PeriodType.MONTH, 30),
            (PeriodType.SEASON, 90),
            (PeriodType.YEAR, 365),
            (PeriodType.HISTORICAL, None),
        ],
        ids=["day-1", "week-7", "month-30", "season-90", "year-365", "historical-none"],
    )
    def test_period_to_days_mapping(self, period, expected_days) -> None:
        """Should map periods to correct number of days."""
        assert period_to_days(period) == expected_days

    @pytest.mark.parametrize(
        "string_period, expected_days",
        [
            ("day", 1),
            ("week", 7),
            ("month", 30),
        ],
        ids=["day", "week", "month"],
    )
    def test_period_to_days_with_string(self, string_period, expected_days) -> None:
        """Should convert string period to days."""
        assert period_to_days(string_period) == expected_days

    def test_period_to_days_invalid_uses_default(self) -> None:
        """Should use DEFAULT (1 day) for invalid period."""
        assert period_to_days("invalid") == 1  # DEFAULT is DAY = 1


class TestGetPeriodLabel:
    """Test get_period_label function."""

    @pytest.mark.parametrize(
        "period, expected_label",
        [
            (PeriodType.DAY, "Today"),
            (PeriodType.WEEK, "This Week"),
            (PeriodType.MONTH, "This Month"),
            (PeriodType.SEASON, "This Season"),
            (PeriodType.YEAR, "This Year"),
            (PeriodType.HISTORICAL, "All Time"),
        ],
        ids=["day", "week", "month", "season", "year", "historical"],
    )
    def test_period_labels(self, period, expected_label) -> None:
        """Should return correct human-readable labels for periods."""
        assert get_period_label(period) == expected_label

    @pytest.mark.parametrize(
        "string_period, expected_label",
        [
            ("day", "Today"),
            ("week", "This Week"),
            ("historical", "All Time"),
        ],
        ids=["day", "week", "historical"],
    )
    def test_period_label_with_string(self, string_period, expected_label) -> None:
        """Should handle string input for period labels."""
        assert get_period_label(string_period) == expected_label

    def test_period_label_invalid_uses_default(self) -> None:
        """Should use DEFAULT label for invalid period."""
        assert get_period_label("invalid") == "Today"  # DEFAULT is DAY


class TestGetCurrentSeason:
    """Test get_current_season function."""

    @pytest.mark.parametrize(
        "month, day, expected_season",
        [
            # Spring months (March-May)
            pytest.param(3, 1, "Spring", id="march-start"),
            pytest.param(4, 15, "Spring", id="april-mid"),
            pytest.param(5, 31, "Spring", id="may-end"),
            # Summer months (June-August)
            pytest.param(6, 1, "Summer", id="june-start"),
            pytest.param(7, 15, "Summer", id="july-mid"),
            pytest.param(8, 31, "Summer", id="august-end"),
            # Fall months (September-November)
            pytest.param(9, 1, "Fall", id="september-start"),
            pytest.param(10, 15, "Fall", id="october-mid"),
            pytest.param(11, 30, "Fall", id="november-end"),
            # Winter months (December-February)
            pytest.param(12, 1, "Winter", id="december-start"),
            pytest.param(1, 15, "Winter", id="january-mid"),
            pytest.param(2, 28, "Winter", id="february-end"),
        ],
    )
    def test_seasons_by_month(self, month, day, expected_season) -> None:
        """Should detect correct season for each month."""
        test_date = datetime(2024, month, day)
        assert get_current_season(test_date) == expected_season

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
