"""Marker base for already-sanitized capsule-boundary failures."""

from __future__ import annotations


class ContentFreeCapsuleError(ValueError):
    """A failure whose public text is already constant and content-free."""
