"""Read-only Lightpanda evidence capabilities for Scumm3's Sandia TalkPipe.

No arbitrary paths, subprocesses, network, browser mutations, code promotion,
or assertions of official WPT conformance.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
ALLOWED = {
    "post4036": ("post4036-cdp-wpt.json", "post4036-wpt.json"),
    "post4129": ("post4129-cdp-wpt.json", "post4129-wpt.json"),
    "bridge": (
        "webdriver-ax-experimental-web-driver-ax-bridge.json",
        "wptrunner-after-switch-probe.json",
    ),
}
SOURCE_SHA = "ccb8b47e2e8ce79cf3713b61338a12f9f5e95c1c0318ae896f98713e517bef13"


class EvidenceError(ValueError):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def exact_bytes(name: str) -> bytes:
    """Read only named, regular, non-symlink local test receipts."""
    if name not in {item for group in ALLOWED.values() for item in group}:
        raise EvidenceError("receipt name is not allowlisted")
    path = RESULTS / name
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 128 * 1024:
        raise EvidenceError("receipt is missing, symbolic, or too large")
    return path.read_bytes()


def bundle_digest(stage: str) -> str:
    if stage not in ALLOWED:
        raise EvidenceError("unknown stage")
    h = hashlib.sha256(b"scumm3-lightpanda-evidence-v1|")
    for name in ALLOWED[stage]:
        h.update(name.encode("ascii") + b"|")
        h.update(exact_bytes(name) + b"|")
    return h.hexdigest()


def _needs(context: dict[str, Any], capability: str, effect: str) -> None:
    if (context.get("authority") != "talkpipe-authoring-execution-only"
        or context.get("capability") != capability
        or context.get("effect") != effect):
        raise EvidenceError("unexpected Scumm3 capability context")


def _unpack(bundle: dict[str, Any], stage: str) -> dict[str, dict[str, Any]]:
    if (not isinstance(bundle, dict) or bundle.get("stage") != stage or
        set(bundle) != {"stage", "digest", "records"} or
        bundle["digest"] != bundle_digest(stage)):
        raise EvidenceError("stage artifact has invalid provenance")
    names = [x["filename"] for x in bundle["records"]]
    if names != list(ALLOWED[stage]):
        raise EvidenceError("stage receipt names mismatch")
    for x in bundle["records"]:
        if (x["sha256"] != _sha(exact_bytes(x["filename"])) or
            x["data"] != json.loads(exact_bytes(x["filename"]))):
            raise EvidenceError("stage receipt content mismatch")
    return {x["filename"]: x["data"] for x in bundle["records"]}


def read_bundle(inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    _needs(context, "lightpanda.evidence.read", "read")
    if set(inputs) != {"stage", "digest"}:
        raise EvidenceError("read requires stage and digest only")
    stage, expected = inputs["stage"], inputs["digest"]
    if not isinstance(expected, str) or expected != bundle_digest(stage):
        raise EvidenceError("source digest mismatch")
    records = []
    for name in ALLOWED[stage]:
        raw = exact_bytes(name)
        records.append({"filename": name, "sha256": _sha(raw), "data": json.loads(raw)})
    return {"bundle": {"stage": stage, "digest": expected, "records": records}}


def _case_result(doc: dict[str, Any], expected: int) -> None:
    if doc.get("correct") != expected or doc.get("total") != 4:
        raise EvidenceError("unexpected accessibility check count")
    details = doc.get("cases", doc.get("findings", []))
    if len(details) != 4:
        raise EvidenceError("incomplete fixture cases")
    if expected == 4 and not all(
        item.get("passed_projection", item.get("match", item.get("matches", False)))
        for item in details
    ):
        raise EvidenceError("passing aggregate contradicts individual cases")
    if expected == 0 and not all(not item.get("passed_projection", False) for item in details):
        raise EvidenceError("missing-state aggregate contradicts individual cases")


def compare(inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    _needs(context, "lightpanda.evidence.compare", "transform")
    if set(inputs) != {"base", "patched", "bridge"}:
        raise EvidenceError("compare requires three stage artifacts")
    base = _unpack(inputs["base"], "post4036")
    patched = _unpack(inputs["patched"], "post4129")
    bridge = _unpack(inputs["bridge"], "bridge")
    bcdp, bmcp = base["post4036-cdp-wpt.json"], base["post4036-wpt.json"]
    pcdp, pmcp = patched["post4129-cdp-wpt.json"], patched["post4129-wpt.json"]
    ax, runner = (bridge["webdriver-ax-experimental-web-driver-ax-bridge.json"],
                  bridge["wptrunner-after-switch-probe.json"])
    for cd, mc, label in ((bcdp, bmcp, "post4036"), (pcdp, pmcp, "post4129")):
        if (cd.get("label") != label or mc.get("label") != label or
            cd.get("binarySha256") != mc.get("binary_sha256")):
            raise EvidenceError("CDP and MCP samples do not share a binary")
    all_source = [
        bcdp.get("sourceSha256"), bmcp.get("source_sha256"),
        pcdp.get("sourceSha256"), pmcp.get("source_sha256"),
        ax.get("wpt_source_sha256"),
    ]
    if any(source != SOURCE_SHA for source in all_source):
        raise EvidenceError("WPT source provenance differs")
    for doc, count in ((bcdp, 4), (bmcp, 0), (pcdp, 4), (pmcp, 4), (ax, 4)):
        _case_result(doc, count)
    if (ax.get("invalid_element") != {"http_status": 404, "error": "no such element"}
        or runner.get("official_wpt_passes") != 0
        or "/window/new" not in runner.get("new_blocker", "")
        or runner.get("single_window_limit") is not True):
        raise EvidenceError("bridge or official runner status inconsistent")
    return {
        "comparison": {
            "classification": "WPT-derived CDP/MCP and experimental WebDriver AX observations; NOT official WPT",
            "sourceSha256": SOURCE_SHA,
            "post4036": {"cdp": "4/4", "mcp": "0/4"},
            "post4129": {"cdp": "4/4", "mcp": "4/4"},
            "experimentalWebDriverAx": "4/4",
            "officialWptPasses": 0,
            "officialWptBlocker": "POST /session/{id}/window/new unsupported",
            "mutatingCapabilities": False,
        }
    }


CAPABILITIES = {
    "lightpanda.evidence.read": read_bundle,
    "lightpanda.evidence.compare": compare,
}
