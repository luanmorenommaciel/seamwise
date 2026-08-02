from __future__ import annotations

from pathlib import Path

import pytest

import seamwise.doctor as doctor_module
from seamwise.doctor import doctor


def test_doctor_reports_native_windows_as_unsupported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(doctor_module, "_supported_platform", lambda: False)
    result = doctor(tmp_path)
    assert result.token == "DOCTOR=BLOCKED"
    assert any(item.code == "unsupported_platform" for item in result.diagnostics)
    platform_check = next(
        item for item in result.data["checks"] if item["name"] == "supported_platform"
    )
    assert platform_check["ok"] is False
