# Architecture

The project uses a ports-and-adapters boundary without imposing a framework on callers.

## Python runtime

The shipped runtime owns deterministic behavior:

1. Pydantic validates the stable Dashboard Studio envelope.
2. The Enterprise profile registry evaluates versioned capabilities.
3. Native validators inspect SPL, DOS, references, canvas bounds, and search graphs.
4. Generators emit canonical JSON with deterministic identifiers.
5. Graph analysis emits immutable optimization proposals and never rewrites a query implicitly.

Splunk-owned visualization and input option dictionaries remain deliberate extension boundaries.
The official schema is better suited to exact option-level validation and runs as a second CI lane.

## CI-only official engine

The official engine adapter is isolated under `.github/ci/npm-validator`:

- Each engine has an exact dependency lock.
- Node is provisioned by GitHub Actions.
- Schema generation runs once per engine profile.
- Dashboard requests cross the process boundary as JSONL through standard input.
- The runner has read-only repository permissions and no secrets.

The adapter is never imported by the Python package. Hatch build inclusion rules and an artifact
inspection gate prevent CI assets from entering the wheel or source distribution.

## Validation authority

Neither validator is treated as a complete oracle:

- The official schema owns exact visualization and input option shapes.
- Python owns product-version policy and cross-object semantics that the NPM validator does not
  consistently enforce, such as chain cycles and missing data-source references.

A dashboard is release-ready only when every required lane agrees with its declared expectation.

## Search-chain limits

The native graph policy follows Splunk Enterprise's documented Dashboard Studio limits: at most
10 direct chain searches from a base search, at most one additional chained level, and no
`queryParameters`, `refresh`, or `refreshType` overrides on a chain. See Splunk's
[base and chain search documentation](https://help.splunk.com/en/splunk-enterprise/create-dashboards-and-reports/dashboard-studio/9.4/use-data-sources/chain-searches-together-with-a-base-search-and-chain-searches).
