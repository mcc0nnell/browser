# Scumm3 → Sandia TalkPipe → Lightpanda AX evidence

A small read-only local experiment. It uses the **actual** Scumm3
`integrations.talkpipe.scumm3_bridge` and the vendored Sandia TalkPipe
`Pipeline` / `AbstractSource` / `AbstractSegment` implementations.

This is not a new browser transport, a WPT runner implementation, a
signed Scumm3/Atlas admission, or a production deployment.

## Execution

1. Scumm3 admits a **locally constructed synthetic** request limited to
   `read` and `transform`. It is deliberately **not** an authorized
   production lease.
2. The read capability loads only six explicitly allowlisted Lightpanda
   synthetic test receipts, with content-digest checks and a maximum size.
   The evidence contains no credentials or third-party browsing data.
3. Three `read` steps produce bounded `post4036`, `post4129`, and
   `bridge` artifacts through the Sandia Pipe API.
4. One `transform` step cross-checks browser binary hashes, four
   pinned WPT-derived expectations, individual test outcomes, and the
   existing WebDriver `no such element` guard. Its handler raises an
   error if the receipts disagree; it does not rely on unimplemented
   assertion semantics.
5. The same request runs through Scumm3's `--stdio` adapter to verify
   transport compatibility. A deterministic, nonsecret run receipt
   records the stage trace and results.

```sh
# Run on Butcher or another host with an installed Scumm3 checkout.
export SCUMM3_SOURCE=/absolute/path/to/scumm3
export PYTHONPATH="$PWD:$SCUMM3_SOURCE/vendor/talkpipe/src:$SCUMM3_SOURCE/vendor/parsy/src:$SCUMM3_SOURCE"
python -m unittest scumm3_lightpanda.test_pipeline -v
python -m scumm3_lightpanda.run
```

Run the commands from `benchmarks/aria-semantic-tree`. Install the Python
dependencies listed in Scumm3's
`integrations/talkpipe/requirements-ci.txt` first, or use a compatible
local environment. This does not invoke GitHub Actions or ProofShot.

Output: [`results/scumm3-talkpipe-lightpanda.json`](../results/scumm3-talkpipe-lightpanda.json).

## What it verified

| Pinned interface projection | After #4036 | At benchmarked #4129 commit |
| --- | --- | --- |
| CDP | 4/4 | 4/4 |
| MCP | 0/4 | 4/4 |

The experimental WebDriver computed AX bridge separately has 4/4 checks
and returns 404 for an invalid element. The official WPT runner still
records **zero passing tests** after stopping at `POST /window/new`.

Scumm3 adds a capability-limited, attributable evidence transformation.
It does **not** make these WPT-derived projections official WPT passes,
grant mutation authority, or replace the browser's computed AX model.

## Limits

- Locally constructed synthetic lease metadata is an input to Scumm3's
  authoring adapter, **not an Atlas/Shell-approved admission**.
- No browser instances, models, hosts, or network services are called by
  the capabilities. The inputs are existing local synthetic receipts.
- Capabilities cannot execute shell commands, navigate arbitrary paths,
  make outbound requests, merge PRs, or deploy.
- The fixed four-case corpus is an engineering smoke test, not an
  accessibility conformance score or agent-success benchmark.
- Scumm3 source and TalkPipe source are *referenced*, not copied or
  modified by this experiment.
