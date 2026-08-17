"""Recipe loading and fail-closed semantic validation."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlsplit

import yaml

from seamwise.constants import (
    EXIT_INVALID,
    EXIT_NEEDS_INPUT,
    EXIT_OK,
    SEAM_AMBIGUOUS,
    SEAM_NEEDS_DECISION,
    SEAM_NEEDS_DISCOVERY,
    SEAM_NEEDS_OWNER,
    SEAM_READY,
)
from seamwise.engine.support import (
    _canonical_project_path,
    _diag,
    _duplicates,
    _paths_overlap,
)
from seamwise.io import (
    sha256_bytes,
    sha256_file,
    strict_yaml_load,
)
from seamwise.result import Diagnostic


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

    from seamwise.assets import assets_root

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
