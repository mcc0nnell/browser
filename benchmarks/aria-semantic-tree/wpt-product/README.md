# Experimental Lightpanda wptrunner browser product

This external Python package registers `lightpanda` in upstream WPT's `wptrunner.products` entry-point group. It launches Lightpanda's native WebDriver server bound to `127.0.0.1` and offers the generic WebDriver testharness and wdspec executors. **It does not enable `aamtest`**, which requires platform accessibility APIs. It makes NO official conformance claim.

## Reproduce the October 21, 2026 boundary

Use a sparse or full upstream WPT checkout (tested at `6f22f9eab8830478cc0cc9c67ad9004a044c5969`) and a compiled Lightpanda binary at `725ff748`. Prepare a Python environment with WPT wptrunner dependencies plus `websockets`, `pytest`, and this local editable product:

```sh
python3 -m venv --system-site-packages /tmp/wpt-lightpanda-venv
/tmp/wpt-lightpanda-venv/bin/pip install -r /path/to/wpt/tools/wptrunner/requirements.txt
/tmp/wpt-lightpanda-venv/bin/pip install 'websockets>=13,<16' 'pytest>=8,<10'
/tmp/wpt-lightpanda-venv/bin/pip install -e ./wpt-product
bash ./run_wptrunner_probe.sh /path/to/wpt /path/to/lightpanda /tmp/wpt-lightpanda-venv/bin/python
```

The direct `wptrunner` invocation is used to avoid changing system `/etc/hosts`; the external product config sets a loopback browser host. The normal WPT `./wpt run` wrapper explicitly checks for a WPT hosts-file setup and rejects this host-isolated arrangement.

Observed: the product was discovered; wptrunner started Lightpanda WebDriver, created its session, loaded the testharness runner page, and began `wai-aria/idlharness.window.html`. Then `WebDriverTestharnessExecutor.close_old_windows` tried `POST /session/{sessionId}/window`, which Lightpanda returned as HTTP 404 `unknown command` (`test_end: ERROR`). That is a reproducible implementation blocker, **not a failed accessibility assertion** and **not a WPT pass**.

Do not submit this plugin to WPT as complete until the WebDriver window-switch command and dependent runner setup succeed. Do not advertise platform-specific AAM testing until Lightpanda can expose actual AT-SPI (Linux) or equivalent operating-system accessibility objects.
