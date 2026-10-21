#!/usr/bin/env python3
"""Exploratory LLM decision pilot. Native MCP tree/click with optional HTML fallback.
This is NOT statistically powered or a standard agent benchmark."""
import argparse, hashlib, http.server, json, os, random, re, signal, statistics, subprocess, threading, time
from pathlib import Path
from benchmark import rpc, parse_tree, SilentHandler, ROOT

SEED=29117
ROLES=(("button","expanded"),("checkbox","checked"),("switch","checked"),("menuitemcheckbox","checked"))
WORDS=("Orion","Cedar","Comet","Harbor","Quartz","Willow","Falcon","Meadow","Ember","Delta","Cobalt","Nimbus")
def fixture():
    random.seed(SEED)
    bits=[True,False]*6
    random.shuffle(bits)
    tasks=[]
    lines=['<!doctype html><html lang="en"><head><title>Held-out accessibility toggles</title></head><body>',
           "<script>function flip(el){ const k=el.hasAttribute('aria-expanded')?'aria-expanded':'aria-checked'; el.setAttribute(k, String(el.getAttribute(k).toLowerCase()!=='true')); }</script>"]
    for i,(label,on) in enumerate(zip(WORDS,bits)):
        role,property=ROLES[i%len(ROLES)]
        ident=f"case-{i:02d}"
        tasks.append(dict(id=ident,name=label+" option",role=role,property=property,initial=on,target=True))
        tag="button" if role=="button" else "div"
        token=("TRUE" if on else "FALSE") if i%4==0 else str(on).lower()
        attr="aria-"+property
        lines.append(f'<{tag} id="{ident}" role="{role}" tabindex="0" aria-label="{label} option" {attr}="{token}" onclick="flip(this)">{label} option</{tag}>')
    lines+=['<div aria-label="Decorative Orion" role="generic" aria-expanded="true"></div>', '</body></html>']
    (ROOT/'fixtures'/'model_heldout.html').write_text("\n".join(lines)+"\n")
    return tasks

def prompt_text(tasks,tree,html=None):
    mapping=[{k:t[k] for k in ("id","name","role")} for t in tasks]
    additional=("The browser has now returned RAW HTML for the same page:\n"+html+"\n" if html is not None else "")
    return ("""You are an AI agent controlling a headless browser with semantic accessibility tools.
GOAL: All 12 task-listed controls should end ENABLED (checked=true, or expanded=true for buttons).
You have one live MCP semantic tree read. Only use the information below. No external tools.
Each task has a selector ID, accessible name, and ARIA role; the ID itself contains no state.
If ANY required state is unknown or missing from the semantic tree, set inspect_html=true
and click_ids=[]; this requests one additional HTML inspection. Never guess.
If all required states are present, set inspect_html=false and include only IDs currently
false/unchecked/collapsed in click_ids. If RAW HTML is provided, derive states from the
matching element's aria-checked/aria-expanded value and set inspect_html=false.
Ignore elements not in the task list. Respond with exactly a valid JSON object with
two keys: {"inspect_html":false,"click_ids":["case-01"]}. No markdown, no prose.
TASKS:
"""+json.dumps(mapping,separators=(",",":"))+"\nMCP TREE:\n"+tree+"\n"+additional)

def ask_model(prompt,workdir,label,phase):
    out=workdir/f"{label}-{phase}.response.txt"
    log=workdir/f"{label}-{phase}.stderr.log"
    (workdir/f"{label}-{phase}.prompt.txt").write_text(prompt)
    cmd=['codex','exec','--ephemeral','--ignore-user-config','--skip-git-repo-check','-s','read-only','-C',str(workdir),'-o',str(out),'-']
    tic=time.perf_counter()
    with log.open("w") as err:
        done=subprocess.run(cmd,input=prompt,text=True,stdout=subprocess.DEVNULL,stderr=err,timeout=100)
    elapsed=round(time.perf_counter()-tic,2)
    if done.returncode:raise RuntimeError(f"model exit={done.returncode}, see {log}")
    text=out.read_text().strip()
    match=re.search(r'\{.*\}',text,re.S)
    if not match:raise RuntimeError("invalid model output "+text[:350])
    obj=json.loads(match.group())
    if not isinstance(obj.get('inspect_html'),bool) or not isinstance(obj.get('click_ids'),list):
        raise RuntimeError("invalid model action shape: "+repr(obj))
    usage=re.search(r'tokens used\s*\n([\d,]+)',log.read_text(),re.I)
    return dict(phase=phase,action=obj,elapsed_s=elapsed,tokens_reported=int(usage.group(1).replace(',','')) if usage else None)

