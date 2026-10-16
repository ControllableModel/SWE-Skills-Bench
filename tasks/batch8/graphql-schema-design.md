# Task: Enforce Domain-Specific Scalars for Contacts (Email, URL, DateTime)

## Background

This is the [Apollo Server](https://github.com/apollographql/apollo-server) monorepo. The `@apollo/server` package (`packages/server`) builds a GraphQL service from `typeDefs` and `resolvers` and executes operations in-process. This task adds a self-contained contacts module that must validate and represent domain-specific values (email addresses, web URLs, timestamps) at the type level rather than as plain strings.

## Files to Create/Modify

- `packages/server/src/examples/contactsModule.ts` (new) — exports `typeDefs` (a GraphQL SDL string), `resolvers`, and an in-memory data store factory for a contacts domain. Importable on its own; must not import from any other example file.
- `packages/server/src/__tests__/examples/contactsModule.test.ts` (new) — a Jest suite building an `ApolloServer` and asserting through `executeOperation`.

Do **not** modify the package's public `index.ts` exports.

## Requirements

### Domain

The module manages **contacts**. Each contact has a stable identifier, a display name, an email address, an optional website URL, and a created-at timestamp. Email, URL, and timestamp are each represented as their own domain-specific scalar type — distinct from one another and from plain `String` — so the schema captures the kind of value, not just "some text." The store seeds a deterministic, fixed set of contacts (no randomness, time, or I/O).

### Scalar validation on input

A mutation that creates a contact accepts its arguments as a **single structured argument** including the name, email, an optional website URL, and a created-at timestamp. Each domain-specific scalar must reject malformed input **before resolvers run**:

- a value that is not a syntactically valid email is rejected.
- a value that is not a syntactically valid web URL is rejected (for the website, which is optional but, when present, must be valid).
- a value that is not a valid ISO-8601 timestamp is rejected.

A well-formed-but-conflicting case (an email already used by an existing contact) is **not** a scalar failure; it is a recoverable outcome reported through the mutation's return payload so a client can distinguish "duplicate email" from success without consulting the top-level `errors` array.

### Scalar values on output

Reading a contact's email, website, and created-at yields the respective domain-specific scalar values, and a round trip (create then fetch) returns the same values that were supplied.

### Queries

The root query exposes a way to fetch a single contact by identifier (absent, no error, on unknown id) and a way to list all contacts (never null, never containing null entries).

### Nullability

Identifier, display name, email, and created-at are always present (never null). The website URL is optional and may be absent. The contact list never resolves to null and never contains null entries.

### Expected Functionality

- Create a contact with a valid email, valid URL, valid timestamp -> succeeds; fetching it back returns the same scalar values.
- Create a contact with a malformed email -> rejected before resolvers run (populated `errors`, no `data` for that field).
- Create with a malformed website URL -> rejected before resolvers run.
- Create with a malformed timestamp -> rejected before resolvers run.
- Create omitting the optional website -> succeeds; the website reads as absent.
- Create with an email already used by a seeded contact -> duplicate-email outcome via the payload; top-level `errors` empty.
- Fetch an unknown contact id -> `null`, no execution error.

## Acceptance Criteria

- `packages/server/src/examples/contactsModule.ts` exports `typeDefs` (string SDL), `resolvers`, and a fresh-store factory; deterministic, no external dependencies.
- An `ApolloServer` built from the module starts successfully.
- Email, URL, and timestamp are each their own scalar type (distinct from `String` and from each other), and malformed inputs for each are rejected before resolvers run while a valid value round-trips unchanged.
- A duplicate-email conflict is reported through the mutation payload, not the top-level `errors` array.
- The new suite contains at least 10 `it`/`test` cases covering: valid create + round-trip, malformed-email rejection, malformed-URL rejection, malformed-timestamp rejection, optional-website omission, duplicate-email payload outcome, fetch hit/miss, and the non-null list contract.
- The following command, run from the repository root, passes with all assertions green:

  ```
  npx jest packages/server/src/__tests__/examples/contactsModule.test.ts --verbose
  ```
