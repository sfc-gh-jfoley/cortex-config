"""Data profiles for synthetic data generation guidance.

Provides built-in YAML profiles that guide the data-engineering agent
toward semantically meaningful seed data instead of generic UNIFORM() expressions.
"""

from specbuilder.src.data_profiles.loader import (
    list_profiles,
    load_profile,
    translate_to_sql_hints,
    validate_profile,
)

__all__ = [
    "load_profile",
    "list_profiles",
    "validate_profile",
    "translate_to_sql_hints",
]
