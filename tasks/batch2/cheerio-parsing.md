# Task: Build an HTML table parser

## Background

The cheerio repository (`cheeriojs/cheerio`) is a Node.js HTML/XML parsing
library. This task adds a standalone helper module that turns an HTML `<table>`
inside a parsed document into an array of row objects, using cheerio's own
loading and traversal API.

## Files to Create/Modify

- `src/api/table.ts` (new) — export a `parseTable(html, tableSelector)` function.
- `src/api/table.spec.ts` (new) — deterministic test cases for the new module.

## Requirements

### Function contract

Implement and export a function `parseTable(html: string, tableSelector: string)`
that loads `html` (a complete HTML string) with cheerio, locates the first
element matching `tableSelector`, and returns an array of plain objects — one
per body data row.

### Behavior and constraints

- The header keys MUST come from the text of the `<th>` cells inside the table's
  `<thead>` (in document order). Each header key MUST have surrounding
  whitespace removed.
- Each object in the result corresponds to one `<tr>` inside the table's
  `<tbody>`, in document order. The keys are the header strings; the value for
  each key is the trimmed text of the `<td>` at the same column index.
- If a row has fewer `<td>` cells than there are headers, the missing trailing
  keys MUST be present in the object with the empty string `''` as value.
- If a row has more `<td>` cells than there are headers, the extra cells MUST be
  ignored (no extra keys).
- If the selector matches no element, the function MUST return an empty array
  `[]` (it MUST NOT throw).
- A table that has a `<tbody>` with no `<tr>` rows MUST yield `[]`.
- Whitespace inside a cell (leading/trailing newlines or spaces) MUST be trimmed
  from the stored value.

### Expected Functionality

- A table with headers `Name`, `Price` and two body rows
  (`Apple`/`$1`, `Pear`/`$3`) -> `[{ Name: 'Apple', Price: '$1' }, { Name: 'Pear', Price: '$3' }]`.
- A row missing its second cell -> that header maps to `''`.
- `parseTable('<div></div>', 'table')` -> `[]`.

## Acceptance Criteria

- `src/api/table.ts` exports `parseTable` with the contract above.
- `src/api/table.spec.ts` contains deterministic cases covering: a multi-row
  table, a row with fewer cells than headers, a row with extra cells, a missing
  table selector, and whitespace trimming on both headers and cells.
- The following command passes from the repo root:

  ```
  npx vitest run src/api/table.spec.ts
  ```
