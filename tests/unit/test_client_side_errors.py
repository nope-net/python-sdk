"""Client-side validation and demo refusals raise ``NopeValidationError``.

Every case fails before a request is built, so the fake API never sees a
call. The error is also a ``ValueError`` (the 4.0.0 docstrings promised one),
carries ``status_code None`` and a machine ``code``: ``invalid_request`` for
input validation, ``not_available_in_demo`` for a demo client calling a
method that has no ``/v1/try/*`` route. Both client flavours run every row.
"""

import warnings
from typing import Any, Dict, List, Tuple

import pytest

from nope_net import NopeError, NopeValidationError
from tests.conftest import ClientFactory, FakeApi

MESSAGE = {"role": "user", "content": "x"}
SYSTEM = {"role": "system", "content": "x"}
CONVERSATION = {"conversation_id": "c1", "messages": [MESSAGE]}

Case = Tuple[str, Tuple[Any, ...], Dict[str, Any], str]

VALIDATION_CASES: List[Case] = [
    ("evaluate", (), {"messages": []}, "'messages' cannot be empty"),
    ("evaluate", (), {}, "Either 'messages' or 'text' must be provided"),
    (
        "evaluate",
        (),
        {"messages": [MESSAGE], "text": "x"},
        "Only one of 'messages' or 'text' can be provided",
    ),
    (
        "evaluate",
        (),
        {"messages": [SYSTEM]},
        "Message 0: role must be 'user' or 'assistant', got 'system'",
    ),
    (
        "evaluate",
        (),
        {"messages": [{"role": "user", "content": 1}]},
        "Message 0: content must be a string",
    ),
    ("evaluate", (), {"messages": [MESSAGE] * 101}, "Too many messages: 101. Maximum allowed: 100"),
    ("screen", (), {"messages": []}, "'messages' cannot be empty"),
    ("screen", (), {}, "Either 'messages' or 'text' must be provided"),
    ("ocular", (), {"messages": []}, "'messages' cannot be empty"),
    (
        "ocular",
        (),
        {"messages": [SYSTEM]},
        "Message 0: role must be 'user' or 'assistant', got 'system'",
    ),
    (
        "ocular",
        (),
        {"messages": [MESSAGE], "trajectory_stride": 0},
        "trajectory_stride must be between 1 and 64",
    ),
    ("ocular", (), {"messages": [MESSAGE], "user_id": ""}, "user_id must be 1 to 256 characters"),
    ("oversight_analyze", ({"conversation_id": "c1"},), {}, '"conversation.messages" is required'),
    ("oversight_analyze", ({"messages": "no"},), {}, '"conversation.messages" must be a list'),
    ("oversight_analyze", ({"messages": []},), {}, '"conversation.messages" cannot be empty'),
    (
        "oversight_analyze",
        ({"messages": [{"role": "bot", "content": "x"}]},),
        {},
        "conversation: message 0 role must be 'user', 'assistant' or 'system'",
    ),
    (
        "oversight_analyze",
        (CONVERSATION,),
        {"behaviors": {"enabled": ["a"], "disabled": ["b"]}},
        '"behaviors.enabled" and "behaviors.disabled" are mutually exclusive',
    ),
    (
        "oversight_analyze",
        (CONVERSATION,),
        {"behaviors": {"min_severity": "severe"}},
        '"behaviors.min_severity" must be one of: low, medium, high, critical',
    ),
    ("oversight_ingest", (), {"conversations": []}, '"conversations" cannot be empty'),
    (
        "oversight_ingest",
        (),
        {"conversations": [CONVERSATION] * 301},
        "Too many conversations: 301. Maximum allowed: 300",
    ),
    (
        "oversight_ingest",
        (),
        {"conversations": [{"messages": [MESSAGE]}]},
        'Conversation at index 0 must have a "conversation_id"',
    ),
    (
        "oversight_ingest",
        (),
        {"conversations": [{"conversation_id": "c1", "messages": []}]},
        'Conversation "c1" must have non-empty "messages"',
    ),
    ("signpost_smart", ("US", ""), {}, "'query' is required"),
    ("signpost_search", (), {"query": ""}, "'query' is required"),
    ("webhooks.create", ("",), {}, "'url' is required"),
]

