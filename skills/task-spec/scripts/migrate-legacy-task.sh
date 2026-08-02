#!/usr/bin/env bash
# migrate-legacy-task.sh — Convert a legacy Task-Spec (v0) to v1-shaped output.
#
# Usage:
#   bash migrate-legacy-task.sh <path/to/T-*.md>
#
# What it does:
#   - Adds format_version: 1 to frontmatter
#   - Adds budget_iterations: 15 if missing
#   - Converts markdown checklist/bullet items under ## Success criteria
#     into stub eval_N() bash functions
#   - Injects a ## Validation Card YAML block
#   - Updates ## Exit check to call all evals
#   - Renames legacy section headers to v1 casing (in-place)
#
# The script modifies the file in-place. Back up before running.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./_lib.sh
source "$SCRIPT_DIR/_lib.sh"
ts_version_flag "$@"

FILE="${1:?Usage: migrate-legacy-task.sh <path/to/T-*.md>}"

if [[ ! -f "$FILE" ]]; then
  echo "FAIL: $FILE not found" >&2
  exit 1
fi

# Use python3 for reliable markdown parsing and rewriting
python3 - "$FILE" <<'PYEOF'
import sys
import re

path = sys.argv[1]

with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# --- Step 1: Update frontmatter ---
frontmatter_start = None
frontmatter_end = None
for i, line in enumerate(lines):
    if line.strip() == "---":
        if frontmatter_start is None:
            frontmatter_start = i
        else:
            frontmatter_end = i
            break

fm_text = "".join(lines[frontmatter_start:frontmatter_end+1]) if frontmatter_start is not None and frontmatter_end is not None else ""

# Add format_version: 1 if missing
if "format_version:" not in fm_text:
    # Insert after the first ---
    lines.insert(frontmatter_start + 1, "format_version: 1\n")
    frontmatter_end += 1
    fm_text = "".join(lines[frontmatter_start:frontmatter_end+1])

# Add budget_iterations: 15 if missing
if "budget_iterations:" not in fm_text:
    # Insert near the end of frontmatter, before the closing ---
    lines.insert(frontmatter_end, "budget_iterations: 15\n")
    frontmatter_end += 1

# --- Step 2: Parse sections ---
Section = []
current_section = None
for i, line in enumerate(lines):
    m = re.match(r'^##\s+(.+)$', line)
    if m:
        current_section = m.group(1).strip()
    Section.append((i, current_section, line))

# --- Step 3: Extract success criteria items ---
# Find the success criteria section and collect checklist/bullet items
sc_items = []
in_sc = False
sc_start = None
sc_end = None
for idx, sec, line in Section:
    if sec and re.match(r'^Success criteria', sec, re.I):
        if sc_start is None:
            sc_start = idx
            in_sc = True
        if in_sc:
            sc_end = idx
        continue
    if in_sc and sec is not None and sec != Section[idx-1][1] if idx > 0 else False:
        # We've hit a new section
        in_sc = False
        break
    if in_sc:
        sc_end = idx

# Refine: success criteria section runs from sc_start to just before next ##
if sc_start is not None:
    for i in range(sc_start + 1, len(lines)):
        if re.match(r'^##\s', lines[i]):
            sc_end = i - 1
            break
    else:
        sc_end = len(lines) - 1

    # Extract items: lines matching - [ ] or - 
    for i in range(sc_start + 1, sc_end + 1):
        line = lines[i]
        m = re.match(r'^(\s*-\s+(?:\[ \]\s*)?)(.+)$', line)
        if m:
            item_text = m.group(2).strip()
            # Normalize: remove backticks for the description
            desc = item_text
            sc_items.append(desc)

# --- Step 4: Build eval stubs ---
eval_blocks = []
for n, desc in enumerate(sc_items, start=1):
    safe_desc = desc.replace('"', '\\"')
    block = f"""# eval-{n}: {desc}
eval_{n}() {{
  echo "TODO: implement check — {safe_desc}"
  return 1
}}
"""
    eval_blocks.append(block)

if not eval_blocks:
    # Fallback: create a single stub eval
    eval_blocks.append("""# eval-1: placeholder (no checklist items detected)
eval_1() {
  echo "TODO: define success criteria eval"
  return 1
}
""")

