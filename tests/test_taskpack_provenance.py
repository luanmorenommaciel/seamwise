from __future__ import annotations

import json

from seamwise.taskpack import assets_root, verify_task_pack


def test_task_pack_matches_pinned_phase_zero_manifest() -> None:
    assert verify_task_pack() == []
    manifest = json.loads(
        (assets_root() / "vendor/task-pack-source.json").read_text(encoding="utf-8")
    )
    assert manifest["source_commit"] == "b585ca792418924182e1c6a87f660a5f8afa07bd"
    assert manifest["source_tree"] == "95dae33bf9c8da852ae50a7b6cfc44176cdaa5c8"
    assert manifest["file_count"] == 125
    assert sum(item["mode"] == "0755" for item in manifest["files"].values()) == 32
