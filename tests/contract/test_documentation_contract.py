"""Public and maintainer-facing claims that must track the deployed API."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_oversight_limits_and_storage_are_route_specific() -> None:
    readme = read("README.md")
    client = read("src/nope_net/client.py")
    client_prose = " ".join(client.split())

    assert "request body is capped at 5 MB" in readme
    assert "request body is capped at 512 KB" not in readme
    assert "5 MB, so a batch near the count limit" in client_prose
    assert "Synchronous; nothing is stored" not in client
    assert "does not write conversation content or full results" in client_prose


def test_urgent_is_documented_as_ranking() -> None:
    client = read("src/nope_net/client.py")
    types = read("src/nope_net/types.py")

    assert "urgent: Only 24/7 resources" not in client
    assert "Only return 24/7 urgent resources" not in types
    assert "24/7 resources first among ties" in client
    assert "Ranking hint" in types


def test_deployed_ticket_references_are_absent_from_fixture_docs() -> None:
    assert "API fix A-" not in read("tests/fixtures/README.md")
    assert "The last published version is 2.3.0" not in read("CHANGELOG.md")


def test_webhook_delivery_test_describes_distinct_ids() -> None:
    source = read("tests/unit/test_webhook_delivery_id.py")
    assert "sends the payload's event_id as X-NOPE-Delivery-ID" not in source
    assert "stored delivery id as X-NOPE-Delivery-ID" in source


def test_package_metadata_marks_the_beta_status_honestly() -> None:
    project = read("pyproject.toml")
    assert "Development Status :: 4 - Beta" in project
    assert "Development Status :: 5 - Production/Stable" not in project
