"""Delivery-plan construction, human review acceptance, and verification."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import yaml

from seamwise.constants import (
    EXIT_CONFLICT,
    EXIT_INVALID,
    EXIT_NEEDS_INPUT,
    EXIT_OK,
    PLAN_ERROR,
    PLAN_NEEDS_DECISION,
    PLAN_NEEDS_OWNER,
    PLAN_NEEDS_REVIEW,
    PLAN_OPEN_OBJECTIONS,
    PLAN_READY,
)
from seamwise.contracts import validate_contract
from seamwise.engine.seams import _owned_artifact_path, verify_seam_map
from seamwise.engine.support import _diag, _event
from seamwise.io import (
    TransactionWriter,
    UnsafeWriteTargetError,
    canonical_json,
    load_frontmatter,
    load_json,
    load_yaml,
    sha256_bytes,
    sha256_file,
    workspace_lock,
)
from seamwise.render import (
    render_leg,
    render_steel_thread,
    render_swimlane,
)
from seamwise.result import Diagnostic, Result
from seamwise.safety import workspace_boundary_diagnostics


def build_plan(root: Path, *, dry_run: bool = False) -> Result:
    boundary_diagnostics = workspace_boundary_diagnostics(root)
    if boundary_diagnostics:
        return Result("plan", PLAN_ERROR, EXIT_CONFLICT, root, diagnostics=boundary_diagnostics)
    seam_map_path = root / "seamwise" / "seam-map.yaml"
    seam_map, seam_diagnostics = verify_seam_map(root)
    if seam_map is None:
        exit_code = (
            EXIT_NEEDS_INPUT
            if any(
                item.code in {"seam_map_missing", "seam_map_not_ready"} for item in seam_diagnostics
            )
            else EXIT_CONFLICT
        )
        return Result(
            "plan",
            PLAN_NEEDS_DECISION,
            exit_code,
            root,
            diagnostics=seam_diagnostics,
            next_steps=['seamwise map --source "/path/to/recipe.yaml"'],
        )
    system_path = root / "seamwise" / "system-map.md"
    try:
        system, _ = load_frontmatter(system_path)
    except (OSError, ValueError) as error:
        return Result(
            "plan",
            PLAN_NEEDS_DECISION,
            EXIT_INVALID,
            root,
            diagnostics=[_diag("system_map_invalid", str(error), system_path)],
        )
    unknowns = system.get("unknowns", [])
    if unknowns:
        return Result(
            "plan",
            PLAN_NEEDS_DECISION,
            EXIT_NEEDS_INPUT,
            root,
            diagnostics=[
                _diag(
                    "architecture_unknown_open",
                    "The authored system map contains unresolved architecture unknowns.",
                    system_path,
                    unknowns=unknowns,
                )
            ],
            next_steps=[
                "Resolve every material unknown in sourced evidence, then map the revised recipe in a clean workspace."
            ],
        )
    objections = system.get("objections", [])
    for objection in objections:
        if objection.get("status") in {"ACCEPTED", "FIXED"} and not (
            str(objection.get("owner", "")).strip() and str(objection.get("rationale", "")).strip()
        ):
            return Result(
                "plan",
                PLAN_NEEDS_OWNER,
                EXIT_NEEDS_INPUT,
                root,
                diagnostics=[
                    _diag(
                        "accepted_objection_incomplete",
                        f"Objection {objection.get('id')} needs owner and rationale.",
                    )
                ],
            )
    token = (
        PLAN_OPEN_OBJECTIONS
        if any(item.get("status") == "OPEN" for item in objections)
        else PLAN_NEEDS_REVIEW
    )
    exit_code = EXIT_NEEDS_INPUT
    writer = TransactionWriter(dry_run=dry_run)
    lane_index: list[dict[str, Any]] = []
    leg_index: list[dict[str, Any]] = []
    with workspace_lock(root, dry_run=dry_run):
        locked_map, locked_diagnostics = verify_seam_map(root)
        if locked_map is None or locked_map != seam_map:
            return Result(
                "plan",
                PLAN_NEEDS_DECISION,
                EXIT_CONFLICT,
                root,
                diagnostics=locked_diagnostics
                or [_diag("seam_map_changed", "Seam map changed while planning.")],
            )
        generated_files: dict[Path, str] = {}
        for seam_record in seam_map["seams"]:
            seam_path = root / seam_record["path"]
            seam, _ = load_frontmatter(seam_path)
            lane = seam["swimlane"]
            lane_path = root / "seamwise" / "swimlanes" / f"{lane['id']}.md"
            lane_content = render_swimlane(lane, seam["id"], seam_record["sha256"])
            writer.text(lane_path, lane_content)
            generated_files[lane_path] = lane_content
            lane_index.append(
                {
                    "id": lane["id"],
                    "seam_id": seam["id"],
                    "owner": lane["owner"],
                    "path": str(lane_path.relative_to(root)),
                    "sha256": sha256_bytes(lane_content.encode("utf-8")),
                }
            )
            for leg in lane["legs"]:
                leg_path = root / "seamwise" / "legs" / f"{leg['id']}.md"
                leg_content = render_leg(leg, seam["id"], lane["id"], seam_record["sha256"])
                writer.text(leg_path, leg_content)
                generated_files[leg_path] = leg_content
                leg_index.append(
                    {
                        "id": leg["id"],
                        "seam_id": seam["id"],
                        "swimlane_id": lane["id"],
                        "path": str(leg_path.relative_to(root)),
                        "sha256": sha256_bytes(leg_content.encode("utf-8")),
                    }
                )
        plan = {
            "schema_version": 1,
            "status": token,
            "seam_map_sha256": sha256_file(seam_map_path),
            "swimlanes": lane_index,
            "legs": leg_index,
            "steel_thread": system.get("proposed_steel_thread", []),
            "objections": objections,
            "contentions": system.get("contentions", []),
        }
        steel_thread_path = root / "seamwise" / "steel-thread.md"
        steel_thread_content = render_steel_thread(plan["steel_thread"], leg_index)
        plan["steel_thread_path"] = str(steel_thread_path.relative_to(root))
        plan["steel_thread_sha256"] = sha256_bytes(steel_thread_content.encode("utf-8"))
        generated_files[steel_thread_path] = steel_thread_content
        existing_path = root / "seamwise" / "delivery-plan.yaml"
        receipt_path = root / "seamwise" / "reviews" / "delivery-plan-review.json"
        if existing_path.is_file() and receipt_path.is_file():
            existing = load_yaml(existing_path)
            receipt = load_json(receipt_path)
            comparable_existing = {**existing, "status": token}
            comparable_existing.pop("review_authority_sha256", None)
            if (
                comparable_existing == plan
                and existing.get("status") == PLAN_READY
                and receipt.get("plan_sha256") == sha256_file(existing_path)
            ):
                verified_existing, review_diagnostics = verify_plan(root)
                if verified_existing is None:
                    return Result(
                        "plan",
                        PLAN_NEEDS_REVIEW,
                        EXIT_CONFLICT,
                        root,
                        diagnostics=review_diagnostics,
                    )
                return Result(
                    "plan",
                    PLAN_READY,
                    EXIT_OK,
                    root,
                    artifacts=[existing_path, receipt_path],
                    next_steps=["seamwise compile"],
                    data={"preserved_review": True},
                )
        if existing_path.is_file():
            verified_prior, prior_diagnostics = verify_plan(root, require_review=False)
            comparable_prior = (
                {**verified_prior, "status": token} if verified_prior is not None else None
            )
            if comparable_prior is not None:
                comparable_prior.pop("review_authority_sha256", None)
            changed = comparable_prior != plan or any(
                not path.is_file() or path.read_text(encoding="utf-8") != content
                for path, content in generated_files.items()
            )
            if verified_prior is None or changed:
                return Result(
                    "plan",
                    PLAN_NEEDS_DECISION,
                    EXIT_CONFLICT,
                    root,
                    diagnostics=prior_diagnostics
                    or [
                        _diag(
                            "plan_projection_replacement_required",
                            "Planning would replace or orphan prior lanes or legs. Archive the "
                            "prior delivery-plan projections explicitly first.",
                        )
                    ],
                )
        schema_errors = validate_contract("delivery-plan", plan)
        if schema_errors:
            return Result(
                "plan",
                PLAN_NEEDS_DECISION,
                EXIT_INVALID,
                root,
                diagnostics=[_diag("projection_schema", item) for item in schema_errors],
            )
        writer.yaml(existing_path, plan)
        writer.text(steel_thread_path, steel_thread_content)
        _event(writer, root, "plan", token, lanes=len(lane_index), legs=len(leg_index))
        try:
            writer.commit()
        except UnsafeWriteTargetError as error:
            return Result(
                "plan",
                PLAN_NEEDS_DECISION,
                EXIT_CONFLICT,
                root,
                diagnostics=[_diag("unsafe_write_target", str(error))],
            )
    next_steps = (
        ["Resolve every OPEN objection, then rerun: seamwise plan"]
        if token == PLAN_OPEN_OBJECTIONS
        else ["seamwise review --accept --reviewer <name> --reason <reason>"]
    )
    return Result(
        "plan",
        token,
        exit_code,
        root,
        artifacts=writer.touched,
        next_steps=next_steps,
        data={"swimlanes": len(lane_index), "legs": len(leg_index), "dry_run": dry_run},
    )


def accept_plan(
    root: Path,
    *,
    reviewer: str,
    reason: str,
    fixture: bool = False,
    dry_run: bool = False,
) -> Result:
    boundary_diagnostics = workspace_boundary_diagnostics(root)
    if boundary_diagnostics:
        return Result("review", PLAN_ERROR, EXIT_CONFLICT, root, diagnostics=boundary_diagnostics)
    plan_path = root / "seamwise" / "delivery-plan.yaml"
    plan, plan_diagnostics = verify_plan(root, require_review=False)
    if plan is None:
        return Result(
            "review",
            PLAN_NEEDS_REVIEW,
            EXIT_NEEDS_INPUT
            if any(item.code == "plan_missing" for item in plan_diagnostics)
            else EXIT_CONFLICT,
            root,
            diagnostics=plan_diagnostics,
            next_steps=["seamwise plan"],
        )
    reviewer = reviewer.strip()
    reason = reason.strip()
    if not reviewer or not reason:
        return Result(
            "review",
            PLAN_NEEDS_REVIEW,
            EXIT_INVALID,
            root,
            diagnostics=[_diag("review_fields_blank", "Reviewer and reason must be nonblank.")],
        )
    if plan.get("status") == PLAN_OPEN_OBJECTIONS or any(
        item.get("status") == "OPEN" for item in plan.get("objections", [])
    ):
        return Result(
            "review",
            PLAN_OPEN_OBJECTIONS,
            EXIT_NEEDS_INPUT,
            root,
            diagnostics=[
                _diag("open_objections", "Review cannot accept a plan with OPEN objections.")
            ],
        )
    if plan.get("seam_map_sha256") != sha256_file(root / "seamwise" / "seam-map.yaml"):
        return Result(
            "review",
            PLAN_NEEDS_REVIEW,
            EXIT_CONFLICT,
            root,
            diagnostics=[
                _diag("seam_map_hash_mismatch", "Seam map changed after plan generation.")
            ],
            next_steps=["seamwise plan"],
        )
    draft_sha = sha256_file(plan_path)
    reviewed_at = dt.datetime.now(dt.UTC).isoformat()
    authority_record = {
        "schema_version": 1,
        "disposition": "accepted",
        "reviewer": reviewer,
        "reason": reason,
        "reviewed_at": reviewed_at,
        "draft_sha256": draft_sha,
        "fixture": fixture,
    }
    plan["status"] = PLAN_READY
    plan["review_authority_sha256"] = sha256_bytes(canonical_json(authority_record).encode("utf-8"))
    ready_content = yaml.safe_dump(plan, allow_unicode=True, sort_keys=False, width=100)
    ready_sha = sha256_bytes(ready_content.encode("utf-8"))
    receipt = {
        **authority_record,
        "plan_sha256": ready_sha,
    }
    errors = validate_contract("delivery-plan-review", receipt)
    if errors:
        return Result(
            "review",
            PLAN_NEEDS_REVIEW,
            EXIT_INVALID,
            root,
            diagnostics=[_diag("review_schema", item) for item in errors],
        )
    writer = TransactionWriter(dry_run=dry_run)
    with workspace_lock(root, dry_run=dry_run):
        locked_plan, locked_diagnostics = verify_plan(root, require_review=False)
        if locked_plan is None or sha256_file(plan_path) != draft_sha:
            return Result(
                "review",
                PLAN_NEEDS_REVIEW,
                EXIT_CONFLICT,
                root,
                diagnostics=locked_diagnostics
                or [_diag("plan_changed", "Delivery plan changed during review.")],
            )
        writer.text(plan_path, ready_content)
        receipt_path = root / "seamwise" / "reviews" / "delivery-plan-review.json"
        writer.json(receipt_path, receipt)
        _event(writer, root, "review", PLAN_READY, reviewer=reviewer, fixture=fixture)
        try:
            writer.commit()
        except UnsafeWriteTargetError as error:
            return Result(
                "review",
                PLAN_NEEDS_REVIEW,
                EXIT_CONFLICT,
                root,
                diagnostics=[_diag("unsafe_write_target", str(error))],
            )
    return Result(
        "review",
        PLAN_READY,
        EXIT_OK,
        root,
        artifacts=writer.touched,
        next_steps=["seamwise compile"],
        data={"fixture": fixture, "dry_run": dry_run},
    )


def verify_plan(
    root: Path, *, require_review: bool = True
) -> tuple[dict[str, Any] | None, list[Diagnostic]]:
    plan_path = root / "seamwise" / "delivery-plan.yaml"
    receipt_path = root / "seamwise" / "reviews" / "delivery-plan-review.json"
    if not plan_path.is_file():
        return None, [_diag("plan_missing", "A delivery plan is required.", plan_path)]
    try:
        plan = load_yaml(plan_path)
    except (OSError, ValueError, yaml.YAMLError) as error:
        return None, [_diag("plan_invalid", str(error), plan_path)]
    if not isinstance(plan, dict):
        return None, [_diag("plan_invalid", "Delivery plan must be a mapping.", plan_path)]
    diagnostics: list[Diagnostic] = []
    diagnostics.extend(
        _diag("plan_schema", message, plan_path)
        for message in validate_contract("delivery-plan", plan)
    )
    seam_map, seam_diagnostics = verify_seam_map(root)
    diagnostics.extend(seam_diagnostics)
    seam_map_path = root / "seamwise" / "seam-map.yaml"
    if seam_map is not None and plan.get("seam_map_sha256") != sha256_file(seam_map_path):
        diagnostics.append(_diag("plan_source_changed", "Seam map changed after planning."))

    expected_lanes = (
        {item["swimlane_id"]: item["id"] for item in seam_map.get("seams", [])} if seam_map else {}
    )
    actual_lanes: dict[str, str] = {}
    actual_legs: set[str] = set()
    indexed_paths: dict[str, set[Path]] = {"swimlanes": set(), "legs": set()}
    for kind, prefix in (("swimlanes", "seamwise/swimlanes"), ("legs", "seamwise/legs")):
        items = plan.get(kind, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict) or not all(
                isinstance(item.get(key), str) for key in ("id", "path", "sha256")
            ):
                diagnostics.append(
                    _diag("plan_artifact_invalid", f"Plan {kind} entry is incomplete.", plan_path)
                )
                continue
            path = _owned_artifact_path(root, item["path"], prefix)
            if path is None or path.name != f"{item['id']}.md":
                diagnostics.append(
                    _diag(
                        "plan_artifact_path_invalid",
                        f"Plan artifact {item['id']} escapes its owned location.",
                    )
                )
                continue
            indexed_paths[kind].add(path)
            if not path.is_file() or sha256_file(path) != item["sha256"]:
                diagnostics.append(
                    _diag("plan_artifact_changed", f"Plan artifact {item['id']} changed.", path)
                )
                continue
            try:
                frontmatter, _ = load_frontmatter(path)
            except (OSError, ValueError, yaml.YAMLError) as error:
                diagnostics.append(_diag("plan_artifact_invalid", str(error), path))
                continue
            if frontmatter.get("id") != item["id"]:
                diagnostics.append(
                    _diag("plan_artifact_id_mismatch", f"Plan artifact ID mismatch: {path}.")
                )
            if kind == "swimlanes":
                seam_id = item.get("seam_id")
                if not isinstance(seam_id, str) or frontmatter.get("seam_id") != seam_id:
                    diagnostics.append(
                        _diag("swimlane_seam_mismatch", f"Swimlane {item['id']} seam mismatch.")
                    )
                if item["id"] in actual_lanes:
                    diagnostics.append(_diag("duplicate_swimlane", f"Duplicate {item['id']}."))
                actual_lanes[item["id"]] = str(seam_id)
            else:
                actual_legs.add(item["id"])
                if frontmatter.get("seam_id") != item.get("seam_id") or frontmatter.get(
                    "swimlane_id"
                ) != item.get("swimlane_id"):
                    diagnostics.append(
                        _diag("leg_lineage_mismatch", f"Capability leg {item['id']} mismatch.")
                    )
    for kind in ("swimlanes", "legs"):
        actual_paths = set((root / "seamwise" / kind).glob("*.md"))
        if actual_paths != indexed_paths[kind]:
            diagnostics.append(
                _diag(
                    f"{kind}_inventory_mismatch",
                    f"{kind.title()} inventory differs from the delivery-plan index.",
                    missing=sorted(str(path) for path in indexed_paths[kind] - actual_paths),
                    extra=sorted(str(path) for path in actual_paths - indexed_paths[kind]),
                )
            )
    if seam_map is not None and actual_lanes != expected_lanes:
        diagnostics.append(
            _diag(
                "swimlane_ownership_mismatch",
                "Every accepted seam must have exactly one matching owning swimlane.",
            )
        )
    steel_thread = plan.get("steel_thread", [])
    if isinstance(steel_thread, list) and not set(steel_thread) <= actual_legs:
        diagnostics.append(_diag("steel_thread_mismatch", "Steel thread names unknown legs."))
    steel_path_value = plan.get("steel_thread_path")
    if isinstance(steel_path_value, str):
        steel_path = _owned_artifact_path(root, steel_path_value, "seamwise")
        if (
            steel_path is None
            or steel_path.name != "steel-thread.md"
            or not steel_path.is_file()
            or sha256_file(steel_path) != plan.get("steel_thread_sha256")
        ):
            diagnostics.append(
                _diag("steel_thread_changed", "Derived steel-thread artifact changed.")
            )

    if require_review and plan.get("status") != PLAN_READY:
        diagnostics.append(_diag("plan_not_ready", "Delivery plan is not marked ready.", plan_path))
    if require_review:
        if not receipt_path.is_file():
            diagnostics.append(
                _diag(
                    "review_missing", "An accepted delivery-plan review is required.", receipt_path
                )
            )
        else:
            try:
                receipt = load_json(receipt_path)
            except (OSError, ValueError) as error:
                diagnostics.append(_diag("review_invalid", str(error), receipt_path))
            else:
                diagnostics.extend(
                    _diag("review_schema", message, receipt_path)
                    for message in validate_contract("delivery-plan-review", receipt)
                )
                if isinstance(receipt, dict) and receipt.get("plan_sha256") != sha256_file(
                    plan_path
                ):
                    diagnostics.append(
                        _diag(
                            "review_hash_mismatch", "Delivery plan changed after review.", plan_path
                        )
                    )
                if isinstance(receipt, dict):
                    authority_record = {
                        key: value for key, value in receipt.items() if key != "plan_sha256"
                    }
                    authority_sha = sha256_bytes(canonical_json(authority_record).encode("utf-8"))
                    if plan.get("review_authority_sha256") != authority_sha:
                        diagnostics.append(
                            _diag(
                                "review_authority_hash_mismatch",
                                "Review identity, rationale, timestamp, draft binding, or fixture class changed after acceptance.",
                                receipt_path,
                            )
                        )
    return (None, diagnostics) if diagnostics else (plan, [])
