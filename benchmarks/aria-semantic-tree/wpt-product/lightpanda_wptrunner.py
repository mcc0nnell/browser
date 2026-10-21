"""Experimental standalone WPT wptrunner product for native Lightpanda WebDriver.
Only basic testharness/wdspec types are advertised; NOT AT-SPI AAM conformance."""
import sys
from wptrunner.browsers.base import WebDriverBrowser, get_timeout_multiplier, require_arg
from wptrunner.executors import executor_kwargs as base_executor_kwargs
from wptrunner.executors.base import PytestExecutor
from wptrunner.executors.executorwebdriver import (
    WebDriverTestharnessExecutor, WebDriverProtocol, WebDriverAccessibilityProtocolPart)
from wptrunner.products import Product

__wptrunner__ = {
    "product": "lightpanda",
    "check_args": "check_args",
    "browser": "LightpandaBrowser",
    "executor": {
        "testharness": "LightpandaTestharnessExecutor",
        "wdspec": "PytestExecutor",
    },
    "browser_kwargs": "browser_kwargs",
    "executor_kwargs": "executor_kwargs",
    "env_extras": "env_extras",
    "env_options": "env_options",
    "timeout_multiplier": "get_timeout_multiplier",
}
class LightpandaAccessibilityProtocolPart(WebDriverAccessibilityProtocolPart):
    """Computed AX state from Lightpanda's same-session vendor extension.

    This is not a WebDriver-standard endpoint or an OS accessibility API.
    """
    def get_accessibility_properties_for_element(self, element):
        result = self.webdriver.send_session_command(
            "GET", f"element/{element.id}/accessibility")
        nodes = result.get("nodes", [])
        if not nodes:
            return {}
        node = nodes[0]
        mapped = {"accessibilityId": node.get("nodeId"),
                  "children": node.get("childIds", [])}
        for source, target in (("role", "role"), ("name", "label"),
                               ("description", "description"), ("value", "value")):
            if isinstance(node.get(source), dict):
                mapped[target] = node[source].get("value")
        for prop in node.get("properties", []):
            if prop.get("name") in {"checked", "pressed", "level", "multiline",
                                    "orientation", "required", "roledescription", "selected"}:
                mapped[prop["name"]] = prop.get("value", {}).get("value")
        return mapped

class LightpandaProtocol(WebDriverProtocol):
    implements = [LightpandaAccessibilityProtocolPart] + [
        p for p in WebDriverProtocol.implements if p.name != "accessibility"]

class LightpandaTestharnessExecutor(WebDriverTestharnessExecutor):
    protocol_cls = LightpandaProtocol

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
