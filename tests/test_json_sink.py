import json
import os
from unittest.mock import MagicMock

from pydantic import BaseModel

from src.adapters.sinks.json_sink import JsonSink


class MockModel(BaseModel):
    id: int
    name: str


class MockAlchemyModel:

    def __init__(self, **kwargs):
        self.__table__ = MagicMock()
        self.__table__.columns = []
        for k, v in kwargs.items():
            setattr(self, k, v)
            col = MagicMock()
            col.name = k
            self.__table__.columns.append(col)


def test_json_sink_export_pydantic(tmp_path):
    # Arrange
    sink = JsonSink()
    data = [MockModel(id=1, name="Test 1"), MockModel(id=2, name="Test 2")]
    output_file = tmp_path / "test_output_pydantic.json"

    # Act
    sink.export(data, str(output_file))

    # Assert
    assert os.path.exists(output_file)
    with open(output_file, "r") as f:
        content = json.load(f)
        assert len(content) == 2
        assert content[0]["name"] == "Test 1"


def test_json_sink_export_sqlalchemy(tmp_path):
    # Arrange
    sink = JsonSink()
    data = [
        MockAlchemyModel(id=1, name="SQLAlchemy Test"),
        MockAlchemyModel(id=2, name="Another"),
    ]
    output_file = tmp_path / "test_output_sa.json"

    # Act
    sink.export(data, str(output_file))

    # Assert
    assert os.path.exists(output_file)
    with open(output_file, "r") as f:
        content = json.load(f)
        assert len(content) == 2
        assert content[0]["name"] == "SQLAlchemy Test"
        assert content[1]["id"] == 2


def test_json_sink_creates_directories(tmp_path):
    # Arrange
    sink = JsonSink()
    data = [MockModel(id=1, name="Test")]
    output_file = tmp_path / "subdir" / "test_output.json"

    # Act
    sink.export(data, str(output_file))

    # Assert
    assert os.path.exists(output_file)


def test_json_sink_export_dicts(tmp_path):
    # Arrange
    sink = JsonSink()
    data = [{"id": 1, "name": "Dict 1"}, {"id": 2, "name": "Dict 2"}]
    output_file = tmp_path / "test_output_dicts.json"

    # Act
    sink.export(data, str(output_file))

    # Assert
    assert os.path.exists(output_file)
    with open(output_file, "r") as f:
        content = json.load(f)
        assert len(content) == 2
        assert content[0]["name"] == "Dict 1"


def test_json_sink_normalizes_non_finite_floats(tmp_path):
    # NaN/Infinity from pandas read_excel must never leak into the export as
    # invalid JSON literal tokens.
    sink = JsonSink()
    data = [
        {
            "id": 1,
            "score": float("nan"),
            "vals": [float("inf"), float("-inf"), 2.5, None],
            "nested": {"site": float("nan")},
        }
    ]
    output_file = tmp_path / "test_output_non_finite.json"

    sink.export(data, str(output_file))

    raw = output_file.read_text(encoding="utf-8")
    assert "NaN" not in raw
    assert "Infinity" not in raw
    assert "-Infinity" not in raw

    parsed = json.loads(raw)
    assert parsed[0]["score"] is None
    assert parsed[0]["vals"][0] is None
    assert parsed[0]["vals"][1] is None
    assert parsed[0]["vals"][2] == 2.5
    assert parsed[0]["vals"][3] is None
    assert parsed[0]["nested"]["site"] is None
