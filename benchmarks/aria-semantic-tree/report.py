#!/usr/bin/env python3
"""Generate verified plain-text summary from artifact files; refuse missing snapshots."""
from pathlib import Path
import csv,json,subprocess
BASE=Path(__file__).resolve().parent
VERSIONS=[
    ("pre4036","0bef9e72","Oct 18 older build","pre4129"),
    ("post4036","463360ad","Merged #4036","post4036"),
    ("post4129","725ff748","PR #4129 head","post4129")
]
rows=[]
for label,sha,stage,prefix in VERSIONS:
    observation=json.loads((BASE/"results"/(prefix+".json")).read_text())
    tasks=json.loads((BASE/"results"/(prefix+"-workflow.json")).read_text())
    mcp_wpt=json.loads((BASE/"results"/(prefix+"-wpt.json")).read_text())
    cdp_wpt=json.loads((BASE/"results"/(prefix+"-cdp-wpt.json")).read_text())
    if mcp_wpt["binary_sha256"] != cdp_wpt["binarySha256"] or mcp_wpt["source_sha256"] != cdp_wpt["sourceSha256"]:
        raise SystemExit("MISMATCH: WPT source/binary differs across MCP and CDP")
    if observation["binary_sha256"]!=tasks["binary_sha256"]:
        raise SystemExit("MISMATCH: binaries differ for "+label)
    if observation["fixture_sha256"] != json.loads((BASE/"results"/"post4129.json").read_text())["fixture_sha256"]:
        raise SystemExit("MISMATCH: regression fixture hashes differ")
    if tasks["fixture_sha256"] != json.loads((BASE/"results"/"post4129-workflow.json").read_text())["fixture_sha256"]:
        raise SystemExit("MISMATCH: workflow fixture hashes differ")
    binary=Path(observation['binary'])
    if binary.exists() and binary.name in ('pre4129','post4036','post4129'):
        proc=subprocess.run([str(binary),"version"],capture_output=True,text=True,check=True)
        version=proc.stdout.strip()
    else:version="unavailable"
    runs=tasks["raw_runs"]
    row={
        "stage":stage,"commit":sha,"version":version,"sha256":observation["binary_sha256"],
        "regression_visible":observation["correct"],"regression_total":observation["total"],
        "regression_wrong":observation["wrong"],"regression_unknown":observation["unknown"],
        "negative_controls_clear":sum(n["present"] and not n["spurious_state"] for n in observation["negative_controls"]),
        "regression_tree_bytes":observation["tree_bytes"],
        "regression_median_ms":observation["median_tree_ms"],
        "workflow_known":int(tasks["median_known"]),"workflow_total":tasks["tasks"],
        "workflow_final_correct":int(tasks["median_final_correct"]),
        "workflow_clicks":int(sorted(r["clicks"] for r in runs)[len(runs)//2]),
        "workflow_tree_bytes":tasks["median_tree_bytes"],
        "workflow_median_ms":tasks["median_tree_ms"],
        "wpt_cdp_projected_correct":cdp_wpt["correct"],
        "wpt_mcp_projected_correct":mcp_wpt["correct"],
        "wpt_projected_total":cdp_wpt["total"]
    }
    rows.append(row)
with (BASE/"results"/"summary.csv").open("w",newline="") as handle:
    writer=csv.DictWriter(handle,fieldnames=list(rows[0]))
    writer.writeheader();writer.writerows(rows)
(BASE/"results"/"summary.json").write_text(json.dumps({"method":"Synthetic local MCP state visibility and deterministic one-read toggle decisions; not LLM accuracy","runs":rows},indent=2)+"\n")
for r in rows:
    print(f'{r["stage"]} ({r["commit"]}): states {r["regression_visible"]}/{r["regression_total"]}; first-read {r["workflow_known"]}/{r["workflow_total"]}; final outcomes {r["workflow_final_correct"]}/{r["workflow_total"]}; median tree {r["workflow_median_ms"]} ms')
