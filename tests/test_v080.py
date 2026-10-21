"""0.8.0: AI 레디 자가진단(ai-ready)."""

import json
from pathlib import Path

from ontocraft_check import __version__
from ontocraft_check import ai_ready
from ontocraft_check.cli import main

FIX = Path(__file__).parent / "fixtures" / "ai_ready"
COMPLETE = str(FIX / "complete")
SPARSE = str(FIX / "sparse")


def by_id(res):
    return {i["id"]: i for i in res["items"]}


def test_version():
    assert __version__ == "0.8.0"


def test_complete_bundle_passes_all_required():
    res = ai_ready.check(COMPLETE)
    st = {k: v["status"] for k, v in by_id(res).items()}
    assert all(v == "ok" for v in st.values()), st
    assert res["summary"]["required_auto_total"] == 10
    assert res["summary"]["required_auto_ok"] == 10
    assert len(res["manual"]) >= 5


def test_sparse_bundle_fails_many():
    res = ai_ready.check(SPARSE)
    it = by_id(res)
    for rid in ("AIR03", "AIR04", "AIR05", "AIR06", "AIR07", "AIR08", "AIR09", "AIR10"):
        assert it[rid]["status"] == "fail", rid
    assert it["AIR01"]["status"] == "ok" and it["AIR02"]["status"] == "ok"
    assert "dct:title" in it["AIR05"]["detail"]["missing"]
    assert it["AIR10"]["detail"]["id_duplicates"][0]["duplicates"] == 1
    assert res["summary"]["required_auto_ok"] == 2
    assert it["AIR06"]["detail"]["over_20pct"][0]["column"] == "memo"


def test_full_iri_keys_accepted(tmp_path):
    d = {"@context": {}, "@type": "http://www.w3.org/ns/dcat#Dataset",
         "http://purl.org/dc/terms/title": "t", "dcterms:description": "d"}
    (tmp_path / "x.jsonld").write_text(json.dumps(d), encoding="utf-8")
    res = ai_ready.check(str(tmp_path))
    it = by_id(res)
    assert it["AIR04"]["status"] == "ok"
    miss = it["AIR05"]["detail"]["missing"]
    assert "dct:title" not in miss and "dct:description" not in miss and "dct:license" in miss


def test_na_without_tables(tmp_path):
    (tmp_path / "a.xml").write_text("<a/>", encoding="utf-8")
    it = by_id(ai_ready.check(str(tmp_path)))
    assert it["AIR01"]["status"] == "ok"
    assert it["AIR06"]["status"] == "na" and it["AIR10"]["status"] == "na"


def test_render_formats_carry_disclaimer():
    res = ai_ready.check(SPARSE)
    md = ai_ready.render(res, "md")
    assert "공식 진단이 아닙니다" in md and "AIR05" in md and "사람 확인 필요" in md
    assert "공식 진단이 아닙니다" in ai_ready.render(res, "html")
    assert json.loads(ai_ready.render(res, "json"))["feature"] == "ai-ready"


def test_cli_dispatch_and_exit_codes(capsys):
    assert main(["ai-ready", COMPLETE]) == 0
    assert "AI 레디 자가진단" in capsys.readouterr().out
    assert main(["ai-ready", SPARSE, "--format", "json"]) == 1
    assert json.loads(capsys.readouterr().out)["summary"]["required_auto_ok"] == 2
    assert main(["ai-ready", str(FIX / "nope")]) == 2


def test_cli_ai_ready_file_wins(tmp_path, monkeypatch, capsys):
    (tmp_path / "ai-ready").write_text("not an ontology", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert main(["ai-ready"]) == 2  # 온톨로지로 읽으려다 실패(입력 오류)


def test_mcp_tool_registered():
    import pytest
    pytest.importorskip("mcp")
    import asyncio
    from ontocraft_check.mcp_server import build_server
    res = asyncio.run(build_server().call_tool("check_ai_ready", {"path": COMPLETE}))
    assert not res.is_error
    assert json.loads(res.content[0].text)["summary"]["required_auto_ok"] == 10


def _air06(tmp_path, readme, schema=None):
    (tmp_path / "d.csv").write_text("id,memo,refs\n1,,x\n2,,y\n3,a,z\n", encoding="utf-8")
    (tmp_path / "README.md").write_text(readme, encoding="utf-8")
    if schema is not None:
        (tmp_path / "schema.json").write_text(json.dumps(schema), encoding="utf-8")
    return by_id(ai_ready.check(str(tmp_path)))["AIR06"]


def test_air06_reason_in_readme_excuses_column(tmp_path):
    r = _air06(tmp_path, "# 자료\n\n## 결측\n\nmemo 가 비면 아직 안 쓴 것입니다.\n")
    assert r["status"] == "ok"
    assert [x["column"] for x in r["detail"]["over_20pct_with_reason"]] == ["memo"]


def test_air06_optional_in_schema_excuses_column(tmp_path):
    r = _air06(tmp_path, "# 자료\n\n## 결측\n\n빈 문자열이 결측입니다.\n",
               {"$schema": "https://json-schema.org/draft/2020-12/schema", "required": ["id", "refs"]})
    assert r["status"] == "ok"
    assert r["detail"]["over_20pct_with_reason"][0]["reason"].startswith("JSON Schema")


def test_air06_no_reason_and_required_fails(tmp_path):
    r = _air06(tmp_path, "# 자료\n\n## 결측\n\nreferences 는 비어도 됩니다.\n",
               {"$schema": "https://json-schema.org/draft/2020-12/schema", "required": ["id", "memo"]})
    assert r["status"] == "fail"
    assert [x["column"] for x in r["detail"]["over_20pct"]] == ["memo"]
    r2 = _air06(tmp_path, "# 자료\n\n## 결측\n\nreferences 는 비어도 됩니다.\n")  # 스키마 없음: refs 는 낱말 경계로 안 맞음
    assert r2["status"] == "fail"


def test_air06_schema_applies_only_to_matching_table(tmp_path):
    """스키마가 정의하지 않은 표(열이 properties 밖)에는 required 로 선택 열을 가리지 않습니다."""
    import json

    from ontocraft_check.ai_ready import check

    (tmp_path / "schema.json").write_text(json.dumps({
        "$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object",
        "required": ["id"], "properties": {"id": {"type": "string"}, "note": {"type": "string"}}}), encoding="utf-8")
    (tmp_path / "records.jsonl").write_text("\n".join(json.dumps({"id": str(i), "note": ""}) for i in range(10)) + "\n", encoding="utf-8")
    (tmp_path / "table.csv").write_text("a,b\n1,\n2,\n3,\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# x\n\n## Missing values\n\n빈 칸은 기록 없음입니다.\n", encoding="utf-8")
    res = check(str(tmp_path))
    air06 = next(i for i in res["items"] if i["id"] == "AIR06")
    detail = json.dumps(air06, ensure_ascii=False)
    assert air06["status"] == "fail"
    assert "table.csv" in detail