# --- Step 5: Build validation card YAML ---
val_card_lines = ["## Validation Card\n", "\n", "```yaml\n"]
val_card_lines.append("success_criteria:\n")
for n, desc in enumerate(sc_items if sc_items else ["placeholder"], start=1):
    safe_desc = desc.replace('"', '\\"')
    val_card_lines.append(f"  - id: eval_{n}\n")
    val_card_lines.append(f"    description: \"{safe_desc}\"\n")
    val_card_lines.append("    runnable: bash\n")
    val_card_lines.append("    terminal: true\n")
    val_card_lines.append("    expected_duration_sec: 5\n")
val_card_lines.append("\n")
val_card_lines.append("retry_policy:\n")
val_card_lines.append("  max_iterations: 15\n")
val_card_lines.append("  circuit_breaker_no_progress: 3\n")
val_card_lines.append("  on_terminal_failure: park_with_context\n")
val_card_lines.append("\n")
val_card_lines.append("agent_contract:\n")
val_card_lines.append("  read: [intent, contract, guardrails, operations]\n")
val_card_lines.append("  produce: code | docs | config\n")
val_card_lines.append("  verify: run all success_criteria\n")
val_card_lines.append("  emit: pass | fail | retry_with_reason | parked_with_context\n")
val_card_lines.append("```\n")
val_card_lines.append("\n")

# --- Step 6: Build exit check ---
exit_check_lines = ["## Exit Check\n", "\n", "```bash\n"]
if sc_items:
    eval_calls = " && ".join(f"eval_{n}" for n in range(1, len(sc_items) + 1))
else:
    eval_calls = "eval_1"
exit_check_lines.append(f"# Final proof-of-done. Returns 0 only when ALL evals pass.\n")
exit_check_lines.append(f"{eval_calls}\n")
exit_check_lines.append("```\n")
exit_check_lines.append("\n")

# --- Step 7: Reconstruct the file ---
new_lines = []

# Frontmatter
new_lines.extend(lines[:frontmatter_end + 1])
new_lines.append("\n")

# Copy everything after frontmatter, transforming sections
post_fm = lines[frontmatter_end + 1:]

i = 0
while i < len(post_fm):
    line = post_fm[i]

    # Detect section headers
    m = re.match(r'^##\s+(.+)$', line)
    if m:
        sec_name = m.group(1).strip()

        # Skip old Validation Card if present (we'll insert our own)
        if re.match(r'^Validation Card', sec_name, re.I):
            i += 1
            while i < len(post_fm) and not re.match(r'^##\s', post_fm[i]):
                i += 1
            continue

        # Transform Success criteria -> Success Criteria with eval stubs
        if re.match(r'^Success criteria', sec_name, re.I):
            new_lines.append("## Success Criteria\n")
            new_lines.append("\n")
            new_lines.append("Each criterion is a runnable bash function returning 0 (pass) or non-zero (fail).\n")
            new_lines.append("Each MUST be terminal (deterministic, idempotent, non-flaky).\n")
            new_lines.append("\n")
            new_lines.append("```bash\n")
            for block in eval_blocks:
                new_lines.append(block)
            new_lines.append("```\n")
            new_lines.append("\n")
            # Skip old section content
            i += 1
            while i < len(post_fm) and not re.match(r'^##\s', post_fm[i]):
                i += 1
            # Insert Validation Card right after Success Criteria
            new_lines.extend(val_card_lines)
            continue

        # Transform Exit check -> Exit Check
        if re.match(r'^Exit check', sec_name, re.I):
            new_lines.extend(exit_check_lines)
            i += 1
            while i < len(post_fm) and not re.match(r'^##\s', post_fm[i]):
                i += 1
            continue

        # Normalize other section headers
        if re.match(r'^Anti-patterns', sec_name, re.I):
            new_lines.append("## Anti-Patterns\n")
            i += 1
            continue
        if re.match(r'^Do-not-touch', sec_name, re.I):
            new_lines.append("## Do-Not-Touch\n")
            i += 1
            continue
        if re.match(r'^Open questions', sec_name, re.I):
            new_lines.append("## Open Questions\n")
            i += 1
            continue
        if re.match(r'^Why this matters', sec_name, re.I):
            new_lines.append("## Context\n")
            i += 1
            continue
        if re.match(r'^Implementation steps', sec_name, re.I):
            new_lines.append("## Context\n")
            i += 1
            continue

    new_lines.append(line)
    i += 1

# Ensure trailing newline
if new_lines and not new_lines[-1].endswith("\n"):
    new_lines[-1] += "\n"

with open(path, "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print(f"Migrated {path} to Task-Spec v1 shape")
PYEOF
