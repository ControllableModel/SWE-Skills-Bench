# Task: Build an In-Memory Tag-to-Link Tagging Store

## Background

The dub monorepo (`apps/web`) is a link-management platform; `apps/web/lib/links/` holds link helpers and the product lets a workspace organize links with reusable tags. This task adds a self-contained, embedded tagging store that models the relationship between tags and links entirely in-process, so tag-membership logic can be unit-tested without the production database or any network service.

## Files to Create/Modify

- `apps/web/lib/links/tag-store/schema.ts` (new) — table and relation definitions plus the inferred row types.
- `apps/web/lib/links/tag-store/store.ts` (new) — the `TagStore` class implementing the public API below, backed by an embedded SQLite database opened with the `better-sqlite3` driver (already available in the workspace).
- `apps/web/lib/links/tag-store/index.ts` (new) — re-exports the store, its factory, and the public types.
- `apps/web/package.json` (modify) — add the `drizzle-orm` runtime dependency required to build the store.
- `apps/web/tests/links/tag-store.test.ts` (new) — vitest suite covering the behavior and edge cases below.

> The store must run against an in-memory database (e.g. constructed from `":memory:"`) so tests never hit a network, file, or external service. Do not reuse the Prisma client or the live API; this module stands alone.

## Requirements

### Data model

Model three entities inside the embedded database:

- **links** — `id` (string, primary key), `domain` (string, required), `key` (string, required).
- **tags** — `id` (string, primary key), `name` (string, required); `name` must be unique across all tags.
- **link_tags** — the association between a link and a tag. A given (link, tag) pair may appear at most once; the pair itself identifies the row (no separate surrogate id needed).

The model must express a many-to-many relationship: one link has many tags and one tag has many links, navigable through `link_tags`. Both directions must be loadable in a single round trip. Row types used by `store.ts` must be derived from the table definitions themselves — hand-written interfaces that can silently drift from the columns are not acceptable.

### Construction and lifecycle

- A factory (e.g. `createTagStore()`) returns a fresh, empty store backed by a new in-memory database with all three tables created.
- Each new store is fully isolated: data inserted into one instance is never visible from another.

### Write API

- `addLink(input)` and `addTag(input)` insert one row and return the stored row.
- `addTag` with a `name` that already exists must throw and must not create a duplicate row.
- `tagLink(linkId, tagId)` associates a tag with a link. Calling it again with the same pair is a no-op (still exactly one association, no error).
- `untagLink(linkId, tagId)` removes the association if present and is a no-op when absent (never throws).
- `setLinkTags(linkId, tagIds[])` replaces the link's entire tag set with exactly the given ids in a single atomic operation: if any tag id in the list does not exist, the whole call throws and the link's existing tags are left unchanged.

### Read API

- `getTagsForLink(linkId)` returns the link's tags ordered by tag `name` ascending; a link with no tags returns an empty list.
- `getLinksForTag(tagId)` returns the links carrying that tag, ordered by `domain` then `key`.
- `getLinkWithTags(linkId)` returns the link row with its tags nested, assembled from a single relation-aware query; an unknown link returns `null`.
- `countLinksPerTag()` returns, for every tag, its `id`, `name`, and the number of links carrying it — **including tags used by zero links** (count `0`).

### Constraints & edge cases

- All filtering, joining, and counting must be performed by the database query, not by loading every row into memory and computing in JavaScript.
- Values passed into queries must be safely parameterized; building query fragments by string-concatenating caller input is not acceptable.
- Querying an unknown link or tag id returns an empty list (for list methods), never throws.

### Expected Functionality

- Tag `l1` with `t1`,`t2` and `l2` with `t2`; `getLinksForTag("t2")` -> `[l1, l2]` (domain/key order) and `getTagsForLink("l1")` -> `[t1, t2]` by name.
- Calling `tagLink("l1","t1")` twice leaves exactly one association.
- `setLinkTags("l1", ["t2"])` makes `getTagsForLink("l1")` -> `[t2]`; calling it with a missing tag id throws and leaves the previous set intact.
- A tag used by no links still appears in `countLinksPerTag()` with count `0`.

## Acceptance Criteria

- The new module builds and is importable from `apps/web/lib/links/tag-store`.
- `apps/web/package.json` declares `drizzle-orm` as a dependency.
- A deterministic vitest suite at `apps/web/tests/links/tag-store.test.ts` exercises: many-to-many navigation in both directions, single-round-trip nested loading, idempotent `tagLink`, no-op `untagLink`, atomic `setLinkTags` (including rollback when a tag id is missing), zero-link tags appearing with count `0`, unique tag-name rejection, store isolation, and unknown-id empty results.
- The suite runs fully in-memory with no network, filesystem, or external-service access and passes deterministically on repeated runs.
- The following command passes:

  ```bash
  cd apps/web && pnpm vitest run tests/links/tag-store.test.ts
  ```
