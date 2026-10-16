# Task: Build a Refetchable Content Graph with a Shared Node Interface

## Background

This is the [Apollo Server](https://github.com/apollographql/apollo-server) monorepo. The `@apollo/server` package (`packages/server`) builds a GraphQL service from `typeDefs` and `resolvers` and executes operations in-process via `new ApolloServer(...).executeOperation(...)`. This task adds a self-contained content-graph module whose central concern is a single, uniform way to refetch any object by a global identifier.

## Files to Create/Modify

- `packages/server/src/examples/contentGraph.ts` (new) — exports `typeDefs` (a GraphQL SDL string), `resolvers`, and an in-memory data store factory for a small content domain (articles, videos, and tags). The module must be importable on its own and must not import from any other example file.
- `packages/server/src/__tests__/examples/contentGraph.test.ts` (new) — a Jest suite that builds an `ApolloServer` from the module and asserts behavior through `executeOperation`.

Do **not** modify the package's public `index.ts` exports; the module is internal and consumed only by the new test.

## Requirements

### Domain

The graph contains three object kinds: **articles**, **videos**, and **tags**. An article and a video each carry a title and a list of tags; a tag carries a label. The store factory seeds a deterministic, fixed set of all three kinds with no randomness, time, or I/O.

### A single refetch entry point

Articles, videos, and tags all share one abstract contract: each exposes a stable, server-assigned identifier that is globally unique across **all three kinds** (no article and video may ever share the same identifier value). The root query must expose **one** field that accepts a single identifier and returns the matching object regardless of which of the three kinds it is — the caller does not say in advance which kind they expect. The returned value must report its concrete kind to the client (an article result is observably an article, a video observably a video), and clients must be able to ask for kind-specific fields by narrowing on the concrete kind.

Requesting the shared identifier field through this single entry point must work without knowing the concrete kind. Requesting an unknown identifier through it resolves to nothing (absent), not an execution error.

### Type-specific queries

In addition to the single refetch entry point, the root query exposes a way to list all articles and a way to list all videos. Each list never resolves to null and never contains null entries.

### Tag links

From an article or a video, its tags must be resolvable as a nested list of tag objects (each with its label and identifier), not as a list of bare identifier strings. The same tag object may be linked from more than one article or video, and refetching that tag's identifier through the single entry point returns the identical tag content.

### Nullability

The shared identifier, an article/video title, and a tag label are always present (never null). The list of tags on an article/video and the top-level article/video lists never resolve to null and never contain null entries; an item with no tags yields an empty list.

### Expected Functionality

- Refetch a known article identifier through the single entry point -> the result is observably an article and exposes its title.
- Refetch a known video identifier through the single entry point -> the result is observably a video.
- Refetch a known tag identifier through the single entry point -> the result is observably a tag and exposes its label.
- Refetch an unknown identifier -> the field resolves to `null` with no execution error.
- Ask only for the shared identifier through the single entry point (without narrowing) on a known id -> succeeds and returns that id.
- List all articles -> every seeded article appears with its tags resolved to nested tag objects.
- A tag shared by two articles -> both articles resolve the same tag content, and refetching that tag id reproduces it.

## Acceptance Criteria

- `packages/server/src/examples/contentGraph.ts` exports `typeDefs` (string SDL), `resolvers`, and a factory producing a fresh in-memory store, with no dependency on network, filesystem, timers, or randomness; repeated runs are deterministic.
- An `ApolloServer` built from the module's `typeDefs`/`resolvers` starts successfully.
- The shared identifier field is requestable through the single refetch entry point without narrowing to a concrete kind, demonstrating the kinds share one abstract contract carrying that field.
- The new suite `packages/server/src/__tests__/examples/contentGraph.test.ts` contains at least 10 `it`/`test` cases covering: refetch hit for each of the three kinds, concrete-kind narrowing for kind-specific fields, refetch miss (absent, no error), the unnarrowed shared-id request, type-specific list queries, nested tag resolution, and a shared tag refetched identically from two parents.
- The following command, run from the repository root, passes with all assertions green:

  ```
  npx jest packages/server/src/__tests__/examples/contentGraph.test.ts --verbose
  ```
