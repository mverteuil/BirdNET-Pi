"""Enums for notification system configuration."""

from enum import Enum


class NotificationService(str, Enum):
    """Available notification services."""

    APPRISE = "apprise"
    WEBHOOK = "webhook"
    MQTT = "mqtt"


class NotificationFrequency(str, Enum):
    """When to send notifications."""

    IMMEDIATE = "immediate"
    DAILY = "daily"
    WEEKLY = "weekly"


class NotificationScope(str, Enum):
    """What detections to include in notifications."""

    ALL = "all"  # Every detection
    NEW_EVER = "new_ever"  # First time ever seeing this species
    NEW_TODAY = "new_today"  # First detection of species today
    NEW_THIS_WEEK = "new_this_week"  # First detection of species this week


class TaxonomicLevel(str, Enum):
    """Taxonomic hierarchy levels for filtering."""

    ORDER = "order"
    FAMILY = "family"
    GENUS = "genus"
    SPECIES = "species"


class WeekDay(str, Enum):
    """Days of the week for scheduling."""

    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"
