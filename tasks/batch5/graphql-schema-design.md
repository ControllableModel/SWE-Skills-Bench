# Task: Evolve a Profile Schema Without Breaking Existing Clients

## Background

This is the [Apollo Server](https://github.com/apollographql/apollo-server) monorepo. The `@apollo/server` package (`packages/server`) builds a GraphQL service from `typeDefs` and `resolvers` and executes operations in-process. This task adds a self-contained user-profile module that must add new shape while keeping an older field shape working and clearly marked as superseded.

## Files to Create/Modify

- `packages/server/src/examples/profileEvolution.ts` (new) — exports `typeDefs` (a GraphQL SDL string), `resolvers`, and an in-memory data store factory for a user-profile domain. Importable on its own; must not import from any other example file.
- `packages/server/src/__tests__/examples/profileEvolution.test.ts` (new) — a Jest suite building an `ApolloServer` and asserting through `executeOperation`.

Do **not** modify the package's public `index.ts` exports.

## Requirements

### Domain

The module serves **user profiles**. Each profile has a stable identifier and a person's full name. Historically the full name was exposed as one combined field (a single string). The schema now also exposes the name as separate first-name and last-name fields. Both the old combined field and the two new fields must coexist and must return mutually consistent data drawn from the same seed. The store seeds a deterministic, fixed set of profiles (no randomness, time, or I/O).

### The old field must keep working but be marked superseded

The old combined-name field must remain queryable and continue to return the correct combined name. It must also carry, in the schema, a machine-readable marker indicating it is superseded together with a non-empty human-readable reason pointing clients at the replacement fields. This marker must be discoverable through GraphQL introspection — a client introspecting the field can tell it is superseded and read the reason. The new first-name / last-name fields must **not** carry that superseded marker.

### A relocated capability

The profile also exposes a contact email. Historically email lived directly on the profile; it now also lives on a nested contact-info object reachable from the profile. The directly-attached email field must remain present and queryable, be marked superseded the same way, and return the same value as the nested location. Both locations must agree for every profile.

### Queries

The root query exposes a way to fetch a single profile by identifier (absent, no error, on unknown id) and a way to list all profiles (never null, never containing null entries).

### Nullability

The identifier, the combined name, the first name, the last name, and the email (at both locations) are always present (never null) for seeded profiles. The profile list never resolves to null and never contains null entries.

### Expected Functionality

- Query the old combined-name field -> returns the correct combined name for a known profile.
- Query the new first-name and last-name fields -> together they are consistent with the combined-name field for the same profile.
- Introspect the old combined-name field -> it is reported as superseded with a non-empty reason; the new first/last fields are not.
- Query the directly-attached email and the nested contact-info email -> identical values for every profile.
- Introspect the directly-attached email field -> reported as superseded.
- Fetch an unknown profile id -> `null`, no execution error.

## Acceptance Criteria

- `packages/server/src/examples/profileEvolution.ts` exports `typeDefs` (string SDL), `resolvers`, and a fresh-store factory; deterministic, no external dependencies.
- An `ApolloServer` built from the module starts successfully.
- The superseded markers on the old fields are discoverable through introspection (with a non-empty reason), and the replacement fields are not marked superseded.
- The old combined-name field and the directly-attached email field still resolve correctly and agree with their replacements for every profile.
- The new suite contains at least 10 `it`/`test` cases covering: old combined-name resolution, new first/last resolution and consistency, introspection of the superseded marker and reason on each old field, absence of the marker on new fields, directly-attached vs nested email agreement, list query, and fetch miss.
- The following command, run from the repository root, passes with all assertions green:

  ```
  npx jest packages/server/src/__tests__/examples/profileEvolution.test.ts --verbose
  ```
