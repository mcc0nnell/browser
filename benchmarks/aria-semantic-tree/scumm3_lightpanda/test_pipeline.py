"""Policy and provenance regressions for the local Scumm3/TalkPipe WPT bridge."""
import copy
import unittest

from scumm3_lightpanda.capabilities import (
    ALLOWED, EvidenceError, SOURCE_SHA, _case_result, bundle_digest,
    exact_bytes, read_bundle,
)
from scumm3_lightpanda.run import CAPABILITIES, request, run


class ReadOnlyTalkpipeTests(unittest.TestCase):
    def test_complete_real_pipe_pipeline(self):
        receipt = run(emit=False, verify_stdio=False)
        self.assertTrue(receipt["realPipeApi"])
        self.assertEqual(4, len(receipt["executionTrace"]))
        self.assertEqual(receipt["comparison"]["experimentalWebDriverAx"], "4/4")
        self.assertEqual(0, receipt["comparison"]["officialWptPasses"])
        self.assertEqual(receipt["comparison"]["post4036"]["mcp"], "0/4")
        self.assertFalse(receipt["authorizedProductionExecution"])
        self.assertFalse(receipt["mutatedBrowserOrRepositories"])

    def test_effects_are_only_read_and_transform(self):
        obj = request()
        self.assertEqual(["read", "transform"], obj["scope"]["effects"])
        self.assertEqual(["read", "transform"], obj["plan"]["requiredEffects"])
        from integrations.talkpipe.scumm3_bridge import build_pipeline, BridgeError
        obj["plan"]["steps"][-1]["effect"] = "write"
        obj["plan"]["requiredEffects"] = ["read", "write"]
        obj["scope"]["effects"] = ["read", "write"]
        with self.assertRaisesRegex(BridgeError, "effect write"):
            build_pipeline(obj, CAPABILITIES)

    def test_strict_stage_and_path_allowlist(self):
        with self.assertRaises(EvidenceError):
            exact_bytes("../private-token.json")
        with self.assertRaises(EvidenceError):
            bundle_digest("../../private")
        self.assertEqual(3, len(ALLOWED))

    def test_digest_substitution_fails(self):
        context = {"authority": "talkpipe-authoring-execution-only",
                   "capability": "lightpanda.evidence.read", "effect": "read"}
        with self.assertRaisesRegex(EvidenceError, "digest mismatch"):
            read_bundle({"stage": "bridge", "digest": "0"*64}, context)

    def test_wrong_authority_fails(self):
        context = {"authority": "unsafe-shell",
                   "capability": "lightpanda.evidence.read", "effect": "read"}
        with self.assertRaisesRegex(EvidenceError, "context"):
            read_bundle({"stage": "bridge", "digest": bundle_digest("bridge")}, context)

    def test_aggregate_cannot_hide_failed_case(self):
        bad = {"correct": 4, "total": 4, "cases": [
            {"passed_projection": True},
            {"passed_projection": True},
            {"passed_projection": True},
            {"passed_projection": False},
        ]}
        with self.assertRaisesRegex(EvidenceError, "contradicts"):
            _case_result(bad, 4)


if __name__ == "__main__":
    unittest.main()
