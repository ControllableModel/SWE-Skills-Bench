# Task: Build a nested-list outline parser

## Background

The cheerio repository (`cheeriojs/cheerio`) is a Node.js HTML/XML parsing
library. This task adds a helper that converts a nested unordered list
(`<ul>`/`<li>`) into a tree of nodes using cheerio child traversal.

## Files to Create/Modify

- `src/api/outline.ts` (new) — export a `parseOutline(html, selector)` function.
- `src/api/outline.spec.ts` (new) — deterministic test cases.

## Requirements

### Function contract

Implement and export `parseOutline(html: string, selector: string)` that loads
`html`, locates the first `<ul>` matching `selector`, and returns an array of
node objects describing its nested structure.

### Node shape

Each node corresponds to a direct-child `<li>` of a `<ul>` and has:

- `text`: the `<li>`'s own immediate text, trimmed, EXCLUDING the text of any
  nested `<ul>` it contains. (Only the label of the item itself.)
- `children`: an array of child nodes parsed from the first nested `<ul>` that is
  a direct child of this `<li>`. If the `<li>` has no nested `<ul>`, `children`
  MUST be an empty array `[]`.

### Behavior and constraints

- Only direct-child `<li>` elements of a given `<ul>` become nodes (grandchild
  `<li>`s belong to their own nested level, not the parent level).
- The `text` MUST NOT include text contributed by descendant `<ul>` items; e.g.
  an `<li>` reading `Fruit<ul><li>Apple</li></ul>` has `text` `'Fruit'`.
- Trimming applies to each node's `text`.
- If the selector matches no `<ul>`, the function MUST return `[]`.
- Arbitrary nesting depth MUST be supported (the structure is recursive).

### Expected Functionality

- `<ul id="o"><li>A<ul><li>A1</li><li>A2</li></ul></li><li>B</li></ul>` with
  selector `#o` ->
  `[{ text: 'A', children: [{ text: 'A1', children: [] }, { text: 'A2', children: [] }] }, { text: 'B', children: [] }]`.
- A leaf `<li>` -> `children: []`.
- `parseOutline('<p>x</p>', 'ul')` -> `[]`.

## Acceptance Criteria

- `src/api/outline.ts` exports `parseOutline` with the contract above.
- `src/api/outline.spec.ts` covers: a two-level tree, a three-level (deeper)
  tree, a leaf node's empty `children`, the exclusion of nested text from a
  parent's `text`, direct-child-only selection, and the missing-selector empty
  result.
- The following command passes from the repo root:

  ```
  npx vitest run src/api/outline.spec.ts
  ```
