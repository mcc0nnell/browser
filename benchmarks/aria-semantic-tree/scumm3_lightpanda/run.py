"""Run a local, read-only Scumm3 -> Sandia TalkPipe evidence reconciliation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scumm3_lightpanda.capabilities import ALLOWED, CAPABILITIES, bundle_digest, SOURCE_SHA

BENCH = Path(__file__).resolve().parents[1]
SCUMM = Path(os.environ.get("SCUMM3_SOURCE", "/home/commander/lab/scumm3-juliana")).resolve()
OUT = BENCH / "results" / "scumm3-talkpipe-lightpanda.json"
PROGRAM = "lightpanda.read-only-ax-reconciliation.v1"


def sha(obj) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def request() -> dict:
    steps = [
        {"id": stage + "-evidence", "capability": "lightpanda.evidence.read",
         "effect": "read", "inputs": {"stage": stage, "digest": bundle_digest(stage)},
         "outputs": [{"name": stage, "slot": "bundle", "mediaType": "application/json"}],
         "ordinal": i}
        for i, stage in enumerate(ALLOWED)
    ]
    steps.append({
        "id": "verify-computed-ax",
        "capability": "lightpanda.evidence.compare",
        "effect": "transform",
        "inputs": {"base": "@post4036", "patched": "@post4129", "bridge": "@bridge"},
        "outputs": [{"name": "comparison", "slot": "comparison",
                     "mediaType": "application/json"}],
        "ordinal": len(steps),
    })
    now = datetime.now(timezone.utc)
    plan = {
        "version": 1,
        "programId": PROGRAM,
        "steps": steps,
        "assertions": [],  # Verified by the capability handler, not delegated.
        "requiredEffects": ["read", "transform"],
        "artifactNames": ["post4036", "post4129", "bridge", "comparison"],
    }
    fingerprint = {k: bundle_digest(k) for k in ALLOWED}
    return {
        "authority": "talkpipe-authoring-execution-only",
        "leaseId": "LOCAL-SYNTHETIC-" + sha(fingerprint)[7:39],
        "candidateDigest": sha(plan),
        "receiptDigest": sha(fingerprint),
        "verificationDigest": sha({"expectedSource": SOURCE_SHA, "officialWptPasses": 0}),
        "hostId": "butcher-local-demo",
        "programId": PROGRAM,
        "scope": {
            "runtime": "sandia-talkpipe",
            "substrate": "pipe-api",
            "adapter": "scumm3-capability-adapter-v1",
            "programId": PROGRAM,
            "capabilities": ["lightpanda.evidence.read", "lightpanda.evidence.compare"],
            "effects": ["read", "transform"],
        },
        "plan": plan,
        "admittedAt": now.isoformat(),
        "expiresAt": (now + timedelta(minutes=10)).isoformat(),
    }


def run(emit: bool = True, verify_stdio: bool = True) -> dict:
    from integrations.talkpipe.scumm3_bridge import build_pipeline, execute_pipeline
    from talkpipe.pipe.core import Pipeline
    if not (SCUMM / "integrations/talkpipe/scumm3_bridge.py").is_file():
        raise RuntimeError("Scumm3 source not found")
    req = request()
    pipeline, _ = build_pipeline(req, CAPABILITIES)
    assert isinstance(pipeline, Pipeline), "not a genuine Sandia TalkPipe Pipeline"
    state = execute_pipeline(req, CAPABILITIES)
    expected_trace = ["post4036-evidence", "post4129-evidence",
                      "bridge-evidence", "verify-computed-ax"]
    if [item["stepId"] for item in state.trace] != expected_trace:
        raise RuntimeError("unexpected Scumm3 execution trace")

    # Exercise the actual Scumm3 stdio adapter as well as the Python Pipe API.
    stdio_receipt = None
    if verify_stdio:
        env = dict(os.environ)
        env["SCUMM3_TALKPIPE_CAPABILITY_MODULE"] = "scumm3_lightpanda.capabilities"
        env["PYTHONPATH"] = os.pathsep.join([
            str(BENCH), str(SCUMM / "vendor/talkpipe/src"),
            str(SCUMM / "vendor/parsy/src"), str(SCUMM),
            env.get("PYTHONPATH", ""),
        ])
        proc = subprocess.run(
            [sys.executable, str(SCUMM / "integrations/talkpipe/scumm3_bridge.py"),
             "--stdio"],
            input=json.dumps(req),
            text=True,
            capture_output=True,
            cwd=SCUMM,
            env=env,
            timeout=15,
            check=False,
        )
        if proc.returncode:
            raise RuntimeError("Scumm3 stdio adapter rejected local read-only plan: "
                               + proc.stderr.strip()[:500])
        stdio_receipt = json.loads(proc.stdout)
        if stdio_receipt.get("status") != "completed":
            raise RuntimeError("Scumm3 stdio did not complete")

    origin = subprocess.check_output(
        ["git", "-C", str(SCUMM), "rev-parse", "HEAD"], text=True,
    ).strip()
    result = {
        "classification": "local synthetic-lease Sandia TalkPipe read/transform demonstration",
        "source": "existing synthetic Lightpanda WPT-derived receipts",
        "scumm3Commit": origin,
        "realPipeApi": True,
        "effects": ["read", "transform"],
        "executionTrace": state.trace,
        "stdio": stdio_receipt,
        "comparison": state.artifacts["comparison"],
        "inputBundleSha256": {k: bundle_digest(k) for k in ALLOWED},
        "officialWptPasses": 0,
        "authorizedProductionExecution": False,
        "mutatedBrowserOrRepositories": False,
    }
    if emit:
        OUT.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-stdio", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()
    result = run(emit=not args.no_write, verify_stdio=not args.no_stdio)
    print(json.dumps({
        "realPipeApi": result["realPipeApi"],
        "steps": [x["stepId"] for x in result["executionTrace"]],
        "comparison": result["comparison"],
        "stdio": result["stdio"],
        "receipt": str(OUT) if not args.no_write else None,
    }, indent=2))
