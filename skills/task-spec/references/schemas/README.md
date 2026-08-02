# Task-Spec v3 — Machine-Readable Schemas

> **Purpose:** JSON Schema (draft 2020-12) definitions for the two YAML blocks in a Task-Spec file: the top-level frontmatter, and the inner `validation_card`. Together they make the current Task-Spec format (v3.1) machine-consumable from any language.
>
> **Single source of truth:** `validate-task-spec.sh --emit-schema <name>` prints the file content of the schema. Downstream consumers should fetch via that command, not hard-code copies.

## Schemas

| File | Validates | Notes |
|------|-----------|-------|
| `task-spec-frontmatter.schema.json` | YAML frontmatter at top of T-*.md | required fields, enums for `status` and `severity`; `execution_backend` as an OPEN STRING (non-normative `examples`, not an enum allow-list); the sign-off envelope shape — structural floor (`signed_off` + `signed_off_by` + `signed_off_at`) plus the key-optional HMAC field `signed_off_sig` (`hmac-sha256-v1:<keyid>:<hex>`, v2.2); v3 fields (`profile`, `parent`, `accepted*`, `requires`, `baseline_ref`, `reference_solution`) |
| `agent-contract.schema.json` | YAML inside the `Validation Card` zone | `success_criteria[]` (incl. `verifies: [B-N]`), `retry_policy{}`, `agent_contract{}` (version=2: `produce`/`required_tools`/`timeout_minutes`/`sandbox_type`/`emit`/`backend_metadata`) |

## Emit-from-validator pattern

```bash
bash .claude/skills/task-spec/scripts/validate-task-spec.sh --emit-schema frontmatter > frontmatter.schema.json
bash .claude/skills/task-spec/scripts/validate-task-spec.sh --emit-schema agent-contract > agent-contract.schema.json
```

Always prefer this over copying the JSON file directly; the validator is the canonical surface.

## Consuming the schemas

### Python (jsonschema)

```python
import json, yaml
from jsonschema import Draft202012Validator

with open("frontmatter.schema.json") as f:
    schema = json.load(f)
with open("T-20260602-golden.md") as f:
    text = f.read()
_, fm, _ = text.split("---\n", 2)
frontmatter = yaml.safe_load(fm)
Draft202012Validator(schema).validate(frontmatter)
```

### Node / TypeScript (ajv)

```typescript
import Ajv from "ajv";
import YAML from "yaml";
import { readFileSync } from "node:fs";

const schema = JSON.parse(readFileSync("frontmatter.schema.json", "utf8"));
const text = readFileSync("T-20260602-golden.md", "utf8");
const [, fm] = text.split("---\n", 3);
const frontmatter = YAML.parse(fm);

const ajv = new Ajv({ strict: false, allErrors: true });
const validate = ajv.compile(schema);
if (!validate(frontmatter)) {
  console.error(validate.errors);
  process.exit(1);
}
```

### Go (gojsonschema)

```go
package main

import (
    "fmt"
    "os"
    "github.com/xeipuuv/gojsonschema"
    "gopkg.in/yaml.v3"
)

func main() {
    schemaLoader := gojsonschema.NewReferenceLoader("file://frontmatter.schema.json")
    raw, _ := os.ReadFile("T-20260602-golden.md")
    parts := splitFrontmatter(string(raw))
    var fm map[string]interface{}
    _ = yaml.Unmarshal([]byte(parts), &fm)
    docLoader := gojsonschema.NewGoLoader(fm)
    result, err := gojsonschema.Validate(schemaLoader, docLoader)
    if err != nil { panic(err) }
    if !result.Valid() {
        for _, desc := range result.Errors() {
            fmt.Println("-", desc)
        }
        os.Exit(1)
    }
}
```

### Rust (jsonschema)

```rust
use jsonschema::{Draft, JSONSchema};
use serde_json::Value;
use serde_yaml;
use std::fs;

fn main() {
    let schema: Value = serde_json::from_str(
        &fs::read_to_string("frontmatter.schema.json").unwrap()
    ).unwrap();
    let compiled = JSONSchema::options()
        .with_draft(Draft::Draft202012)
        .compile(&schema)
        .expect("schema compiles");
    let raw = fs::read_to_string("T-20260602-golden.md").unwrap();
    let parts: Vec<&str> = raw.splitn(3, "---\n").collect();
    let fm: Value = serde_yaml::from_str(parts[1]).unwrap();
    if let Err(errors) = compiled.validate(&fm) {
        for e in errors { eprintln!("- {}", e); }
        std::process::exit(1);
    }
}
```

## Versioning

The schema `$id` includes the Task-Spec format version. Breaking schema changes bump the format version and require:

1. New schema file pinned to the new `$id`
2. CHANGELOG entry under the `[Unreleased]` heading
3. The validator continues to accept the prior format with deprecation warnings until the format is retired

## Related

- `references/concepts/agent-contract.md` — human-readable field reference for `agent_contract` v2
- `references/concepts/task-spec-v1.md` — format definition (zones, frontmatter, validation card)
- `examples/consume-task-spec.py` — minimal Python consumer
- `examples/consume-task-spec.ts` — minimal TypeScript consumer
