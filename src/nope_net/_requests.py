"""Request builders shared by the sync and async clients.

Each builder validates its inputs, serialises models to plain dicts and returns
the path plus body (or query) to send. Keeping them here means the two clients
cannot drift: a method body in ``client.py`` is one builder call plus one
``_request`` call.
"""

from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from pydantic import BaseModel

MAX_EVALUATE_MESSAGES = 100
MAX_INGEST_CONVERSATIONS = 300
OVERSIGHT_SEVERITIES = ("low", "medium", "high", "critical")
MAX_TRAJECTORY_STRIDE = 64
MAX_OCULAR_IDENTITY_LENGTH = 256

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
        raise ValueError("Only one of 'messages' or 'text' can be provided")
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


# =============================================================================
# Oversight
# =============================================================================


def _validate_oversight_conversation(
    conversation: JsonDict, *, index: Optional[int] = None
) -> None:
    label = "conversation" if index is None else f"Conversation at index {index}"
    messages = conversation.get("messages")
    if messages is None:
        raise ValueError(f'"{label}.messages" is required')
    if not isinstance(messages, list):
        raise ValueError(f'"{label}.messages" must be a list')
    if len(messages) == 0:
        raise ValueError(f'"{label}.messages" cannot be empty')
    for position, message in enumerate(messages):
        role = message.get("role") if isinstance(message, dict) else None
        if role not in ("user", "assistant", "system"):
            raise ValueError(
                f"{label}: message {position} role must be 'user', 'assistant' or 'system'"
            )


def _validate_behavior_filter(behaviors: JsonDict) -> None:
    if behaviors.get("enabled") and behaviors.get("disabled"):
        raise ValueError('"behaviors.enabled" and "behaviors.disabled" are mutually exclusive')
    min_severity = behaviors.get("min_severity")
    if min_severity is not None and min_severity not in OVERSIGHT_SEVERITIES:
        raise ValueError(
            '"behaviors.min_severity" must be one of: ' + ", ".join(OVERSIGHT_SEVERITIES)
        )


def build_oversight_analyze_request(
    *,
    conversation: Union[BaseModel, JsonDict],
    bot_context: Optional[str],
    config: Optional[Union[BaseModel, JsonDict]],
    behaviors: Optional[Union[BaseModel, JsonDict]],
    demo: bool,
) -> Tuple[str, JsonDict]:
    """Return ``(path, body)`` for ``oversight_analyze``."""
    conversation_dict = dump(conversation)
    _validate_oversight_conversation(conversation_dict)
    payload: JsonDict = {"conversation": conversation_dict}
    if bot_context is not None:
        payload["bot_context"] = bot_context
    if config is not None:
        payload["config"] = dump(config)
    if behaviors is not None:
        behaviors_dict = dump(behaviors)
        _validate_behavior_filter(behaviors_dict)
        payload["behaviors"] = behaviors_dict
    path = "/v1/try/oversight/analyze" if demo else "/v1/oversight/analyze"
    return path, payload


def build_oversight_ingest_request(
    *,
    conversations: Sequence[Union[BaseModel, JsonDict]],
    webhook_url: Optional[str],
    config: Optional[Union[BaseModel, JsonDict]],
) -> Tuple[str, JsonDict]:
    """Return ``(path, body)`` for ``oversight_ingest`` (client cap 300 conversations)."""
    if not conversations:
        raise ValueError('"conversations" cannot be empty')
    if len(conversations) > MAX_INGEST_CONVERSATIONS:
        raise ValueError(
            f"Too many conversations: {len(conversations)}. "
            f"Maximum allowed: {MAX_INGEST_CONVERSATIONS}"
        )
    conversation_list: List[JsonDict] = []
    for index, conversation in enumerate(conversations):
        data = dump(conversation)
        if not data.get("conversation_id"):
            raise ValueError(f'Conversation at index {index} must have a "conversation_id"')
        if not data.get("messages"):
            raise ValueError(
                f'Conversation "{data["conversation_id"]}" must have non-empty "messages"'
            )
        conversation_list.append(data)
    payload: JsonDict = {"conversations": conversation_list}
    if webhook_url is not None:
        payload["webhook_url"] = webhook_url
    if config is not None:
        payload["config"] = dump(config)
    return "/v1/oversight/ingest", payload


