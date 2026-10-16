# Task: Pin down watch event-filter construction

## Background

In etcd's v3 Watch service (`server/etcdserver/api/v3rpc`), `FiltersFromRequest` turns the
filter flags on a `WatchCreateRequest` into a list of predicate functions that the watch
machinery applies to suppress unwanted event types (for example, a client that only cares
about deletes can ask the server to filter out puts). Getting this mapping right is what
lets a client subscribe to a precise slice of the event stream.

## Files to Create/Modify

- `server/etcdserver/api/v3rpc/watch.go` (modify only if a real defect is found; otherwise
  leave the production logic intact).
- `server/etcdserver/api/v3rpc/watch_test.go` (modify) — add a test (e.g.
  `TestFiltersFromRequest`) that exercises the flag-to-predicate mapping and the behavior of
  the resulting predicates.

## Requirements

### Mapping flags to predicates

`FiltersFromRequest` takes a `*pb.WatchCreateRequest` whose `Filters` field lists zero or
more filter flags. The function MUST return one predicate per recognized flag, in the order
the flags appear:

- A no-empty request (no filter flags) MUST yield an empty predicate list.
- The "no put" flag MUST contribute a predicate that suppresses put events.
- The "no delete" flag MUST contribute a predicate that suppresses delete events.
- Both flags together MUST yield two predicates.
- An unrecognized flag value MUST contribute no predicate (it is ignored, not an error).

### Predicate semantics

Each returned predicate decides whether an event should be filtered out (suppressed):

- The "no put" predicate MUST report that a put event should be suppressed and that a
  delete event should NOT be suppressed.
- The "no delete" predicate MUST report that a delete event should be suppressed and that a
  put event should NOT be suppressed.

### Constraints

- The number and meaning of predicates MUST be driven by the request's filter flags, not by
  inspecting the events at construction time.
- The function MUST never return `nil` in place of an empty list for a request with no
  filters (callers range over the result).

### Expected Functionality

- `Filters=[]` -> zero predicates.
- `Filters=[NOPUT]` -> one predicate; suppresses a put event, keeps a delete event.
- `Filters=[NODELETE]` -> one predicate; suppresses a delete event, keeps a put event.
- `Filters=[NOPUT, NODELETE]` -> two predicates.
- `Filters=[<unknown value>]` -> zero predicates.

## Acceptance Criteria

- The new test builds `*pb.WatchCreateRequest` values, asserts the length of the returned
  predicate slice for each flag combination, and—by constructing `mvccpb.Event` values of
  PUT and DELETE type—asserts that each predicate suppresses exactly the intended event type.
- The existing watch tests continue to pass.
- The following command, run from the repository root, MUST succeed:

  ```
  cd server && go test ./etcdserver/api/v3rpc/ -run TestFiltersFromRequest -count=1 -v
  ```
