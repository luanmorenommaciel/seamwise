"""The four deterministic, fail-closed Seamwise transformations."""

from __future__ import annotations

import datetime as dt
import itertools
from collections import defaultdict, deque
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlsplit

import yaml

from seamwise.constants import (
    EXIT_CONFLICT,
    EXIT_INVALID,
    EXIT_NEEDS_INPUT,
    EXIT_OK,
    GRAPH_BLOCKED,
    GRAPH_COLLISION,
    GRAPH_CYCLE,
    GRAPH_READY,
    GRAPH_UNPROVABLE,
    PLAN_ERROR,
    PLAN_NEEDS_DECISION,
    PLAN_NEEDS_OWNER,
    PLAN_NEEDS_REVIEW,
    PLAN_OPEN_OBJECTIONS,
    PLAN_READY,
    SEAM_AMBIGUOUS,
    SEAM_ERROR,
    SEAM_NEEDS_DECISION,
    SEAM_NEEDS_DISCOVERY,
    SEAM_NEEDS_OWNER,
    SEAM_READY,
)
from seamwise.contracts import validate_contract
from seamwise.io import (
    TransactionWriter,
    UnsafeWriteTargetError,
    canonical_json,
    load_frontmatter,
    load_json,
    load_yaml,
    sha256_bytes,
    sha256_file,
    strict_yaml_load,
    workspace_lock,
)
from seamwise.render import (
    render_decision,
    render_intent,
    render_leg,
    render_seam,
    render_steel_thread,
    render_swimlane,
    render_system_map,
    render_task_spec,
)
from seamwise.result import Diagnostic, Result
from seamwise.safety import workspace_boundary_diagnostics


def _diag(code: str, message: str, artifact: Path | None = None, **detail: Any) -> Diagnostic:
    return Diagnostic(code, message, str(artifact) if artifact else None, detail)


def _load_recipe(
    source: Path,
) -> tuple[dict[str, Any] | None, list[Diagnostic], str | None]:
    try:
        raw = source.read_bytes()
        value = strict_yaml_load(raw.decode("utf-8"))
    except (OSError, yaml.YAMLError) as error:
        return None, [_diag("recipe_unreadable", str(error), source)], None
    except UnicodeDecodeError as error:
        return None, [_diag("recipe_unreadable", str(error), source)], None
    if not isinstance(value, dict):
        return None, [_diag("recipe_not_mapping", "Recipe root must be a mapping.", source)], None
    return value, [], sha256_bytes(raw)


def _duplicates(values: list[str]) -> list[str]:
    counts: dict[str, int] = defaultdict(int)
    for value in values:
        counts[value] += 1
    return sorted(key for key, count in counts.items() if count > 1)


def _canonical_project_path(value: str) -> str | None:
    """Return one portable project-relative spelling, or reject the path."""

    if "\\" in value or value.startswith("/") or any(char in value for char in "*?[]{}"):
        return None
    raw_parts = value.split("/")
    if any(part in ("", ".", "..") for part in raw_parts):
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value:
        return None
    return path.as_posix()


def _paths_overlap(left: str, right: str) -> bool:
    return left == right or left.startswith(f"{right}/") or right.startswith(f"{left}/")


def _authored_text_diagnostics(recipe: dict[str, Any]) -> list[Diagnostic]:
    """Reject semantic prose that is present in shape only.

    JSON Schema's ``minLength`` treats whitespace as content. Seamwise does not:
    human-readable intent, architecture, proof, and Task-Spec fields must carry
    at least one non-whitespace character. Identifiers, paths, tool tokens, and
    source locators retain their own syntax-specific validation.
    """

    values: list[tuple[str, str]] = []

    def add(field: str, value: str) -> None:
        values.append((field, value))

    intent = recipe["intent"]
    add("intent.title", intent["title"])
    add("intent.summary", intent["summary"])
    for index, value in enumerate(intent["success"]):
        add(f"intent.success[{index}]", value)
    for index, value in enumerate(intent["out_of_scope"]):
        add(f"intent.out_of_scope[{index}]", value)

    system_map = recipe["system_map"]
    for collection in ("components", "external_dependencies", "unknowns"):
        for index, value in enumerate(system_map[collection]):
            add(f"system_map.{collection}[{index}]", value)

    for index, evidence in enumerate(recipe["evidence"]):
        add(f"evidence[{index}].summary", evidence["summary"])
    for index, decision in enumerate(recipe.get("decisions", [])):
        add(f"decisions[{index}].owner", decision["owner"])
        add(f"decisions[{index}].rationale", decision["rationale"])
    for index, objection in enumerate(recipe.get("objections", [])):
        add(f"objections[{index}].summary", objection["summary"])
        for field in ("owner", "rationale"):
            if field in objection:
                add(f"objections[{index}].{field}", objection[field])
    for index, contention in enumerate(recipe.get("contentions", [])):
        add(f"contentions[{index}].resolution", contention["resolution"])

    for seam_index, seam in enumerate(recipe["seams"]):
        seam_field = f"seams[{seam_index}]"
        for field in (
            "name",
            "description",
            "responsibility",
            "owner",
            "independent_proof",
        ):
            add(f"{seam_field}.{field}", seam[field])
        for collection in ("consumes", "produces"):
            for index, value in enumerate(seam[collection]):
                add(f"{seam_field}.{collection}[{index}]", value)
        for index, alternative in enumerate(seam["rejected_alternatives"]):
            add(
                f"{seam_field}.rejected_alternatives[{index}].alternative",
                alternative["alternative"],
            )
            add(f"{seam_field}.rejected_alternatives[{index}].reason", alternative["reason"])

        lane = seam["swimlane"]
        lane_field = f"{seam_field}.swimlane"
        add(f"{lane_field}.name", lane["name"])
        add(f"{lane_field}.owner", lane["owner"])
        for leg_index, leg in enumerate(lane["legs"]):
            leg_field = f"{lane_field}.legs[{leg_index}]"
            add(f"{leg_field}.observable_state", leg["observable_state"])
            add(f"{leg_field}.proof", leg["proof"])
            for collection in ("requires", "produces"):
                for index, value in enumerate(leg[collection]):
                    add(f"{leg_field}.{collection}[{index}]", value)

            for task_index, task in enumerate(leg["tasks"]):
                task_field = f"{leg_field}.tasks[{task_index}]"
                for field in ("title", "goal", "done_condition"):
                    add(f"{task_field}.{field}", task[field])
                for field in ("rollback", "observability"):
                    if field in task:
                        add(f"{task_field}.{field}", task[field])
                for index, behavior in enumerate(task["behavior"]):
                    for field in ("given", "when", "then"):
                        add(f"{task_field}.behavior[{index}].{field}", behavior[field])
                for index, evaluation in enumerate(task["evals"]):
                    add(f"{task_field}.evals[{index}].description", evaluation["description"])
                    add(f"{task_field}.evals[{index}].bash", evaluation["bash"])
                for index, anti_pattern in enumerate(task["anti_patterns"]):
                    for field in ("action", "reason", "instead"):
                        add(f"{task_field}.anti_patterns[{index}].{field}", anti_pattern[field])

    return [
        _diag(
            "blank_authored_text",
            f"Authored semantic field {field} must contain non-whitespace text.",
            field=field,
        )
        for field, value in values
        if not value.strip()
    ]


