"""Service package for Structured Interval Training (feature 026).

Owns the pure domain logic (block flattening + guardrail validations) and the
transaction-owning CRUD for ``IntervalStructure``. Templates, matching and the
instructivo PDF live in sibling modules of this package and reuse the pure
helpers exported here (``flatten_blocks``, ``validate_structure_blocks``,
``total_planned_duration_s``).
"""
