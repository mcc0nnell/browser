#!/usr/bin/env python3
"""Read-only local MCP semantic-state benchmark. No LLM, clicks, or external URLs."""
import argparse
import hashlib
import http.server
import json
import os
from pathlib import Path
import select
import signal
import statistics
import subprocess
import threading
import time

ROOT = Path(__file__).resolve().parent
CASES = [
    ("Expanded details", "expanded"), ("Collapsed details", "collapsed"),
    ("Uppercase expanded", "expanded"), ("Uppercase collapsed", "collapsed"),
    ("Mixed terms", "mixed"), ("Checked terms", "checked"),
    ("Unfocusable terms", "unchecked"), ("Uppercase mixed", "mixed"),
    ("Absent checked", "unchecked"), ("Switch checked", "checked"),
    ("Switch mixed", "unchecked"), ("Menu checkbox checked", "checked"),
    ("Menu checkbox mixed", "mixed"), ("Radio unchecked", "unchecked"),
    ("Radio absent", "unchecked"), ("Menu radio checked", "checked"),
    ("Custom anchor", "expanded"), ("Custom image", "expanded"),
    ("Expanded switch", "expanded"),
]
CONTROLS = ["Generic expanded", "Invalid details", "Invalid state"]
STATES = {s for _, s in CASES}
NO_STATES = [" [expanded]", " [collapsed]", " [checked]", " [unchecked]", " [mixed]"]

class SilentHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "fixtures"), **kwargs)
    def log_message(self, *args):
        pass

def rpc(proc, msg, timeout=15):
    proc.stdin.write((json.dumps(msg, separators=(",", ":")) + "\n").encode())
    proc.stdin.flush()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("Lightpanda exited while awaiting MCP response")
        if select.select([proc.stdout], [], [], min(0.25, deadline-time.monotonic()))[0]:
            b = proc.stdout.readline()
            if not b:
                raise RuntimeError("MCP stream ended")
            try:
                result = json.loads(b)
            except json.JSONDecodeError:
                raise RuntimeError("Non-JSON MCP output: " + repr(b[:200])) from None
            if result.get("id") == msg.get("id"):
                if "error" in result:
                    raise RuntimeError(str(result["error"]))
                return result.get("result", {})
    raise TimeoutError("MCP response exceeded timeout")

def parse_tree(result):
    texts = [v.get("text","") for v in result.get("content", []) if v.get("type") == "text"]
    if result.get("isError"):
        raise RuntimeError("MCP tool error: " + repr(texts)[:400])
    if not texts:
        raise RuntimeError("No text in MCP content: " + repr(result)[:500])
    return "\n".join(texts)

def summarize(tree):
    # Search by quoted accessibility name only; prevent accidental substring matches.
    observed = []
    for name, expected in CASES:
        lines = [line.strip() for line in tree.splitlines() if ("'" + name + "'") in line]
        if len(lines) != 1:
            observed.append({"name":name,"expected":expected,"observed":None,"outcome":"missing_or_ambiguous"})
            continue
        # Some roles (e.g. switch) legitimately expose both expanded and checked.
        # Match the property under test, not all unrelated state tokens.
        allowed = ("expanded", "collapsed") if expected in ("expanded", "collapsed") else ("checked", "unchecked", "mixed")
        got = [v for v in allowed if " [" + v + "]" in lines[0]]
        if len(got) != 1:
            outcome = "unknown" if len(got) == 0 else "ambiguous"
            observed.append({"name":name,"expected":expected,"observed":got or None,"outcome":outcome})
            continue
        observed.append({"name":name,"expected":expected,"observed":got[0],"outcome":"correct" if got[0] == expected else "wrong"})
    negatives = []
    for name in CONTROLS:
        lines = [line.strip() for line in tree.splitlines() if ("'" + name + "'") in line]
        has_state = any(s in line for line in lines for s in NO_STATES)
        negatives.append({"name":name,"present":bool(lines),"spurious_state":has_state})
    return observed, negatives

def single_run(exe, url, samples, stderr_path):
    stat = os.stat(exe)
    sha = hashlib.sha256(Path(exe).read_bytes()).hexdigest()
    results = []
    with open(stderr_path, "w") as err:
        for sample in range(samples):
            proc = subprocess.Popen([str(exe),"mcp","--log-level","error"],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=err,start_new_session=True,bufsize=0)
            try:
                init = rpc(proc, {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"windanvil-panda-state-bench","version":"1.0"}}})
                proc.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
                proc.stdin.flush()
                start = time.perf_counter_ns()
                result = rpc(proc, {"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"tree","arguments":{"url":url}}},timeout=20)
                duration_ms = round((time.perf_counter_ns()-start)/1e6,3)
                tree = parse_tree(result)
                observed,negatives = summarize(tree)
                results.append({"sample":sample+1,"tree_ms":duration_ms,"tree_bytes":len(tree.encode()),"tree":tree,"observations":observed,"controls":negatives})
            finally:
                try:os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:pass
                proc.wait(timeout=5)
    # Use first sample for correctness and check that all samples agree.
    first = results[0]
    signatures = [ [(x["name"], str(x["observed"])) for x in r["observations"]] for r in results]
    if any(sig != signatures[0] for sig in signatures):
        raise RuntimeError("Inconsistent observed control states between samples")
    return {"binary":str(exe),"binary_sha256":sha,"binary_bytes":stat.st_size,"samples":samples,
            "correct":sum(x["outcome"]=="correct" for x in first["observations"]),
            "wrong":sum(x["outcome"]=="wrong" for x in first["observations"]),
            "unknown":sum(x["outcome"]!="correct" and x["outcome"]!="wrong" for x in first["observations"]),
            "total":len(CASES), "negative_controls":first["controls"],
            "median_tree_ms":round(statistics.median(r["tree_ms"] for r in results),3),
            "min_tree_ms":min(r["tree_ms"] for r in results),
            "max_tree_ms":max(r["tree_ms"] for r in results),
            "tree_bytes":first["tree_bytes"],
            "observations":first["observations"],"raw_samples":results}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--binary",required=True)
    ap.add_argument("--label",required=True)
    ap.add_argument("--samples",type=int,default=3)
    args=ap.parse_args()
    exe=Path(args.binary).resolve()
    if not exe.is_file():raise SystemExit("missing binary " + str(exe))
    assert args.samples>=1
    server=http.server.ThreadingHTTPServer(("127.0.0.1",0),SilentHandler)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    url=f"http://127.0.0.1:{server.server_port}/ax_aria_states.html"
    try:
        out=single_run(exe,url,args.samples,ROOT/"results"/(args.label+".stderr.log"))
    finally:
        server.shutdown()
        server.server_close()
    out.update({"label":args.label,"fixture_sha256":hashlib.sha256((ROOT/"fixtures"/"ax_aria_states.html").read_bytes()).hexdigest(),
                "measurement":"MCP tree one-shot state visibility; no LLM and no agent action"})
    target=ROOT/"results"/(args.label+".json")
    target.write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps({k:v for k,v in out.items() if k not in ("observations","raw_samples","negative_controls")},indent=2))
    print("NEGATIVE",out["negative_controls"])
    print("SAVED",target)
if __name__=="__main__":
    main()
