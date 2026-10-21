# Lightpanda ARIA semantics benchmark

Local synthetic benchmark of native Lightpanda MCP `tree` state visibility before and after #4036 / #4129. **Not an official WPT run, LLM agent performance measurement, WCAG audit, or browser speed comparison.**

| Build | Commit | MCP states visible | 40 deterministic tasks complete | WPT-derived CDP | WPT-derived MCP |
|---|---|---:|---:|---:|---:|
| Older build, October 18 | `0bef9e72` | 0/19 | 20/40 | 0/4 | 0/4 |
| Exact #4036 merge | `463360ad` | 0/19 | 20/40 | **4/4** | 0/4 |
| #4129 benchmarked commit | `725ff748` | **19/19** | **40/40** | **4/4** | **4/4** |

The 40 tasks are four types of control with ten examples each. Half start in the target state. A deterministic policy gets one MCP tree read; it clicks a supplied selector only if a state is explicitly false/collapsed, and otherwise abstains. A final MCP evaluate checks the DOM only after decisions. Three runs per build agree. A real agent might recover hidden states with raw HTML or extra calls. This is **state availability**, not a real-agent success-rate improvement.

The four WPT-derived cases are from [wai-aria/checked/checked.tentative.html](https://github.com/web-platform-tests/wpt/blob/b4b303c8dca22989c43e2d76fce199c36d4b77a7/wai-aria/checked/checked.tentative.html), pinned to WPT revision `b4b303c8dca22989c43e2d76fce199c36d4b77a7`. Source SHA-256: `ccb8b47e2e8ce79cf3713b61338a12f9f5e95c1c0318ae896f98713e517bef13`. The adapter parses WPT metadata and tests equivalent local markup through MCP, **not the WPT WebDriver/testdriver harness**. WPT [aamtests](https://web-platform-tests.org/writing-tests/aamtest.html) instead verify platform accessibility API mappings.

To reproduce, build the three exact git commits with the Lightpanda Zig 0.17/V8 toolchain, verify executable version/SHA-256, and run Python 3.12+ standard library and Node.js 22 commands:

```sh
python3 benchmark.py --binary /path/to/older/lightpanda --label pre4129 --samples 5
python3 workflows.py --binary /path/to/older/lightpanda --label pre4129 --samples 3
python3 wpt_smoke.py --binary /path/to/older/lightpanda --label pre4129
node cdp_aria.mjs /path/to/older/lightpanda pre4129
# Repeat all four commands with label post4036 and binary 463360ad.
# Repeat all four with label post4129 and binary 725ff748.
python3 report.py
```

Review `results/summary.csv`, `results/summary.json` and individual receipt JSON for exact hashes, tree strings, state decisions, click counts and timings. Binaries are not committed. The October 18 snapshot includes unrelated upstream changes, but exact #4036 controls that confound; its CDP changes did not directly add MCP state exposure. Timings are low-sample diagnostics, not a performance claim. **Known discrepancy:** MCP `tree` can still include inert controls ignored by CDP. Next work: model-driven held-out tasks with normal fallback tools, cost accounting, and official WPT where a compliant driver exists.

No WPT PR was submitted. Review the WPT [LLM contribution policy](https://web-platform-tests.org/writing-tests/ai-policy.html) before proposing any upstream WPT additions.

## WPT integration and model-driven pilot — October 21, 2026

The separate [model-driven pilot](model_pilot.py) used the authenticated Codex CLI (`gpt-6-astra` as reported by the tool) in read-only, ephemeral mode. It tested a NEW, deterministic 12-control held-out fixture with real MCP tree, optional HTML fallback, actual click calls and final DOM scoring. Both versions achieved **12/12**. Exact merged #4036 required **two** model decisions, 9 MCP calls and HTML fallback; benchmarked #4129 commit `725ff748` required **one** model decision, 8 MCP calls and no fallback. Reported tokens were 5,502 versus 2,513. A single small synthetic fixture is NOT a statistical agent-success benchmark or a measured cost improvement.

Reproduce with authenticated Codex CLI and verified binaries:

```sh
python3 model_pilot.py --binary /path/to/post4036/lightpanda --label post4036
python3 model_pilot.py --binary /path/to/post4129/lightpanda --label post4129
```

**Genuine WPT-authored pages:** The [WPT page pilot](wpt_page_pilot.py) used upstream `./wpt serve` with an isolated loopback config and temporarily swapped in Lightpanda's [custom WPT reporter](lightpanda-testharnessreport.js). The original reporter was restored after execution. WPT revision `6f22f9eab8830478cc0cc9c67ad9004a044c5969` reported **101 Pass / 20 Fail** for `wai-aria/idlharness.window.html` (notably missing `ariaNotify` and ARIA element-reference APIs). The checked-state WPT page reported four failures because the `test_driver.get_accessibility_properties_for_element` hook was unavailable. Both Lightpanda builds matched these outcomes. These are actual WPT pages and testharness.js, but **not official wptrunner results**.

**Experimental upstream wptrunner product:** The [external Lightpanda product plugin](wpt-product/) registers Lightpanda without modifying upstream WPT. Lightpanda successfully returned WebDriver `/status` and `/session` responses; upstream `wptrunner` launched the browser and issued `test_start` for the ARIA IDL test. It then failed with `unknown command` on `POST /session/{sessionId}/window` (HTTP 404). See the [probe receipt](results/wptrunner-integration-probe.json). **No official WPT test passed through wptrunner.** The normal `./wpt run` frontend also enforces WPT host-file setup; the direct runner was used with local host overrides and without system host mutations.

**Remaining integration work:** implement the WebDriver switch-window operation; wire WPT's accessibility-property testdriver action to real browser accessibility data; and expose operating-system accessibility APIs (e.g. AT-SPI on Linux) before enabling WPT `aamtest`. The plugin deliberately does not advertise `aamtest`. Do not count MCP/CDP state projections as official WPT conformance.

## WebDriver window-switch follow-up

The separate branch `feat/webdriver-switch-window-20261021` adds W3C `POST /session/{id}/window` for the existing browsing context and rejects unknown handles. With that binary the direct WPT runner advances beyond `close_old_windows`, but now fails at **`POST /session/{id}/window/new`**, since Lightpanda currently supports only one top-level browsing context. See [the after-switch receipt](results/wptrunner-after-switch-probe.json). Do not claim the runner has completed a test.

## Experimental computed-AX WebDriver bridge

In [fork branch `feat/wpt-accessibility-bridge-20261021`](https://github.com/mcc0nnell/browser/tree/feat/wpt-accessibility-bridge-20261021), commit `d745d082`, a **nonstandard** WebDriver endpoint, `GET /session/{id}/element/{id}/accessibility`, returns computed CDP AX nodes from the *same live WebDriver session* and validates WebDriver element references. The [external WPT browser plugin](wpt-product/) maps that output to the `get_accessibility_properties_for_element` action's role, label and checked fields. This is not an operating-system accessibility API.

With [the bridge probe](bridge_probe.py), four pinned WPT checked-property expectations all matched the native computed AX values (absent→false, true, false, mixed); an invalid element returned HTTP 404 `no such element`. [Receipt](results/webdriver-ax-experimental-web-driver-ax-bridge.json). The plugin's mixed-state mapping was separately unit-checked. **This is WPT-sourced test data through an experimental extension, not an official WPT or `aamtest` result.** The official runner remains blocked at `POST /window/new` because Lightpanda does not yet support multiple top-level browsing contexts. The bridge is **not proposed for upstream merge** without maintainer input on vendor endpoint design.

Reproduce with the binary built at `d745d082` and the pinned local WPT source fixture:

```sh
python3 bridge_probe.py --binary /path/to/lightpanda --label webdriver-ax-experimental
```

## Scumm3 + TalkPipe evidence experiment

A read-only [Scumm3/TalkPipe adapter](scumm3_lightpanda/README.md) now
reconciles the pinned CDP, MCP, and experimental WebDriver AX evidence
through **Scumm3's real Sandia TalkPipe Pipe API**. The four-step pipeline
verifies record hashes, matching browser identities and WPT-derived
expectations, then checks that the official runner still reports zero
passes because `window/new` is unsupported.

The [local execution receipt](results/scumm3-talkpipe-lightpanda.json)
records the stage trace and the Scumm3 standard-input bridge completion.
This used only a local synthetic lease and read/transform capabilities:
**no approved Atlas/Shell admission, no browser or repository mutations,
and no official WPT conformance claim.** Six adapter-specific policy
tests and six unchanged Scumm3 bridge regressions passed locally.
