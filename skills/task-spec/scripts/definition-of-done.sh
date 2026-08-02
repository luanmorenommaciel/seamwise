#!/usr/bin/env bash
# definition-of-done.sh — render a Task-Spec's Definition of Done + traceability
# matrix, and gate on it. The 2026 agent-spec SOTA (Brodner, Moai, Thread AI, Nimbalyst)
# converges on ONE highest-value artifact: a reviewable "every acceptance criterion →
# its verifying eval → result" matrix, so "is this done?" is answerable in seconds and
# an agent cannot stop early. cvg already carries the data (Behavior B-N + the Validation
# Card's `verifies:` mapping); this surfaces it and makes an untraced behavior FAIL.
#
# Usage: definition-of-done.sh <task-spec.md>
# Token (last line): DOD=COMPLETE | GAPS | USAGE_ERROR
# Exit: 0 complete · 1 gaps (a behavior with no verifying eval, or an eval untraced) · 2 usage
# bash 3.2-safe; Python stdlib-only (no pip, no yaml lib).
set -euo pipefail

# Honor --version uniformly (doc-lint requires every task-spec script to answer
# --version). Source the shared lib only for ts_version_flag / TASKSPEC_VERSION;
# the analysis itself remains Python-stdlib.
_DOD_LIB="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_lib.sh"
# shellcheck source=./_lib.sh
source "$_DOD_LIB"
ts_version_flag "$@"

FILE="${1:-}"
if [ -z "$FILE" ] || [ ! -f "$FILE" ]; then
  echo "ERROR: usage: definition-of-done.sh <task-spec.md>" >&2
  echo "DOD=USAGE_ERROR"; exit 2
fi

set +e
python3 - "$FILE" <<'PY'
import re, sys
spec = open(sys.argv[1], encoding="utf-8", errors="replace").read()

# behaviors: "- **B-1** — text"
behaviors = re.findall(r'^\s*-\s*\*\*(B-\d+)\*\*\s*[—-]?\s*(.+?)\s*$', spec, re.M)
bmap = dict(behaviors)

# the Validation Card success_criteria block (up to retry_policy/agent_contract)
m = re.search(r'success_criteria:\s*\n(.*?)\n\s*(?:retry_policy:|agent_contract:)', spec, re.S)
sc = m.group(1) if m else ""
# split into entries at top-level "- " list markers (handles inline {..} and block form)
entries = [e for e in re.split(r'\n\s{0,4}-\s', "\n" + sc) if e.strip()]
evals = []
for e in entries:
    eid = re.search(r'\bid:\s*(eval_\d+)', e)
    if not eid:
        continue
    desc = re.search(r'\bdescription:\s*"?([^,\n}"]+)', e)
    ver = re.search(r'\bverifies:\s*\[([^\]]*)\]', e)
    term = re.search(r'\bterminal:\s*(true|false)', e)
    evals.append({
        "id": eid.group(1),
        "desc": (desc.group(1).strip() if desc else ""),
        "verifies": [v.strip() for v in (ver.group(1).split(",") if ver and ver.group(1).strip() else [])],
        "terminal": (term.group(1) == "true" if term else False),
    })

# Exit Check (the runnable DoD)
xc = re.search(r'##\s*Exit Check\s*\n+```bash\s*\n(.*?)\n```', spec, re.S)
exit_check = xc.group(1).strip() if xc else "(none)"

print("== Definition of Done · %s ==" % sys.argv[1].split("/")[-1])
gaps = []

if behaviors:
    print("\nTraceability (every behavior → its verifying eval):")
    verified_by = {}
    for ev in evals:
        for b in ev["verifies"]:
            verified_by.setdefault(b, []).append(ev["id"])
    for bid, btext in behaviors:
        evs = verified_by.get(bid, [])
        mark = "x" if evs else " "
        print("  [%s] %s → %s" % (mark, bid, (", ".join(evs) if evs else "NO EVAL — untraced")))
        print("        %s" % (btext[:96]))
        if not evs:
            gaps.append("%s has no verifying eval" % bid)
    # every eval should trace to a behavior when behaviors exist
    for ev in evals:
        if not ev["verifies"]:
            gaps.append("%s has no verifies: mapping" % ev["id"])
else:
    print("\n(no Behavior zone — profile: lite; the evals ARE the definition of done)")

print("\nDoD checklist (each acceptance criterion, terminal marked *):")
if not evals:
    gaps.append("no success_criteria / evals declared")
for ev in evals:
    star = " *" if ev["terminal"] else "  "
    trace = (" ⟵ %s" % ",".join(ev["verifies"])) if ev["verifies"] else ""
    print("  [ ]%s %s — %s%s" % (star, ev["id"], (ev["desc"] or "(no description)"), trace))
print("\nExit Check (runnable):\n  %s" % exit_check)

print("")
if gaps:
    for g in gaps:
        print("  GAP: %s" % g, file=sys.stderr)
    print("DOD=GAPS"); sys.exit(1)
print("DOD=COMPLETE"); sys.exit(0)
PY
RC=$?
set -e
exit "$RC"
