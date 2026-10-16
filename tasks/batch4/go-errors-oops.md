# Task: Build a Structured Error JSON-Envelope Module

## Background

The `samber/oops` repository ships several self-contained demonstration modules under `examples/` (each its own Go module, wired into the workspace via `go.work`). This task adds a new example module, `examples/envelope`, that converts a rich failure into a stable JSON envelope suitable for an API response or log line, driven entirely by the structured metadata carried on the error.

## Files to Create/Modify

- `examples/envelope/envelope.go` (new) — the failure producer and the envelope builder.
- `examples/envelope/envelope_test.go` (new) — the deterministic tests described below.
- `examples/envelope/go.mod` (new) — module `github.com/samber/oops/examples/envelope`, Go 1.21, requiring `github.com/samber/oops`.
- `go.work` (modify) — add `./examples/envelope` to the `use (...)` block.

## Requirements

The module produces an error and then renders it into a deterministic, JSON-serializable map. No network or server is involved.

### Failure producer

Provide an exported function that returns a non-nil error carrying a full set of structured metadata:

```go
func LookupAsset(assetID string) error
```

When `assetID == "known"` it returns `nil`. For any other value it returns a `samber/oops` error that carries: a machine-readable code `"asset_missing"`, a domain `"asset-registry"`, a user-safe public message `"The requested asset is unavailable."`, at least one categorization tag `"registry"`, and a context attribute `"asset_id"` equal to the supplied id.

### Envelope builder

Provide:

```go
func Envelope(err error) map[string]any
```

`Envelope` MUST return a map derived from the error's structured accessors (NOT from parsing `err.Error()`), shaped exactly as:

- key `"code"` -> the error's machine-readable code (string).
- key `"message"` -> the error's user-safe public message.
- key `"domain"` -> the error's domain.
- key `"tags"` -> a `[]string` of the error's tags.
- key `"context"` -> a `map[string]any` of the error's structured context.

If `err` is `nil`, `Envelope` MUST return `nil`. If `err` is a non-oops error, `Envelope` MUST still return a map with `"code"` set to the empty string and `"message"` set to `err.Error()` (the remaining keys may be empty/zero values).

### Determinism / round-trip

The map returned by `Envelope` MUST be JSON-serializable via `encoding/json` without error, and serializing the same error twice MUST yield byte-identical JSON. The `"message"` value MUST be the static public message and MUST NOT contain the variable `asset_id`; the variable id MUST appear only under `"context"`.

### Expected Functionality

- `Envelope(LookupAsset("known"))` -> `nil`.
- `Envelope(LookupAsset("xyz"))` -> map with `code == "asset_missing"`, `message == "The requested asset is unavailable."`, `domain == "asset-registry"`, `tags` containing `"registry"`, `context["asset_id"] == "xyz"`.
- `Envelope(errors.New("boom"))` -> map with `code == ""`, `message == "boom"`.
- `json.Marshal(Envelope(LookupAsset("a")))` and a second marshal of `Envelope(LookupAsset("a"))` produce identical bytes.

## Acceptance Criteria

- `examples/envelope/go.mod` declares module `github.com/samber/oops/examples/envelope` and `go.work` lists `./examples/envelope`.
- A naive implementation that string-parses the error message, or that puts the asset id into `"message"`, fails the tests.
- The added tests are deterministic and pass:

```
go test ./examples/envelope/...
```

  run from the repository root, including the nil case, the oops case (all five keys verified), the plain-error fallback case, and a JSON round-trip stability assertion.
