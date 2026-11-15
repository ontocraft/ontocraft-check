"""AI 답변 근거 검사(answer)입니다.

에이전트가 낸 답(JSON)과 근거 원장(CSV: id,type,text)을 받아, 답이 원장에 기대고 있는지 형식으로만 검사합니다.
검사 C1~C10 은 제조 AI 책 12장 실습 검증기(ch12_meeting_output_validator.html, 브라우저 JavaScript)를
파이썬으로 옮긴 것입니다. 기본 허용 상태, 금지 표현, 필수 칸은 책 값이고 설정으로 바꿀 수 있습니다.

하지 않는 것: 인용이 내용상 주장을 뒷받침하는지 판단하지 않습니다. C9 는 글자 일치만 봅니다.
금지 표현은 목록에 든 말만 잡습니다. LLM 을 부르지 않습니다.
"""

from __future__ import annotations

import csv
import io
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_REQUIRED_FIELDS = ["meeting_question", "observations", "hypotheses", "cannot_conclude", "decisions_for_humans"]
DEFAULT_ALLOWED_STATUSES = ["Needs Evidence", "Association", "Tested", "Rejected"]
DEFAULT_BANNED_PHRASES = ["원인으로 확인", "확인되었습니다", "원인입니다", "확실히", "틀림없이", "확정되었습니다", "때문임이 분명"]
DEFAULT_TEST_TYPES = ["test"]
DEFAULT_UNKNOWN_TYPES = ["unknown", "GAP"]

CONFIG_KEYS = {
    "required_fields": DEFAULT_REQUIRED_FIELDS,
    "allowed_statuses": DEFAULT_ALLOWED_STATUSES,
    "banned_phrases": DEFAULT_BANNED_PHRASES,
    "test_types": DEFAULT_TEST_TYPES,
    "unknown_types": DEFAULT_UNKNOWN_TYPES,
}

HUMAN_NOTE = "인용이 내용상 맞는지는 사람이 확인합니다."
# 책 검증기의 /\d+(\.\d+)?/g 와 같게 ASCII 숫자만 셉니다(파이썬 \d 는 다른 문자 체계의 숫자도 잡음).
NUM_RE = re.compile(r"[0-9]+(?:\.[0-9]+)?")


class InputError(ValueError):
    """답·원장·설정을 읽을 수 없을 때 냅니다."""


@dataclass
class Result:
    id: str
    name: str
    ok: bool
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


# ---------- 입력 읽기 ----------

def parse_ledger(text: str) -> list[dict]:
    """원장 CSV 본문(머리 줄 id,type,text)을 읽습니다. type 은 signal, maintenance, test, unknown, GAP 등입니다."""
    if text.startswith("\ufeff"):
        text = text[1:]
    reader = csv.DictReader(io.StringIO(text))
    fields = [f.strip() for f in (reader.fieldnames or [])]
    missing = [k for k in ("id", "type", "text") if k not in fields]
    if missing:
        raise InputError("원장 CSV 머리 줄에 빠진 칸: " + ", ".join(missing) + " (필요한 칸: id,type,text)")
    rows = []
    for raw in reader:
        row = {(k or "").strip(): (v or "") for k, v in raw.items() if k is not None}
        rid = row.get("id", "").strip()
        if not rid:
            continue
        rows.append({"id": rid, "type": row.get("type", "").strip(), "text": row.get("text", "")})
    return rows


def read_ledger(path: str | Path) -> list[dict]:
    p = Path(path)
    if not p.is_file():
        raise InputError(f"원장 파일이 없습니다: {path}")
    return parse_ledger(p.read_text(encoding="utf-8"))


def load_config(path: str | Path | None) -> dict | None:
    """설정 파일(JSON, 또는 PyYAML 이 설치되어 있으면 YAML)을 읽습니다."""
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        raise InputError(f"설정 파일이 없습니다: {path}")
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore[import-not-found]
        except ImportError as exc:
            raise InputError("YAML 설정을 읽으려면 PyYAML 이 필요합니다. 설치하지 않았으면 같은 내용을 JSON 으로 줍니다.") from exc
        data = yaml.safe_load(text)
    else:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise InputError(f"설정 JSON 을 읽을 수 없습니다: {exc}") from exc
    return data


