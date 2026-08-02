#!/usr/bin/env -S npx ts-node
/**
 * Minimal Task-Spec v2.1.1 consumer (TypeScript).
 *
 * Parses a T-*.md file, validates the YAML frontmatter against the published
 * JSON Schema, extracts the validation_card block (agent_contract +
 * retry_policy + success_criteria), enumerates eval_N() bash blocks, and
 * prints a structured TaskSpec record.
 *
 * Runtime: Node 18+. Third-party deps: `yaml` (parser) and `ajv` (validator),
 * pinned in references/examples/package.json. Schemas are resolved relative
 * to this file: ../schemas/task-spec-frontmatter.schema.json.
 *
 * Usage:
 *   npx ts-node consume-task-spec.ts <path/to/T-*.md>
 *
 * Exit codes:
 *   0 — parsed and validated cleanly
 *   1 — file missing / unreadable / frontmatter malformed
 *   2 — schema validation failed
 */
import { readFileSync, existsSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import YAML from "yaml";
import Ajv2020 from "ajv/dist/2020.js";

const __filename =
  typeof __dirname !== "undefined"
    ? `${__dirname}/consume-task-spec.ts`
    : fileURLToPath(import.meta.url);
const HERE = dirname(__filename);
const SCHEMAS_DIR = resolve(HERE, "..", "schemas");
const FRONTMATTER_SCHEMA = resolve(SCHEMAS_DIR, "task-spec-frontmatter.schema.json");
const CONTRACT_SCHEMA = resolve(SCHEMAS_DIR, "agent-contract.schema.json");

const EVAL_FN_RE = /^(eval_\d+)\s*\(\)\s*\{/gm;

interface TaskSpec {
  path: string;
  id: string;
  title: string;
  status: string;
  format_version: unknown;
  execution_backend: string;
  signed_off: boolean;
  frontmatter: Record<string, unknown>;
  validation_card: Record<string, unknown>;
  eval_ids: string[];
}

function splitFrontmatter(text: string): { frontmatter: Record<string, unknown>; body: string } {
  if (!text.startsWith("---")) {
    throw new Error("file does not start with YAML frontmatter '---'");
  }
  const parts = text.split("---\n");
  if (parts.length < 3) {
    throw new Error("frontmatter not terminated by a closing '---' line");
  }
  const yamlText = parts[1];
  const body = parts.slice(2).join("---\n");
  const fm = (YAML.parse(yamlText) ?? {}) as Record<string, unknown>;
  return { frontmatter: fm, body };
}

function extractValidationCard(body: string): Record<string, unknown> {
  const marker = "## Validation Card";
  const idx = body.indexOf(marker);
  if (idx === -1) return {};
  const after = body.slice(idx + marker.length);
  const fenceStart = after.indexOf("```yaml");
  if (fenceStart === -1) return {};
  const fromYaml = after.slice(fenceStart + "```yaml".length);
  const fenceEnd = fromYaml.indexOf("```");
  if (fenceEnd === -1) return {};
  return (YAML.parse(fromYaml.slice(0, fenceEnd)) ?? {}) as Record<string, unknown>;
}

function extractEvalIds(body: string): string[] {
  const marker = "## Success Criteria";
  const idx = body.indexOf(marker);
  if (idx === -1) return [];
  const after = body.slice(idx + marker.length);
  const end = after.indexOf("\n## ");
  const block = end === -1 ? after : after.slice(0, end);
  const ids: string[] = [];
  let match: RegExpExecArray | null;
  while ((match = EVAL_FN_RE.exec(block)) !== null) {
    ids.push(match[1]);
  }
  return ids;
}

function validate(
  instance: unknown,
  schemaPath: string,
  label: string,
  ajv: Ajv2020,
): void {
  if (!existsSync(schemaPath)) {
    process.stderr.write(`WARN: ${label} schema missing at ${schemaPath}\n`);
    return;
  }
  const schema = JSON.parse(readFileSync(schemaPath, "utf8"));
  const validateFn = ajv.compile(schema);
  if (!validateFn(instance)) {
    for (const err of validateFn.errors ?? []) {
      process.stderr.write(`FAIL ${label}: ${err.instancePath || "(root)"} — ${err.message}\n`);
    }
    process.exit(2);
  }
}

function parse(path: string): TaskSpec {
  const text = readFileSync(path, "utf8");
  const { frontmatter, body } = splitFrontmatter(text);
  const card = extractValidationCard(body);
  const evalIds = extractEvalIds(body);
  const ajv = new Ajv2020({ strict: false, allErrors: true });
  validate(frontmatter, FRONTMATTER_SCHEMA, "frontmatter", ajv);
  if (Object.keys(card).length > 0) {
    validate(card, CONTRACT_SCHEMA, "validation_card", ajv);
  }
  return {
    path,
    id: String(frontmatter["id"] ?? ""),
    title: String(frontmatter["title"] ?? ""),
    status: String(frontmatter["status"] ?? ""),
    format_version: frontmatter["format_version"],
    execution_backend: String(frontmatter["execution_backend"] ?? ""),
    signed_off: Boolean(frontmatter["signed_off"] ?? false),
    frontmatter,
    validation_card: card,
    eval_ids: evalIds,
  };
}

function main(argv: string[]): number {
  if (argv.length === 0) {
    process.stderr.write("Usage: consume-task-spec.ts <path/to/T-*.md>\n");
    return 1;
  }
  const target = resolve(argv[0]);
  if (!existsSync(target)) {
    process.stderr.write(`ERROR: ${target} not found\n`);
    return 1;
  }
  const spec = parse(target);
  const summary = {
    ...spec,
    frontmatter: {
      id: spec.frontmatter["id"],
      status: spec.frontmatter["status"],
      format_version: spec.frontmatter["format_version"],
      execution_backend: spec.frontmatter["execution_backend"],
      signed_off: spec.frontmatter["signed_off"],
    },
  };
  process.stdout.write(JSON.stringify(summary, null, 2) + "\n");
  return 0;
}

process.exit(main(process.argv.slice(2)));
