"""Signpost: signatures that match the docs, typed search rows, detect_country, deprecations."""

import warnings
from typing import get_args

import pytest
from pydantic import ValidationError

import nope_net
from nope_net import (
    POPULATIONS,
    SERVICE_SCOPES,
    CrisisResource,
    DetectCountryResponse,
    OpenStatus,
    Population,
    ResourcesConfig,
    ResourcesResponse,
    ServiceScope,
    SignpostByIdResponse,
    SignpostConfig,
    SignpostCountriesResponse,
    SignpostResponse,
    SignpostSearchContact,
    SignpostSearchResponse,
    SignpostSearchResult,
    SignpostSmartConfig,
    SignpostSmartResponse,
)
from tests.conftest import ClientFactory, FakeApi, load_fixture


class TestGeneratedVocabularies:
    def test_counts(self) -> None:
        assert len(SERVICE_SCOPES) == 93
        assert len(get_args(ServiceScope)) == 93
        assert len(POPULATIONS) == 26
        assert len(get_args(Population)) == 26

    def test_documented_examples_are_valid(self) -> None:
        assert "suicide" in SERVICE_SCOPES
        assert "domestic_violence" in SERVICE_SCOPES
        assert "suicide_prevention" not in SERVICE_SCOPES
        assert "youth" in POPULATIONS

    def test_no_invalid_scope_examples_in_docstrings(self) -> None:
        import inspect

        source = inspect.getsource(nope_net.client)
        assert "suicide_prevention" not in source


class TestSignpostBasic:
    async def test_top_level_filters(self, api: FakeApi, make: ClientFactory) -> None:
        api.add("GET", "/v1/signpost", json_body=load_fixture("signpost/auth.gb.json"))
        client = make(api_key="k")
        result = await client.call(
            "signpost",
            "gb",
            scopes=["suicide", "crisis"],
            populations=["youth"],
            subdivisions=["GB-NIR", "GB-SCT"],
            limit=3,
            urgent=True,
        )
        await client.close()

        assert api.last_request.url.path == "/v1/signpost"
        assert dict(api.last_request.url.params) == {
            "country": "GB",
            "scopes": "suicide,crisis",
            "populations": "youth",
            "subdivisions": "GB-NIR,GB-SCT",
            "limit": "3",
            "urgent": "true",
        }
        assert isinstance(result, SignpostResponse)
        assert result.country == "GB"
        assert result.count == 3
        assert isinstance(result.resources[0], CrisisResource)
        assert result.resources[0].name == "Samaritans"

    async def test_config_form(self, api: FakeApi, make: ClientFactory) -> None:
        api.add("GET", "/v1/signpost", json_body=load_fixture("signpost/auth.gb.json"))
        client = make(api_key="k")
        await client.call(
            "signpost",
            country="US",
            config=SignpostConfig(scopes=["suicide"], limit=5, urgent=False),
        )
        await client.close()

        assert dict(api.last_request.url.params) == {
            "country": "US",
            "scopes": "suicide",
            "limit": "5",
        }

    async def test_top_level_wins_over_config(self, api: FakeApi, make: ClientFactory) -> None:
        api.add("GET", "/v1/signpost", json_body=load_fixture("signpost/auth.gb.json"))
        client = make(api_key="k")
        await client.call(
            "signpost",
            "US",
            config={"scopes": ["crisis"], "limit": 2, "urgent": True},
            scopes=["suicide"],
            limit=9,
        )
        await client.close()

        assert dict(api.last_request.url.params) == {
            "country": "US",
            "scopes": "suicide",
            "limit": "9",
            "urgent": "true",
        }

    async def test_readme_example_shape_runs(self, api: FakeApi, make: ClientFactory) -> None:
        api.add("GET", "/v1/signpost", json_body=load_fixture("signpost/auth.gb.json"))
        client = make(api_key="k")
        result = await client.call("signpost", country="US", scopes=["suicide"], urgent=True)
        await client.close()

        assert result.resources[0].phone == "116 123"

    async def test_not_available_in_demo(self, make: ClientFactory) -> None:
        client = make(demo=True)
        with pytest.raises(ValueError, match="not available in demo mode"):
            await client.call("signpost", "US")
        await client.close()

    def test_config_fields(self) -> None:
        assert set(SignpostConfig.model_fields) == {
            "scopes",
            "populations",
            "subdivisions",
            "limit",
            "urgent",
        }
        with pytest.raises(ValidationError, match="scopes"):
            SignpostConfig(scopes=["suicide_prevention"])
        assert ResourcesConfig is SignpostConfig