def resolve_config(config: dict | None) -> dict:
    cfg = {k: list(v) for k, v in CONFIG_KEYS.items()}
    if config is None:
        return cfg
    if not isinstance(config, dict):
        raise InputError("설정은 객체(키: " + ", ".join(CONFIG_KEYS) + ")여야 합니다.")
    unknown = [k for k in config if k not in CONFIG_KEYS]
    if unknown:
        raise InputError("모르는 설정 키: " + ", ".join(unknown) + ". 쓸 수 있는 키: " + ", ".join(CONFIG_KEYS))
    for k, v in config.items():
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            raise InputError(f"설정 {k} 는 문자열 목록이어야 합니다.")
        cfg[k] = list(v)
    return cfg


# ---------- 검사 ----------

def _list(x) -> list:
    return x if isinstance(x, list) else []


def _dict(x) -> dict:
    return x if isinstance(x, dict) else {}


def _strings(o, acc: list[str]) -> list[str]:
    """책 검증기의 strings(): 값에 든 문자열을 모두 모읍니다(객체 키는 넣지 않음)."""
    if isinstance(o, str):
        acc.append(o)
    elif isinstance(o, list):
        for x in o:
            _strings(x, acc)
    elif isinstance(o, dict):
        for x in o.values():
            _strings(x, acc)
    return acc


def _uniq(xs: list[str]) -> list[str]:
    return list(dict.fromkeys(xs))


def _js(x) -> str:
    return "undefined" if x is None else str(x)


def check_answer(answer, ledger: list[dict], config: dict | None = None) -> list[Result]:
    """답(사전)을 원장으로 검사해 C1~C10 결과를 돌려줍니다."""
    cfg = resolve_config(config)
    req = cfg["required_fields"]
    statuses = cfg["allowed_statuses"]
    banned = cfg["banned_phrases"]
    test_types = set(cfg["test_types"])
    unknown_types = {t.lower() for t in cfg["unknown_types"]}
    R: list[Result] = []

    def add(cid: str, name: str, ok: bool, msg: str) -> None:
        R.append(Result(cid, name, bool(ok), msg))

    if isinstance(answer, dict):
        d = answer
        miss = [k for k in req if k not in d]
        extra = [k for k in d if k not in req]
        msg = (("빠진 칸: " + ", ".join(miss) + ". ") if miss else "") + (("허용하지 않는 칸: " + ", ".join(extra)) if extra else "")
        add("C1", "필수 칸", not miss and not extra, msg or "필수 칸이 모두 있고 다른 칸이 없습니다")
    else:
        d = {}
        add("C1", "필수 칸", False, "답의 최상위가 객체가 아닙니다")

    by_id = {e["id"]: e for e in reversed(ledger)}  # JS find() 처럼 같은 id 는 첫 행을 씁니다

    H = [_dict(h) for h in _list(d.get("hypotheses"))]
    obs = [_dict(o) for o in _list(d.get("observations"))]

    bad_s = [_js(h.get("id")) + "=" + _js(h.get("status")) for h in H if h.get("status") not in statuses]
    add("C2", "가설 상태", not bad_s, ("허용 목록 밖의 상태: " + ", ".join(bad_s)) if bad_s else "모든 상태가 허용 목록 안입니다")

    cited: list = []
    for o in obs:
        cited.extend(_list(o.get("evidence")))
    for h in H:
        for k in ("supporting", "contradicting", "missing"):
            cited.extend(_list(h.get(k)))
    unk = _uniq([_js(x) for x in cited if not (isinstance(x, str) and x in by_id)])
    add("C3", "인용 ID 존재", not unk,
        ("원장에 없는 ID: " + ", ".join(unk)) if unk else f"인용 {len(cited)}건이 모두 원장에 있습니다")

    no_obs_ev = sum(1 for o in obs if not _list(o.get("evidence")))
    add("C4", "관찰마다 인용", no_obs_ev == 0, f"인용 없는 관찰 {no_obs_ev}건" if no_obs_ev else "모든 관찰에 인용이 있습니다")

    def _type(x) -> str:
        return by_id[x]["type"] if isinstance(x, str) and x in by_id else ""

    tested = [_js(h.get("id")) for h in H
              if h.get("status") == "Tested" and not any(_type(x) in test_types for x in _list(h.get("supporting")))]
    add("C5", "Tested 근거", not tested,
        ("시험 기록 없이 Tested: " + ", ".join(tested)) if tested else "시험 기록 없는 Tested가 없습니다")

    no_next = []
    for h in H:
        nc = h.get("next_check")
        if not isinstance(nc, dict) or not nc.get("what") or not nc.get("decision_rule"):
            no_next.append(_js(h.get("id")))
    add("C6", "다음 검증", not no_next,
        ("다음 검증 또는 판정 규칙이 없는 가설: " + ", ".join(no_next)) if no_next else "모든 가설에 다음 검증과 판정 규칙이 있습니다")

    cc = isinstance(d.get("cannot_conclude"), list) and len(d["cannot_conclude"]) > 0
    n_unknown = sum(1 for e in ledger if e["type"].lower() in unknown_types)
    add("C7", "확정할 수 없는 것", cc,
        "비어 있지 않습니다" if cc else f"비어 있습니다. 원장에 unknown 항목이 {n_unknown}개 있습니다")

    hits = [b for s in _strings(d, []) for b in banned if b in s]
    add("C8", "금지 표현", not hits, ("발견: " + ", ".join(_uniq(hits))) if hits else "금지 표현이 없습니다")

    num_bad = []
    for h in H:
        st = h.get("statement")
        nums = NUM_RE.findall(st) if isinstance(st, str) else []
        refs = _list(h.get("supporting")) + _list(h.get("contradicting")) + _list(h.get("missing"))
        ev = " ".join(by_id[x]["text"] if isinstance(x, str) and x in by_id else "" for x in refs)
        num_bad.extend(_js(h.get("id")) + ": " + n for n in nums if n not in ev)
    add("C9", "숫자 출처", not num_bad,
        ("인용한 근거에 없는 숫자: " + ", ".join(num_bad)) if num_bad else "가설 문장의 숫자가 모두 인용한 근거에 있습니다")

    dh = isinstance(d.get("decisions_for_humans"), list) and len(d["decisions_for_humans"]) > 0
    add("C10", "사람 결정 지점", dh, "사람이 결정할 항목이 있습니다" if dh else "비어 있습니다")
    return R


