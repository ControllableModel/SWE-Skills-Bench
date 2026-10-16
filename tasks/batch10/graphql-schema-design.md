# Task: Add Argument-Driven Filtering and Sorting to a Product Listing

## Background

This is the [Apollo Server](https://github.com/apollographql/apollo-server) monorepo. The `@apollo/server` package (`packages/server`) builds a GraphQL service from `typeDefs` and `resolvers` and executes operations in-process. This task adds a self-contained product-listing module whose central concern is expressing filtering, sorting, and ranges through field arguments and a structured filter input rather than ad-hoc string parsing.

## Files to Create/Modify

- `packages/server/src/examples/productListing.ts` (new) — exports `typeDefs` (a GraphQL SDL string), `resolvers`, and an in-memory data store factory for a product-catalog domain. Importable on its own; must not import from any other example file.
- `packages/server/src/__tests__/examples/productListing.test.ts` (new) — a Jest suite building an `ApolloServer` and asserting through `executeOperation`.

Do **not** modify the package's public `index.ts` exports.

## Requirements

### Domain

The module lists **products**. Each product has a stable identifier, a name, a category, an integer price (in minor units), and a boolean in-stock flag. The store seeds a deterministic, fixed catalog spanning several categories and prices (no randomness, time, or I/O).

### A listing field driven by arguments

The root query exposes a single products-listing field that accepts:

1. An optional **structured filter argument** (a single input object) that may constrain results by category, by an inclusive minimum and/or maximum price, and by in-stock flag. Any combination of these may be supplied or omitted; omitting the whole filter lists all products. Filters combine conjunctively (all supplied constraints must hold).
2. An optional **sort key** drawn from a fixed closed set of permitted sort keys (for example: by name, by price, by category), and an optional **sort direction** drawn from a fixed closed set (ascending or descending). The sort key and direction sets must be discoverable through GraphQL introspection. Supplying a sort key or direction outside its set must be rejected **before resolvers run** (operation validation failure), not coerced or ignored.

The category constraint must itself be drawn from a fixed closed set of categories (an enumerated category type), introspectable, and an out-of-set category in the filter must be rejected before resolvers run.

Sorting must be total and deterministic: ties broken by identifier so the same arguments always yield the same order. The result list never resolves to null and never contains null entries; a filter matching nothing yields an empty list, not null.

### Nullability

Identifier, name, category, price, and in-stock flag are always present (never null). The listing result is a non-null list of non-null products.

### Expected Functionality

- List with no filter, sorted by price ascending -> all products in non-decreasing price order, ties broken by id.
- List filtered by a single category -> only products in that category appear.
- List filtered by min and max price (inclusive) -> only products within the range appear.
- List filtered by in-stock = true -> only in-stock products appear.
- Combine category + price-range + in-stock -> the conjunction holds for every result.
- Filter matching nothing -> empty list (not null), no execution error.
- Introspect the sort-key, sort-direction, and category types -> exactly the documented closed sets.
- Supply an out-of-set sort key, sort direction, or category -> validation failure before resolvers run.

## Acceptance Criteria

- `packages/server/src/examples/productListing.ts` exports `typeDefs` (string SDL), `resolvers`, and a fresh-store factory; deterministic, no external dependencies.
- An `ApolloServer` built from the module starts successfully.
- Filtering uses a single structured filter input; sort key, sort direction, and category are each a fixed introspectable closed set, and out-of-set values for any of them fail operation validation before resolvers run.
- Sorting is total and deterministic (ties broken by identifier), and conjunctive filters combine correctly.
- The new suite contains at least 10 `it`/`test` cases covering: unfiltered sorted listing, single-category filter, price-range filter, in-stock filter, combined conjunctive filter, empty-result-not-null, introspection of the sort-key / sort-direction / category sets, and out-of-set validation failures before resolvers run.
- The following command, run from the repository root, passes with all assertions green:

  ```
  npx jest packages/server/src/__tests__/examples/productListing.test.ts --verbose
  ```
