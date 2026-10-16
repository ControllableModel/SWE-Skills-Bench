# Task: Build a Paginated Catalog Query Module

## Background

The `hono` repository ships small, self-contained helper modules under `src/helper/` (for example `src/helper/route/` and `src/helper/accepts/`), each exporting a focused feature plus a colocated `index.test.ts`. This task adds a new helper module that serves a read-only product catalog with query-driven filtering, sorting, and pagination.

## Files to Create/Modify

- `src/helper/catalog/index.ts` (new) — the catalog query module.
- `src/helper/catalog/index.test.ts` (new) — the deterministic test suite for the module.

## Requirements

### Module Surface

The module must export a factory function named `createCatalog(items)` that accepts an array of products, where each product is `{ "id": string, "name": string, "price": number, "category": string }`. Calling it returns a fresh sub-application instance that serves a read-only view over the supplied items. The returned value must be mountable into a parent application under an arbitrary prefix. Two separate calls hold independent item sets.

### Routes and Behavior

A single listing route at the collection root reads query parameters to filter, sort, and paginate. The contract must hold both directly and when mounted under a non-empty prefix.

#### Listing
- A `GET` request to the collection root returns `200` with a JSON body `{ "items": [...], "total": <number>, "page": <number>, "pageSize": <number> }`. `total` is the number of items matching the active filters (before pagination); `items` is the current page slice.
- `page` defaults to `1` and `pageSize` defaults to `10` when those query parameters are absent. When present, they override the defaults.
- Pagination is `1`-based: `page=2` with `pageSize=2` returns matching items at index `2` and `3` (zero-based) of the filtered result.

#### Filtering
- A `category` query parameter restricts results to items whose `category` equals that exact value.
- A `maxPrice` query parameter restricts results to items whose `price` is less than or equal to that numeric value.
- When both filters are present, only items satisfying both are included.

#### Sorting
- A `sort` query parameter of `price` orders the filtered items by ascending `price`; a value of `-price` orders by descending `price`. Sorting is applied before pagination. When `sort` is absent, the original input order is preserved.

#### Validation
- If `page` or `pageSize` is present but not a positive integer, the request returns `400` with a JSON body `{ "error": <string> }`.

### Constraints and Edge Cases

- `total` reflects the filtered count, not the page slice length.
- Requesting a `page` beyond the available results returns `200` with an empty `items` array and the correct `total`.
- `category` matching is exact and case-sensitive.
- All behavior must be verifiable through in-memory request dispatch (no network, no external services).

### Expected Functionality

- catalog of 5 items, `GET /?pageSize=2&page=2` -> `items` has the 3rd and 4th items, `total` is `5`.
- `GET /?category=books` -> only book items, correct `total`.
- `GET /?sort=-price` -> items ordered by descending price.
- `GET /?maxPrice=10&category=books` -> items in both constraints.
- `GET /?page=0` -> `400`.

## Acceptance Criteria

- `src/helper/catalog/index.ts` exports `createCatalog`, which returns a value mountable into a parent application, serving a read-only view with query-driven filtering, sorting, and pagination.
- All listing, default, filtering, sorting, pagination, and validation behaviors above are satisfied, verified by dispatching in-memory requests against both a directly-used and a mounted instance.
- A naive implementation (e.g. ignoring pagination, returning page-slice length as `total`, dropping filters, or skipping `page`/`pageSize` validation) must fail the test suite.
- The colocated test suite contains at least 10 distinct test cases and passes with:

```
npx vitest --run src/helper/catalog/index.test.ts
```
