"""Experimental standalone WPT wptrunner product for native Lightpanda WebDriver.
Only basic testharness/wdspec types are advertised; NOT AT-SPI AAM conformance."""
import sys
from wptrunner.browsers.base import WebDriverBrowser, get_timeout_multiplier, require_arg
from wptrunner.executors import executor_kwargs as base_executor_kwargs
from wptrunner.executors.base import PytestExecutor
from wptrunner.executors.executorwebdriver import WebDriverTestharnessExecutor
from wptrunner.products import Product

__wptrunner__ = {
    "product": "lightpanda",
    "check_args": "check_args",
    "browser": "LightpandaBrowser",
    "executor": {
        "testharness": "WebDriverTestharnessExecutor",
        "wdspec": "PytestExecutor",
    },
    "browser_kwargs": "browser_kwargs",
    "executor_kwargs": "executor_kwargs",
    "env_extras": "env_extras",
    "env_options": "env_options",
    "timeout_multiplier": "get_timeout_multiplier",
}
def check_args(**kwargs):
    require_arg(kwargs, "binary")
def browser_kwargs(logger, test_type, run_info_data, config, **kwargs):
    return {"binary":kwargs["binary"],"webdriver_binary":kwargs["binary"],
            "webdriver_args":kwargs.get("webdriver_args") or []}
def executor_kwargs(logger, test_type, test_environment, run_info_data, **kwargs):
    result=base_executor_kwargs(test_type, test_environment, run_info_data, **kwargs)
    result["capabilities"]={}
    return result
def env_extras(**kwargs):return []
def env_options():
    return {"server_host":"127.0.0.1","browser_host":"localhost","supports_debugger":False}
class LightpandaBrowser(WebDriverBrowser):
    def make_command(self):
        return [self.webdriver_binary,"serve","--host","127.0.0.1","--port",str(self.port),
                "--protocol","webdriver","--log-level","error"]+self.webdriver_args
def product():
    return Product._from_dunder_wptrunner(sys.modules[__name__])
