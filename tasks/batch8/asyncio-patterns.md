# Task: Add an Async Event Broker with Topic Subscriptions

## Background

`aiohttp` servers commonly fan out notifications to multiple interested handlers
(for example WebSocket broadcast loops). This task adds a reusable in-process async
event broker so producers can publish messages on named topics and any number of
subscribers can consume them through async iteration.

## Files to Create/Modify

- `aiohttp/event_broker.py` (new) — an `EventBroker` class.
- `tests/test_event_broker.py` (new) — deterministic test suite.

## Requirements

### Public API

Add to `aiohttp/event_broker.py`:

```python
class EventBroker:
    def __init__(self) -> None: ...
    def subscribe(self, topic: str) -> "Subscription": ...
    async def publish(self, topic: str, message) -> int: ...   # returns number of subscribers delivered to
    async def close(self) -> None: ...
```

Where a `Subscription` supports:

```python
async for message in subscription: ...
async def aclose(self) -> None: ...
```

(It may also be used as an async context manager that unsubscribes on exit.)

### Behavior

- `subscribe(topic)` registers a new subscriber for `topic` and returns a
  `Subscription` that asynchronously yields messages published to that topic
  **after** the subscription was created.
- `publish(topic, message)` delivers `message` to every current subscriber of
  `topic` and returns the count of subscribers it delivered to. Publishing to a
  topic with no subscribers returns `0` and does nothing else.
- Each subscriber receives every message published to its topic while it is
  subscribed, in publish order. A slow subscriber must not lose messages nor block
  delivery to other subscribers (each subscription buffers its own pending messages).
- `subscription.aclose()` (or exiting the subscription's `async with`) ends the
  async iteration cleanly and unsubscribes it so future publishes ignore it.
- `broker.close()` ends all active subscriptions; their async iterations stop.

### Isolation

- Messages on topic `A` are never delivered to subscribers of topic `B`.

### Edge cases

- A subscriber created after a message was published does not receive that earlier
  message.
- Closing a subscription that has already been closed is a no-op.

### Expected Functionality

- Scenario: two subscribers on `"news"`, publish `"a"` then `"b"` -> each subscriber
  iterates exactly `["a", "b"]` in order; `publish` returns `2` each time.
- Scenario: subscriber on `"news"` and subscriber on `"sports"`, publish on `"news"`
  -> only the `"news"` subscriber receives it; `publish` returns `1`.
- Scenario: publish on a topic with no subscribers -> returns `0`.
- Scenario: subscribe after a message was published, then publish again -> the new
  subscriber sees only the later message.
- Scenario: `broker.close()` while a subscriber is iterating -> the iteration ends.

## Acceptance Criteria

- `aiohttp.event_broker.EventBroker` is importable; subscriptions are async-iterable.
- Each subscriber receives all and only the messages for its topic published during
  its lifetime, in order; `publish` returns the delivered-subscriber count.
- Closing a subscription or the broker stops the relevant iteration cleanly.
- Topic isolation and the late-subscriber rule hold.
- The following command passes:

```bash
python -m pytest tests/test_event_broker.py -v
```
