"""Technique & Gymkhana Library — service layer (feature 018).

Public surface re-exported from sub-modules so callers can use either:

    from app.services.technique import catalog
    from app.services.technique.catalog import list_exercises, get_exercise

Sub-modules
-----------
catalog
    Read-only catalog queries: list/filter exercises, skills, materials.
    No write operations; curation and session assembly live in separate modules.
"""
from app.services.technique import catalog

__all__ = ["catalog"]
