"""Shared table list for subset-harness sqlite engines.

Every test file that builds an in-memory sqlite engine with an explicit
``Base.metadata.create_all(..., tables=[...])`` subset must include these
tables, since audited writes, multi-coach session assignment, athlete
archiving (soft-delete) and user deactivation/deletion now touch them
regardless of the domain under test. See
specs/041-multi-coach-governance/contracts/audit-recording.md §8.

Trampa conocida: ``Base.metadata.create_all(..., tables=[...])`` no deduplica la
lista que recibe, así que un nombre repetido produce ``OperationalError: table
<x> already exists`` y tumba el módulo de pruebas entero. Por eso ningún archivo
debe listar de forma literal un nombre que ya venga en ``AUDIT_TABLES``: se
incluye la constante con ``*AUDIT_TABLES`` y nada más.
"""

AUDIT_TABLES = [
    "audit_log",
    "training_session_coaches",
    "privacy_policies",
    "parent_invites",
]
