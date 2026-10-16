# Task: Harden the server-side RPC error translation layer

## Background

In etcd's v3 RPC server (`server/etcdserver/api/v3rpc`), every handler funnels the
errors it produces through a single translation function, `togRPCError`, before they
leave the process and travel back to a client. This function is the only place where
internal domain errors are turned into the over-the-wire errors that clients inspect
to decide how to react. This task hardens that translation layer so it behaves
correctly for two cases it currently mishandles.

## Files to Create/Modify

- `server/etcdserver/api/v3rpc/util.go` (modify) — the `togRPCError` translation function.
- `server/etcdserver/api/v3rpc/util_test.go` (modify) — extend `TestGRPCError` (and/or add a sibling test) to cover the new behavior.

## Requirements

### Current behavior to preserve

The translation currently maps a fixed set of internal domain errors (the entries in
`toGRPCErrorMap`) to their corresponding over-the-wire errors, leaves the two context
errors (`context.Canceled`, `context.DeadlineExceeded`) untouched, and turns anything
unrecognized into an opaque error. All of the existing mappings and the existing
`TestGRPCError` expectations MUST continue to pass unchanged.

### Wrapped-error translation

Handlers do not always pass a known domain error directly — an error may have been
annotated with additional context as it propagated up the call stack (for example, an
internal error joined or wrapped with surrounding context, while still carrying one of
the known sentinel domain errors in its chain).

- When the error passed to `togRPCError` is not itself a key in the mapping table but
  *contains* a known domain error somewhere in its chain, the translation MUST resolve
  to the same over-the-wire result that the unwrapped domain error would have produced.
- The same rule applies to the two context errors: an error that wraps
  `context.Canceled` or `context.DeadlineExceeded` MUST be treated identically to the
  bare context error (i.e. returned so the surrounding machinery converts it to the
  appropriate transport-level outcome), rather than being flattened.
- Resolution MUST prefer the most specific match: if the error chain contains a known
  domain error, that mapping wins; the fallback path is taken only when no known
  domain error and no context error is present anywhere in the chain.

### Preserving an already-classified error

Some errors that reach the translation function already carry a fully-formed transport
classification (i.e. they were produced as a transport-level error with an explicit,
non-generic classification attached). Today, any error that is not found in the mapping
table is collapsed into a single opaque "unknown" classification, discarding whatever
actionable classification it already carried.

- When an unmapped error already carries an explicit, non-generic transport
  classification, `togRPCError` MUST return it unchanged so that classification reaches
  the client intact.
- An unmapped error that carries no transport classification (a plain Go error), or one
  whose only classification is the generic/unknown one, MUST still be turned into an
  opaque "unknown" error exactly as before, so that clients are never handed a plain Go
  error string with no actionable classification.

### Edge cases

- A `nil` error MUST translate to `nil`.
- The behavior MUST be driven by the error chain and the carried classification — not by
  string matching on error messages.

### Expected Functionality

- Known domain error wrapped with extra context -> same over-the-wire result as the bare domain error.
- `context.Canceled` / `context.DeadlineExceeded` wrapped with extra context -> handled like the bare context error.
- Unmapped error already carrying a specific transport classification -> returned unchanged, classification preserved.
- Unmapped plain Go error (no classification, or only the generic one) -> opaque "unknown" error, as today.
- Recognized bare domain error -> existing mapping, unchanged.
- `nil` -> `nil`.

## Acceptance Criteria

- The existing `TestGRPCError` cases continue to pass.
- New test cases prove that:
  - an error wrapping a known domain error resolves to that domain error's over-the-wire result;
  - an error wrapping a context error is preserved (not flattened to the opaque "unknown" result);
  - an unmapped error that already carries a specific, non-generic transport classification is returned unchanged with that classification intact;
  - an unmapped plain Go error (and an error whose classification is only the generic/unknown one) still becomes the opaque "unknown" result;
  - `nil` translates to `nil`.
- The package builds and its tests pass. The following command, run from the repository root, MUST succeed:

  ```
  cd server && go test ./etcdserver/api/v3rpc/ -run TestGRPCError -count=1 -v
  ```

  (If the new cases are placed in a separate test function, widen the `-run` pattern to include it, e.g. `-run 'TestGRPCError|TestGRPCErrorWrapped'`.)
