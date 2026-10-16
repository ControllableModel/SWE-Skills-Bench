# Task: Model an Inventory Service with Enumerated States and a Money Scalar

## Background

This is the [Apollo Server](https://github.com/apollographql/apollo-server) monorepo. The `@apollo/server` package (`packages/server`) builds a GraphQL service from `typeDefs` and `resolvers` and executes operations in-process. This task adds a self-contained warehouse-inventory module that must represent fixed-domain states and a domain-specific money value precisely, rather than as free-form strings.

## Files to Create/Modify

- `packages/server/src/examples/inventoryService.ts` (new) — exports `typeDefs` (a GraphQL SDL string), `resolvers`, and an in-memory data store factory for an inventory domain (stock items). Importable on its own; must not import from any other example file.
- `packages/server/src/__tests__/examples/inventoryService.test.ts` (new) — a Jest suite building an `ApolloServer` and asserting through `executeOperation`.

Do **not** modify the package's public `index.ts` exports.

## Requirements

### Domain

The service tracks **stock items**. Each item has a stable server-assigned identifier, a name, a unit price expressed as a domain-specific money value, an availability state, and a non-negative quantity on hand. The store seeds a deterministic, fixed set of items (no randomness, time, or I/O).

### Availability state is a closed set

An item's availability is one of exactly four fixed states: in stock, low stock, out of stock, discontinued. These are the only permitted values anywhere availability is supplied or returned. A query that filters by availability, or a mutation that sets availability, using any value outside this set must be **rejected before any resolver runs** (it fails operation validation). The complete set of permitted availability values must be discoverable through GraphQL introspection.

### Money is a structured scalar value, not a bare number

A unit price is represented as a single domain-specific scalar value (not a plain `Int`/`Float` and not a `String`). On output, reading an item's price yields that scalar. On input, a mutation that sets a price accepts the same scalar form. Supplying a malformed money value (for example, a negative amount or a value that is not a well-formed money string) on input must fail before resolvers run. Two items with the same price must compare equal when their price values are read back.

### Queries

The root query exposes:

1. Fetch a single item by identifier; an unknown identifier resolves to nothing (absent), not an execution error.
2. List items, optionally filtered by availability state. With no filter, all items are listed; with a filter, only items in that state appear.

### Mutation

Provide a mutation that adjusts an existing item's quantity on hand by a signed delta and, as a side effect, recomputes the availability state from the resulting quantity (zero -> out of stock, otherwise in stock unless already discontinued). The mutation accepts its arguments as a **single structured argument**. Adjusting a non-existent item is a recoverable outcome reported through the return payload (a client can distinguish "item not found" from success by inspecting the returned data), not via the top-level `errors` array. An adjustment that would drive quantity below zero is likewise reported through the payload, not as a thrown error.

### Nullability

Identifier, name, price, availability state, and quantity are always present (never null). The item list never resolves to null and never contains null entries.

### Expected Functionality

- Fetch a known item -> returns name, price scalar, availability, quantity matching seed data.
- Fetch an unknown id -> `null`, no execution error.
- List filtered by `OUT_OF_STOCK` -> only out-of-stock items appear.
- Filter by an availability value outside the fixed set -> validation failure (populated `errors`, no `data` for that field) before resolvers run.
- Introspect the availability type -> exactly the four documented values are present.
- Set a malformed money value on input -> fails before resolvers run.
- Two seeded items priced identically -> their read-back price values compare equal.
- Adjust quantity of an existing item to zero -> availability becomes out of stock in the returned payload.
- Adjust a non-existent item / drive quantity negative -> reported via the returned payload, top-level `errors` empty.

## Acceptance Criteria

- `packages/server/src/examples/inventoryService.ts` exports `typeDefs` (string SDL), `resolvers`, and a fresh-store factory; deterministic, no external dependencies.
- An `ApolloServer` built from the module starts successfully.
- The availability fixed-value set is introspectable, and invalid availability inputs fail operation validation before resolvers run.
- Prices round-trip through a single domain-specific scalar (not a bare numeric/string field), and malformed money inputs are rejected before resolvers run.
- The new suite contains at least 10 `it`/`test` cases covering: fetch hit/miss, availability filtering, the introspectable availability value set, invalid-availability validation failure, malformed-money input rejection, price-equality round-trip, quantity-adjust success with state recomputation, and the item-not-found / negative-quantity outcomes distinguished from success without the top-level `errors` array.
- The following command, run from the repository root, passes with all assertions green:

  ```
  npx jest packages/server/src/__tests__/examples/inventoryService.test.ts --verbose
  ```
