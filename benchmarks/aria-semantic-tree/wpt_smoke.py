#!/usr/bin/env python3
"""WPT-derived checkbox case adapter, NOT wptrunner/aamtest or a WPT pass claim."""
import argparse, hashlib, http.server, json, os, re, signal, subprocess, threading, time
from pathlib import Path
from html.parser import HTMLParser
from benchmark import ROOT, SilentHandler, rpc, parse_tree
UPSTREAM="https://github.com/web-platform-tests/wpt/blob/b4b303c8dca22989c43e2d76fce199c36d4b77a7/wai-aria/checked/checked.tentative.html"

class Cases(HTMLParser):
    def __init__(self):super().__init__();self.cases=[]
    def handle_starttag(self,tag,attrs):
        attr=dict(attrs)
        if tag!="div" or "data-expectedproperties" not in attr:return
        assert attr.get("role")=="checkbox"
        expected=json.loads(attr["data-expectedproperties"])
        assert list(expected)==["checked"]
        name=attr["data-testname"]
        self.cases.append({"name":name,"expected":expected["checked"],"raw_checked":attr.get("aria-checked")})

def build():
    raw=(ROOT/"fixtures"/"wpt_checked_source.html").read_bytes()
    parser=Cases();parser.feed(raw.decode())
    assert len(parser.cases)==4
    lines=['<!doctype html><html lang="en"><head><title>WPT checked semantic adapter</title></head><body>']
    for i,c in enumerate(parser.cases):
        checked=(f' aria-checked="{c["raw_checked"]}"' if c["raw_checked"] is not None else "")
        lines.append(f'<div id="wptcase-{i}" role="checkbox" aria-label="{c["name"]}" tabindex="0"{checked}></div>')
    lines.append("</body></html>")
    (ROOT/"fixtures"/"wpt_checked_local.html").write_text("\n".join(lines)+"\n")
    return parser.cases,hashlib.sha256(raw).hexdigest()

def run(exe,label):
    cases,source_sha=build()
    server=http.server.ThreadingHTTPServer(("127.0.0.1",0),SilentHandler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    proc=subprocess.Popen([str(exe),"mcp","--log-level","error"],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True)
    try:
        rpc(proc,{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"panda-wpt-projection","version":"1"}}})
        proc.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n');proc.stdin.flush()
        tree=parse_tree(rpc(proc,{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"tree","arguments":{"url":f"http://127.0.0.1:{server.server_port}/wpt_checked_local.html"}}}))
        observations=[]
        for c in cases:
            lines=[line for line in tree.splitlines() if "'"+c["name"]+"'" in line]
            expected_token={"false":"unchecked","true":"checked","mixed":"mixed"}[c["expected"]]
            actual=[v for v in ("checked","unchecked","mixed") if lines and " ["+v+"]" in lines[0]]
            observations.append({**c,"observed":actual,"passed_projection":actual==[expected_token],"matched_nodes":len(lines)})
        obj={"label":label,"source_url":UPSTREAM,"source_sha256":source_sha,"binary_sha256":hashlib.sha256(exe.read_bytes()).hexdigest(),
             "result_kind":"WPT-sourced case projection onto Lightpanda MCP tree, not an official WPT run",
             "correct":sum(x["passed_projection"] for x in observations),"total":len(cases),"cases":observations}
        (ROOT/"results"/f"{label}-wpt.json").write_text(json.dumps(obj,indent=2)+"\n")
        return {"label":label,"correct":obj["correct"],"total":obj["total"],"source_sha256":source_sha}
    finally:
        os.killpg(proc.pid,signal.SIGKILL);proc.wait();server.shutdown();server.server_close()

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--binary",required=True);p.add_argument("--label",required=True);a=p.parse_args();print(json.dumps(run(Path(a.binary).resolve(),a.label),indent=2))
