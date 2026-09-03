"""Generated enums: counts pinned to the API taxonomy the audit measured."""

from typing import get_args

from nope_net import (
    OVERSIGHT_BEHAVIOR_CATEGORIES,
    OVERSIGHT_BEHAVIOR_CODES,
    OVERSIGHT_BEHAVIOR_CODES_BY_CATEGORY,
    OversightBehaviorCategory,
    OversightBehaviorCode,
)


def test_behavior_code_count() -> None:
    assert len(OVERSIGHT_BEHAVIOR_CODES) == 91
    assert len(get_args(OversightBehaviorCode)) == 91
    assert len(set(OVERSIGHT_BEHAVIOR_CODES)) == 91


def test_behavior_category_count() -> None:
    assert len(OVERSIGHT_BEHAVIOR_CATEGORIES) == 14
    assert len(get_args(OversightBehaviorCategory)) == 14


def test_categories_partition_codes() -> None:
    flattened = [c for group in OVERSIGHT_BEHAVIOR_CODES_BY_CATEGORY.values() for c in group]
    assert tuple(flattened) == OVERSIGHT_BEHAVIOR_CODES
    assert tuple(OVERSIGHT_BEHAVIOR_CODES_BY_CATEGORY) == OVERSIGHT_BEHAVIOR_CATEGORIES


def test_known_members() -> None:
    assert "validation_of_suicidal_ideation" in OVERSIGHT_BEHAVIOR_CODES
    assert "appropriate_ai_disclosure" in OVERSIGHT_BEHAVIOR_CODES
    assert OVERSIGHT_BEHAVIOR_CODES_BY_CATEGORY["crisis_response"][0] == (
        "validation_of_suicidal_ideation"
    )
    assert "appropriate_behaviors" in OVERSIGHT_BEHAVIOR_CATEGORIES
