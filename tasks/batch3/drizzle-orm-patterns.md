# Task: Build an In-Memory Folder Hierarchy and Permission Store

## Background

The dub monorepo (`apps/web`) is a link-management platform; `apps/web/lib/folder/` holds folder helpers including `permissions.ts`, and the product organizes links into nestable folders with per-member access roles. This task adds a self-contained, embedded store that models a folder tree plus member permissions entirely in-process, so hierarchy and access logic can be unit-tested without the production database or any network service.

## Files to Create/Modify

- `apps/web/lib/folder/folder-store/schema.ts` (new) — table and relation definitions plus the inferred row types.
- `apps/web/lib/folder/folder-store/store.ts` (new) — the `FolderStore` class implementing the public API below, backed by an embedded SQLite database opened with the `better-sqlite3` driver (already available in the workspace).
- `apps/web/lib/folder/folder-store/index.ts` (new) — re-exports the store, its factory, and the public types.
- `apps/web/package.json` (modify) — add the `drizzle-orm` runtime dependency required to build the store.
- `apps/web/tests/folders/folder-store.test.ts` (new) — vitest suite covering the behavior and edge cases below.

> The store must run against an in-memory database (e.g. constructed from `":memory:"`) so tests never hit a network, file, or external service. Do not reuse the Prisma client or the live API; this module stands alone.

## Requirements

### Data model

Model two entities inside the embedded database:

- **folders** — `id` (string, primary key), `name` (string, required), `parentId` (string or null, referencing another folder; `null` means a top-level root folder).
- **folder_access** — grants for a member on a folder: `folderId` (string, required, referencing a folder), `userId` (string, required), `role` (one of exactly `"viewer"`, `"editor"`, `"owner"`). A user has at most one grant per folder; the (folder, user) pair identifies the grant.

The model must express that a folder may have a parent and many children (a self-referencing relationship), and that a folder has many access grants. Row types used by `store.ts` must be derived from the table definitions themselves — hand-written interfaces that can silently drift from the columns are not acceptable. The `role` column must constrain values to the three allowed roles at the type level.

### Construction and lifecycle

- A factory (e.g. `createFolderStore()`) returns a fresh, empty store backed by a new in-memory database with both tables created.
- Each new store is fully isolated.

### Write API

- `addFolder(input)` inserts one folder and returns it. A non-null `parentId` that does not reference an existing folder must throw, and no row is created.
- `grantAccess(folderId, userId, role)` upserts a grant: if the (folder, user) pair already has a grant, its role is updated in place rather than duplicated.
- `revokeAccess(folderId, userId)` removes the grant if present and is a no-op otherwise.

### Read API

- `getChildren(folderId)` returns the direct children of a folder ordered by `name`; a leaf folder returns an empty list.
- `getDescendantIds(folderId)` returns the ids of all folders beneath the given folder at any depth (children, grandchildren, ...), excluding the folder itself, computed by the database in a single recursive traversal rather than repeated per-level queries from JavaScript.
- `getAccessibleFolders(userId)` returns the folders for which the user holds any grant, each paired with the user's `role`, ordered by folder `name`.
- `getEffectiveRole(folderId, userId)` returns the user's role on a folder, or `null` if the user has no grant on it.

### Constraints & edge cases

- `getDescendantIds` on a leaf returns an empty list; the implementation must not loop forever and must work for trees several levels deep.
- All filtering and traversal must be performed by the database query, not by loading every folder into memory and walking the tree in JavaScript.
- Values passed into queries must be safely parameterized; string-concatenating caller input into SQL is not acceptable.
- Unknown folder or user ids yield empty lists / `null`, never throw.

### Expected Functionality

- Build `root -> a -> b -> c` and `root -> d`; `getChildren("root")` -> `[a, d]` by name; `getDescendantIds("root")` -> `{a, b, c, d}`; `getDescendantIds("c")` -> `[]`.
- `grantAccess("a","u1","viewer")` then `grantAccess("a","u1","owner")` leaves exactly one grant with role `"owner"`; `getEffectiveRole("a","u1")` -> `"owner"`.
- `getAccessibleFolders("u1")` lists only folders where `u1` has a grant, each with its role.
- Adding a folder whose `parentId` points at a non-existent folder throws and creates no row.

## Acceptance Criteria

- The new module builds and is importable from `apps/web/lib/folder/folder-store`.
- `apps/web/package.json` declares `drizzle-orm` as a dependency.
- A deterministic vitest suite at `apps/web/tests/folders/folder-store.test.ts` exercises: self-referencing parent/child loading, multi-level descendant traversal computed in-database, role-constrained grants, upsert-on-conflict role updates (no duplicate grants), no-op revoke, accessible-folder listing with role, `getEffectiveRole` returning `null` when no grant exists, invalid-parent rejection, store isolation, and unknown-id empty/`null` results.
- The suite runs fully in-memory with no network, filesystem, or external-service access and passes deterministically on repeated runs.
- The following command passes:

  ```bash
  cd apps/web && pnpm vitest run tests/folders/folder-store.test.ts
  ```
