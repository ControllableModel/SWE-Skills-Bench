# Task: Build a Hierarchical Category Tree Layer

## Background

The TypeORM repository (`typeorm/typeorm`) verifies the ORM end-to-end with functional tests under `test/functional/` that run against an in-memory SQLite database via the repo's own public API. This task adds a self-contained "category tree" feature where categories nest arbitrarily deep, verified through that API.

## Files to Create/Modify

- `test/functional/category-tree/entity/Category.ts` (new) — the self-referential category record type.
- `test/functional/category-tree/tree-service.ts` (new) — a service constructed from a `DataSource` exposing the operations below.
- `test/functional/category-tree/category-tree.test.ts` (new) — the functional test that wires the entity into a testing `DataSource` and verifies every requirement.

Follow the existing conventions in `test/functional/` (see `test/functional/custom-repository/custom-repository.test.ts` and the existing tree tests under `test/functional/tree-tables/`): import decorators/types from the repo's own `src/` via relative paths, use `createTestingConnections`, `reloadTestingDatabases`, and `closeTestingConnections` from `../../utils/test-utils`, and assert with `chai`.

## Requirements

### Domain model

A **Category** has a database-generated numeric identity and a `name` string. A category may have one parent category and any number of child categories, forming a tree of arbitrary depth. The hierarchy must be persisted as a self-referential structure that the ORM can reconstruct into nested parent/child objects, not flattened into a single denormalized column.

### Tree service

`tree-service.ts` must export a class (or factory) built from a `DataSource` providing at least:

- **addRoot(name)** — persists a new top-level category (no parent) and returns it with its generated id.
- **addChild(parentId, name)** — persists a new category as a child of the given parent and returns it.
- **getSubtree(categoryId)** — returns the category with its full descendant hierarchy attached as nested children (children, grandchildren, and so on), reconstructed by the ORM rather than assembled by issuing one query per node in application code.
- **getAncestors(categoryId)** — returns the chain of ancestors from the given category up to its root.
- **getRoots()** — returns all top-level categories (those without a parent).

### Constraints

- The test must run without any external database server: enable only the SQLite-based driver(s) when creating the testing connections.
- The schema must be derived from the record-type definition by the ORM during test setup; no hand-written `CREATE TABLE` SQL.
- The descendant/ancestor retrieval must be performed by the ORM's tree-aware loading, not by an application-level recursion that issues a separate query per node.

### Expected Functionality

- Building a three-level tree (root → child → grandchild), then `getSubtree(root)` → returns the root with the child nested beneath it and the grandchild nested beneath the child.
- `getAncestors(grandchild)` → returns the grandchild's ancestor chain including its parent and the root.
- `getRoots()` over a forest with two roots → returns exactly the two roots and none of their descendants.
- Adding a child under a parent → that child appears in the parent's subtree and reports the parent as its ancestor.

## Acceptance Criteria

- The three files exist under `test/functional/category-tree/`; entity and service are imported by the test from the repo's own `src/` and `utils`.
- All scenarios in **Expected Functionality** are asserted and pass against the SQLite driver.
- An implementation that flattens the hierarchy into a denormalized path string, or that rebuilds the tree by issuing one query per node, must fail at least one assertion.
- The test compiles and passes. From the repo root:

```bash
pnpm run compile && npx mocha ./build/compiled/test/functional/category-tree/category-tree.test.js
```
