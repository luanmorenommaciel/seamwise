"""Recipe-to-seam-map projection and seam-map verification."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from seamwise.constants import (
    EXIT_CONFLICT,
    EXIT_INVALID,
    EXIT_NEEDS_INPUT,
    SEAM_AMBIGUOUS,
    SEAM_ERROR,
    SEAM_NEEDS_DISCOVERY,
    SEAM_NEEDS_OWNER,
    SEAM_READY,
)
from seamwise.contracts import validate_contract
from seamwise.engine.recipe import (
    _load_recipe,
    _semantic_recipe_checks,
    _verify_local_recipe_sources,
    _write_path_state_diagnostics,
)
from seamwise.engine.support import _canonical_project_path, _diag, _event
from seamwise.io import (
    TransactionWriter,
    UnsafeWriteTargetError,
    canonical_json,
    load_yaml,
    sha256_bytes,
    sha256_file,
    workspace_lock,
)
from seamwise.render import (
    render_decision,
    render_intent,
    render_seam,
    render_system_map,
)
from seamwise.result import Diagnostic, Result
from seamwise.safety import workspace_boundary_diagnostics


def map_recipe(root: Path, source: Path, *, dry_run: bool = False) -> Result:
    boundary_diagnostics = workspace_boundary_diagnostics(root)
    if boundary_diagnostics:
        return Result("map", SEAM_ERROR, EXIT_CONFLICT, root, diagnostics=boundary_diagnostics)
    recipe, diagnostics, recipe_sha = _load_recipe(source)
    if recipe is None:
        return Result("map", SEAM_ERROR, EXIT_INVALID, root, diagnostics=diagnostics)
    assert recipe_sha is not None
    schema_errors = validate_contract("recipe", recipe)
    if schema_errors:
        if not recipe.get("evidence"):
            token, exit_code = SEAM_NEEDS_DISCOVERY, EXIT_NEEDS_INPUT
        elif any(
            not seam.get("owner")
            or not isinstance(seam.get("swimlane"), dict)
            or not seam["swimlane"].get("owner")
            for seam in recipe.get("seams", [])
            if isinstance(seam, dict)
        ):
            token, exit_code = SEAM_NEEDS_OWNER, EXIT_NEEDS_INPUT
        else:
            token, exit_code = SEAM_ERROR, EXIT_INVALID
        return Result(
            "map",
            token,
            exit_code,
            root,
            diagnostics=[_diag("recipe_schema", message, source) for message in schema_errors],
            next_steps=["Repair the authored recipe without inventing missing facts."],
        )
    source_diagnostics = _verify_local_recipe_sources(root, source, recipe)
    if source_diagnostics:
        mismatch = any(item.code == "local_source_hash_mismatch" for item in source_diagnostics)
        return Result(
            "map",
            SEAM_AMBIGUOUS if mismatch else SEAM_NEEDS_DISCOVERY,
            EXIT_CONFLICT if mismatch else EXIT_NEEDS_INPUT,
            root,
            diagnostics=source_diagnostics,
            next_steps=["Restore or attach the exact declared source evidence, then rerun map."],
        )
    token, exit_code, semantic_diagnostics = _semantic_recipe_checks(recipe)
    if exit_code:
        return Result(
            "map",
            token,
            exit_code,
            root,
            diagnostics=semantic_diagnostics,
            next_steps=["Add the named evidence, owner, or accepted decision; then rerun map."],
        )
    path_state_diagnostics = _write_path_state_diagnostics(root, recipe)
    if path_state_diagnostics:
        return Result(
            "map",
            SEAM_AMBIGUOUS,
            EXIT_CONFLICT,
            root,
            diagnostics=path_state_diagnostics,
            next_steps=[
                "Correct touches_paths/creates_paths against the target checkout, then rerun map."
            ],
        )
    writer = TransactionWriter(dry_run=dry_run)
    with workspace_lock(root, dry_run=dry_run):
        generated_files: dict[Path, str] = {}
        intent_text = render_intent(recipe["intent"])
        intent_path = root / "seamwise" / "intent.md"
        writer.text(intent_path, intent_text)
        generated_files[intent_path] = intent_text
        system_map_text = render_system_map(recipe["system_map"], recipe)
        system_map_path = root / "seamwise" / "system-map.md"
        writer.text(
            system_map_path,
            system_map_text,
        )
        generated_files[system_map_path] = system_map_text
        evidence_text = "".join(canonical_json(item) + "\n" for item in recipe["evidence"])
        evidence_path = root / "seamwise" / "evidence.jsonl"
        writer.text(evidence_path, evidence_text)
        generated_files[evidence_path] = evidence_text
        decision_index: list[dict[str, Any]] = []
        for decision in recipe.get("decisions", []):
            decision_path = root / "seamwise" / "decisions" / f"{decision['id']}.md"
            decision_content = render_decision(decision)
            writer.text(
                decision_path,
                decision_content,
            )
            generated_files[decision_path] = decision_content
            decision_index.append(
                {
                    "id": decision["id"],
                    "path": str(decision_path.relative_to(root)),
                    "status": decision["status"],
                    "sha256": sha256_bytes(decision_content.encode("utf-8")),
                }
            )
        seam_index: list[dict[str, Any]] = []
        for seam in recipe["seams"]:
            path = root / "seamwise" / "seams" / f"{seam['id']}.md"
            content = render_seam(seam)
            writer.text(path, content)
            generated_files[path] = content
            seam_index.append(
                {
                    "id": seam["id"],
                    "path": str(path.relative_to(root)),
                    "owner": seam["owner"],
                    "evidence": seam["evidence"],
                    "swimlane_id": seam["swimlane"]["id"],
                    "sha256": sha256_bytes(content.encode("utf-8")),
                }
            )
        seam_map = {
            "schema_version": 1,
            "status": SEAM_READY,
            "intent_id": recipe["intent"]["id"],
            "source_recipe": {"name": source.name, "sha256": recipe_sha},
            "intent_sha256": sha256_bytes(intent_text.encode("utf-8")),
            "system_map_sha256": sha256_bytes(system_map_text.encode("utf-8")),
            "evidence_sha256": sha256_bytes(evidence_text.encode("utf-8")),
            "decisions": decision_index,
            "seams": seam_index,
        }
        schema_errors = validate_contract("seam-map", seam_map)
        if schema_errors:
            return Result(
                "map",
                SEAM_ERROR,
                EXIT_INVALID,
                root,
                diagnostics=[_diag("projection_schema", item) for item in schema_errors],
            )
        seam_map_path = root / "seamwise" / "seam-map.yaml"
        if seam_map_path.is_file():
            try:
                prior = load_yaml(seam_map_path)
            except (OSError, ValueError, yaml.YAMLError):
                prior = None
            if isinstance(prior, dict) and prior.get("status") != "empty":
                verified_prior, prior_diagnostics = verify_seam_map(root)
                changed = verified_prior != seam_map or any(
                    not path.is_file() or path.read_text(encoding="utf-8") != content
                    for path, content in generated_files.items()
                )
                if verified_prior is None or changed:
                    return Result(
                        "map",
                        SEAM_AMBIGUOUS,
                        EXIT_CONFLICT,
                        root,
                        diagnostics=prior_diagnostics
                        or [
                            _diag(
                                "seam_projection_replacement_required",
                                "Mapping would replace or orphan prior canonical projections. "
                                "Archive the prior seam-map artifacts explicitly first.",
                            )
                        ],
                    )
        writer.yaml(seam_map_path, seam_map)
        _event(
            writer,
            root,
            "map",
            token,
            source={"name": source.name, "sha256": recipe_sha},
        )
        try:
            writer.commit()
        except UnsafeWriteTargetError as error:
            return Result(
                "map",
                SEAM_AMBIGUOUS,
                EXIT_CONFLICT,
                root,
                diagnostics=[_diag("unsafe_write_target", str(error))],
            )
    return Result(
        "map",
        token,
        exit_code,
        root,
        artifacts=writer.touched,
        next_steps=["seamwise plan"],
        data={"seams": len(recipe["seams"]), "dry_run": dry_run},
    )


def _verify_seam_sources(root: Path, seam_map: dict[str, Any]) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    intent_path = root / "seamwise" / "intent.md"
    if not intent_path.is_file() or sha256_file(intent_path) != seam_map["intent_sha256"]:
        diagnostics.append(
            _diag("intent_hash_mismatch", "Intent changed after seam mapping.", intent_path)
        )
    for name, key in (
        ("system-map.md", "system_map_sha256"),
        ("evidence.jsonl", "evidence_sha256"),
    ):
        path = root / "seamwise" / name
        if not path.is_file() or sha256_file(path) != seam_map.get(key):
            diagnostics.append(
                _diag(
                    f"{key.removesuffix('_sha256')}_hash_mismatch",
                    f"{name} changed after seam mapping.",
                    path,
                )
            )
    indexed_decisions: set[Path] = set()
    for record in seam_map.get("decisions", []):
        raw_path = record.get("path")
        if not isinstance(raw_path, str):
            diagnostics.append(_diag("decision_path_invalid", "Decision path is invalid."))
            continue
        decision_path = _owned_artifact_path(root, raw_path, "seamwise/decisions")
        if decision_path is None or decision_path.name != f"{record.get('id')}.md":
            diagnostics.append(
                _diag("decision_path_invalid", f"Decision {record.get('id')} path is invalid.")
            )
            continue
        indexed_decisions.add(decision_path)
        if not decision_path.is_file() or sha256_file(decision_path) != record.get("sha256"):
            diagnostics.append(
                _diag(
                    "decision_hash_mismatch",
                    f"Decision {record.get('id')} changed.",
                    decision_path,
                )
            )
    actual_decisions = set((root / "seamwise" / "decisions").glob("*.md"))
    if actual_decisions != indexed_decisions:
        diagnostics.append(
            _diag(
                "decision_inventory_mismatch",
                "Decision inventory differs from the seam-map index.",
                missing=sorted(str(path) for path in indexed_decisions - actual_decisions),
                extra=sorted(str(path) for path in actual_decisions - indexed_decisions),
            )
        )
    indexed_seams: set[Path] = set()
    for record in seam_map["seams"]:
        raw_path = record.get("path")
        if not isinstance(raw_path, str):
            diagnostics.append(_diag("seam_path_invalid", "Mapped seam path is invalid."))
            continue
        seam_path = _owned_artifact_path(root, raw_path, "seamwise/seams")
        if seam_path is None or seam_path.name != f"{record.get('id')}.md":
            diagnostics.append(
                _diag(
                    "seam_path_invalid",
                    f"Mapped seam {record.get('id')} escapes its owned location.",
                )
            )
            continue
        indexed_seams.add(seam_path)
        if not seam_path.is_file():
            diagnostics.append(
                _diag("seam_missing", f"Mapped seam {record['id']} is missing.", seam_path)
            )
        elif sha256_file(seam_path) != record["sha256"]:
            diagnostics.append(
                _diag("seam_hash_mismatch", f"Mapped seam {record['id']} changed.", seam_path)
            )
    actual_seams = set((root / "seamwise" / "seams").glob("*.md"))
    if actual_seams != indexed_seams:
        diagnostics.append(
            _diag(
                "seam_inventory_mismatch",
                "Seam inventory differs from the seam-map index.",
                missing=sorted(str(path) for path in indexed_seams - actual_seams),
                extra=sorted(str(path) for path in actual_seams - indexed_seams),
            )
        )
    return diagnostics


def _owned_artifact_path(root: Path, value: str, prefix: str) -> Path | None:
    canonical = _canonical_project_path(value)
    if canonical is None or not (canonical == prefix or canonical.startswith(f"{prefix}/")):
        return None
    candidate = (root / canonical).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def verify_seam_map(root: Path) -> tuple[dict[str, Any] | None, list[Diagnostic]]:
    path = root / "seamwise" / "seam-map.yaml"
    if not path.is_file():
        return None, [_diag("seam_map_missing", "Run the seam-map transformation first.", path)]
    try:
        value = load_yaml(path)
    except (OSError, ValueError, yaml.YAMLError) as error:
        return None, [_diag("seam_map_invalid", str(error), path)]
    if not isinstance(value, dict):
        return None, [_diag("seam_map_invalid", "Seam map must be a mapping.", path)]
    diagnostics = [
        _diag("seam_map_schema", message, path) for message in validate_contract("seam-map", value)
    ]
    if value.get("status") != SEAM_READY:
        diagnostics.append(_diag("seam_map_not_ready", "Seam map is not ready.", path))
    if not diagnostics:
        diagnostics.extend(_verify_seam_sources(root, value))
    return (None, diagnostics) if diagnostics else (value, [])
