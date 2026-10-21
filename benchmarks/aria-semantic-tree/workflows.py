#!/usr/bin/env python3
"""40 synthetic one-read toggle tasks over native Lightpanda MCP. No LLM.
Selectors and target 'on' are provided to policy as task instructions.
All final-state verification is hidden from policy."""
import argparse, hashlib, html, http.server, json, os, select, signal
import statistics, subprocess, threading, time
from pathlib import Path
from benchmark import rpc, parse_tree, SilentHandler
BASE=Path(__file__).resolve().parent
KINDS=(("accordion","button","expanded"),("checkbox","checkbox","checked"),("switch","switch","checked"),("menuitemcheckbox","menuitemcheckbox","checked"))
TASKS=[]
for kind,role,prop in KINDS:
    for i in range(10):
        key=f"{kind}-{i:02d}"
        initial=(i%2==0)
        TASKS.append({"id":key,"role":role,"kind":kind,"property":prop,"initial":initial,"target":True,"name":f"{kind.upper()} TASK {i:02d}"})
def create_fixture():
    parts=['<!doctype html><html lang="en"><head><title>ARIA toggle decisions</title></head><body>']
    parts.append("""<script>
function toggle(el) {
  const attr = el.hasAttribute('aria-expanded') ? 'aria-expanded' : 'aria-checked';
  const value = el.getAttribute(attr);
  el.setAttribute(attr, String(value.toLowerCase() !== 'true'));
}
</script>""")
    for task in TASKS:
        attr='aria-expanded' if task['property']=='expanded' else 'aria-checked'
        value=('TRUE' if task['initial'] else 'false') if int(task['id'][-2:]) in (0,4,8) else str(task['initial']).lower()
        tag='button' if task['role']=='button' else 'div'
        parts.append(f'<{tag} id="{task["id"]}" role="{task["role"]}" {attr}="{value}" tabindex="0" aria-label="{task["name"]}" onclick="toggle(this)">{task["name"]}</{tag}>')
    parts.append('</body></html>')
    path=BASE/"fixtures"/"workflow_states.html"
    path.write_text("\n".join(parts)+"\n")
    (BASE/"fixtures"/"workflow_tasks.json").write_text(json.dumps(TASKS,indent=2)+"\n")
    return path

def extract_lines(tree, task):
    lines=[line for line in tree.splitlines() if "'"+task["name"]+"'" in line]
    if len(lines)!=1: return None, "missing_node"
    line=lines[0]
    true_token='[expanded]' if task['property']=='expanded' else '[checked]'
    false_token='[collapsed]' if task['property']=='expanded' else '[unchecked]'
    if true_token in line and false_token not in line: return True,"known"
    if false_token in line and true_token not in line: return False,"known"
    return None,"unknown"

def run(exe, samples, label):
    server=http.server.ThreadingHTTPServer(("127.0.0.1",0),SilentHandler)
    t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
    url=f"http://127.0.0.1:{server.server_port}/workflow_states.html"
    outcomes=[]
    with (BASE/"results"/(label+"-workflow.stderr.log")).open("w") as err:
        try:
            for i in range(samples):
                p=subprocess.Popen([str(exe),"mcp","--log-level","error"],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=err,start_new_session=True,bufsize=0)
                try:
                    rpc(p,{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"panda-one-read-workflow-bench","version":"1.0"}}})
                    p.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n');p.stdin.flush()
                    tic=time.perf_counter_ns()
                    tree=parse_tree(rpc(p,{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"tree","arguments":{"url":url}}},timeout=25))
                    tree_ms=(time.perf_counter_ns()-tic)/1e6
                    known=0; clicks=0; decisions=[]; next_id=3
                    for task in TASKS:
                        seen,status=extract_lines(tree,task)
                        if seen is not None:known+=1
                        # State-aware policy: toggle only when known false;
                        # if unknown, abstain rather than making a speculative click.
                        should_click=seen is False
                        decisions.append({"id":task['id'],"expected_initial":task["initial"],"seen":seen,"status":status,"clicked":should_click})
                        if should_click:
                            res=rpc(p,{"jsonrpc":"2.0","id":next_id,"method":"tools/call","params":{"name":"click","arguments":{"selector":"#"+task["id"]}}},timeout=15)
                            next_id+=1
                            if res.get("isError"):raise RuntimeError("click tool failed: "+repr(res))
                            clicks+=1
                    # Evaluate only after all actions. Not seen by the policy.
                    js="Array.from(document.querySelectorAll('[id]')).filter(e=>e.id.includes('-')).map(e=>e.id+'='+String(e.getAttribute('aria-expanded')??e.getAttribute('aria-checked'))).join(';')"
                    res=rpc(p,{"jsonrpc":"2.0","id":next_id,"method":"tools/call","params":{"name":"evaluate","arguments":{"script":js}}},timeout=20)
                    if res.get("isError"):raise RuntimeError("evaluation failed: "+repr(res))
                    score_text=parse_tree(res)
                    import re
                    actual=dict((key,val.lower()) for key,val in re.findall(r'([a-z]+-\d{2})=(TRUE|FALSE|true|false)',score_text))
                    if len(actual)!=len(TASKS):raise RuntimeError("Insufficient final verification states: "+score_text[:1000])
                    correct=sum(actual[task["id"]]=='true' for task in TASKS)
                    outcomes.append({"run":i+1,"known":known,"total":len(TASKS),"clicks":clicks,"correct_final_state":correct,"tree_ms":round(tree_ms,3),"tree_bytes":len(tree.encode()),"decisions":decisions,"final_states":actual})
                finally:
                    try:os.killpg(p.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    p.wait(timeout=5)
        finally:
            server.shutdown();server.server_close()
    metric={
        "label":label,"binary":str(exe),"binary_sha256":hashlib.sha256(exe.read_bytes()).hexdigest(),
        "fixture_sha256":hashlib.sha256((BASE/"fixtures"/"workflow_states.html").read_bytes()).hexdigest(),
        "samples":samples,"tasks":len(TASKS),
        "median_known":statistics.median(v["known"] for v in outcomes),
        "median_final_correct":statistics.median(v["correct_final_state"] for v in outcomes),
        "median_tree_ms":round(statistics.median(v["tree_ms"] for v in outcomes),3),
        "median_tree_bytes":statistics.median(v["tree_bytes"] for v in outcomes),
        "measurement":"Deterministic one-read tree-state policy. No LLM, real MCP click used if state known false; scorer reads DOM after decisions",
        "raw_runs":outcomes
    }
    (BASE/"results"/(label+"-workflow.json")).write_text(json.dumps(metric,indent=2)+"\n")
    return {k:v for k,v in metric.items() if k!="raw_runs"}

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--binary",required=True);ap.add_argument("--label",required=True);ap.add_argument("--samples",type=int,default=3);args=ap.parse_args()
    create_fixture()
    print(json.dumps(run(Path(args.binary).resolve(),args.samples,args.label),indent=2))
