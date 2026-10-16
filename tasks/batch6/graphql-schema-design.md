# Task: Model Seat-Reservation Mutations With Typed Success and Error Outcomes

## Background

This is the [Apollo Server](https://github.com/apollographql/apollo-server) monorepo. The `@apollo/server` package (`packages/server`) builds a GraphQL service from `typeDefs` and `resolvers` and executes operations in-process. This task adds a self-contained event seat-reservation module whose mutations must communicate expected, recoverable failures through their return shape rather than through thrown GraphQL errors.

## Files to Create/Modify

- `packages/server/src/examples/seatReservation.ts` (new) — exports `typeDefs` (a GraphQL SDL string), `resolvers`, and an in-memory data store factory for an events-and-seats domain. Importable on its own; must not import from any other example file.
- `packages/server/src/__tests__/examples/seatReservation.test.ts` (new) — a Jest suite building an `ApolloServer` and asserting through `executeOperation`.

Do **not** modify the package's public `index.ts` exports.

## Requirements

### Domain

The module manages **events**, each with a stable identifier, a name, and a fixed set of **seats**. Each seat has a stable identifier, a label, and a booking state (free or held by a named holder). The store seeds a deterministic, fixed set of events and seats (no randomness, time, or I/O).

### Reserve mutation with discriminated outcomes

Provide a mutation that reserves a seat for a holder. It takes its arguments as a **single structured argument** (the event identifier, the seat identifier, and the holder's name). Its return value must let a client distinguish, by inspecting the returned data alone (never the top-level `errors` array), between these mutually exclusive outcomes:

- success — the seat is now reserved; the returned payload carries the updated seat showing it held by that holder.
- seat already taken — the seat exists but is already held; the payload identifies this case and surfaces who currently holds it.
- seat not found — no seat with that identifier exists in the event; the payload identifies this case.

Each outcome is a distinct, observable result kind; the client narrows the returned value to learn which one occurred and to read the case-specific fields. A successful reservation must actually mutate the store so a subsequent query reflects the seat as held.

### Release mutation

Provide a second mutation that releases a held seat, returning a discriminated outcome that distinguishes success, seat-not-found, and seat-already-free, all through the return shape and never the top-level `errors` array.

### Validation that must still throw

The holder name supplied to reserve must be a non-empty string; supplying an explicitly empty holder name must be rejected before resolvers run (a true validation/illegal-input failure), so not every bad input is funneled through the payload.

### Queries

The root query exposes a way to fetch a single event by identifier (absent, no error, on unknown id) and to read its seats. The seats list never resolves to null and never contains null entries.

### Nullability

Event identifier and name, seat identifier and label, and a held seat's holder are non-null where applicable. A free seat has no holder (absent). The seats list is non-null with no null entries.

### Expected Functionality

- Reserve a free seat -> success outcome; payload shows the seat held by that holder; a follow-up query confirms it.
- Reserve a seat already held -> already-taken outcome naming the current holder; top-level `errors` empty.
- Reserve a non-existent seat -> seat-not-found outcome; top-level `errors` empty.
- Release a held seat -> success; a follow-up query shows it free again.
- Release a free seat / non-existent seat -> the respective discriminated outcome; top-level `errors` empty.
- Reserve with an explicitly empty holder name -> rejected before resolvers run (true validation failure), not a payload outcome.

## Acceptance Criteria

- `packages/server/src/examples/seatReservation.ts` exports `typeDefs` (string SDL), `resolvers`, and a fresh-store factory; deterministic, no external dependencies.
- An `ApolloServer` built from the module starts successfully.
- Reserve and release each return a discriminated result that distinguishes success from the documented recoverable failures purely through the payload shape, with the top-level `errors` array empty in those cases.
- The new suite contains at least 10 `it`/`test` cases covering: reserve success with persistence, reserve already-taken, reserve seat-not-found, release success with persistence, release already-free, release seat-not-found, empty-holder validation failure before resolvers run, and event fetch hit/miss.
- The following command, run from the repository root, passes with all assertions green:

  ```
  npx jest packages/server/src/__tests__/examples/seatReservation.test.ts --verbose
  ```