def _semantic_recipe_checks(recipe: dict[str, Any]) -> tuple[str, int, list[Diagnostic]]:
    evidence_ids = [item["id"] for item in recipe["evidence"]]
    if duplicates := _duplicates(evidence_ids):
        return (
            SEAM_AMBIGUOUS,
            EXIT_INVALID,
            [_diag("duplicate_evidence", "Evidence IDs must be unique.", ids=duplicates)],
        )
    all_ids: list[str] = [recipe["intent"]["id"], *evidence_ids]
    all_ids.extend(item["id"] for item in recipe.get("decisions", []))
    task_ids: list[str] = []
    leg_ids: list[str] = []
    lane_ids: list[str] = []
    seam_ids: list[str] = []
    diagnostics = _authored_text_diagnostics(recipe)
    for evidence in recipe["evidence"]:
        if not evidence["summary"].strip():
            diagnostics.append(
                _diag(
                    "missing_evidence",
                    f"Evidence {evidence['id']} needs a non-blank summary.",
                )
            )
    for decision in recipe.get("decisions", []):
        if not decision["owner"].strip() or not decision["rationale"].strip():
            diagnostics.append(
                _diag(
                    "unaccepted_decision",
                    f"Decision {decision['id']} needs a non-blank owner and rationale.",
                )
            )
    for objection in recipe.get("objections", []):
        if not objection["summary"].strip():
            diagnostics.append(
                _diag(
                    "missing_evidence",
                    f"Objection {objection['id']} needs a non-blank summary.",
                )
            )
        if objection["status"] in {"FIXED", "ACCEPTED"} and not (
            str(objection.get("owner", "")).strip() and str(objection.get("rationale", "")).strip()
        ):
            diagnostics.append(
                _diag(
                    "unaccepted_decision",
                    f"{objection['status']} objection {objection['id']} needs repair ownership and rationale.",
                )
            )
    accepted_decisions = {
        item["id"] for item in recipe.get("decisions", []) if item["status"] == "accepted"
    }
    for seam in recipe["seams"]:
        seam_ids.append(seam["id"])
        all_ids.append(seam["id"])
        missing_evidence = sorted(set(seam["evidence"]) - set(evidence_ids))
        if missing_evidence:
            diagnostics.append(
                _diag(
                    "missing_evidence",
                    f"Seam {seam['id']} cites evidence that is not present.",
                    ids=missing_evidence,
                )
            )
        if not seam["owner"].strip() or not seam["swimlane"]["owner"].strip():
            diagnostics.append(_diag("missing_owner", f"Seam {seam['id']} has no owner."))
        elif seam["owner"] != seam["swimlane"]["owner"]:
            diagnostics.append(
                _diag(
                    "missing_owner",
                    f"Seam {seam['id']} and its one owning swimlane must name the same owner.",
                )
            )
        if not seam["responsibility"].strip() or not seam["independent_proof"].strip():
            diagnostics.append(
                _diag(
                    "missing_evidence",
                    f"Seam {seam['id']} needs non-blank responsibility and independent proof.",
                )
            )
        unresolved = sorted(set(seam.get("decision_ids", [])) - accepted_decisions)
        if unresolved:
            diagnostics.append(
                _diag(
                    "unaccepted_decision",
                    f"Seam {seam['id']} depends on decisions that are not accepted.",
                    ids=unresolved,
                )
            )
        lane = seam["swimlane"]
        lane_ids.append(lane["id"])
        all_ids.append(lane["id"])
        for leg in lane["legs"]:
            leg_ids.append(leg["id"])
            all_ids.append(leg["id"])
            if not leg["observable_state"].strip() or not leg["proof"].strip():
                diagnostics.append(
                    _diag(
                        "missing_evidence",
                        f"Capability leg {leg['id']} needs a non-blank observable state and proof.",
                    )
                )
            for task in leg["tasks"]:
                task_ids.append(task["id"])
                unsafe_scalars = [
                    value
                    for value in [task["execution_backend"], *task["required_tools"]]
                    if not isinstance(yaml.safe_load(value), str)
                ]
                if unsafe_scalars:
                    diagnostics.append(
                        _diag(
                            "yaml_scalar_ambiguous",
                            f"Task {task['id']} uses backend/tool names that YAML would not preserve as strings.",
                            values=unsafe_scalars,
                        )
                    )
                ordered_behavior_ids = [item["id"] for item in task["behavior"]]
                ordered_eval_ids = [item["id"] for item in task["evals"]]
                if ordered_behavior_ids != ["B-1", "B-2"] or ordered_eval_ids != [
                    "eval_1",
                    "eval_2",
                    "eval_3",
                ]:
                    diagnostics.append(
                        _diag(
                            "unsupported_traceability_shape",
                            f"Task {task['id']} must author B-1/B-2 and eval_1/eval_2/eval_3 in canonical order.",
                            behavior_ids=ordered_behavior_ids,
                            eval_ids=ordered_eval_ids,
                        )
                    )
                for value in [
                    *task["touches_paths"],
                    *task["creates_paths"],
                    *task["do_not_touch"],
                ]:
                    if _canonical_project_path(value) is None:
                        diagnostics.append(
                            _diag(
                                "noncanonical_project_path",
                                f"Task {task['id']} uses a noncanonical project path: {value!r}.",
                            )
                        )
                writes = [
                    value
                    for raw in [*task["touches_paths"], *task["creates_paths"]]
                    if (value := _canonical_project_path(raw)) is not None
                ]
                forbidden = [
                    value
                    for raw in task["do_not_touch"]
                    if (value := _canonical_project_path(raw)) is not None
                ]
                contradictions = sorted(
                    {
                        f"{write} <> {protected}"
                        for write in writes
                        for protected in forbidden
                        if _paths_overlap(write, protected)
                    }
                )
                if contradictions:
                    diagnostics.append(
                        _diag(
                            "forbidden_write_overlap",
                            f"Task {task['id']} writes inside its do-not-touch boundary.",
                            paths=contradictions,
                        )
                    )
                if not (task["touches_paths"] or task["creates_paths"]):
                    diagnostics.append(
                        _diag("empty_write_surface", f"Task {task['id']} owns no write surface.")
                    )
                behavior_ids = set(ordered_behavior_ids)
                verified = {item for evaluation in task["evals"] for item in evaluation["verifies"]}
                if behavior_ids != verified:
                    diagnostics.append(
                        _diag(
                            "behavior_eval_mismatch",
                            f"Task {task['id']} behavior/eval traceability is incomplete.",
                            behaviors=sorted(behavior_ids),
                            verified=sorted(verified),
                        )
                    )
    duplicate_groups = {
        "seams": _duplicates(seam_ids),
        "swimlanes": _duplicates(lane_ids),
        "legs": _duplicates(leg_ids),
        "tasks": _duplicates(task_ids),
        "all": _duplicates(all_ids),
    }
    for kind, values in duplicate_groups.items():
        if values:
            diagnostics.append(_diag("duplicate_id", f"Duplicate {kind} IDs.", ids=values))
    task_id_set = set(task_ids)
    for seam in recipe["seams"]:
        for leg in seam["swimlane"]["legs"]:
            for task in leg["tasks"]:
                unknown = sorted(set(task["depends_on"]) - task_id_set)
                if unknown:
                    diagnostics.append(
                        _diag(
                            "unknown_dependency",
                            f"Task {task['id']} depends on unknown tasks.",
                            ids=unknown,
                        )
                    )
    unknown_thread = sorted(set(recipe["steel_thread"]) - set(leg_ids))
    if unknown_thread:
        diagnostics.append(
            _diag(
                "unknown_steel_thread_leg", "Steel thread names unknown legs.", ids=unknown_thread
            )
        )
    if diagnostics:
        codes = {item.code for item in diagnostics}
        if "missing_evidence" in codes:
            return SEAM_NEEDS_DISCOVERY, EXIT_NEEDS_INPUT, diagnostics
        if "missing_owner" in codes:
            return SEAM_NEEDS_OWNER, EXIT_NEEDS_INPUT, diagnostics
        if "unaccepted_decision" in codes:
            return SEAM_NEEDS_DECISION, EXIT_NEEDS_INPUT, diagnostics
        return SEAM_AMBIGUOUS, EXIT_INVALID, diagnostics
    return SEAM_READY, EXIT_OK, []


