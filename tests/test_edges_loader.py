"""Edge cases for the data loader (loader.R via app.load_table_r)."""
import os

import pytest

import app
from helpers import FIXTURES


def test_loader_missing_file():
    with pytest.raises(RuntimeError, match="File not found"):
        app.load_table_r(os.path.join(FIXTURES, "does_not_exist.csv"))


def test_loader_header_only(tmp_path):
    p = tmp_path / "header_only.csv"
    p.write_text("a,b\n", encoding="utf-8")
    cols, rows = app.load_table_r(str(p))
    assert cols == ["a", "b"] and rows == []


def test_loader_quoted_commas(tmp_path):
    p = tmp_path / "quoted.csv"
    p.write_text('name,age\n"Smith, John",34\n"Doe, Jane",28\n', encoding="utf-8")
    cols, rows = app.load_table_r(str(p))
    assert len(rows) == 2 and rows[0]["name"] == "Smith, John"


def test_loader_utf8_bom(tmp_path):
    p = tmp_path / "bom.csv"
    p.write_text("valeur\n1\n2\n3\n", encoding="utf-8-sig")
    cols, rows = app.load_table_r(str(p))
    assert cols == ["valeur"] and rows[0]["valeur"] == 1
