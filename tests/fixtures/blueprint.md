# Rate-limiting steel thread (test evidence fixture)

Synthetic evidence source for `rate-limiting-recipe.yaml`. It exists so the
proving fixture has a real local file to hash, and so source verification,
digest mismatch, and tamper rejection can be exercised without depending on
a large binary document.

## Steel thread order

1. A versioned policy schema rejects invalid limits and windows.
2. Resolution produces exactly one effective policy for an organization.
3. Request 101 is denied after 100 allowed requests in the same window.
4. The denial returns a stable reason and emits matching decision telemetry.

## Boundaries

- Provider-owned usage metering is out of scope.
- Production storage and deployment infrastructure are not selected here.

This file is fixture input. It is not documentation of shipped behavior.
