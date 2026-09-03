"""Contract tests: every sanitized live fixture parses into its SDK model and round-trips.

Each fixture under ``tests/fixtures/`` (except ``webhooks/``, ``headers/`` and the
README) is mapped to the public model that the client returns for that call. The
model must ``model_validate`` the body with no cast and ``model_dump`` it back to an
equal dict, so a typed-but-never-emitted field or a required-but-absent field fails
here before it reaches a customer.

Error bodies are mapped to the exception class the shared parser must build.

Model names are resolved lazily through ``getattr(nope_net, name)`` so a missing
model fails its own row instead of breaking collection.
"""

import json
from pathlib import Path
from typing import Any, Dict, Tuple

import pytest

import nope_net
from tests.conftest import FIXTURES_DIR, load_fixture

# fixture path -> public model name on the nope_net package
FIXTURE_MODELS: Dict[str, str] = {
    "evaluate/auth.benign.json": "EvaluateResponse",
    "evaluate/try.gb.json": "EvaluateResponse",
    "evaluate/try.us.json": "EvaluateResponse",
    "oversight/auth.fast.json": "OversightAnalyzeResponse",
    "oversight/try.fast.json": "OversightDemoAnalyzeResponse",
    "oversight/try.full.json": "OversightDemoAnalyzeResponse",
    "ocular/auth.json": "OcularResponse",
    "ocular/try.json": "OcularDemoResponse",
    "signpost/auth.gb.json": "SignpostResponse",
    "signpost/countries.json": "SignpostCountriesResponse",
    "signpost/detect-country.miss.json": "DetectCountryResponse",
    "signpost/search.auth.json": "SignpostSearchResponse",
    "signpost/try.smart.json": "SignpostSmartResponse",
    "billing/balance.json": "BillingBalanceResponse",
    "billing/pricing.json": "BillingPricingResponse",
    "billing/usage.json": "BillingUsageResponse",
}

# fixture path -> (HTTP status, exception class name, expected `details` subset)
ERROR_FIXTURES: Dict[str, Tuple[int, str, Dict[str, Any]]] = {
    "errors/400.evaluate-empty.json": (400, "NopeValidationError", {}),
    "errors/400.evaluate-role.json": (400, "NopeValidationError", {}),
    "errors/400.signpost-scope.json": (
        400,
        "NopeValidationError",
        {
            "invalid_scopes": ["suicide_prevention"],
            "hint": "See docs.nope.net for valid scope values",
        },
    ),
    "errors/401.missing-auth.json": (401, "NopeAuthError", {}),
    "errors/404.signpost-id.json": (404, "NopeNotFoundError", {}),
    "errors/413.payload-too-large.json": (413, "NopeValidationError", {"max_bytes": 524288}),
}

EXCLUDED_PREFIXES = ("webhooks/", "headers/")


def _all_fixture_paths() -> Tuple[str, ...]:
    paths = []
    for path in sorted(FIXTURES_DIR.rglob("*")):
        if not path.is_file() or path.name == "README.md":
            continue
        rel = path.relative_to(FIXTURES_DIR).as_posix()
        if rel.startswith(EXCLUDED_PREFIXES):
            continue
        paths.append(rel)
    return tuple(paths)


def test_every_fixture_is_mapped() -> None:
    mapped = set(FIXTURE_MODELS) | set(ERROR_FIXTURES)
    on_disk = set(_all_fixture_paths())
    assert on_disk - mapped == set(), "fixtures without a contract mapping"
    assert mapped - on_disk == set(), "mappings without a fixture file"


@pytest.mark.parametrize("relative_path", sorted(FIXTURE_MODELS))
def test_fixture_round_trips_through_model(relative_path: str) -> None:
    model_name = FIXTURE_MODELS[relative_path]
    model = getattr(nope_net, model_name)
    data = load_fixture(relative_path)

    parsed = model.model_validate(data)
    dumped = parsed.model_dump(mode="json", exclude_unset=True)

    assert dumped == data


@pytest.mark.parametrize("relative_path", sorted(ERROR_FIXTURES))
def test_error_fixture_maps_to_exception(relative_path: str) -> None:
    status, class_name, expected_details = ERROR_FIXTURES[relative_path]
    body = load_fixture(relative_path)
    raw = json.dumps(body)

    from nope_net._http import build_error

    err = build_error(status, {}, raw)

    assert isinstance(err, getattr(nope_net, class_name))
    assert err.status_code == status
    assert err.response_body == raw
    assert err.message == body.get("message", body.get("error"))
    if body.get("error", "").isidentifier():
        assert err.code == body["error"]
    for key, value in expected_details.items():
        assert err.details[key] == value


def test_fixture_dir_exists() -> None:
    assert Path(FIXTURES_DIR).is_dir()
