"""Isolated, opt-in source collectors for Part 2 integration.

Importing this package performs no network, database, environment-file, or
dependency-install work. Each collector is an explicit call to its adapter.
"""

__all__ = ["contracts", "catalog", "runtime", "normalize"]
