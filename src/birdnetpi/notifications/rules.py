"""Notification rule processing and matching logic.

This module handles matching detections against notification rules,
including taxa filtering, scope checking, and quiet hours validation.
"""

import logging
from datetime import UTC, datetime, time, timedelta
from typing import Any

from jinja2 import Template
from sqlalchemy.ext.asyncio import AsyncSession

from birdnetpi.config.models import BirdNETConfig
from birdnetpi.database.species import SpeciesDatabaseService
from birdnetpi.detections.models import Detection
from birdnetpi.detections.queries import DetectionQueryService
from birdnetpi.notifications.enums import NotificationFrequency, NotificationScope

logger = logging.getLogger(__name__)


class NotificationRuleProcessor:
    """Processes notification rules and matches detections."""

    def __init__(
        self,
        config: BirdNETConfig,
        db_session: AsyncSession,
        species_db_service: SpeciesDatabaseService,
        detection_query_service: DetectionQueryService,
    ) -> None:
        """Initialize rule processor.

        Args:
            config: Application configuration
            db_session: Database session for taxonomy lookups
            species_db_service: Species database service for taxonomy lookups
            detection_query_service: Detection query service for first detection checks
        """
        self.config = config
        self.db_session = db_session
        self.species_db_service = species_db_service
        self.detection_query_service = detection_query_service

    async def find_matching_rules(self, detection: Detection) -> list[dict[str, Any]]:
        """Find all notification rules that match a detection.

        Args:
            detection: Detection to match against rules

        Returns:
            List of matching rule dictionaries
        """
        matching_rules = []

        for rule in self.config.notification_rules:
            if await self._rule_matches_detection(rule, detection):
                matching_rules.append(rule)

        return matching_rules

    async def _rule_matches_detection(self, rule: dict[str, Any], detection: Detection) -> bool:
        """Check if a rule matches a detection.

        Args:
            rule: Notification rule dictionary
            detection: Detection to check

        Returns:
            True if the rule matches, False otherwise
        """
        # Rule must be enabled
        if not rule.get("enabled", False):
            logger.debug("Rule '%s' is disabled", rule.get("name", "unnamed"))
            return False

        # Check frequency - only process immediate notifications here
        frequency = rule.get("frequency", {})
        if frequency.get("when") != NotificationFrequency.IMMEDIATE:
            logger.debug(
                "Rule '%s' is not immediate (frequency: %s)",
                rule.get("name", "unnamed"),
                frequency.get("when"),
            )
            return False

        # Check quiet hours
        if not self._check_quiet_hours():
            logger.debug(
                "Currently in quiet hours, skipping rule '%s'", rule.get("name", "unnamed")
            )
            return False

        # Check minimum confidence
        minimum_confidence = rule.get("minimum_confidence", 0)
        detection_confidence_pct = detection.confidence * 100
        if minimum_confidence > 0 and detection_confidence_pct < minimum_confidence:
            logger.debug(
                "Detection confidence %.1f%% below minimum %.1f%% for rule '%s'",
                detection_confidence_pct,
                minimum_confidence,
                rule.get("name", "unnamed"),
            )
            return False

        # Check taxa filters
        if not await self._check_taxa_filters(rule, detection):
            logger.debug(
                "Detection does not match taxa filters for rule '%s'", rule.get("name", "unnamed")
            )
            return False

        # Check scope
        if not await self._check_scope(rule, detection):
            logger.debug(
                "Detection does not match scope filter for rule '%s'", rule.get("name", "unnamed")
            )
            return False

        logger.debug("Rule '%s' matches detection", rule.get("name", "unnamed"))
        return True

    def _check_quiet_hours(self) -> bool:
        """Check if current time is within quiet hours.

        Returns:
            True if notifications are allowed (not in quiet hours), False otherwise
        """
        start_str = self.config.notify_quiet_hours_start
        end_str = self.config.notify_quiet_hours_end

        # No quiet hours configured
        if not start_str or not end_str:
            return True

        try:
            # Parse quiet hours
            start_time = time.fromisoformat(start_str)
            end_time = time.fromisoformat(end_str)
            current_time = datetime.now(UTC).time()

            # Handle overnight quiet hours (e.g., 22:00 to 08:00)
            if start_time <= end_time:
                # Same day range (e.g., 08:00 to 22:00)
                in_quiet_hours = start_time <= current_time <= end_time
            else:
                # Overnight range (e.g., 22:00 to 08:00)
                in_quiet_hours = current_time >= start_time or current_time <= end_time

            # Return True if NOT in quiet hours
            return not in_quiet_hours

        except ValueError as e:
            logger.warning("Invalid quiet hours format: %s", e)
            return True  # Allow notifications if config is invalid

    async def _check_taxa_filters(self, rule: dict[str, Any], detection: Detection) -> bool:
        """Check if detection matches taxa include/exclude filters.

        Args:
            rule: Notification rule with include_taxa and exclude_taxa
            detection: Detection to check

        Returns:
            True if detection passes taxa filters, False otherwise
        """
        include_taxa = rule.get("include_taxa", {})
        exclude_taxa = rule.get("exclude_taxa", {})

        # If no filters specified, allow all
        if not include_taxa and not exclude_taxa:
            return True

        # Get detection's scientific name
        scientific_name = detection.scientific_name

        # Check exclude filters first (they take precedence)
        if exclude_taxa:
            if await self._matches_taxa_filter(exclude_taxa, scientific_name):
                logger.debug("Detection excluded by taxa filter: %s", scientific_name)
                return False

        # Check include filters
        if include_taxa:
            if not await self._matches_taxa_filter(include_taxa, scientific_name):
                logger.debug("Detection not included by taxa filter: %s", scientific_name)
                return False

        return True

    async def _matches_taxa_filter(
        self, taxa_filter: dict[str, list[str]], scientific_name: str
    ) -> bool:
        """Check if a scientific name matches a taxa filter.

        Args:
            taxa_filter: Dictionary with "species", "genera", "families", "orders" lists
            scientific_name: Scientific name to check

        Returns:
            True if the scientific name matches any filter, False otherwise
        """
        # Check species match (exact match)
        species_list = taxa_filter.get("species", [])
        if scientific_name in species_list:
            return True

        # Check genus match (first word of scientific name)
        genera_list = taxa_filter.get("genera", [])
        if genera_list:
            genus = scientific_name.split()[0] if scientific_name else ""
            if genus in genera_list:
                return True

        # For family and order, we'd need to query the IOC database
        families_list = taxa_filter.get("families", [])
        orders_list = taxa_filter.get("orders", [])

        if families_list or orders_list:
            # Query IOC database for taxonomy
            taxonomy = await self.species_db_service.get_species_taxonomy(
                self.db_session, scientific_name
            )
            if taxonomy:
                if families_list and taxonomy.get("family") in families_list:
                    return True
                if orders_list and taxonomy.get("order") in orders_list:
                    return True

        return False

    async def _check_scope(self, rule: dict[str, Any], detection: Detection) -> bool:
        """Check if detection matches the rule's scope filter.

        Delegates to DetectionQueryService for window function queries.

        Args:
            rule: Notification rule with scope setting
            detection: Detection to check

        Returns:
            True if detection matches scope, False otherwise
        """
        scope = rule.get("scope", NotificationScope.ALL)

        if scope == NotificationScope.ALL:
            return True

        # Delegate to DetectionQueryService for first detection checks
        scientific_name = detection.scientific_name
        detection_id = str(detection.id)

        if scope == NotificationScope.NEW_EVER:
            return await self.detection_query_service.is_first_detection_ever(
                detection_id, scientific_name
            )

        elif scope == NotificationScope.NEW_TODAY:
            now = datetime.now(UTC)
            start_of_day = datetime.combine(now.date(), time.min, tzinfo=UTC)
            return await self.detection_query_service.is_first_detection_in_period(
                detection_id, scientific_name, start_of_day
            )

        elif scope == NotificationScope.NEW_THIS_WEEK:
            now = datetime.now(UTC)
            start_of_week = datetime.combine(
                now.date() - timedelta(days=now.weekday()),
                time.min,
                tzinfo=UTC,
            )
            return await self.detection_query_service.is_first_detection_in_period(
                detection_id, scientific_name, start_of_week
            )

        logger.warning("Unknown scope type: %s", scope)
        return False

    def render_template(
        self,
        template_str: str,
        detection: Detection,
        default_template: str | None = None,
    ) -> str:
        """Render a Jinja2 template with detection context.

        Args:
            template_str: Template string to render (empty string uses default)
            detection: Detection object for template context
            default_template: Default template if template_str is empty

        Returns:
            Rendered template string
        """
        # Use default if template is empty
        if not template_str and default_template:
            template_str = default_template

        if not template_str:
            return ""

        try:
            template = Template(template_str)

            # Build template context
            context = {
                "common_name": detection.common_name,
                "scientific_name": detection.scientific_name,
                "confidence": f"{detection.confidence * 100:.1f}",
                "confidence_pct": f"{detection.confidence * 100:.1f}%",
                "timestamp": detection.timestamp.isoformat() if detection.timestamp else "",
                "date": detection.timestamp.strftime("%Y-%m-%d") if detection.timestamp else "",
                "time": detection.timestamp.strftime("%H:%M:%S") if detection.timestamp else "",
                "latitude": detection.latitude,
                "longitude": detection.longitude,
            }

            return template.render(**context)

        except Exception as e:
            logger.error("Error rendering template: %s", e)
            return f"Error rendering template: {e}"