def execute(exe,label,tasks,workdir):
    server=http.server.ThreadingHTTPServer(("127.0.0.1",0),SilentHandler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    url=f"http://127.0.0.1:{server.server_port}/model_heldout.html"
    with (workdir/f"{label}-mcp.stderr.log").open("w") as err:
        process=subprocess.Popen([str(exe),"mcp","--log-level","error"],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=err,start_new_session=True,bufsize=0)
        calls=0
        def tool(i,name,args):
            nonlocal calls
            calls+=1
            res=rpc(process,{"jsonrpc":"2.0","id":i,"method":"tools/call","params":{"name":name,"arguments":args}},timeout=20)
            if res.get('isError'):raise RuntimeError(f"MCP {name} error {res}")
            return parse_tree(res)
        try:
            rpc(process,{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"heldout-agent-pilot","version":"0.1"}}})
            process.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n');process.stdin.flush()
            tree=tool(2,"tree",{"url":url})
            model_steps=[ask_model(prompt_text(tasks,tree),workdir,label,"initial")]
            decision=model_steps[-1]['action']
            n=3
            if decision['inspect_html']:
                if decision['click_ids']:raise RuntimeError("inspection and click in same response")
                markup=tool(n,"html",{});n+=1
                model_steps.append(ask_model(prompt_text(tasks,tree,markup),workdir,label,"after-html"))
                decision=model_steps[-1]['action']
            if decision['inspect_html']:raise RuntimeError("unresolved state after one permitted HTML inspection")
            ids=[x['id'] for x in tasks]
            clicks=decision['click_ids']
            if len(clicks)!=len(set(clicks)) or any(x not in ids for x in clicks):
                raise RuntimeError("unknown or duplicate model action id")
            for ident in clicks:
                tool(n,"click",{"selector":"#"+ident});n+=1
            final=tool(n,"evaluate",{"script":"Array.from(document.querySelectorAll('[id^=case-]')).map(el=>el.id+'='+String(el.getAttribute('aria-checked')??el.getAttribute('aria-expanded'))).join(';')"})
            states=dict((k,v.lower()) for k,v in re.findall(r'(case-\d{2})=(true|false|TRUE|FALSE)',final))
            if len(states)!=len(tasks):raise RuntimeError("scorer saw incomplete states "+repr(final))
            correct=sum(states[t['id']]=='true' for t in tasks)
            return dict(label=label,binary_sha256=hashlib.sha256(exe.read_bytes()).hexdigest(),fixture_sha256=hashlib.sha256((ROOT/'fixtures'/'model_heldout.html').read_bytes()).hexdigest(),
                        tasks=len(tasks),correct_final=correct,initial_true=sum(t['initial'] for t in tasks),
                        mcp_tool_calls=calls,click_count=len(clicks),model_calls=len(model_steps),
                        model_time_s=sum(x['elapsed_s'] for x in model_steps),model_tokens_reported=sum(x['tokens_reported'] or 0 for x in model_steps),
                        model_decisions=model_steps,actual_final=states,measurement="1 synthetic held-out fixture, model decisions via Codex exec; exploratory only")
        finally:
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            process.wait(timeout=5);server.shutdown();server.server_close()

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument('--binary',required=True)
    p.add_argument('--label',required=True)
    a=p.parse_args()
    task=fixture()
    w=ROOT/'model-pilot';w.mkdir(exist_ok=True)
    output=execute(Path(a.binary).resolve(),a.label,task,w)
    (ROOT/'results'/f"{a.label}-model-pilot.json").write_text(json.dumps(output,indent=2)+"\n")
    print(json.dumps({k:v for k,v in output.items() if k not in ('model_decisions','actual_final')},indent=2))
