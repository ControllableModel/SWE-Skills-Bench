# Task: Implement a Heterogeneous Search Field Returning Mixed Result Kinds

## Background

This is the [Apollo Server](https://github.com/apollographql/apollo-server) monorepo. The `@apollo/server` package (`packages/server`) builds a GraphQL service from `typeDefs` and `resolvers` and executes operations in-process. This task adds a self-contained search module whose single search field returns results of several mutually exclusive kinds in one list.

## Files to Create/Modify

- `packages/server/src/examples/searchModule.ts` (new) — exports `typeDefs` (a GraphQL SDL string), `resolvers`, and an in-memory data store factory for a small directory domain (people, projects, and documents). Importable on its own; must not import from any other example file.
- `packages/server/src/__tests__/examples/searchModule.test.ts` (new) — a Jest suite building an `ApolloServer` and asserting through `executeOperation`.

Do **not** modify the package's public `index.ts` exports.

## Requirements

### Domain

Three distinct object kinds are searchable: **people** (with a display name and an email), **projects** (with a name and a status), and **documents** (with a title and a word count). These three kinds do **not** share a common field set beyond being searchable; each has its own shape. The store seeds a deterministic, fixed population of all three kinds (no randomness, time, or I/O).

### One search field, several result kinds

The root query exposes a single search field taking a free-text query string and returning a list whose elements may each be a person, a project, or a document — these are mutually exclusive kinds combined into one result list. A given returned element is exactly one kind; the client must be able to discover which concrete kind each element is and then read that kind's own fields. The result list never resolves to null and never contains null entries; a search matching nothing yields an empty list, not null.

Matching is a deterministic, case-insensitive substring test against the human-readable text of each kind (a person's display name, a project's name, a document's title). Results are returned in a stable, deterministic order so the same query always yields the same sequence.

### Kind-specific queries remain available

Besides search, the root query exposes a way to fetch a single person by identifier and a single project by identifier, each absent (resolving to nothing, no error) when the identifier is unknown.

### Nullability

Identifiers and each kind's human-readable label field are always present (never null). A project's status is one of a fixed closed set of values, discoverable through introspection, and supplying any other status value where status is accepted is rejected before resolvers run.

### Expected Functionality

- Search a term matching one person and one project -> the result list contains exactly those two elements, each observably its own kind, each exposing its own fields.
- Search a term matching nothing -> empty list, no execution error.
- Search and narrow a result to the person kind -> the person's email is readable; narrowing the same element to the document kind yields nothing for document-only fields.
- Repeated identical searches -> identical result sequences (stable order).
- Fetch a person / project by unknown id -> `null`, no error.
- Introspect project status -> exactly the documented closed set of values.
- Supply an out-of-set project status where status is accepted -> validation failure before resolvers run.

## Acceptance Criteria

- `packages/server/src/examples/searchModule.ts` exports `typeDefs` (string SDL), `resolvers`, and a fresh-store factory; deterministic, no external dependencies.
- An `ApolloServer` built from the module starts successfully.
- The single search field returns a list mixing all three mutually exclusive kinds, and clients can both discover each element's concrete kind and read that kind's own fields.
- The new suite contains at least 10 `it`/`test` cases covering: a multi-kind search hit, an empty search, concrete-kind narrowing for each kind's own fields, stable deterministic ordering, kind-specific fetch hit/miss, the introspectable project-status value set, and out-of-set status validation failure before resolvers run.
- The following command, run from the repository root, passes with all assertions green:

  ```
  npx jest packages/server/src/__tests__/examples/searchModule.test.ts --verbose
  ```
