"""Task-graph projection, topology proof, and Mermaid rendering."""

from __future__ import annotations

import itertools
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from seamwise.constants import (
    GRAPH_COLLISION,
    GRAPH_CYCLE,
    GRAPH_READY,
    GRAPH_UNPROVABLE,
)
from seamwise.engine.support import (
    _canonical_project_path,
    _diag,
    _duplicates,
    _paths_overlap,
)
from seamwise.io import (
    load_frontmatter,
    sha256_bytes,
)
from seamwise.result import Diagnostic


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
