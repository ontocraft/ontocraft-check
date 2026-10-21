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