def _write_path_state_diagnostics(root: Path, recipe: dict[str, Any]) -> list[Diagnostic]:
    """Prove each modified path exists now or is created by an ancestor task."""

    tasks = [
        task
        for seam in recipe["seams"]
        for leg in seam["swimlane"]["legs"]
        for task in leg["tasks"]
    ]
    dependencies = {task["id"]: set(task["depends_on"]) for task in tasks}
    creators: dict[str, set[str]] = defaultdict(set)
    spellings: dict[str, set[str]] = defaultdict(set)
    for task in tasks:
        for path in [*task["touches_paths"], *task["creates_paths"]]:
            spellings[path.casefold()].add(path)
        for path in task["creates_paths"]:
            creators[path].add(task["id"])

    def ancestors(task_id: str) -> set[str]:
        pending = list(dependencies[task_id])
        found: set[str] = set()
        while pending:
            dependency = pending.pop()
            if dependency in found or dependency not in dependencies:
                continue
            found.add(dependency)
            pending.extend(dependencies[dependency] - found)
        return found

    diagnostics: list[Diagnostic] = []
    for variants in spellings.values():
        if len(variants) > 1:
            diagnostics.append(
                _diag(
                    "case_portability_collision",
                    "Write paths differ only by case and are unsafe on case-insensitive filesystems.",
                    paths=sorted(variants),
                )
            )

    def symlink_component(value: str, *, include_leaf: bool) -> Path | None:
        parts = PurePosixPath(value).parts if include_leaf else PurePosixPath(value).parts[:-1]
        current = root
        for part in parts:
            current /= part
            if current.is_symlink():
                return current
            if not current.exists():
                break
        return None

    for task in tasks:
        task_ancestors = ancestors(task["id"])
        overlap = sorted(set(task["touches_paths"]) & set(task["creates_paths"]))
        if overlap:
            diagnostics.append(
                _diag(
                    "write_path_role_conflict",
                    f"Task {task['id']} declares the same path as both existing and new.",
                    paths=overlap,
                )
            )
        for value in task["touches_paths"]:
            canonical = _canonical_project_path(value)
            if canonical is None:
                continue
            unsafe_component = symlink_component(canonical, include_leaf=True)
            if unsafe_component is not None:
                diagnostics.append(
                    _diag(
                        "write_path_symlink_escape",
                        f"Task {task['id']} touch path crosses a symlink component: {canonical}",
                        unsafe_component,
                    )
                )
                continue
            if (root / canonical).exists() or creators.get(canonical, set()) & task_ancestors:
                continue
            diagnostics.append(
                _diag(
                    "touch_path_unprovable",
                    f"Task {task['id']} modifies a path that neither exists nor is created by an ancestor task: {canonical}",
                )
            )
        for value in task["creates_paths"]:
            canonical = _canonical_project_path(value)
            if canonical is None:
                continue
            unsafe_component = symlink_component(canonical, include_leaf=True)
            if unsafe_component is not None:
                diagnostics.append(
                    _diag(
                        "write_path_symlink_escape",
                        f"Task {task['id']} create path crosses a symlink component: {canonical}",
                        unsafe_component,
                    )
                )
            elif (root / canonical).exists():
                diagnostics.append(
                    _diag(
                        "create_path_already_exists",
                        f"Task {task['id']} declares an already-existing path as new: {canonical}",
                    )
                )
    return diagnostics


