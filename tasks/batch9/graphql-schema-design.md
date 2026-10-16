# Task: Enforce Intentional Nullability Across a Task-Board Schema

## Background

This is the [Apollo Server](https://github.com/apollographql/apollo-server) monorepo. The `@apollo/server` package (`packages/server`) builds a GraphQL service from `typeDefs` and `resolvers` and executes operations in-process. This task adds a self-contained task-board module whose central concern is getting nullability and list contracts exactly right and verifiable through introspection.

## Files to Create/Modify

- `packages/server/src/examples/taskBoard.ts` (new) — exports `typeDefs` (a GraphQL SDL string), `resolvers`, and an in-memory data store factory for a task-board domain (boards, columns, cards). Importable on its own; must not import from any other example file.
- `packages/server/src/__tests__/examples/taskBoard.test.ts` (new) — a Jest suite building an `ApolloServer` and asserting through `executeOperation`.

Do **not** modify the package's public `index.ts` exports.

## Requirements

### Domain

The module manages **boards**. A board has a stable identifier, a name, and an ordered list of **columns**. A column has a stable identifier, a title, and an ordered list of **cards**. A card has a stable identifier, a title, an optional description, an optional assignee handle, and a list of label strings. The store seeds a deterministic, fixed set of boards, columns, and cards — including a column with zero cards and a card with no description, no assignee, and no labels — so the null/empty distinctions are exercised by the seed (no randomness, time, or I/O).

### The nullability contract (verifiable by introspection)

The schema's nullability must be deliberate and discoverable through GraphQL introspection:

- **Always present (non-null):** every identifier; a board name; a column title; a card title.
- **Optional (nullable):** a card's description; a card's assignee handle.
- **List contracts:** a board's columns, a column's cards, and a card's labels are each a non-null list of non-null items. A board with columns yields those columns; a column with zero cards yields an **empty list, not null**; a card with no labels yields an **empty list, not null**.

A client introspecting the types must be able to confirm, for each field above, whether it is non-null, nullable, a non-null list of non-null items, etc. — the wrapping (non-null / list / list-of-non-null) must match the contract above exactly.

### Queries

The root query exposes a way to fetch a single board by identifier (absent, no error, on unknown id) and a way to list all boards (non-null list of non-null boards). Columns and cards are reachable as nested lists from their parents.

### Expected Functionality

- Fetch a known board -> returns its name, its columns in order, and within columns the cards in order.
- A column seeded with zero cards -> its cards field is an empty list, not null, and no execution error.
- A card seeded with no labels -> its labels field is an empty list, not null.
- A card with no description / no assignee -> those fields read as `null` (absent), not as empty strings, and no execution error.
- Introspect the card type -> description and assignee are nullable; title and identifier are non-null; labels is a non-null list of non-null items.
- Introspect the board type -> columns is a non-null list of non-null items.
- Fetch an unknown board id -> `null`, no execution error.

## Acceptance Criteria

- `packages/server/src/examples/taskBoard.ts` exports `typeDefs` (string SDL), `resolvers`, and a fresh-store factory; deterministic, no external dependencies.
- An `ApolloServer` built from the module starts successfully.
- Introspection confirms the exact nullability/list wrappings described above for board, column, and card fields (non-null where required, nullable where optional, non-null list of non-null items for every list field).
- Empty lists are returned as empty lists (never null), and absent optional scalars read as `null` (never empty-string substitutes).
- The new suite contains at least 10 `it`/`test` cases covering: nested board->columns->cards resolution in order, empty-cards-list-not-null, empty-labels-list-not-null, null description, null assignee, introspection of card nullability wrappings, introspection of a list field's non-null-list-of-non-null wrapping, board list query, and board fetch miss.
- The following command, run from the repository root, passes with all assertions green:

  ```
  npx jest packages/server/src/__tests__/examples/taskBoard.test.ts --verbose
  ```
