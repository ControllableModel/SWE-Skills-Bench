# Task: Add a case-insensitive search for query snippets within an organization

## Background
Redash (`redash/models/__init__.py`) stores `QuerySnippet` records, each scoped to an organization and carrying a `trigger` and a `description`. The model already exposes `QuerySnippet.all(org)`, which returns every snippet in an organization, but there is no way to search snippets by a free-text term.

## Files to Create/Modify
- `redash/models/__init__.py` (modify) — add a new classmethod on the `QuerySnippet` model that searches an org's snippets by term.
- `tests/models/test_query_snippets.py` (new) — add a test module (using `tests.BaseTestCase` and `self.factory`) that exercises the new classmethod against seeded data.

## Requirements

### New classmethod
Add a classmethod to the `QuerySnippet` model with this exact signature:

```python
@classmethod
def search(cls, org, term):
    ...
```

It must return an iterable of `QuerySnippet` rows belonging to the given `org` whose `trigger` or `description` matches `term`.

### Matching rules
- The match must be a case-insensitive substring match: a snippet qualifies when `term` appears (ignoring letter case) anywhere inside its `trigger` **or** anywhere inside its `description`.
- Only snippets belonging to the given `org` may appear. A matching snippet in a different organization must never appear.
- A snippet must appear at most once even if `term` matches both its `trigger` and its `description`.

### Edge cases
- If no snippet matches, the result must be empty when wrapped in `list(...)`.
- An empty `term` matches every snippet in the org (an empty string is a substring of any string), and only those in the given org.
- The method must not mutate the database and must accept exactly two arguments beyond `cls` (`org` and `term`).

### Expected Functionality
- Snippet with trigger `"sum_sales"` and snippet with description containing `"SUMmary"` → searching `"sum"` returns both.
- Searching `"SUM"` (uppercase) returns the same matches as searching `"sum"`.
- A snippet in a different org whose trigger contains the term → it does not appear.
- A snippet matching on both trigger and description → it appears exactly once.

## Acceptance Criteria
- `QuerySnippet.search(org, term)` exists as a classmethod and returns an iterable of `QuerySnippet` objects matching the term case-insensitively on trigger or description, scoped to the given org.
- Snippets from other organizations are excluded, and a snippet that matches multiple fields appears only once.
- An empty term yields all snippets in the org; a non-matching term yields an empty result.
- The added tests in `tests/models/test_query_snippets.py` pass. Run, from the repository root:

  ```
  pytest tests/models/test_query_snippets.py
  ```
