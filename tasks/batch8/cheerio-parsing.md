# Task: Build a metadata extractor for document head tags

## Background

The cheerio repository (`cheeriojs/cheerio`) is a Node.js HTML/XML parsing
library. This task adds a helper that reads page metadata out of a parsed
document's `<head>` using attribute-based selectors.

## Files to Create/Modify

- `src/api/metadata.ts` (new) — export an `extractMetadata(html)` function.
- `src/api/metadata.spec.ts` (new) — deterministic test cases.

## Requirements

### Function contract

Implement and export `extractMetadata(html: string)` that loads `html` and
returns an object summarizing the document's metadata.

### Result shape

The returned object MUST have these keys:

- `title`: the trimmed text of the `<title>` element, or `null` if absent.
- `description`: the `content` attribute of `<meta name="description">`, or
  `null` if that meta tag is absent.
- `canonical`: the `href` of `<link rel="canonical">`, or `null` if absent.
- `og`: an object mapping each Open Graph property to its content — built from
  every `<meta>` whose `property` attribute starts with `og:`. The keys MUST be
  the property string with the leading `og:` removed (e.g. `og:title` -> `title`).
  If there are no such tags, `og` MUST be an empty object `{}`.

### Behavior and constraints

- Attribute matching MUST be exact for `name="description"` and
  `rel="canonical"`.
- Whitespace around the title text MUST be trimmed.
- When multiple `og:` tags share the same property, the last one in document
  order wins.
- The function MUST NOT throw on a document missing any of these tags; absent
  scalar fields become `null` and `og` becomes `{}`.

### Expected Functionality

- A head with `<title> Home </title>`, `<meta name="description" content="Hi">`,
  `<link rel="canonical" href="/x">`, `<meta property="og:title" content="T">`
  -> `{ title: 'Home', description: 'Hi', canonical: '/x', og: { title: 'T' } }`.
- A document with none of these tags ->
  `{ title: null, description: null, canonical: null, og: {} }`.

## Acceptance Criteria

- `src/api/metadata.ts` exports `extractMetadata` with the contract above.
- `src/api/metadata.spec.ts` covers: full metadata extraction, all-absent
  defaults, title trimming, the `og:` prefix stripping, the last-wins rule for
  duplicate og properties, and an empty `og` object when no og tags exist.
- The following command passes from the repo root:

  ```
  npx vitest run src/api/metadata.spec.ts
  ```
