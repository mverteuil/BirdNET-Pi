"""General utility helper functions."""

from typing import TypeVar

T = TypeVar("T")


def prefer(new_value: T | None, fallback: T) -> T:
    """Return new_value if not None, otherwise return fallback.

    Useful for merging optional form fields with current config values.

    Args:
        new_value: The potentially updated value
        fallback: The fallback value to use if new_value is None

    Returns:
        new_value if it's not None, otherwise fallback

    Example:
        >>> prefer("updated", "original")
        'updated'
        >>> prefer(None, "original")
        'original'
        >>> prefer(False, True)  # Works with falsy values
        False
    """
    return new_value if new_value is not None else fallback