def check_answer_text(text: str, ledger: list[dict], config: dict | None = None) -> list[Result]:
    """답 JSON 본문을 검사합니다. JSON 으로 읽을 수 없으면 C1(JSON 형식) 실패 하나만 돌려줍니다(책 검증기와 같음)."""
    resolve_config(config)
    try:
        answer = json.loads(text)
    except json.JSONDecodeError as exc:
        return [Result("C1", "JSON 형식", False, f"JSON으로 읽을 수 없습니다: {exc}")]
    return check_answer(answer, ledger, config)


# ---------- 결과 묶기와 출력 ----------

def headline(results: list[Result]) -> str:
    n = sum(1 for r in results if not r.ok)
    return "형식 검사 통과" if n == 0 else f"형식 검사 실패 {n}건"


def to_payload(results: list[Result]) -> dict:
    n = sum(1 for r in results if not r.ok)
    return {
        "feature": "answer",
        "summary": headline(results),
        "failed": n,
        "checks": len(results),
        "failed_ids": [r.id for r in results if not r.ok],
        "results": [r.to_dict() for r in results],
        "note": HUMAN_NOTE,
    }


def render_table(results: list[Result]) -> str:
    n = sum(1 for r in results if not r.ok)
    lines = [f"{headline(results)} (검사 {len(results)}건)", "",
             "| 검사 | 이름 | 결과 | 내용 |", "|---|---|---|---|"]
    for r in results:
        msg = r.message.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {r.id} | {r.name} | {'통과' if r.ok else '실패'} | {msg} |")
    lines += ["", f"실패 {n}건 / 검사 {len(results)}건", HUMAN_NOTE, ""]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        prog="ontocraft-check answer",
        description="AI 답변(JSON)이 근거 원장(CSV: id,type,text)에 기대고 있는지 형식으로 검사합니다(C1~C10). "
                    "인용이 내용상 맞는지는 판단하지 않습니다.")
    ap.add_argument("answer", help="답 JSON 파일")
    ap.add_argument("--ledger", required=True, help="근거 원장 CSV 파일(머리 줄 id,type,text)")
    ap.add_argument("--config", help="설정 파일(JSON. PyYAML 이 있으면 YAML). 키: " + ", ".join(CONFIG_KEYS))
    ap.add_argument("--json", action="store_true", help="결과를 JSON 으로 냅니다")
    args = ap.parse_args(argv)
    try:
        ledger = read_ledger(args.ledger)
        config = load_config(args.config)
        p = Path(args.answer)
        if not p.is_file():
            raise InputError(f"답 파일이 없습니다: {args.answer}")
        results = check_answer_text(p.read_text(encoding="utf-8"), ledger, config)
    except InputError as exc:
        print(f"ontocraft-check: {exc}", file=sys.stderr)
        return 2
    if args.json:
        sys.stdout.write(json.dumps(to_payload(results), ensure_ascii=False, indent=1) + "\n")
    else:
        sys.stdout.write(render_table(results))
    return 0 if all(r.ok for r in results) else 1