def _verify_local_recipe_sources(
    root: Path, source: Path, recipe: dict[str, Any]
) -> list[Diagnostic]:
    """Verify local bytes and reject remote claims without immutable snapshots."""

    from seamwise.taskpack import assets_root

    source_records = [recipe["intent"]["source"]]
    source_records.extend(item["source"] for item in recipe["evidence"])
    diagnostics: list[Diagnostic] = []
    checked: set[tuple[str, str]] = set()
    for record in source_records:
        uri = record["uri"]
        expected_sha = record["sha256"]
        key = (uri, expected_sha)
        if key in checked:
            continue
        checked.add(key)
        parsed = urlsplit(uri)
        candidates: list[Path]
        if parsed.scheme == "file" and parsed.netloc not in ("", "localhost"):
            diagnostics.append(
                _diag(
                    "remote_source_unverified",
                    f"Remote file evidence has no locally verifiable snapshot: {uri}",
                    source,
                )
            )
            continue
        if parsed.scheme == "file":
            candidates = [Path(unquote(parsed.path)).expanduser()]
        elif parsed.scheme:
            diagnostics.append(
                _diag(
                    "remote_source_unverified",
                    f"Remote evidence cannot become verified compilation input without a local immutable snapshot: {uri}",
                    source,
                    scheme=parsed.scheme,
                )
            )
            continue
        else:
            relative = Path(unquote(parsed.path))
            candidates = [source.parent / relative, root / relative, assets_root() / relative]
        resolved = next(
            (candidate.resolve() for candidate in candidates if candidate.is_file()), None
        )
        if resolved is None:
            diagnostics.append(
                _diag(
                    "local_source_unavailable",
                    f"Local evidence source is unavailable: {uri}",
                    source,
                )
            )
        elif sha256_file(resolved) != expected_sha:
            diagnostics.append(
                _diag(
                    "local_source_hash_mismatch",
                    f"Local evidence source does not match its declared SHA-256: {uri}",
                    resolved,
                )
            )
    return diagnostics


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


def _event(
    writer: TransactionWriter, root: Path, stage: str, token: str, **attributes: Any
) -> None:
    path = root / "telemetry" / "events.jsonl"
    existing: list[dict[str, Any]] = []
    if path.is_file():
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    import json

                    value = json.loads(line)
                    if isinstance(value, dict):
                        existing.append(value)
        except (OSError, ValueError):
            existing = []
            attributes["prior_telemetry_invalid"] = True
    existing.append(
        {
            "schema_version": 1,
            "time": dt.datetime.now(dt.UTC).isoformat(),
            "event": f"seamwise.{stage}",
            "token": token,
            "attributes": attributes,
            "authorization": False,
        }
    )
    writer.jsonl(path, existing)


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