class TestSignpostSmart:
    async def test_authenticated(self, api: FakeApi, make: ClientFactory) -> None:
        api.add("GET", "/v1/signpost/smart", json_body=load_fixture("signpost/try.smart.json"))
        client = make(api_key="k")
        result = await client.call(
            "signpost_smart",
            "us",
            "teen eating disorder",
            config=SignpostSmartConfig(scopes=["eating_disorder"], populations=["youth"], limit=3),
        )
        await client.close()

        assert api.last_request.url.path == "/v1/signpost/smart"
        assert dict(api.last_request.url.params) == {
            "country": "US",
            "query": "teen eating disorder",
            "scopes": "eating_disorder",
            "populations": "youth",
            "limit": "3",
        }
        assert isinstance(result, SignpostSmartResponse)
        assert result.ranked[0].rank == 1
        assert result.ranked[0].resource.name == "ANAD Eating Disorders Helpline"
        assert result.ranked[0].why.startswith("Directly addresses")

    async def test_demo_routes_to_try(self, api: FakeApi, make: ClientFactory) -> None:
        api.add("GET", "/v1/try/signpost/smart", json_body=load_fixture("signpost/try.smart.json"))
        client = make(demo=True)
        result = await client.call("signpost_smart", country="US", query="teen eating disorder")
        await client.close()

        assert api.last_request.url.path == "/v1/try/signpost/smart"
        assert result.try_endpoint is True
        assert result.message is None

    def test_empty_pool_message(self) -> None:
        body = {
            "country": "AQ",
            "query": "help",
            "ranked": [],
            "count": 0,
            "message": "No resources found for this country",
        }
        result = SignpostSmartResponse.model_validate(body)
        assert result.message == "No resources found for this country"
        assert result.model_dump(mode="json", exclude_unset=True) == body

    def test_smart_config_has_no_urgent(self) -> None:
        assert set(SignpostSmartConfig.model_fields) == {"scopes", "populations", "limit"}


class TestSignpostSearch:
    def test_explicit_row_model(self) -> None:
        result = SignpostSearchResponse.model_validate(load_fixture("signpost/search.auth.json"))
        row = result.results[0]

        assert isinstance(row, SignpostSearchResult)
        assert not isinstance(row, CrisisResource)
        assert row.id == "80dcd17e-504a-48f3-b28b-40d204eec38d"
        assert row.name_local is None
        assert row.subdivision_code is None
        assert row.country_code == "GB"
        assert row.service_scopes[0] == "lgbtq"
        assert row.populations == ["lgbtq", "transgender"]
        assert row.resource_type == "support_service"
        assert row.type == "support_service"
        assert isinstance(row.contacts[0], SignpostSearchContact)
        assert row.contacts[0].tier == "1"
        assert row.contacts[0].value == "0345 3 30 30 30"
        assert row.is_24_7 is False
        assert row.similarity == pytest.approx(0.560408288549103)
        assert isinstance(row.open_status, OpenStatus)
        assert row.open_status.next_change == "2026-09-03T16:00:00.000Z"
        assert result.country == "GB"
        for name in ("resource_kind", "service_scope", "population_served", "priority_tier"):
            assert name not in SignpostSearchResult.model_fields, name

    def test_country_may_be_null(self) -> None:
        body = load_fixture("signpost/search.auth.json")
        body["country"] = None
        assert SignpostSearchResponse.model_validate(body).country is None


class TestSignpostSearchGuards:
    async def test_not_available_in_demo(self, make: ClientFactory) -> None:
        client = make(demo=True)
        with pytest.raises(ValueError, match="not available in demo mode"):
            await client.call("signpost_search", query="x")
        await client.close()


class TestSignpostByIdAndCountries:
    async def test_by_id(self, api: FakeApi, make: ClientFactory) -> None:
        resource = load_fixture("signpost/auth.gb.json")["resources"][0]
        api.add("GET", "/v1/signpost/abc-123", json_body={"resource": resource})
        client = make()
        result = await client.call("signpost_by_id", "abc-123")
        await client.close()

        assert isinstance(result, SignpostByIdResponse)
        assert result.resource.name == "Samaritans"

    async def test_countries(self, api: FakeApi, make: ClientFactory) -> None:
        api.add("GET", "/v1/signpost/countries", json_body=load_fixture("signpost/countries.json"))
        client = make()
        result = await client.call("signpost_countries")
        await client.close()

        assert isinstance(result, SignpostCountriesResponse)
        assert "US" in result.countries
        assert result.count == 224


