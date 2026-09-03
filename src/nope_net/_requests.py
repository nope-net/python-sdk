"""Request builders shared by the sync and async clients.

Each builder validates its inputs, serialises models to plain dicts and returns
the path plus body (or query) to send. Keeping them here means the two clients
cannot drift: a method body in ``client.py`` is one builder call plus one
``_request`` call.
"""

from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from pydantic import BaseModel

MAX_EVALUATE_MESSAGES = 100

JsonDict = Dict[str, Any]


def dump(value: Union[BaseModel, JsonDict]) -> JsonDict:
    """Serialise a model or pass a dict through (copied)."""
    if isinstance(value, BaseModel):
        return value.model_dump(exclude_none=True)
    return dict(value)


def normalize_messages(
    messages: Sequence[Union[BaseModel, JsonDict]],
    *,
    allowed_roles: Tuple[str, ...],
    max_messages: Optional[int],
) -> List[JsonDict]:
    """Validate and serialise a message list."""
    if len(messages) == 0:
        raise ValueError("'messages' cannot be empty")
    if max_messages is not None and len(messages) > max_messages:
        raise ValueError(f"Too many messages: {len(messages)}. Maximum allowed: {max_messages}")
    out: List[JsonDict] = []
    for index, message in enumerate(messages):
        data = dump(message)
        role = data.get("role")
        if role not in allowed_roles:
            allowed = " or ".join(repr(r) for r in allowed_roles)
            raise ValueError(f"Message {index}: role must be {allowed}, got {role!r}")
        if not isinstance(data.get("content"), str):
            raise ValueError(f"Message {index}: content must be a string")
        out.append(data)
    return out


def _messages_or_text(
    messages: Optional[Sequence[Union[BaseModel, JsonDict]]],
    text: Optional[str],
    *,
    allowed_roles: Tuple[str, ...],
    max_messages: Optional[int],
) -> JsonDict:
    if messages is None and text is None:
        raise ValueError("Either 'messages' or 'text' must be provided")
    if messages is not None and text is not None:
        raise ValueError("Only one of 'messages' or 'text' can be provided, not both")
    payload: JsonDict = {}
    if messages is not None:
        payload["messages"] = normalize_messages(
            messages, allowed_roles=allowed_roles, max_messages=max_messages
        )
    if text is not None:
        payload["text"] = text
    return payload


# =============================================================================
# Evaluate / screen
# =============================================================================


def build_evaluate_request(
    *,
    messages: Optional[Sequence[Union[BaseModel, JsonDict]]],
    text: Optional[str],
    config: Optional[Union[BaseModel, JsonDict]],
    demo: bool,
) -> Tuple[str, JsonDict]:
    """Return ``(path, body)`` for ``evaluate``.

    In demo mode ``config.user_country`` mirrors ``config.country`` because the
    ``/v1/try/evaluate`` route reads that key until API fix A-1 is deployed.
    """
    payload = _messages_or_text(
        messages, text, allowed_roles=("user", "assistant"), max_messages=MAX_EVALUATE_MESSAGES
    )
    config_dict = dump(config) if config is not None else {}
    if demo and config_dict.get("country") and "user_country" not in config_dict:
        config_dict["user_country"] = config_dict["country"]
    payload["config"] = config_dict
    path = "/v1/try/evaluate" if demo else "/v1/evaluate"
    return path, payload


def build_screen_request(
    *,
    messages: Optional[Sequence[Union[BaseModel, JsonDict]]],
    text: Optional[str],
    config: Optional[Union[BaseModel, JsonDict]],
) -> Tuple[str, JsonDict]:
    """Return ``(path, body)`` for the legacy ``screen`` call."""
    payload = _messages_or_text(
        messages, text, allowed_roles=("user", "assistant"), max_messages=MAX_EVALUATE_MESSAGES
    )
    if config is not None:
        payload["config"] = dump(config)
    return "/v0/screen", payload