def _task_records(root: Path, plan: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in plan["legs"]:
        leg, _ = load_frontmatter(root / item["path"])
        for task in leg["tasks"]:
            records.append(
                {
                    "task": task,
                    "seam_id": leg["seam_id"],
                    "swimlane_id": leg["swimlane_id"],
                    "leg_id": leg["id"],
                    "leg_requires": leg["requires"],
                    "leg_produces": leg["produces"],
                    "leg_path": item["path"],
                    "source_sha256": item["sha256"],
                }
            )
    return records


def _transitive_path(start: str, target: str, adjacency: dict[str, set[str]]) -> bool:
    pending = [start]
    seen: set[str] = set()
    while pending:
        node = pending.pop()
        if node == target:
            return True
        if node in seen:
            continue
        seen.add(node)
        pending.extend(adjacency[node] - seen)
    return False


def _topological(nodes: list[str], edges: list[dict[str, str]]) -> tuple[list[str], list[str]]:
    adjacency: dict[str, set[str]] = {node: set() for node in nodes}
    indegree = {node: 0 for node in nodes}
    for edge in edges:
        source, target = edge["from"], edge["to"]
        if target not in adjacency[source]:
            adjacency[source].add(target)
            indegree[target] += 1
    queue = deque(sorted(node for node, count in indegree.items() if count == 0))
    order: list[str] = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for target in sorted(adjacency[node]):
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    cycle = sorted(set(nodes) - set(order))
    return order, cycle


def _critical_path(nodes: list[str], edges: list[dict[str, str]], order: list[str]) -> list[str]:
    incoming: dict[str, list[str]] = {node: [] for node in nodes}
    for edge in edges:
        incoming[edge["to"]].append(edge["from"])
    paths: dict[str, list[str]] = {}
    for node in order:
        candidates = [paths[parent] for parent in sorted(incoming[node])]
        best = max(candidates, key=lambda path: (len(path), path), default=[])
        paths[node] = [*best, node]
    return max(paths.values(), key=lambda path: (len(path), path), default=[])


def _graph_projection(
    records: list[dict[str, Any]], plan: dict[str, Any], plan_sha: str
) -> tuple[dict[str, Any], list[Diagnostic]]:
    tasks = [record["task"] for record in records]
    ids = [task["id"] for task in tasks]
    diagnostics: list[Diagnostic] = []
    if duplicates := _duplicates(ids):
        diagnostics.append(_diag("duplicate_task", "Task IDs must be unique.", ids=duplicates))
        return _empty_graph(GRAPH_UNPROVABLE, plan_sha), diagnostics
    id_set = set(ids)
    for task in tasks:
        unknown = sorted(set(task["depends_on"]) - id_set)
        if unknown:
            diagnostics.append(
                _diag(
                    "unknown_dependency",
                    f"Task {task['id']} has unknown dependencies.",
                    ids=unknown,
                )
            )
        raw_paths = [*task["touches_paths"], *task["creates_paths"]]
        canonical_paths = [_canonical_project_path(value) for value in raw_paths]
        if any(value is None for value in canonical_paths):
            diagnostics.append(
                _diag(
                    "noncanonical_project_path",
                    f"Task {task['id']} contains a noncanonical project path.",
                    paths=raw_paths,
                )
            )
        forbidden_paths = [
            value
            for raw in task["do_not_touch"]
            if (value := _canonical_project_path(raw)) is not None
        ]
        contradictions = sorted(
            {
                f"{write} <> {protected}"
                for write in canonical_paths
                if write is not None
                for protected in forbidden_paths
                if _paths_overlap(write, protected)
            }
        )
        if contradictions:
            diagnostics.append(
                _diag(
                    "forbidden_write_overlap",
                    f"Task {task['id']} writes inside its do-not-touch boundary.",
                    paths=contradictions,
                )
            )
        write_count = len({value for value in canonical_paths if value is not None})
        limit = {"XS": 1, "S": 2, "M": 3, "L": 5}[task["effort"]]
        if write_count > limit:
            diagnostics.append(
                _diag(
                    "write_surface_too_large",
                    f"Task {task['id']} owns {write_count} paths; {task['effort']} allows {limit}.",
                )
            )
        if not task["done_condition"].strip() or len(task["evals"]) < 3:
            diagnostics.append(
                _diag("unprovable_task", f"Task {task['id']} has no coherent proof.")
            )
    if diagnostics:
        return _empty_graph(GRAPH_UNPROVABLE, plan_sha), diagnostics
    edges = [
        {"from": dependency, "to": task["id"], "kind": "depends_on"}
        for task in tasks
        for dependency in task["depends_on"]
    ]
    for contention in plan.get("contentions", []):
        before, after = contention["order"]
        if set(contention["between"]) != {before, after} or not {before, after} <= id_set:
            diagnostics.append(
                _diag("invalid_contention", "Contention order must name the same two known tasks.")
            )
        else:
            edges.append({"from": before, "to": after, "kind": "contention_order"})
    order, cycle = _topological(ids, edges)
    if cycle:
        graph = _empty_graph(GRAPH_CYCLE, plan_sha)
        graph["edges"] = edges
        return graph, [_diag("cycle", "Task dependencies contain a cycle.", ids=cycle)]
    adjacency: dict[str, set[str]] = {task_id: set() for task_id in ids}
    for edge in edges:
        adjacency[edge["from"]].add(edge["to"])
    dependency_adjacency: dict[str, set[str]] = {task_id: set() for task_id in ids}
    for task in tasks:
        for dependency in task["depends_on"]:
            dependency_adjacency[dependency].add(task["id"])

    records_by_leg: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        records_by_leg[record["leg_id"]].append(record)
    thread = plan.get("steel_thread", [])
    thread_position = {leg_id: index for index, leg_id in enumerate(thread)}
    artifact_producers: dict[str, set[str]] = defaultdict(set)
    for leg_id, leg_records in records_by_leg.items():
        if leg_records:
            for artifact in leg_records[0]["leg_produces"]:
                artifact_producers[artifact].add(leg_id)
    task_leg = {record["task"]["id"]: record["leg_id"] for record in records}
    causal_diagnostics: list[Diagnostic] = []
    for consumer_leg in sorted(records_by_leg):
        consumer_records = records_by_leg[consumer_leg]
        if not consumer_records:
            causal_diagnostics.append(
                _diag(
                    "capability_leg_has_no_tasks",
                    f"Capability leg {consumer_leg} has no runnable Task-Spec leaves.",
                )
            )
            continue
        consumer_tasks = [record["task"] for record in consumer_records]
        roots = [
            task
            for task in consumer_tasks
            if not any(
                task_leg.get(dependency) == consumer_leg for dependency in task["depends_on"]
            )
        ]
        for artifact in consumer_records[0]["leg_requires"]:
            producers = sorted(artifact_producers.get(artifact, set()))
            if not producers:
                causal_diagnostics.append(
                    _diag(
                        "capability_requirement_unproduced",
                        f"Required state {artifact!r} for {consumer_leg} has no producing capability leg.",
                    )
                )
                continue
            if len(producers) != 1 or producers[0] == consumer_leg:
                causal_diagnostics.append(
                    _diag(
                        "capability_producer_ambiguous",
                        f"Required state {artifact!r} for {consumer_leg} must have exactly one distinct producer.",
                        producers=producers,
                    )
                )
                continue
            producer_leg = producers[0]
            if (
                producer_leg in thread_position
                and consumer_leg in thread_position
                and thread_position[producer_leg] >= thread_position[consumer_leg]
            ):
                causal_diagnostics.append(
                    _diag(
                        "steel_thread_order_mismatch",
                        f"Steel-thread producer {producer_leg} must precede consumer {consumer_leg} for {artifact!r}.",
                    )
                )
                continue
            producer_tasks = [record["task"]["id"] for record in records_by_leg[producer_leg]]
            unlinked = [
                task["id"]
                for task in roots
                if not any(
                    _transitive_path(producer, task["id"], dependency_adjacency)
                    for producer in producer_tasks
                )
            ]
            if unlinked:
                causal_diagnostics.append(
                    _diag(
                        "missing_capability_dependency",
                        f"Root tasks in {consumer_leg} consume {artifact!r} without a transitive dependency on {producer_leg}.",
                        tasks=unlinked,
                    )
                )
    if causal_diagnostics:
        graph = _empty_graph(GRAPH_UNPROVABLE, plan_sha)
        graph["edges"] = edges
        graph["contentions"] = plan.get("contentions", [])
        return graph, causal_diagnostics

    declared_contentions = {frozenset(item["between"]) for item in plan.get("contentions", [])}
    for left, right in itertools.combinations(tasks, 2):
        left_paths = {
            value
            for raw in [*left["touches_paths"], *left["creates_paths"]]
            if (value := _canonical_project_path(raw)) is not None
        }
        right_paths = {
            value
            for raw in [*right["touches_paths"], *right["creates_paths"]]
            if (value := _canonical_project_path(raw)) is not None
        }
        overlap = sorted(
            {
                shorter if len(shorter) <= len(longer) else longer
                for shorter in left_paths
                for longer in right_paths
                if shorter == longer
                or shorter.startswith(f"{longer}/")
                or longer.startswith(f"{shorter}/")
            }
        )
        if not overlap:
            continue
        ordered = _transitive_path(left["id"], right["id"], adjacency) or _transitive_path(
            right["id"], left["id"], adjacency
        )
        if not ordered and frozenset({left["id"], right["id"]}) not in declared_contentions:
            diagnostics.append(
                _diag(
                    "path_collision",
                    f"Sibling tasks {left['id']} and {right['id']} overlap without ordering.",
                    paths=overlap,
                )
            )
    if diagnostics:
        graph = _empty_graph(GRAPH_COLLISION, plan_sha)
        graph["edges"] = edges
        graph["contentions"] = plan.get("contentions", [])
        return graph, diagnostics
    nodes = [
        {
            "id": record["task"]["id"],
            "title": record["task"]["title"],
            "seam_id": record["seam_id"],
            "swimlane_id": record["swimlane_id"],
            "leg_id": record["leg_id"],
            "effort": record["task"]["effort"],
            "profile": record["task"]["profile"],
            "done_condition": record["task"]["done_condition"],
            "touches_paths": record["task"]["touches_paths"],
            "creates_paths": record["task"]["creates_paths"],
        }
        for record in sorted(records, key=lambda item: item["task"]["id"])
    ]
    graph = {
        "schema_version": 1,
        "status": GRAPH_READY,
        "plan_sha256": plan_sha,
        "nodes": nodes,
        "edges": sorted(edges, key=lambda item: (item["from"], item["to"], item["kind"])),
        "contentions": plan.get("contentions", []),
        "critical_path": _critical_path(ids, edges, order),
    }
    graph["critical_path_mermaid_sha256"] = sha256_bytes(
        render_graph_mermaid(graph).encode("utf-8")
    )
    return graph, []


def _empty_graph(status: str, plan_sha: str) -> dict[str, Any]:
    graph: dict[str, Any] = {
        "schema_version": 1,
        "status": status,
        "plan_sha256": plan_sha,
        "nodes": [],
        "edges": [],
        "contentions": [],
        "critical_path": [],
    }
    graph["critical_path_mermaid_sha256"] = sha256_bytes(
        render_graph_mermaid(graph).encode("utf-8")
    )
    return graph


def render_graph_mermaid(graph: dict[str, Any]) -> str:
    def label(value: Any) -> str:
        normalized = " ".join(str(value).split())
        return "".join(
            character if character.isalnum() or character in " -_.,:/" else f"&#{ord(character)};"
            for character in normalized
        )

    lines = ["flowchart LR"]
    for node in graph["nodes"]:
        title = label(node["title"])
        node_id = str(node["id"])
        lines.append(f'  {node_id.replace("-", "_")}["{label(node_id)}: {title}"]')
    for edge in graph["edges"]:
        source = edge["from"].replace("-", "_")
        target = edge["to"].replace("-", "_")
        connector = "-.->" if edge["kind"] == "contention_order" else "-->"
        lines.append(f"  {source} {connector} {target}")
    return "\n".join(lines) + "\n"


def _existing_spec_diagnostics(root: Path, generated: dict[str, str]) -> list[Diagnostic]:
    existing = sorted((root / "tasks").glob("T-*.md"))
    if not existing:
        return []
    lineage_path = root / "tasks" / "task-lineage.json"
    if not lineage_path.is_file():
        return [
            _diag(
                "unowned_task_specs",
                "Existing Task-Specs have no Seamwise lineage receipt; refusing to replace them.",
            )
        ]
    try:
        lineage = load_json(lineage_path)
    except (OSError, ValueError) as error:
        return [_diag("task_lineage_invalid", str(error), lineage_path)]
    errors = validate_contract("task-lineage", lineage)
    if errors:
        return [_diag("task_lineage_schema", item, lineage_path) for item in errors]
    diagnostics: list[Diagnostic] = []
    expected_existing = set(lineage["tasks"])
    actual_existing = {path.stem for path in existing}
    if actual_existing != expected_existing:
        diagnostics.append(
            _diag(
                "stale_or_unowned_task_specs",
                "Existing Task-Spec files do not exactly match the prior lineage receipt.",
                missing=sorted(expected_existing - actual_existing),
                extra=sorted(actual_existing - expected_existing),
            )
        )
    for task_id, entry in lineage["tasks"].items():
        expected_relative = f"tasks/{task_id}.md"
        path = _owned_artifact_path(root, entry["spec"], "tasks")
        if path is None or entry["spec"] != expected_relative:
            diagnostics.append(
                _diag("task_spec_path_invalid", f"Prior lineage path is invalid for {task_id}.")
            )
        elif not path.is_file() or sha256_file(path) != entry["spec_sha256"]:
            diagnostics.append(
                _diag(
                    "task_spec_changed",
                    f"Existing Task-Spec {task_id} changed after compilation.",
                    path,
                )
            )
    if diagnostics:
        return diagnostics
    if set(generated) != actual_existing or any(
        (root / "tasks" / f"{task_id}.md").read_text(encoding="utf-8") != content
        for task_id, content in generated.items()
    ):
        return [
            _diag(
                "task_spec_replacement_required",
                "Compilation would replace or orphan prior drafts. Archive the receipt-owned "
                "tasks/T-*.md files and task-lineage.json explicitly, then rerun compile.",
            )
        ]
    return []


def derive_task_bundle(
    root: Path, plan: dict[str, Any], task_pack_root: Path
) -> tuple[
    list[dict[str, Any]],
    dict[str, Any],
    dict[str, Any] | None,
    dict[str, str],
    list[Diagnostic],
]:
    """Deterministically rebuild every compiler-owned task projection."""

    plan_sha = sha256_file(root / "seamwise" / "delivery-plan.yaml")
    records = _task_records(root, plan)
    graph, diagnostics = _graph_projection(records, plan, plan_sha)
    if diagnostics or graph["status"] != GRAPH_READY:
        return records, graph, None, {}, diagnostics
    try:
        intent, _ = load_frontmatter(root / "seamwise" / "intent.md")
        lineage: dict[str, Any] = {
            "schema_version": 1,
            "intent": intent["id"],
            "plan_sha256": plan_sha,
            "fixture": bool(
                load_json(root / "seamwise" / "reviews" / "delivery-plan-review.json").get(
                    "fixture"
                )
            ),
            "tasks": {},
        }
        generated_specs: dict[str, str] = {}
        for record in records:
            task = record["task"]
            content = render_task_spec(
                task=task,
                intent_id=intent["id"],
                seam_id=record["seam_id"],
                lane_id=record["swimlane_id"],
                leg_id=record["leg_id"],
                source_sha256=record["source_sha256"],
                task_pack_root=task_pack_root,
            )
            generated_specs[task["id"]] = content
            lineage["tasks"][task["id"]] = {
                "seam": record["seam_id"],
                "swimlane": record["swimlane_id"],
                "leg": record["leg_id"],
                "spec": f"tasks/{task['id']}.md",
                "spec_sha256": sha256_bytes(content.encode("utf-8")),
                "source_sha256": record["source_sha256"],
            }
    except (OSError, ValueError, KeyError, yaml.YAMLError) as error:
        return records, graph, None, {}, [_diag("task_spec_render_failed", str(error))]
    projection_errors = [
        *validate_contract("task-graph", graph),
        *validate_contract("task-lineage", lineage),
    ]
    if projection_errors:
        return (
            records,
            graph,
            None,
            {},
            [_diag("projection_schema", item) for item in projection_errors],
        )
    return records, graph, lineage, generated_specs, []


def compile_graph(
    root: Path,
    *,
    task_pack_root: Path,
    dry_run: bool = False,
    command: str = "compile",
) -> Result:
    boundary_diagnostics = workspace_boundary_diagnostics(root)
    if boundary_diagnostics:
        return Result(command, GRAPH_BLOCKED, EXIT_CONFLICT, root, diagnostics=boundary_diagnostics)
    plan, diagnostics = verify_plan(root)
    if plan is None:
        missing_authority = {"plan_missing", "plan_not_ready", "review_missing"}
        return Result(
            command,
            GRAPH_BLOCKED,
            EXIT_NEEDS_INPUT
            if diagnostics and all(item.code in missing_authority for item in diagnostics)
            else EXIT_CONFLICT,
            root,
            diagnostics=diagnostics,
            next_steps=[
                "seamwise plan",
                "seamwise review --accept --reviewer <name> --reason <reason>",
            ],
        )
    plan_path = root / "seamwise" / "delivery-plan.yaml"
    plan_sha = sha256_file(plan_path)
    records, graph, lineage, generated_specs, graph_diagnostics = derive_task_bundle(
        root, plan, task_pack_root
    )
    token = graph["status"]
    exit_code = EXIT_OK if token == GRAPH_READY else EXIT_CONFLICT
    writer = TransactionWriter(dry_run=dry_run)
    graph_path = root / "tasks" / "task-graph.yaml"
    if token == GRAPH_READY:
        if graph_diagnostics or lineage is None:
            return Result(
                command,
                GRAPH_UNPROVABLE,
                EXIT_INVALID,
                root,
                diagnostics=graph_diagnostics,
            )
        existing_diagnostics = _existing_spec_diagnostics(root, generated_specs)
        if existing_diagnostics:
            return Result(
                command,
                GRAPH_BLOCKED,
                EXIT_CONFLICT,
                root,
                diagnostics=existing_diagnostics,
                next_steps=["Archive the named prior drafts explicitly, then rerun compile."],
            )
    with workspace_lock(root, dry_run=dry_run):
        locked_plan, locked_diagnostics = verify_plan(root)
        if locked_plan is None or sha256_file(plan_path) != plan_sha:
            return Result(
                command,
                GRAPH_BLOCKED,
                EXIT_CONFLICT,
                root,
                diagnostics=locked_diagnostics
                or [_diag("plan_changed", "Delivery plan changed during compilation.")],
            )
        locked_spec_diagnostics = _existing_spec_diagnostics(root, generated_specs)
        if locked_spec_diagnostics:
            return Result(
                command,
                GRAPH_BLOCKED,
                EXIT_CONFLICT,
                root,
                diagnostics=locked_spec_diagnostics,
            )
        writer.yaml(graph_path, graph)
        writer.text(root / "tasks" / "critical-path.mmd", render_graph_mermaid(graph))
        if token == GRAPH_READY and lineage is not None:
            for task_id, content in generated_specs.items():
                writer.text(root / "tasks" / f"{task_id}.md", content)
            writer.json(root / "tasks" / "task-lineage.json", lineage)
        _event(writer, root, "compile", token, tasks=len(records))
        try:
            writer.commit()
        except UnsafeWriteTargetError as error:
            return Result(
                command,
                GRAPH_BLOCKED,
                EXIT_CONFLICT,
                root,
                diagnostics=[_diag("unsafe_write_target", str(error))],
            )
    return Result(
        command,
        token,
        exit_code,
        root,
        artifacts=writer.touched,
        diagnostics=graph_diagnostics,
        next_steps=["seamwise tasks validate"]
        if token == GRAPH_READY
        else ["Resolve graph diagnostics, then rerun compile."],
        data={"tasks": len(records), "dry_run": dry_run},
    )


def inspect_lineage(root: Path, task_id: str | None = None) -> Result:
    from seamwise.taskpack import _verify_task_bundle_unlocked

    boundary_diagnostics = workspace_boundary_diagnostics(root)
    if boundary_diagnostics:
        return Result(
            "inspect",
            GRAPH_BLOCKED,
            EXIT_CONFLICT,
            root,
            diagnostics=boundary_diagnostics,
        )
    with workspace_lock(root):
        specs, lineage, diagnostics = _verify_task_bundle_unlocked(root)
        path = root / "tasks" / "task-lineage.json"
        if lineage is None:
            return Result(
                "inspect",
                GRAPH_BLOCKED,
                EXIT_CONFLICT if diagnostics else EXIT_NEEDS_INPUT,
                root,
                diagnostics=diagnostics
                or [_diag("lineage_missing", "Compile a task graph first.", path)],
                next_steps=["seamwise compile"],
            )
        if task_id is not None:
            task = lineage["tasks"].get(task_id)
            if task is None:
                return Result(
                    "inspect",
                    GRAPH_UNPROVABLE,
                    EXIT_INVALID,
                    root,
                    diagnostics=[_diag("unknown_task", f"No lineage for {task_id}.")],
                )
            data = {"task_id": task_id, **task}
        else:
            data = lineage
        return Result(
            "inspect", "LINEAGE=READY", EXIT_OK, root, artifacts=[path, *specs], data=data
        )