class TestDetectCountry:
    async def test_miss_shape(self, api: FakeApi, make: ClientFactory) -> None:
        api.add(
            "GET",
            "/v1/signpost/detect-country",
            json_body=load_fixture("signpost/detect-country.miss.json"),
        )
        client = make()
        result = await client.call("detect_country")
        await client.close()

        assert isinstance(result, DetectCountryResponse)
        assert result.detected is False
        assert result.country_code == ""
        assert result.error == "Could not detect country from headers"
        assert "x-country" not in api.last_request.headers

    async def test_hint_sends_x_country(self, api: FakeApi, make: ClientFactory) -> None:
        body = {
            "country_code": "GB",
            "country_name": "United Kingdom",
            "subdivision_code": "GB-SCT",
            "subdivision_name": "Scotland",
        }
        api.add("GET", "/v1/signpost/detect-country", json_body=body)
        client = make()
        result = await client.call("detect_country", country_hint="gb")
        await client.close()

        assert api.last_request.headers["x-country"] == "GB"
        assert result.detected is True
        assert result.subdivision_code == "GB-SCT"
        assert result.subdivision_name == "Scotland"
        assert result.model_dump(mode="json", exclude_unset=True) == body


class TestDeprecatedResources:
    async def test_resources_warns_with_sunset(self, api: FakeApi, make: ClientFactory) -> None:
        api.add("GET", "/v1/resources", json_body=load_fixture("signpost/auth.gb.json"))
        client = make(api_key="k")
        with pytest.warns(DeprecationWarning) as record:
            result = await client.call("resources", "GB", scopes=["suicide"])
        await client.close()

        message = str(record[0].message)
        assert "sunset 2027-01-01" in message
        assert "use signpost()" in message
        assert api.last_request.url.path == "/v1/resources"
        assert dict(api.last_request.url.params) == {"country": "GB", "scopes": "suicide"}
        assert isinstance(result, ResourcesResponse)
        assert ResourcesResponse is SignpostResponse

    @pytest.mark.parametrize(
        ("method", "path", "fixture", "args"),
        [
            ("resources_smart", "/v1/resources/smart", "signpost/try.smart.json", ("US", "q")),
            ("resource_by_id", "/v1/resources/abc", "signpost/auth.gb.json", ("abc",)),
            ("resources_countries", "/v1/resources/countries", "signpost/countries.json", ()),
        ],
    )
    async def test_other_deprecated_methods(
        self,
        api: FakeApi,
        make: ClientFactory,
        method: str,
        path: str,
        fixture: str,
        args: tuple,
    ) -> None:
        body = load_fixture(fixture)
        if method == "resource_by_id":
            body = {"resource": body["resources"][0]}
        api.add("GET", path, json_body=body)
        client = make(api_key="k")
        with pytest.warns(DeprecationWarning, match="sunset 2027-01-01"):
            await client.call(method, *args)
        await client.close()

        assert api.last_request.url.path == path

    async def test_warning_text_identical_across_clients(self, api: FakeApi) -> None:
        from tests.conftest import make_client

        api.add("GET", "/v1/resources", json_body=load_fixture("signpost/auth.gb.json"))
        api.add("GET", "/v1/resources/smart", json_body=load_fixture("signpost/try.smart.json"))
        api.add(
            "GET",
            "/v1/resources/abc",
            json_body={"resource": load_fixture("signpost/auth.gb.json")["resources"][0]},
        )
        api.add("GET", "/v1/resources/countries", json_body=load_fixture("signpost/countries.json"))
        texts = {}
        for kind in ("sync", "async"):
            client = make_client(kind, api, api_key="k")
            with pytest.warns(DeprecationWarning) as record:
                await client.call("resources", "GB")
                await client.call("resources_smart", "US", "q")
                await client.call("resource_by_id", "abc")
                await client.call("resources_countries")
            await client.close()
            texts[kind] = [str(w.message) for w in record]

        assert texts["sync"] == texts["async"]
        assert len(texts["sync"]) == 4
        assert all("sunset 2027-01-01" in t and "use signpost" in t for t in texts["sync"])

    async def test_demo_smart_deprecated_route(self, api: FakeApi, make: ClientFactory) -> None:
        api.add("GET", "/v1/try/resources/smart", json_body=load_fixture("signpost/try.smart.json"))
        client = make(demo=True)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            await client.call("resources_smart", country="US", query="q")
        await client.close()

        assert api.last_request.url.path == "/v1/try/resources/smart"


def test_detect_country_repr_shows_detected() -> None:
    """detected is a property, so pydantic's default repr and str omit it."""
    miss = DetectCountryResponse.model_validate(load_fixture("signpost/detect-country.miss.json"))
    assert "detected=False" in repr(miss)
    assert "detected=False" in str(miss)

    hit = DetectCountryResponse(country_code="GB", country_name="United Kingdom")
    assert "detected=True" in repr(hit)
    assert "country_code='GB'" in repr(hit)
    assert "detected" not in hit.model_dump()
    assert "detected" not in DetectCountryResponse.model_fields
