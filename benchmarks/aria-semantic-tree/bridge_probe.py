#!/usr/bin/env python3
"""Verify same-WebDriver-session AX computed values against four WPT-sourced cases.
Not a WPT runner conformance result or platform AAM test."""
import argparse, hashlib, http.server, json, os, select, signal, socket, subprocess, threading, time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from wpt_smoke import build, ROOT

def request(base, path, method="GET", data=None):
    payload=json.dumps(data).encode() if data is not None else None
    req=Request(base+path,data=payload,method=method,
                headers={"content-type":"application/json"} if payload is not None else {})
    with urlopen(req,timeout=8) as response:
        return response.status,json.load(response).get("value")

def run(binary,label):
    cases,source_sha=build()
    fixture_dir=ROOT/"fixtures"
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self,*a,**kw): super().__init__(*a,directory=str(fixture_dir),**kw)
        def log_message(self,*a):pass
    server=http.server.ThreadingHTTPServer(("127.0.0.1",0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    sock=socket.socket();sock.bind(("127.0.0.1",0));port=sock.getsockname()[1];sock.close()
    base=f"http://127.0.0.1:{port}"
    stderr_path=ROOT/"results"/(label+"-bridge.stderr.log")
    with stderr_path.open("w") as stderr:
        proc=subprocess.Popen([str(binary),"serve","--host","127.0.0.1","--port",str(port),
                               "--protocol","webdriver","--log-level","error"],
                              stdout=subprocess.DEVNULL,stderr=stderr,start_new_session=True)
        try:
            for i in range(80):
                try:
                    _,status=request(base,"/status")
                    if status.get("ready"):break
                except Exception:pass
                if proc.poll() is not None:raise RuntimeError("Lightpanda exited before startup")
                time.sleep(.1)
            else:raise TimeoutError("WebDriver status not ready")
            code,sess=request(base,"/session","POST",{"capabilities":{"alwaysMatch":{}}})
            sid=sess["sessionId"]
            try:
                url=f"http://127.0.0.1:{server.server_port}/wpt_checked_local.html"
                code,_=request(base,f"/session/{sid}/url","POST",{"url":url})
                findings=[]
                for i,c in enumerate(cases):
                    _,element=request(base,f"/session/{sid}/element","POST",
                                      {"using":"css selector","value":f"#wptcase-{i}"})
                    ref=element["element-6066-11e4-a52e-4f735466cecf"]
                    _,value=request(base,f"/session/{sid}/element/{ref}/accessibility")
                    nodes=value["nodes"]
                    node=nodes[0] if nodes else {}
                    props={p["name"]:p.get("value",{}).get("value") for p in node.get("properties",[])}
                    role=node.get("role",{}).get("value")
                    observed=props.get("checked")
                    findings.append({"name":c["name"],"expected":c["expected"],"observed":str(observed).lower() if observed is not None else None,
                                     "role":role,"node_count":len(nodes),
                                     "matches":role=="checkbox" and str(observed).lower()==c["expected"]})
                bad=None
                try:
                    request(base,f"/session/{sid}/element/99999999/accessibility")
                except HTTPError as exc:
                    bad={"http_status":exc.code,"error":json.loads(exc.read()).get("value",{}).get("error")}
                out={"label":label,"binary_sha256":hashlib.sha256(binary.read_bytes()).hexdigest(),
                     "wpt_source_sha256":source_sha,"wpt_source_revision":"b4b303c8dca22989c43e2d76fce199c36d4b77a7",
                     "classification":"WPT-sourced checkbox expectations tested against computed CDP AX exposed via experimental same-session WebDriver extension. Not official WPT.",
                     "correct":sum(x["matches"] for x in findings),"total":len(findings),
                     "invalid_element":bad,"findings":findings}
                (ROOT/"results"/(label+"-web-driver-ax-bridge.json")).write_text(json.dumps(out,indent=2)+"\n")
                print(json.dumps(out,indent=2))
                return out
            finally:
                try:request(base,f"/session/{sid}","DELETE")
                except Exception:pass
        finally:
            try:os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            proc.wait(timeout=5)
            server.shutdown();server.server_close()

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--binary",required=True,type=Path);ap.add_argument("--label",required=True);a=ap.parse_args()
    out=run(a.binary.resolve(),a.label)
    if out["correct"]!=out["total"] or out["invalid_element"]!={"http_status":404,"error":"no such element"}:
        raise SystemExit(1)
