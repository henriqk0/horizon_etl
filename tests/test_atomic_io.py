import json
import math

import pytest

from src.core.logic.atomic_io import atomic_write_json


def test_atomic_write_json_writes_valid_json(tmp_path):
    output_file = tmp_path / "export.json"
    atomic_write_json(str(output_file), {"a": 1, "b": [None, "x"]})
    assert json.loads(output_file.read_text(encoding="utf-8")) == {
        "a": 1,
        "b": [None, "x"],
    }


def test_atomic_write_json_fails_loudly_on_non_finite_floats(tmp_path):
    output_file = tmp_path / "export.json"
    with pytest.raises(ValueError):
        atomic_write_json(str(output_file), {"score": float("nan")})
    with pytest.raises(ValueError):
        atomic_write_json(str(output_file), {"score": float("inf")})
    assert not output_file.exists()


def test_atomic_write_json_accepts_finite_floats(tmp_path):
    output_file = tmp_path / "export.json"
    atomic_write_json(str(output_file), {"score": math.pi})
    assert json.loads(output_file.read_text(encoding="utf-8"))["score"] == math.pi
