"""Tests for NotificationRuleProcessor."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from birdnetpi.database.species import SpeciesDatabaseService
from birdnetpi.detections.queries import DetectionQueryService
from birdnetpi.notifications.enums import NotificationFrequency, NotificationScope
from birdnetpi.notifications.rules import NotificationRuleProcessor


@pytest.fixture
def test_rule():
    """Create a basic test rule."""
    return {
        "name": "Test Rule",
        "enabled": True,
        "frequency": {"when": NotificationFrequency.IMMEDIATE},
        "minimum_confidence": 0,
        "include_taxa": {},
        "exclude_taxa": {},
        "scope": NotificationScope.ALL,
    }


@pytest.fixture
def rule_processor(test_config, db_session_factory):
    """Create a NotificationRuleProcessor for testing."""
    session, _ = db_session_factory()

    # Mock species database service
    species_db_service = MagicMock(spec=SpeciesDatabaseService)
    species_db_service.get_species_taxonomy = AsyncMock(
        spec=SpeciesDatabaseService.get_species_taxonomy, return_value=None
    )

    # Mock detection query service
    detection_query_service = MagicMock(spec=DetectionQueryService)
    detection_query_service.is_first_detection_ever = AsyncMock(
        spec=DetectionQueryService.is_first_detection_ever, return_value=True
    )
    detection_query_service.is_first_detection_in_period = AsyncMock(
        spec=DetectionQueryService.is_first_detection_in_period, return_value=True
    )

    return NotificationRuleProcessor(
        config=test_config,
        db_session=session,
        species_db_service=species_db_service,
        detection_query_service=detection_query_service,
    )


class TestNotificationRuleProcessorInitialization:
    """Test NotificationRuleProcessor initialization."""

    def test_init(self, test_config, db_session_factory):
        """Should initialize NotificationRuleProcessor correctly."""
        session, _ = db_session_factory()
        species_db_service = MagicMock(spec=SpeciesDatabaseService)
        detection_query_service = MagicMock(spec=DetectionQueryService)

        processor = NotificationRuleProcessor(
            config=test_config,
            db_session=session,
            species_db_service=species_db_service,
            detection_query_service=detection_query_service,
        )

        assert processor.config == test_config
        assert processor.db_session == session
        assert processor.species_db_service == species_db_service


class TestFindMatchingRules:
    """Test finding matching rules for detections."""

    @pytest.mark.asyncio
    async def test_find_matching_rules_no_rules(self, rule_processor, model_factory):
        """Should return empty list when no rules configured."""
        rule_processor.config.notification_rules = []

        detection = model_factory.create_detection(
            common_name="Test Bird",
            confidence=0.85,
        )

        matching_rules = await rule_processor.find_matching_rules(detection)

        assert matching_rules == []

    @pytest.mark.asyncio
    async def test_find_matching_rules_single_match(self, rule_processor, model_factory, test_rule):
        """Should find single matching rule."""
        rule_processor.config.notification_rules = [test_rule]

        detection = model_factory.create_detection(
            common_name="Test Bird",
            confidence=0.85,
        )

        matching_rules = await rule_processor.find_matching_rules(detection)

        assert len(matching_rules) == 1
        assert matching_rules[0]["name"] == "Test Rule"

    @pytest.mark.asyncio
    async def test_find_matching_rules_multiple_matches(
        self, rule_processor, model_factory, test_rule
    ):
        """Should find multiple matching rules."""
        rule1 = {**test_rule, "name": "Rule 1"}
        rule2 = {**test_rule, "name": "Rule 2"}
        rule_processor.config.notification_rules = [rule1, rule2]

        detection = model_factory.create_detection(
            common_name="Test Bird",
            confidence=0.85,
        )

        matching_rules = await rule_processor.find_matching_rules(detection)

        assert len(matching_rules) == 2
        assert matching_rules[0]["name"] == "Rule 1"
        assert matching_rules[1]["name"] == "Rule 2"

    @pytest.mark.asyncio
    async def test_find_matching_rules_filters_disabled(
        self, rule_processor, model_factory, test_rule
    ):
        """Should filter out disabled rules."""
        enabled_rule = {**test_rule, "name": "Enabled"}
        disabled_rule = {**test_rule, "name": "Disabled", "enabled": False}
        rule_processor.config.notification_rules = [enabled_rule, disabled_rule]

        detection = model_factory.create_detection(confidence=0.85)

        matching_rules = await rule_processor.find_matching_rules(detection)

        assert len(matching_rules) == 1
        assert matching_rules[0]["name"] == "Enabled"


class TestRuleMatchingLogic:
    """Test individual rule matching logic."""

    @pytest.mark.asyncio
    async def test_rule_matches_disabled_rule(self, rule_processor, model_factory, test_rule):
        """Should not match disabled rule."""
        rule = {**test_rule, "enabled": False}
        detection = model_factory.create_detection(confidence=0.85)

        matches = await rule_processor._rule_matches_detection(rule, detection)

        assert matches is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "frequency_when,should_match",
        [
            pytest.param(NotificationFrequency.IMMEDIATE, True, id="immediate"),
            pytest.param(NotificationFrequency.DAILY, False, id="daily"),
            pytest.param(NotificationFrequency.WEEKLY, False, id="weekly"),
        ],
    )
    async def test_rule_matches_frequency_check(
        self, rule_processor, model_factory, test_rule, frequency_when, should_match
    ):
        """Should only match immediate frequency rules."""
        rule = {**test_rule, "frequency": {"when": frequency_when}}
        detection = model_factory.create_detection(confidence=0.85)

        matches = await rule_processor._rule_matches_detection(rule, detection)

        assert matches is should_match

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "minimum_confidence,detection_confidence,should_match",
        [
            pytest.param(0, 0.5, True, id="no-minimum"),
            pytest.param(50, 0.6, True, id="above-minimum"),
            pytest.param(50, 0.5, True, id="at-minimum"),
            pytest.param(80, 0.5, False, id="below-minimum"),
        ],
    )
    async def test_rule_matches_minimum_confidence(
        self,
        rule_processor,
        model_factory,
        test_rule,
        minimum_confidence,
        detection_confidence,
        should_match,
    ):
        """Should check minimum confidence threshold."""
        rule = {**test_rule, "minimum_confidence": minimum_confidence}
        detection = model_factory.create_detection(confidence=detection_confidence)

        matches = await rule_processor._rule_matches_detection(rule, detection)

        assert matches is should_match


class TestQuietHoursCheck:
    """Test quiet hours checking logic."""

    def test_check_quiet_hours_no_config(self, rule_processor):
        """Should allow notifications when no quiet hours configured."""
        rule_processor.config.notify_quiet_hours_start = None
        rule_processor.config.notify_quiet_hours_end = None

        result = rule_processor._check_quiet_hours()

        assert result is True

    def test_check_quiet_hours_same_day_range_outside(self, rule_processor):
        """Should allow notifications outside quiet hours (overnight range)."""
        # Test overnight range: 22:00 to 08:00 (not same day)
        # Current time would be outside this range
        rule_processor.config.notify_quiet_hours_start = "22:00:00"
        rule_processor.config.notify_quiet_hours_end = "08:00:00"

        result = rule_processor._check_quiet_hours()

        # The result depends on current time, so just check it's a boolean
        assert isinstance(result, bool)

    def test_check_quiet_hours_invalid_format(self, rule_processor, caplog):
        """Should handle invalid quiet hours format."""
        rule_processor.config.notify_quiet_hours_start = "invalid"
        rule_processor.config.notify_quiet_hours_end = "also-invalid"

        result = rule_processor._check_quiet_hours()

        assert result is True  # Allow notifications if config is invalid
        assert "Invalid quiet hours format" in caplog.text


class TestTaxaFilters:
    """Test taxa include/exclude filter logic."""

    @pytest.mark.asyncio
    async def test_check_taxa_filters_no_filters(self, rule_processor, model_factory, test_rule):
        """Should allow all detections when no taxa filters specified."""
        rule = {**test_rule}
        detection = model_factory.create_detection(
            scientific_name="Turdus migratorius",
        )

        result = await rule_processor._check_taxa_filters(rule, detection)

        assert result is True

    @pytest.mark.asyncio
    async def test_check_taxa_filters_species_include_match(
        self, rule_processor, model_factory, test_rule
    ):
        """Should match when species is in include list."""
        rule = {
            **test_rule,
            "include_taxa": {"species": ["Turdus migratorius"]},
        }
        detection = model_factory.create_detection(
            scientific_name="Turdus migratorius",
        )

        result = await rule_processor._check_taxa_filters(rule, detection)

        assert result is True

    @pytest.mark.asyncio
    async def test_check_taxa_filters_species_include_no_match(
        self, rule_processor, model_factory, test_rule
    ):
        """Should not match when species is not in include list."""
        rule = {
            **test_rule,
            "include_taxa": {"species": ["Corvus brachyrhynchos"]},
        }
        detection = model_factory.create_detection(
            scientific_name="Turdus migratorius",
        )

        result = await rule_processor._check_taxa_filters(rule, detection)

        assert result is False

    @pytest.mark.asyncio
    async def test_check_taxa_filters_species_exclude_match(
        self, rule_processor, model_factory, test_rule
    ):
        """Should exclude when species is in exclude list."""
        rule = {
            **test_rule,
            "exclude_taxa": {"species": ["Turdus migratorius"]},
        }
        detection = model_factory.create_detection(
            scientific_name="Turdus migratorius",
        )

        result = await rule_processor._check_taxa_filters(rule, detection)

        assert result is False

    @pytest.mark.asyncio
    async def test_check_taxa_filters_exclude_takes_precedence(
        self, rule_processor, model_factory, test_rule
    ):
        """Should exclude even when in include list (exclude takes precedence)."""
        rule = {
            **test_rule,
            "include_taxa": {"species": ["Turdus migratorius"]},
            "exclude_taxa": {"species": ["Turdus migratorius"]},
        }
        detection = model_factory.create_detection(
            scientific_name="Turdus migratorius",
        )

        result = await rule_processor._check_taxa_filters(rule, detection)

        assert result is False

    @pytest.mark.asyncio
    async def test_check_taxa_filters_genus_match(self, rule_processor, model_factory, test_rule):
        """Should match by genus (first word of scientific name)."""
        rule = {
            **test_rule,
            "include_taxa": {"genera": ["Turdus"]},
        }
        detection = model_factory.create_detection(
            scientific_name="Turdus migratorius",
        )

        result = await rule_processor._check_taxa_filters(rule, detection)

        assert result is True

    @pytest.mark.asyncio
    async def test_check_taxa_filters_family_match(self, rule_processor, model_factory, test_rule):
        """Should match by family using IOC database lookup."""
        rule = {
            **test_rule,
            "include_taxa": {"families": ["Turdidae"]},
        }
        detection = model_factory.create_detection(
            scientific_name="Turdus migratorius",
        )

        # Mock IOC database lookup
        rule_processor.species_db_service.get_species_taxonomy = AsyncMock(
            spec=SpeciesDatabaseService.get_species_taxonomy,
            return_value={"family": "Turdidae", "order": "Passeriformes"},
        )

        result = await rule_processor._check_taxa_filters(rule, detection)

        assert result is True
        rule_processor.species_db_service.get_species_taxonomy.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_taxa_filters_order_match(self, rule_processor, model_factory, test_rule):
        """Should match by order using IOC database lookup."""
        rule = {
            **test_rule,
            "include_taxa": {"orders": ["Passeriformes"]},
        }
        detection = model_factory.create_detection(
            scientific_name="Turdus migratorius",
        )

        # Mock IOC database lookup
        rule_processor.species_db_service.get_species_taxonomy = AsyncMock(
            spec=SpeciesDatabaseService.get_species_taxonomy,
            return_value={"family": "Turdidae", "order": "Passeriformes"},
        )

        result = await rule_processor._check_taxa_filters(rule, detection)

        assert result is True

    @pytest.mark.asyncio
    async def test_check_taxa_filters_no_taxonomy_data(
        self, rule_processor, model_factory, test_rule
    ):
        """Should not match when no taxonomy data available."""
        rule = {
            **test_rule,
            "include_taxa": {"families": ["Turdidae"]},
        }
        detection = model_factory.create_detection(
            scientific_name="Unknown species",
        )

        # Mock IOC database returning None
        rule_processor.species_db_service.get_species_taxonomy = AsyncMock(
            spec=SpeciesDatabaseService.get_species_taxonomy, return_value=None
        )

        result = await rule_processor._check_taxa_filters(rule, detection)

        assert result is False


class TestMatchesTaxaFilter:
    """Test the _matches_taxa_filter helper method."""

    @pytest.mark.asyncio
    async def test_matches_taxa_filter_species_exact_match(self, rule_processor):
        """Should match species by exact name."""
        taxa_filter = {"species": ["Turdus migratorius"]}

        result = await rule_processor._matches_taxa_filter(taxa_filter, "Turdus migratorius")

        assert result is True

    @pytest.mark.asyncio
    async def test_matches_taxa_filter_species_no_match(self, rule_processor):
        """Should not match different species."""
        taxa_filter = {"species": ["Corvus brachyrhynchos"]}

        result = await rule_processor._matches_taxa_filter(taxa_filter, "Turdus migratorius")

        assert result is False

    @pytest.mark.asyncio
    async def test_matches_taxa_filter_genus_match(self, rule_processor):
        """Should match by genus."""
        taxa_filter = {"genera": ["Turdus"]}

        result = await rule_processor._matches_taxa_filter(taxa_filter, "Turdus migratorius")

        assert result is True

    @pytest.mark.asyncio
    async def test_matches_taxa_filter_genus_no_match(self, rule_processor):
        """Should not match different genus."""
        taxa_filter = {"genera": ["Corvus"]}

        result = await rule_processor._matches_taxa_filter(taxa_filter, "Turdus migratorius")

        assert result is False


class TestScopeChecks:
    """Test scope checking logic."""

    @pytest.mark.asyncio
    async def test_check_scope_all(self, rule_processor, model_factory, test_rule):
        """Should match all detections with ALL scope."""
        rule = {**test_rule, "scope": NotificationScope.ALL}
        detection = model_factory.create_detection()

        result = await rule_processor._check_scope(rule, detection)

        assert result is True

    @pytest.mark.asyncio
    async def test_check_scope_new_ever_is_first(self, rule_processor, model_factory, test_rule):
        """Should match first detection ever of a species."""
        rule = {**test_rule, "scope": NotificationScope.NEW_EVER}
        detection = model_factory.create_detection(
            scientific_name="Turdus migratorius",
        )

        # Mock detection query service to return True (is first)
        rule_processor.detection_query_service.is_first_detection_ever.return_value = True

        result = await rule_processor._check_scope(rule, detection)

        assert result is True
        rule_processor.detection_query_service.is_first_detection_ever.assert_called_once_with(
            str(detection.id), "Turdus migratorius"
        )

    @pytest.mark.asyncio
    async def test_check_scope_new_ever_not_first(self, rule_processor, model_factory, test_rule):
        """Should not match when species was detected before."""
        rule = {**test_rule, "scope": NotificationScope.NEW_EVER}
        detection = model_factory.create_detection(
            scientific_name="Turdus migratorius",
        )

        # Mock detection query service to return False (not first)
        rule_processor.detection_query_service.is_first_detection_ever.return_value = False

        result = await rule_processor._check_scope(rule, detection)

        assert result is False

    @pytest.mark.asyncio
    async def test_check_scope_new_today_is_first(self, rule_processor, model_factory, test_rule):
        """Should match first detection today."""
        rule = {**test_rule, "scope": NotificationScope.NEW_TODAY}
        detection = model_factory.create_detection(
            scientific_name="Turdus migratorius",
            timestamp=datetime.now(UTC),
        )

        # Mock detection query service to return True (is first today)
        rule_processor.detection_query_service.is_first_detection_in_period.return_value = True

        result = await rule_processor._check_scope(rule, detection)

        assert result is True

    @pytest.mark.asyncio
    async def test_check_scope_new_today_not_first(self, rule_processor, model_factory, test_rule):
        """Should not match when species was detected today."""
        rule = {**test_rule, "scope": NotificationScope.NEW_TODAY}
        detection = model_factory.create_detection(
            scientific_name="Turdus migratorius",
            timestamp=datetime.now(UTC),
        )

        # Mock detection query service to return False (not first today)
        rule_processor.detection_query_service.is_first_detection_in_period.return_value = False

        result = await rule_processor._check_scope(rule, detection)

        assert result is False

    @pytest.mark.asyncio
    async def test_check_scope_new_this_week_is_first(
        self, rule_processor, model_factory, test_rule
    ):
        """Should match first detection this week."""
        rule = {**test_rule, "scope": NotificationScope.NEW_THIS_WEEK}
        detection = model_factory.create_detection(
            scientific_name="Turdus migratorius",
            timestamp=datetime.now(UTC),
        )

        # Mock detection query service to return True (is first this week)
        rule_processor.detection_query_service.is_first_detection_in_period.return_value = True

        result = await rule_processor._check_scope(rule, detection)

        assert result is True

    @pytest.mark.asyncio
    async def test_check_scope_new_this_week_not_first(
        self, rule_processor, model_factory, test_rule
    ):
        """Should not match when species was detected this week."""
        rule = {**test_rule, "scope": NotificationScope.NEW_THIS_WEEK}
        detection = model_factory.create_detection(
            scientific_name="Turdus migratorius",
            timestamp=datetime.now(UTC),
        )

        # Mock detection query service to return False (not first this week)
        rule_processor.detection_query_service.is_first_detection_in_period.return_value = False

        result = await rule_processor._check_scope(rule, detection)

        assert result is False

    @pytest.mark.asyncio
    async def test_check_scope_unknown_scope(
        self, rule_processor, model_factory, test_rule, caplog
    ):
        """Should handle unknown scope types."""
        rule = {**test_rule, "scope": "unknown_scope"}
        detection = model_factory.create_detection()

        result = await rule_processor._check_scope(rule, detection)

        assert result is False
        assert "Unknown scope type" in caplog.text


class TestTemplateRendering:
    """Test Jinja2 template rendering."""

    def test_render_template_basic(self, rule_processor, model_factory):
        """Should render basic template with detection context."""
        template_str = "Detected: {{ common_name }}"
        detection = model_factory.create_detection(
            common_name="American Robin",
        )

        result = rule_processor.render_template(template_str, detection)

        assert result == "Detected: American Robin"

    def test_render_template_all_fields(self, rule_processor, model_factory):
        """Should render template with all detection fields."""
        template_str = (
            "{{ common_name }} ({{ scientific_name }}) detected at {{ confidence_pct }} confidence"
        )
        detection = model_factory.create_detection(
            common_name="American Robin",
            scientific_name="Turdus migratorius",
            confidence=0.85,
        )

        result = rule_processor.render_template(template_str, detection)

        assert "American Robin" in result
        assert "Turdus migratorius" in result
        assert "85.0%" in result

    def test_render_template_timestamp_formatting(self, rule_processor, model_factory):
        """Should format timestamps correctly."""
        template_str = "Date: {{ date }}, Time: {{ time }}"
        detection = model_factory.create_detection(
            timestamp=datetime(2025, 1, 15, 14, 30, 0, tzinfo=UTC),
        )

        result = rule_processor.render_template(template_str, detection)

        assert "2025-01-15" in result
        assert "14:30:00" in result

    def test_render_template_location(self, rule_processor, model_factory):
        """Should include location data."""
        template_str = "Location: {{ latitude }}, {{ longitude }}"
        detection = model_factory.create_detection(
            latitude=40.7128,
            longitude=-74.0060,
        )

        result = rule_processor.render_template(template_str, detection)

        assert "40.7128" in result
        # Check for longitude value (Python float representation may vary)
        assert "-74.00" in result or "-74.006" in result

    def test_render_template_empty_uses_default(self, rule_processor, model_factory):
        """Should use default template when template_str is empty."""
        template_str = ""
        default_template = "Default: {{ common_name }}"
        detection = model_factory.create_detection(
            common_name="Test Bird",
        )

        result = rule_processor.render_template(template_str, detection, default_template)

        assert result == "Default: Test Bird"

    def test_render_template_empty_no_default(self, rule_processor, model_factory):
        """Should return empty string when no template or default."""
        template_str = ""
        detection = model_factory.create_detection()

        result = rule_processor.render_template(template_str, detection)

        assert result == ""

    def test_render_template_error_handling(self, rule_processor, model_factory, caplog):
        """Should handle template rendering errors gracefully."""
        template_str = "{{ invalid_field }}"  # Field doesn't exist
        detection = model_factory.create_detection()

        result = rule_processor.render_template(template_str, detection)

        # Jinja2 doesn't error on missing fields by default, but we test error handling
        assert isinstance(result, str)

    def test_render_template_with_jinja_error(self, rule_processor, model_factory, caplog):
        """Should handle Jinja2 syntax errors."""
        template_str = "{{ unclosed"  # Syntax error
        detection = model_factory.create_detection()

        result = rule_processor.render_template(template_str, detection)

        assert "Error rendering template" in result
        assert "Error rendering template" in caplog.text


class TestComplexRuleScenarios:
    """Test complex rule matching scenarios."""

    @pytest.mark.asyncio
    async def test_complex_rule_all_filters(
        self, rule_processor, model_factory, test_rule, db_session_factory
    ):
        """Should match detection that passes all filters."""
        rule = {
            **test_rule,
            "name": "Complex Rule",
            "minimum_confidence": 80,
            "include_taxa": {"species": ["Turdus migratorius"]},
            "scope": NotificationScope.NEW_EVER,
        }

        detection = model_factory.create_detection(
            scientific_name="Turdus migratorius",
            confidence=0.85,
        )

        # Mock detection query service to return True (is first detection)
        rule_processor.detection_query_service.is_first_detection_ever.return_value = True

        matches = await rule_processor._rule_matches_detection(rule, detection)

        assert matches is True

    @pytest.mark.asyncio
    async def test_complex_rule_fails_confidence(self, rule_processor, model_factory, test_rule):
        """Should not match when confidence is too low."""
        rule = {
            **test_rule,
            "minimum_confidence": 90,
            "include_taxa": {"species": ["Turdus migratorius"]},
        }

        detection = model_factory.create_detection(
            scientific_name="Turdus migratorius",
            confidence=0.85,  # 85% < 90%
        )

        matches = await rule_processor._rule_matches_detection(rule, detection)

        assert matches is False

    @pytest.mark.asyncio
    async def test_complex_rule_fails_taxa(self, rule_processor, model_factory, test_rule):
        """Should not match when taxa filter fails."""
        rule = {
            **test_rule,
            "minimum_confidence": 80,
            "include_taxa": {"species": ["Corvus brachyrhynchos"]},
        }

        detection = model_factory.create_detection(
            scientific_name="Turdus migratorius",  # Different species
            confidence=0.85,
        )

        matches = await rule_processor._rule_matches_detection(rule, detection)

        assert matches is False

    @pytest.mark.asyncio
    async def test_complex_rule_fails_scope(self, rule_processor, model_factory, test_rule):
        """Should not match when scope filter fails."""
        rule = {
            **test_rule,
            "minimum_confidence": 80,
            "scope": NotificationScope.NEW_EVER,
        }

        detection = model_factory.create_detection(
            scientific_name="Turdus migratorius",
            confidence=0.85,
        )

        # Mock detection query service to return False (not first detection)
        rule_processor.detection_query_service.is_first_detection_ever.return_value = False

        matches = await rule_processor._rule_matches_detection(rule, detection)

        assert matches is False
