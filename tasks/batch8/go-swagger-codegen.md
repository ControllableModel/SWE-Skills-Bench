# Task: Add MIME-Type Aliases for `@Accept` / `@Produce`

## Background

`swaggo/swag` lets handler annotations name request/response media types with short aliases (e.g. `@Accept json` expands to `application/json`). The alias table lives in `operation.go` and is consulted by `parseMimeTypeList`, which underlies both `ParseAcceptComment` and `ParseProduceComment`. The current table omits several common content types, forcing authors to spell out the full MIME string. This task adds three widely used aliases.

## Files to Create/Modify

- `operation.go` (modify) — add new entries to the MIME-type alias table so the short forms below expand correctly.
- `operation_test.go` (modify) — extend the accept/produce tests (build on `TestParseAcceptComment` / `TestParseProduceComment`) to cover the new aliases.

## Requirements

### New Aliases

The following short aliases MUST resolve to the given full media types when used in `@Accept` or `@Produce`:

| Alias | Expands to |
| --- | --- |
| `csv` | `text/csv` |
| `yaml` | `application/x-yaml` |
| `pdf` | `application/pdf` |

### Behavior

- `@Accept csv` MUST append `text/csv` to the operation's consumed types.
- `@Produce yaml` MUST append `application/x-yaml` to the operation's produced types.
- A comma-separated list MUST resolve each entry independently, e.g. `@Accept json,csv` yields `application/json` then `text/csv` in order.
- A fully-qualified MIME type passed directly (matching `type/subtype`) MUST still pass through unchanged.
- An unknown alias that is neither a known alias nor a `type/subtype` string MUST still produce an error (unchanged behavior).

### Expected Functionality

| Annotation argument | Resulting list |
| --- | --- |
| `csv` (Accept) | `["text/csv"]` |
| `yaml` (Produce) | `["application/x-yaml"]` |
| `pdf` (Produce) | `["application/pdf"]` |
| `json,csv` (Accept) | `["application/json", "text/csv"]` |
| `bogus` | error |

## Acceptance Criteria

- Parsing `@Accept csv` leaves `operation.Consumes == []string{"text/csv"}`.
- Parsing `@Produce yaml` leaves `operation.Produces == []string{"application/x-yaml"}`.
- Parsing `@Produce pdf` leaves `operation.Produces == []string{"application/pdf"}`.
- Parsing `@Accept json,csv` leaves `operation.Consumes == []string{"application/json", "text/csv"}`.
- Parsing `@Accept bogus` returns a non-nil error.
- The pre-existing `TestParseAcceptComment` and `TestParseProduceComment` assertions continue to pass.
- The following command passes from the repository root:

  ```bash
  go test -run 'TestParseAcceptComment|TestParseProduceComment' ./...
  ```
