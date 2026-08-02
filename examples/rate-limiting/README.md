# Rate-limiting proving case

This fixture exercises the canonical steel thread from [`docs/seamwise.pdf`](../../docs/seamwise.pdf):

1. a policy schema is valid;
2. an effective policy resolves deterministically;
3. request 101 is denied when the effective limit is 100;
4. the denial exposes a stable reason and decision telemetry.

`recipe.yaml` is authored proposal data. The compiler validates and lowers it;
the fixture does not claim that the fictional target application is implemented.
`seamwise recipe example` materializes an exact SHA-256-pinned copy of that PDF
beside the editable recipe, so a wheel-only user can resolve and verify the
evidence without this source checkout or network access.
The end-to-end test records an explicit **fixture** review receipt, validates all
emitted Task-Specs, and asserts that none is sealed.
