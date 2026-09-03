"""mypy --strict fixture: ``messages`` accepts any Sequence of Message or Mapping.

Checked by ``tests/unit/test_typing.py`` and the ``mypy src tests/typing``
gate; never imported at runtime. Every call here fails on the 4.0.0
``List[Union[Message, Dict[str, Any]]]`` parameters ("list" is invariant) and
passes once they are ``Sequence[Union[Message, Mapping[str, Any]]]``.
"""

from typing import Any, Dict, List, Mapping, Sequence, Tuple, Union

from nope_net import AsyncNopeClient, Message, NopeClient, OversightConversation


def plain_dicts(client: NopeClient, messages: List[Dict[str, str]]) -> None:
    client.evaluate(messages=messages)
    client.screen(messages=messages)
    client.ocular(messages=messages)


def any_dicts(client: NopeClient, messages: List[Dict[str, Any]]) -> None:
    client.evaluate(messages=messages)
    client.screen(messages=messages)
    client.ocular(messages=messages)


def models(client: NopeClient, messages: List[Message]) -> None:
    client.evaluate(messages=messages)
    client.screen(messages=messages)
    client.ocular(messages=messages)


def a_tuple(client: NopeClient, messages: Tuple[Dict[str, str], ...]) -> None:
    client.evaluate(messages=messages)
    client.screen(messages=messages)
    client.ocular(messages=messages)


def mixed(client: NopeClient, messages: Sequence[Union[Message, Mapping[str, Any]]]) -> None:
    client.evaluate(messages=messages)
    client.screen(messages=messages)
    client.ocular(messages=messages)


def oversight(
    client: NopeClient,
    conversation: Dict[str, Any],
    frozen: Mapping[str, Any],
    model: OversightConversation,
    conversations: List[Dict[str, Any]],
) -> None:
    client.oversight_analyze(conversation)
    client.oversight_analyze(frozen)
    client.oversight_analyze(model)
    client.oversight_ingest(conversations=conversations)
    client.oversight_ingest(conversations=tuple(conversations))
    client.oversight_ingest(conversations=[model])


async def async_plain_dicts(client: AsyncNopeClient, messages: List[Dict[str, str]]) -> None:
    await client.evaluate(messages=messages)
    await client.screen(messages=messages)
    await client.ocular(messages=messages)


async def async_models(client: AsyncNopeClient, messages: List[Message]) -> None:
    await client.evaluate(messages=messages)
    await client.screen(messages=messages)
    await client.ocular(messages=messages)


async def async_tuple(client: AsyncNopeClient, messages: Tuple[Dict[str, str], ...]) -> None:
    await client.evaluate(messages=messages)
    await client.screen(messages=messages)
    await client.ocular(messages=messages)


async def async_oversight(
    client: AsyncNopeClient,
    conversation: Dict[str, Any],
    frozen: Mapping[str, Any],
    conversations: List[Dict[str, Any]],
) -> None:
    await client.oversight_analyze(conversation)
    await client.oversight_analyze(frozen)
    await client.oversight_ingest(conversations=conversations)
    await client.oversight_ingest(conversations=tuple(conversations))
