# Lightpanda ARIA semantics benchmark

Local synthetic benchmark of native Lightpanda MCP `tree` state visibility before and after #4036 / #4129. **Not an official WPT run, LLM agent performance measurement, WCAG audit, or browser speed comparison.**

| Build | Commit | MCP states visible | 40 deterministic tasks complete | WPT-derived checks |
|---|---|---:|---:|---:|
| Older build, October 18 | `0bef9e72` | 0/19 | 20/40 | 0/4 |
| Exact #4036 merge | `463360ad` | 0/19 | 20/40 | 0/4 |
| #4129 head (unmerged) | `725ff748` | **19/19** | **40/40** | **4/4** |

The 40 tasks are four types of control with ten examples each. Half start in the target state. A deterministic policy gets one MCP tree read; it clicks a supplied selector only if a state is explicitly false/collapsed, and otherwise abstains. A final MCP evaluate checks the DOM only after decisions. Three runs per build agree. A real agent might recover hidden states with raw HTML or extra calls. This is **state availability**, not a real-agent success-rate improvement.

The four WPT-derived cases are from [wai-aria/checked/checked.tentative.html](https://github.com/web-platform-tests/wpt/blob/b4b303c8dca22989c43e2d76fce199c36d4b77a7/wai-aria/checked/checked.tentative.html), pinned to WPT revision `b4b303c8dca22989c43e2d76fce199c36d4b77a7`. Source SHA-256: `ccb8b47e2e8ce79cf3713b61338a12f9f5e95c1c0318ae896f98713e517bef13`. The adapter parses WPT metadata and tests equivalent local markup through MCP, **not the WPT WebDriver/testdriver harness**. WPT [aamtests](https://web-platform-tests.org/writing-tests/aamtest.html) instead verify platform accessibility API mappings.

To reproduce, build the three exact git commits with the Lightpanda Zig 0.17/V8 toolchain, verify executable version/SHA-256, and run Python 3.12+ standard library commands:

```sh
python3 benchmark.py --binary /path/to/older/lightpanda --label pre4129 --samples 5
python3 workflows.py --binary /path/to/older/lightpanda --label pre4129 --samples 3
python3 wpt_smoke.py --binary /path/to/older/lightpanda --label pre4129
# Repeat with label post4036 and the binary for 463360ad.
# Repeat with label post4129 and the binary for 725ff748.
python3 report.py
```

Review `results/summary.csv`, `results/summary.json` and individual receipt JSON for exact hashes, tree strings, state decisions, click counts and timings. Binaries are not committed. The October 18 snapshot includes unrelated upstream changes, but exact #4036 controls that confound; its CDP changes did not directly add MCP state exposure. Timings are low-sample diagnostics, not a performance claim. **Known discrepancy:** MCP `tree` can still include inert controls ignored by CDP. Next work: model-driven held-out tasks with normal fallback tools, cost accounting, and official WPT where a compliant driver exists.

No WPT PR was submitted. Review the WPT [LLM contribution policy](https://web-platform-tests.org/writing-tests/ai-policy.html) before proposing any upstream WPT additions.