DEMO_CASES: List[Case] = [
    (
        "screen",
        (),
        {"text": "x"},
        "screen() is not available in demo mode. Use evaluate(), which routes to /v1/try/evaluate.",
    ),
    (
        "oversight_ingest",
        (),
        {"conversations": [CONVERSATION]},
        "Oversight ingest is not available in demo mode. Use an API key.",
    ),
    ("signpost", ("GB",), {}, "signpost() is not available in demo mode. Use an API key."),
    (
        "signpost_search",
        (),
        {"query": "q"},
        "signpost_search() is not available in demo mode. Use an API key.",
    ),
    ("webhooks.create", ("https://x.example/h",), {}, "webhooks.create() is not available"),
    ("webhooks.list", (), {}, "webhooks.list() is not available"),
    ("webhooks.get", ("wh_1",), {}, "webhooks.get() is not available"),
    ("webhooks.update", ("wh_1", {"enabled": False}), {}, "webhooks.update() is not available"),
    ("webhooks.delete", ("wh_1",), {}, "webhooks.delete() is not available"),
    ("webhooks.regenerate_secret", ("wh_1",), {}, "webhooks.regenerate_secret() is not available"),
    ("webhooks.test", ("wh_1",), {}, "webhooks.test() is not available"),
    ("webhooks.events", (), {}, "webhooks.events() is not available"),
    ("billing.balance", (), {}, "billing.balance() is not available"),
    ("billing.usage", (), {}, "billing.usage() is not available"),
    ("billing.usage_history", (), {}, "billing.usage_history() is not available"),
    ("billing.topup", (1000,), {}, "billing.topup() is not available"),
]

DEMO_SUFFIX = " in demo mode. Use an API key."


def _ids(cases: List[Case]) -> List[str]:
    return [f"{method}:{message[:28]}" for method, _, _, message in cases]


def _assert_client_side(err: NopeValidationError, code: str, message: str) -> None:
    assert isinstance(err, NopeError)
    assert isinstance(err, ValueError)
    assert err.code == code
    assert err.status_code is None
    assert err.message == message
    assert err.details == {}
    assert err.response_body is None
    assert message in str(err)


@pytest.mark.parametrize(
    ("method", "args", "kwargs", "message"), VALIDATION_CASES, ids=_ids(VALIDATION_CASES)
)
async def test_input_validation_raises_nope_validation_error(
    api: FakeApi,
    make: ClientFactory,
    method: str,
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
    message: str,
) -> None:
    client = make(api_key="k")
    with pytest.raises(NopeValidationError) as exc_info:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)  # screen() warns by design
            await client.call(method, *args, **kwargs)
    await client.close()

    _assert_client_side(exc_info.value, "invalid_request", message)
    assert api.requests == []


@pytest.mark.parametrize(("method", "args", "kwargs", "message"), DEMO_CASES, ids=_ids(DEMO_CASES))
async def test_demo_refusal_raises_nope_validation_error(
    api: FakeApi,
    make: ClientFactory,
    method: str,
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
    message: str,
) -> None:
    client = make(demo=True)
    with pytest.raises(NopeValidationError) as exc_info:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)  # screen() warns by design
            await client.call(method, *args, **kwargs)
    await client.close()

    expected = message if message.endswith(".") else message + DEMO_SUFFIX
    _assert_client_side(exc_info.value, "not_available_in_demo", expected)
    assert api.requests == []


def test_validation_error_is_a_value_error_with_optional_status() -> None:
    """``except ValueError`` keeps catching what the 4.0.0 docstrings promised."""
    assert issubclass(NopeValidationError, ValueError)
    err = NopeValidationError("bad input", status_code=None, code="invalid_request")
    assert err.status_code is None
    assert str(err) == "invalid_request: bad input"

    from_api = NopeValidationError("Payload too large", status_code=413)
    assert from_api.status_code == 413
    assert str(from_api) == "[413] Payload too large"
