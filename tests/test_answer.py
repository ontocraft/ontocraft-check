"""AI 답변 근거 검사(answer). 자료 출처: 제조 AI 책 12장 실습, 합성(tests/fixtures/answer/README.md)."""

import asyncio
import json
from pathlib import Path

import pytest

from ontocraft_check import answer as A
from ontocraft_check import tools as T
from ontocraft_check.cli import main

FIX = Path(__file__).parent / "fixtures" / "answer"
GOOD = FIX / "good.json"
BAD = FIX / "bad.json"
LEDGER = FIX / "ledger.csv"
BAD_FAILS = {"C1", "C2", "C3", "C6", "C7", "C8", "C9", "C10"}


def load(p):
    return json.loads(p.read_text(encoding="utf-8"))


def failed(results):
    return {r.id for r in results if not r.ok}


def test_book_good_passes():
    res = A.check_answer(load(GOOD), A.read_ledger(LEDGER))
    assert [r.id for r in res] == [f"C{i}" for i in range(1, 11)]
    assert failed(res) == set()
    assert A.headline(res) == "형식 검사 통과"


def test_book_bad_fails_eight():
    res = A.check_answer(load(BAD), A.read_ledger(LEDGER))
    assert len(failed(res)) == 8
    assert failed(res) == BAD_FAILS
    assert A.headline(res) == "형식 검사 실패 8건"
    msg = {r.id: r.message for r in res}
    assert msg["C3"] == "원장에 없는 ID: WO-2433"
    assert msg["C9"] == "인용한 근거에 없는 숫자: H1: 120"
    assert msg["C8"] == "발견: 원인입니다, 때문임이 분명"


def test_ledger_drives_c3_and_c9():
    led = A.read_ledger(LEDGER)
    # 원장에 WO-2433 을 더하고 그 문장에 120 을 넣으면 나쁜 예의 C3·C9 가 통과합니다.
    led2 = led + [{"id": "WO-2433", "type": "maintenance", "text": "공구 수명 120분 기록"}]
    assert {"C3", "C9"} <= failed(A.check_answer(load(BAD), led))
    assert not {"C3", "C9"} & failed(A.check_answer(load(BAD), led2))
    # 좋은 예도 SIG-057 을 원장에서 빼면 C3 이, 문장 숫자를 다르게 두면 C9 가 실패합니다.
    led3 = [e for e in led if e["id"] != "SIG-057"]
    assert {"C3", "C9"} <= failed(A.check_answer(load(GOOD), led3))


def test_config_overrides():
    led = A.read_ledger(LEDGER)
    bad = load(BAD)
    cfg = {"allowed_statuses": ["Confirmed"], "banned_phrases": [],
           "required_fields": A.DEFAULT_REQUIRED_FIELDS + ["actions"]}
    assert not {"C1", "C2", "C8"} & failed(A.check_answer(bad, led, cfg))
    with pytest.raises(A.InputError):
        A.check_answer(bad, led, {"nope": []})


def test_invalid_json_is_c1():
    res = A.check_answer_text("{not json", A.read_ledger(LEDGER))
    assert len(res) == 1 and res[0].id == "C1" and not res[0].ok


def test_ledger_csv_accepts_gap_type():
    led = A.parse_ledger("id,type,text\nGAP-X,GAP,기록 없음\nT-1,test,시험 10회\n")
    assert [e["type"] for e in led] == ["GAP", "test"]
    with pytest.raises(A.InputError):
        A.parse_ledger("id,kind\nx,y\n")


def test_cli_exit_codes(capsys):
    assert main(["answer", str(GOOD), "--ledger", str(LEDGER)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("형식 검사 통과")
    assert "인용이 내용상 맞는지는 사람이 확인합니다" in out
    assert "정확함" not in out and "검증됨" not in out
    assert main(["answer", str(BAD), "--ledger", str(LEDGER), "--json"]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["summary"] == "형식 검사 실패 8건" and set(data["failed_ids"]) == BAD_FAILS
    assert main(["answer", str(FIX / "nope.json"), "--ledger", str(LEDGER)]) == 2


def test_tool_function_direct():
    res = T.check_answer(BAD.read_text(encoding="utf-8"), LEDGER.read_text(encoding="utf-8"))
    assert res["failed"] == 8 and set(res["failed_ids"]) == BAD_FAILS
    assert res["note"] == A.HUMAN_NOTE
    ok = T.check_answer(load(GOOD), LEDGER.read_text(encoding="utf-8"), "{}")
    assert ok["summary"] == "형식 검사 통과"
    with pytest.raises(T.InputError):
        T.check_answer("{}", "id,type,text\n", "{bad")


def test_mcp_tool_registered():
    pytest.importorskip("mcp")
    from ontocraft_check.mcp_server import build_server

    res = asyncio.run(build_server().call_tool(
        "check_answer", {"answer": GOOD.read_text(encoding="utf-8"), "ledger": LEDGER.read_text(encoding="utf-8")}))
    assert not res.is_error
    assert json.loads(res.content[0].text)["summary"] == "형식 검사 통과"
