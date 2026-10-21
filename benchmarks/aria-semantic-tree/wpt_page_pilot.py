#!/usr/bin/env python3
"""Run real WPT-authored pages on native Lightpanda + WPT's actual local server.
This uses Lightpanda's custom testharnessreport.js, NOT standard wptrunner."""
import argparse, collections, hashlib, json, os, signal, subprocess, time, urllib.request
from pathlib import Path
from benchmark import rpc,parse_tree,ROOT
WPT=ROOT/'wpt-official'
REPORT=WPT/'resources'/'testharnessreport.js'
FORK_REPORT=ROOT/'lightpanda-testharnessreport.js'
CONFIG=ROOT/'wpt-loopback.json'
PATHS=['/wai-aria/idlharness.window.html','/wai-aria/checked/checked.tentative.html']

def ready(url):
    try:
        with urllib.request.urlopen(url, timeout=1.5) as r:return r.status
    except Exception:return None

def mcp_run(exe,url,label,test):
    logfile=ROOT/'results'/f'{label}-{test}-wpt-harness.stderr.log'
    with logfile.open('w') as err:
        p=subprocess.Popen([str(exe),'mcp','--log-level','error'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=err,start_new_session=True,bufsize=0)
        ident=1
        def call(name,args):
            nonlocal ident
            ident+=1
            response=rpc(p,{'jsonrpc':'2.0','id':ident,'method':'tools/call','params':{'name':name,'arguments':args}},timeout=20)
            if response.get('isError'):raise RuntimeError(f'{name}: {response}')
            return parse_tree(response)
        try:
            rpc(p,{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'wpt-page-pilot','version':'1'}}})
            p.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n');p.stdin.flush()
            call('tree',{'url':url})
            done=None
            for j in range(35):
                value=call('evaluate',{'script':"JSON.stringify((typeof report !== 'undefined') ? {complete:report.complete,completed:report.completed,cases:report.cases}: {missing:true})"})
                try:
                    done=json.loads(value)
                except Exception:
                    done={'parse_error':value[:250]}
                if done.get('complete'):break
                time.sleep(.25)
            return {'url':url,'complete':bool(done and done.get('complete')),'report':done,'polls':j+1}
        finally:
            try:os.killpg(p.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            p.wait(timeout=5)

def main(args):
    orig=REPORT.read_bytes()
    config={'browser_host':'localhost','alternate_hosts':{'alt':'127.0.0.1'},'server_host':'127.0.0.1','check_subdomains':False}
    CONFIG.write_text(json.dumps(config)+'\n')
    serverlog=(ROOT/'results'/'official-wpt-serve.log').open('w')
    server=None
    try:
        REPORT.write_bytes(FORK_REPORT.read_bytes())
        server=subprocess.Popen(['./wpt','serve','--config',str(CONFIG),'--no-h2'],cwd=WPT,stdout=serverlog,stderr=subprocess.STDOUT,start_new_session=True)
        for i in range(70):
            if server.poll() is not None:raise RuntimeError('WPT server exited; see official-wpt-serve.log')
            if ready('http://127.0.0.1:8000/wai-aria/checked/checked.tentative.html')==200:break
            time.sleep(.2)
        else:raise RuntimeError('WPT server readiness timeout')
        runs=[]
        for path in PATHS:
            slug=path.split('/')[-1].replace('.','_')
            url='http://127.0.0.1:8000'+path
            code=ready(url)
            if code!=200:
                runs.append({'url':url,'http_code':code,'error':'WPT generated page not available'});continue
            try:res=mcp_run(args.binary,url,args.label,slug)
            except Exception as exc:res={'url':url,'error':repr(exc)}
            cases=res.get('report',{}).get('cases',{}) if isinstance(res.get('report'),dict) else {}
            status=collections.Counter()
            for name,record in cases.items():
                if isinstance(record,str):
                    parts=record.split('|');status[parts[1] if len(parts)>1 else 'Unrecognized']+=1
            res['status_counts']=dict(status)
            res['total_reported']=len(cases)
            runs.append(res)
        receipt={'label':args.label,'binary':str(args.binary),'binary_sha256':hashlib.sha256(args.binary.read_bytes()).hexdigest(),
                 'wpt_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=WPT,text=True).strip(),
                 'server':'official ./wpt serve, loopback configuration',
                 'reporter':'Lightpanda fork custom testharnessreport.js replaces vanilla WPT reporter',
                 'classification':'actual WPT-authored pages + WPT testharness JS but NOT official wptrunner result',
                 'runs':runs}
        (ROOT/'results'/f'{args.label}-wpt-page-pilot.json').write_text(json.dumps(receipt,indent=2)+'\n')
        print(json.dumps({**receipt,'runs':[{k:v for k,v in r.items() if k!='report'} for r in runs]},indent=2))
    finally:
        REPORT.write_bytes(orig)
        if server:
            try:os.killpg(server.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            server.wait(timeout=5)
        serverlog.close()

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--binary',required=True,type=Path);a.add_argument('--label',required=True)
    main(a.parse_args())