# =============================================================================
# Ocular
# =============================================================================


def build_ocular_request(
    *,
    messages: Optional[Sequence[Union[BaseModel, JsonDict]]],
    text: Optional[str],
    thoroughness: Optional[str],
    per_turn: Optional[bool],
    trajectory_stride: Optional[int],
    user_id: Optional[str],
    session_id: Optional[str],
    agent_id: Optional[str],
    demo: bool,
) -> Tuple[str, JsonDict]:
    """Return ``(path, body)`` for ``ocular``.

    The demo route accepts only ``messages``/``text``, ``per_turn`` and
    ``trajectory_stride``; the other fields are dropped there.
    """
    payload = _messages_or_text(
        messages, text, allowed_roles=("user", "assistant"), max_messages=None
    )
    if trajectory_stride is not None and not 1 <= trajectory_stride <= MAX_TRAJECTORY_STRIDE:
        raise ValueError(f"trajectory_stride must be between 1 and {MAX_TRAJECTORY_STRIDE}")
    for name, value in (("user_id", user_id), ("session_id", session_id), ("agent_id", agent_id)):
        if value is not None and not 1 <= len(value) <= MAX_OCULAR_IDENTITY_LENGTH:
            raise ValueError(f"{name} must be 1 to {MAX_OCULAR_IDENTITY_LENGTH} characters")
    if per_turn is not None:
        payload["per_turn"] = per_turn
    if trajectory_stride is not None:
        payload["trajectory_stride"] = trajectory_stride
    if demo:
        return "/v1/try/ocular", payload
    if thoroughness is not None:
        payload["thoroughness"] = thoroughness
    if user_id is not None:
        payload["user_id"] = user_id
    if session_id is not None:
        payload["session_id"] = session_id
    if agent_id is not None:
        payload["agent_id"] = agent_id
    return "/v1/ocular", payload


# =============================================================================
# Signpost
# =============================================================================


def _join(values: Optional[Sequence[str]]) -> Optional[str]:
    if values is None:
        return None
    return ",".join(values)


def build_signpost_params(
    *,
    country: str,
    config: Optional[Union[BaseModel, JsonDict]],
    scopes: Optional[Sequence[str]],
    populations: Optional[Sequence[str]],
    subdivisions: Optional[Sequence[str]],
    limit: Optional[int],
    urgent: Optional[bool],
) -> Dict[str, str]:
    """Query params for the basic lookup. Top-level filters win over ``config``."""
    cfg = dump(config) if config is not None else {}
    merged: JsonDict = {
        "scopes": scopes if scopes is not None else cfg.get("scopes"),
        "populations": populations if populations is not None else cfg.get("populations"),
        "subdivisions": subdivisions if subdivisions is not None else cfg.get("subdivisions"),
        "limit": limit if limit is not None else cfg.get("limit"),
        "urgent": urgent if urgent is not None else cfg.get("urgent"),
    }
    params: Dict[str, str] = {"country": country.upper()}
    for key in ("scopes", "populations", "subdivisions"):
        joined = _join(merged[key])
        if joined:
            params[key] = joined
    if merged["limit"] is not None:
        params["limit"] = str(merged["limit"])
    if merged["urgent"]:
        params["urgent"] = "true"
    return params


def build_signpost_smart_params(
    *,
    country: str,
    query: str,
    config: Optional[Union[BaseModel, JsonDict]],
) -> Dict[str, str]:
    """Query params for the smart (LLM-ranked) lookup."""
    if not query:
        raise ValueError("'query' is required")
    cfg = dump(config) if config is not None else {}
    params: Dict[str, str] = {"country": country.upper(), "query": query}
    for key in ("scopes", "populations"):
        joined = _join(cfg.get(key))
        if joined:
            params[key] = joined
    if cfg.get("limit") is not None:
        params["limit"] = str(cfg["limit"])
    return params


def build_signpost_search_params(
    *,
    query: str,
    country: Optional[str],
    limit: Optional[int],
    threshold: Optional[float],
) -> Dict[str, str]:
    """Query params for vector search."""
    if not query:
        raise ValueError("'query' is required")
    params: Dict[str, str] = {"query": query}
    if country:
        params["country"] = country.upper()
    if limit is not None:
        params["limit"] = str(limit)
    if threshold is not None:
        params["threshold"] = str(threshold)
    return params
