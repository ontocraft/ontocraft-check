"""AI 레디 자가진단(0.8.0)입니다. 데이터 묶음(폴더 또는 파일)에서 기계로 확인할 수 있는 항목만 점검합니다.

근거는 행정안전부·NIA 「공공데이터의 인공지능 친화적 관리 가이드라인 V1.0」(2026-03-31) 부록의 자가진단 문항입니다.
이 점검은 공식 진단이 아니며 그 가이드라인의 판정을 대신하지 않습니다. 규칙 id 는 AIR01~AIR14 입니다.
"""

from __future__ import annotations

import csv
import html
import json
import re
import sys
from pathlib import Path

from . import __version__

DISCLAIMER = (
    "이 점검은 공식 진단이 아닙니다. 행정안전부·NIA 「공공데이터의 인공지능 친화적 관리 가이드라인 V1.0」 부록 자가진단 문항 가운데 "
    "기계로 확인할 수 있는 것만 근사해서 봅니다. 공식 진단 결과나 인증을 대신하지 못하고, 적정이 나와도 가이드라인 충족을 뜻하지 않습니다."
)
STATUS_KO = {"ok": "적정", "fail": "미흡", "na": "해당없음", "manual": "사람 확인 필요"}
LEVEL_SEVERITY = {"필수": "중요", "권장": "경미"}
MAX_ROWS = 100_000
MAX_JSON_BYTES = 30_000_000

# 규칙 id: (필수/권장, 제목, 고치는 법)
RULES = {
    "AIR01": ("필수", "개방형 포맷", "CSV, JSON, JSONL, XML, Parquet, JSON-LD 가운데 하나 이상으로 데이터를 내려받게 합니다."),
    "AIR02": ("필수", "기계가 이해하는 구조", "머리 줄이 있는 표(CSV)나 JSON 객체 목록(JSONL, JSON 배열)으로 데이터를 둡니다."),
    "AIR03": ("필수", "스키마 정의", "JSON Schema(schema.json)나 Croissant recordSet 의 필드 정의로 열 이름과 타입을 적습니다."),
    "AIR04": ("필수", "표준 스키마 메타데이터", "DCAT(dcat.jsonld)이나 Croissant(croissant.json) 기록을 묶음에 넣습니다."),
    "AIR05": ("필수", "DCAT 필수 항목", "빠진 항목을 DCAT 기록에 채웁니다. 배포(dcat:distribution)에는 accessURL, byteSize, mediaType 을 둡니다."),
    "AIR06": ("필수", "결측값 관리", "빈 값이 20%를 넘는 열은 채우거나 선택 열임을 밝히고, README 에 결측 표기 규칙(빈 문자열, null 등)을 적습니다."),
    "AIR07": ("필수", "품질평가 결과의 메타데이터 수록", "quality.json 을 두거나 DCAT·Croissant 에 dqv: 품질 속성을 적습니다."),
    "AIR08": ("필수", "합성·자동 생성 구분 표시", "authoring 열, dct:provenance, prov:, skos:editorialNote, Croissant rai 확장 가운데 하나로 AI 생성 여부를 밝힙니다."),
    "AIR09": ("필수", "이용 허락 범위의 라이선스 표시", "DCAT dct:license, Croissant license, README 라이선스 절 가운데 하나에 라이선스를 적습니다."),
    "AIR10": ("필수", "같은 개념 같은 용어(근사)", "id 열의 중복을 없애고, 같은 표제어가 여러 행에 있으면 하나로 합치거나 구분 열을 둡니다."),
    "AIR11": ("권장", "영구 식별자", "dct:identifier 를 http(s) 주소나 DOI 로 적거나 레코드마다 uri 열을 둡니다."),
    "AIR12": ("권장", "데이터 카드", "README.md 에 무엇을 담았고 어떻게 만들었는지 적거나 Croissant 기록을 둡니다."),
    "AIR13": ("권장", "버전별 변경 이력", "CHANGELOG 파일이나 README 변경 기록 절, adms:versionNotes 를 둡니다."),
    "AIR14": ("권장", "해시", "파일마다 sha256 을 Croissant distribution 이나 체크섬 파일에 적습니다."),
}

# 자동으로 보지 못하는 문항입니다. 가이드라인 문항 번호가 아니라 이 도구가 묶은 이름입니다.
MANUAL = [
    ("데이터 사전 내용 적정성", "열 설명이 실제 값과 맞고 단위·코드값 뜻이 빠짐없이 적혔는지는 사람이 읽어야 합니다."),
    ("개인정보 비식별 조치", "개인정보나 민감정보가 들었는지, 비식별 조치를 했는지는 내용을 아는 사람이 판단합니다."),
    ("재식별 위험 평가", "여러 열을 합치면 개인을 알아볼 수 있는지 평가했는지는 자동으로 알 수 없습니다."),
    ("책임 주체의 실제 운영", "담당 기관과 연락처가 적혀 있어도 실제로 답을 받는지는 확인되지 않습니다."),
    ("오류 신고와 정정 절차", "오류를 받아 고치는 창구와 처리 절차가 운영되는지는 사람이 확인합니다."),
    ("API 제공 여부와 품질", "내려받기 외에 API 가 필요한 자료인지, 제공한다면 명세와 안정성이 맞는지 봅니다."),
    ("표준 용어·코드 사용 적정성", "공공 표준 용어와 코드 체계를 따라야 하는 열이 따랐는지는 도메인 지식으로 판단합니다."),
    ("갱신 주기 준수", "적어 둔 갱신 주기를 실제로 지키는지는 시간이 지나야 알 수 있습니다."),
    ("유형별 문항(비정형 등)", "이미지·문서 같은 비정형 자료나 유형별 문항은 자료 종류에 따라 사람이 봅니다."),
]

_NS = {
    "dct": "http://purl.org/dc/terms/", "dcat": "http://www.w3.org/ns/dcat#", "owl": "http://www.w3.org/2002/07/owl#",
    "vcard": "http://www.w3.org/2006/vcard/ns#", "foaf": "http://xmlns.com/foaf/0.1/", "adms": "http://www.w3.org/ns/adms#",
    "dqv": "http://www.w3.org/ns/dqv#", "prov": "http://www.w3.org/ns/prov#", "skos": "http://www.w3.org/2004/02/skos/core#",
}
_ALIAS = {"dcterms": "dct"}
_DATA_SUFFIX = {".csv": "CSV", ".json": "JSON", ".jsonl": "JSONL", ".ndjson": "JSONL", ".parquet": "Parquet",
                ".jsonld": "JSON-LD", ".xml": "XML"}
ID_COLS = ("id", "identifier", "uri", "iri")
LABEL_COLS = ("ko", "label", "name", "title")
DCAT_REQUIRED = ["dct:title", "dct:description", "dct:references", "dct:creator", "dct:publisher", "dcat:landingPage",
                 "dct:accrualPeriodicity", "dcat:theme", "dcat:keyword", "dct:identifier", "dcat:contactPoint",
                 "dct:language", "dcat:distribution", "dct:issued", "dct:modified", "dct:license", "dct:rights"]


class InputError(ValueError):
    pass


def _canon(key: str, ctx) -> str:
    """접두사 표기와 전체 IRI 표기를 `접두사:이름` 하나로 맞춥니다."""
    iri = None
    if key.startswith(("http://", "https://")):
        iri = key
    elif ":" in key:
        pfx, loc = key.split(":", 1)
        base = None
        for c in (ctx if isinstance(ctx, list) else [ctx]):
            if isinstance(c, dict) and pfx in c:
                v = c[pfx]
                base = v.get("@id") if isinstance(v, dict) else v
        if not isinstance(base, str):
            pfx = _ALIAS.get(pfx, pfx)
            base = _NS.get(pfx)
        if base:
            iri = base + loc
        else:
            return key
    else:
        return key
    for pfx, base in _NS.items():
        if iri.startswith(base):
            return f"{pfx}:{iri[len(base):]}"
    return iri


def _filled(v) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, (list, dict)):
        return bool(v)
    return True


def _as_list(v) -> list:
    return v if isinstance(v, list) else [v]


def _node_keys(node: dict, ctx) -> dict:
    return {_canon(k, ctx): v for k, v in node.items() if not k.startswith("@") or k in ("@type",)}


def _types(node: dict, ctx) -> set[str]:
    return {_canon(t, ctx) for t in _as_list(node.get("@type", [])) if isinstance(t, str)}


def _read_json(p: Path):
    if p.stat().st_size > MAX_JSON_BYTES:
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def _read_table(p: Path, kind: str):
    """(열 이름 목록, 행 목록)을 돌려줍니다. 읽을 수 없거나 표 모양이 아니면 None."""
    try:
        if kind == "CSV":
            csv.field_size_limit(10_000_000)
            with p.open(encoding="utf-8-sig", newline="") as fh:
                rd = csv.DictReader(fh)
                cols = list(rd.fieldnames or [])
                rows = []
                for i, r in enumerate(rd):
                    if i >= MAX_ROWS:
                        break
                    rows.append(r)
            return (cols, rows) if cols and rows else None
        if kind == "JSONL":
            rows = []
            with p.open(encoding="utf-8-sig") as fh:
                for i, line in enumerate(fh):
                    if i >= MAX_ROWS:
                        break
                    if line.strip():
                        o = json.loads(line)
                        if not isinstance(o, dict):
                            return None
                        rows.append(o)
            cols = list(dict.fromkeys(k for r in rows for k in r))
            return (cols, rows) if rows else None
        if kind in ("JSON", "JSON-LD"):
            obj = _read_json(p)
            if isinstance(obj, dict) and isinstance(obj.get("@graph"), list):
                obj = obj["@graph"]
            if isinstance(obj, list) and obj and all(isinstance(x, dict) for x in obj):
                cols = list(dict.fromkeys(k for r in obj for k in r))
                return cols, obj
    except (OSError, ValueError, csv.Error):
        return None
    return None


def _scan(root: Path) -> dict:
    files = [root] if root.is_file() else sorted(
        p for p in root.rglob("*") if p.is_file() and not any(part.startswith(".") for part in p.relative_to(root).parts))
    base = root.parent if root.is_file() else root
    rel = lambda p: str(p.relative_to(base)) if p != root else p.name  # noqa: E731
    s = {"files": [rel(p) for p in files], "dcat": [], "croissant": [], "schema": [], "quality": [], "readme": None,
         "changelog": [], "checksum": [], "data": [], "formats": {}}
    for p in files:
        name = p.name.lower()
        suf = p.suffix.lower()
        if name.startswith("readme") and s["readme"] is None and suf in (".md", ".txt", ""):
            s["readme"] = p
        if name.startswith(("changelog", "changes", "history")):
            s["changelog"].append(rel(p))
        if name.startswith(("sha256", "checksum")) or suf in (".sha256", ".sha512"):
            s["checksum"].append(rel(p))
        if suf not in _DATA_SUFFIX:
            continue
        role = None
        obj = None
        if suf in (".json", ".jsonld") and p.stat().st_size <= MAX_JSON_BYTES:
            head = ""
            try:
                with p.open(encoding="utf-8-sig") as fh:
                    head = fh.read(20000)
            except OSError:
                pass
            sniff = ("dcat" in head.lower() and "dataset" in head.lower()) or "croissant" in head.lower() or "$schema" in head
            if sniff or "quality" in name or name in ("schema.json",):
                obj = _read_json(p)
        if isinstance(obj, dict):
            ctx = obj.get("@context", {})
            nodes = [obj] + [n for n in _as_list(obj.get("@graph", [])) if isinstance(n, dict)]
            conf = json.dumps(obj.get("conformsTo", ""), ensure_ascii=False).lower()
            if "mlcommons.org/croissant" in conf or name == "croissant.json":
                role = "croissant"
                s["croissant"].append((rel(p), obj))
            elif "$schema" in obj or name == "schema.json":
                role = "schema"
                s["schema"].append((rel(p), obj))
            else:
                for n in nodes:
                    if "dcat:Dataset" in _types(n, ctx):
                        role = "dcat"
                        s["dcat"].append((rel(p), n, ctx))
                        break
            if role is None and "quality" in name:
                role = "quality"
                s["quality"].append((rel(p), obj))
        elif "quality" in name and suf in (".json", ".jsonld"):
            role = "quality"
            s["quality"].append((rel(p), None))
        if role:
            continue
        kind = _DATA_SUFFIX[suf]
        s["formats"].setdefault(kind, []).append(rel(p))
        rec = {"file": rel(p), "kind": kind, "table": None}
        if kind in ("CSV", "JSONL", "JSON", "JSON-LD"):
            rec["table"] = _read_table(p, kind)
        s["data"].append(rec)
    return s


def _res(rid, status, message, detail=None):
    level, title, fix = RULES[rid]
    return {"id": rid, "title": title, "level": level, "severity": LEVEL_SEVERITY[level], "status": status,
            "status_ko": STATUS_KO[status], "message": message, "fix": fix if status == "fail" else "",
            "detail": detail or {}}


def _check_rules(s: dict) -> list[dict]:
    out = []
    tables = [(d["file"], d["table"]) for d in s["data"] if d["table"]]
    meta_docs = [(f, n, c) for f, n, c in s["dcat"]]
    dcat = meta_docs[0] if meta_docs else None
    cro = s["croissant"][0] if s["croissant"] else None
    dkeys = _node_keys(dcat[1], dcat[2]) if dcat else {}
    ckeys = {k: v for k, v in cro[1].items()} if cro else {}
    readme = ""
    if s["readme"]:
        try:
            readme = s["readme"].read_text(encoding="utf-8-sig")
        except OSError:
            readme = ""

    # AIR01
    fmts = {k: len(v) for k, v in s["formats"].items() if k != "Parquet" or v}
    out.append(_res("AIR01", "ok" if fmts else "fail",
                    ("개방형 포맷 파일이 있습니다: " + ", ".join(f"{k} {n}개" for k, n in fmts.items())) if fmts
                    else "개방형 포맷(CSV, JSON, JSONL, XML, Parquet, JSON-LD) 파일을 찾지 못했습니다.", {"formats": fmts}))
    # AIR02
    if tables:
        out.append(_res("AIR02", "ok", f"표 또는 객체 목록으로 읽힌 파일이 {len(tables)}개입니다.", {"files": [f for f, _ in tables]}))
    elif s["formats"].get("Parquet"):
        out.append(_res("AIR02", "ok", "Parquet 파일은 열 구조를 가진 형식이라 구조가 있다고 봅니다. 내용은 읽지 않았습니다.", {"files": s["formats"]["Parquet"]}))
    else:
        out.append(_res("AIR02", "fail", "표나 JSON 객체 목록으로 읽히는 파일이 없습니다."))
    # AIR03
    cfields = 0
    if cro:
        for rs in _as_list(ckeys.get("recordSet", [])) or []:
            if isinstance(rs, dict):
                cfields += sum(1 for _ in _as_list(rs.get("field", [])) if _)
    if s["schema"] or cfields:
        src = []
        if s["schema"]:
            src.append("JSON Schema " + ", ".join(f for f, _ in s["schema"]))
        if cfields:
            src.append(f"Croissant recordSet 필드 {cfields}개")
        out.append(_res("AIR03", "ok", "스키마가 정의되어 있습니다: " + "; ".join(src) + ".", {"json_schema": [f for f, _ in s["schema"]], "croissant_fields": cfields}))
    else:
        out.append(_res("AIR03", "fail", "JSON Schema 도 Croissant recordSet 필드도 찾지 못했습니다."))
    # AIR04
    std = [x for x in (("DCAT " + dcat[0]) if dcat else None, ("Croissant " + cro[0]) if cro else None) if x]
    out.append(_res("AIR04", "ok" if std else "fail", ("표준 스키마 메타데이터가 있습니다: " + ", ".join(std) + ".") if std
                    else "DCAT 기록도 Croissant 기록도 찾지 못했습니다."))
    # AIR05
    if not dcat:
        out.append(_res("AIR05", "fail", "DCAT 기록이 없어 필수 항목을 점검하지 못했습니다.", {"missing": DCAT_REQUIRED}))
    else:
        missing = [k for k in DCAT_REQUIRED if not _filled(dkeys.get(k))]
        if not (_filled(dkeys.get("dcat:version")) or _filled(dkeys.get("owl:versionInfo"))):
            missing.append("dcat:version 또는 owl:versionInfo")
        dist_missing = []
        for i, d in enumerate(x for x in _as_list(dkeys.get("dcat:distribution", [])) if isinstance(x, dict)):
            dk = _node_keys(d, dcat[2])
            for k in ("dcat:accessURL", "dcat:byteSize", "dcat:mediaType"):
                if not _filled(dk.get(k)):
                    dist_missing.append(f"dcat:distribution[{i}] 의 {k}")
        missing += dist_missing
        out.append(_res("AIR05", "fail" if missing else "ok",
                        ("DCAT 필수 항목 " + str(len(missing)) + "개가 빠졌습니다: " + ", ".join(missing) + ".") if missing
                        else "DCAT 필수 항목이 모두 있습니다.", {"missing": missing, "file": dcat[0]}))
    # AIR06
    tb = [(f, t) for f, t in tables if not f.lower().endswith((".jsonld",)) and next(d for d in s["data"] if d["file"] == f)["kind"] in ("CSV", "JSONL")]
    has_rule = bool(re.search(r"결측|missing", readme, re.I))
    if not tb:
        out.append(_res("AIR06", "na", "빈 값 비율을 셀 CSV·JSONL 표가 없습니다."))
    else:
        bad = []
        for f, (cols, rows) in tb:
            for c in cols:
                n = sum(1 for r in rows if r.get(c) is None or (isinstance(r.get(c), str) and not r.get(c).strip()))
                if n / len(rows) > 0.20:
                    bad.append({"file": f, "column": c, "empty_pct": round(100 * n / len(rows), 1)})
        problems = []
        if bad:
            problems.append(f"빈 값이 20%를 넘는 열이 {len(bad)}개입니다")
        if not has_rule:
            problems.append("README 에 결측 표기 규칙(「결측」 또는 「missing」)이 없습니다")
        msg = "; ".join(problems) + "." if problems else "빈 값이 20%를 넘는 열이 없고 README 에 결측 표기 규칙이 있습니다."
        if bad and has_rule:
            msg += " README 에 결측 표기 규칙은 있습니다. 선택 열이라 비어 있는 것이면 그 사유를 README 에 열 이름과 함께 적어 둡니다."
        if bad:
            msg += " 대표 열: " + ", ".join(f"{b['file']}:{b['column']} {b['empty_pct']}%" for b in bad[:6]) + ("..." if len(bad) > 6 else "") + "."
        out.append(_res("AIR06", "fail" if problems else "ok", msg, {"over_20pct": bad, "readme_missing_rule": has_rule, "scanned_files": [f for f, _ in tb]}))
    # AIR07
    qual = list(s["quality"])
    qkeys = [k for k in list(dkeys) + list(ckeys) if k.startswith("dqv:") or "quality" in k.lower()]
    if qual or qkeys:
        out.append(_res("AIR07", "ok", "품질평가 결과가 있습니다: " + ", ".join([f for f, _ in qual] + qkeys) + "."))
    else:
        out.append(_res("AIR07", "fail", "quality 파일도 dqv: 품질 속성도 찾지 못했습니다."))
    # AIR08
    auth = []
    for f, (cols, rows) in tables:
        for c in cols:
            if c.lower() in ("authoring", "generated", "synthetic", "provenance"):
                auth.append(f"{f} 의 {c} 열")
    for k in list(dkeys) + list(ckeys):
        kl = k.lower()
        if k in ("dct:provenance", "skos:editorialNote") or kl.startswith(("prov:", "rai:")) or "issyntheticdata" in kl or "croissant/rai" in kl:
            auth.append(k)
    out.append(_res("AIR08", "ok" if auth else "fail", ("합성·자동 생성 구분 표시가 있습니다: " + ", ".join(list(dict.fromkeys(auth))[:5]) + ".") if auth
                    else "authoring, dct:provenance, prov:, skos:editorialNote, Croissant rai 확장 가운데 어느 것도 찾지 못했습니다."))
    # AIR09
    lic = []
    if _filled(dkeys.get("dct:license")):
        lic.append("DCAT dct:license")
    if _filled(ckeys.get("license")):
        lic.append("Croissant license")
    if re.search(r"^#+\s*.*(라이선스|license)", readme, re.I | re.M):
        lic.append("README 라이선스 절")
    out.append(_res("AIR09", "ok" if lic else "fail", ("라이선스가 표시되어 있습니다: " + ", ".join(lic) + ".") if lic
                    else "DCAT dct:license, Croissant license, README 라이선스 절 어디에도 라이선스가 없습니다."))
    # AIR10
    if not tb:
        out.append(_res("AIR10", "na", "id 열과 표제어 열을 셀 CSV·JSONL 표가 없습니다."))
    else:
        dup_id, dup_label, checked = [], [], 0
        for f, (cols, rows) in tb:
            low = {c.lower(): c for c in cols}
            for key in ID_COLS:
                if key in low:
                    c = low[key]
                    vals = [str(r.get(c)).strip() for r in rows if _filled(r.get(c))]
                    n = len(vals) - len(set(vals))
                    checked += 1
                    if n:
                        dup_id.append({"file": f, "column": c, "duplicates": n})
                    break
            for key in LABEL_COLS:
                if key in low:
                    c = low[key]
                    grp = low.get("domain")
                    seen, n = set(), 0
                    for r in rows:
                        if _filled(r.get(c)):
                            k = (str(r.get(grp)) if grp else "", str(r.get(c)).strip())
                            n += k in seen
                            seen.add(k)
                    checked += 1
                    if n:
                        dup_label.append({"file": f, "column": c, "duplicates": n})
                    break
        if not checked:
            out.append(_res("AIR10", "na", "id 열도 표제어 열(ko, label, name, title)도 없어 점검하지 않았습니다."))
        else:
            bad = dup_id + dup_label
            msg = ("id 열 중복 " + str(sum(x["duplicates"] for x in dup_id)) + "건, 표제어 열 중복 " + str(sum(x["duplicates"] for x in dup_label)) + "건입니다. "
                   + ", ".join(f"{x['file']}:{x['column']} {x['duplicates']}" for x in bad[:6]) + ".") if bad else "id 열과 표제어 열에 중복이 없습니다."
            out.append(_res("AIR10", "fail" if bad else "ok", msg, {"id_duplicates": dup_id, "label_duplicates": dup_label}))
    # AIR11
    ident = dkeys.get("dct:identifier")
    ident_s = " ".join(map(str, _as_list(ident))) if _filled(ident) else ""
    uri_col = [f for f, (cols, _) in tables if any(c.lower() in ("uri", "iri") for c in cols)]
    persistent = bool(re.search(r"https?://|doi:|10\.\d{4,}/", ident_s, re.I))
    if persistent or uri_col:
        out.append(_res("AIR11", "ok", "영구 식별자가 있습니다: " + ("dct:identifier " + ident_s if persistent else "레코드 uri 열 " + uri_col[0]) + "."))
    else:
        out.append(_res("AIR11", "fail", "dct:identifier 가 http(s) 주소나 DOI 가 아니고 레코드 uri 열도 없습니다."))
    # AIR12
    card = (["README.md"] if readme else []) + (["Croissant"] if cro else [])
    out.append(_res("AIR12", "ok" if card else "fail", ("데이터 카드가 있습니다: " + ", ".join(card) + ".") if card else "README.md 도 Croissant 기록도 없습니다."))
    # AIR13
    chg = list(s["changelog"])
    if re.search(r"^#+\s*.*(변경\s*(이력|기록)|changelog|release notes|version history)", readme, re.I | re.M):
        chg.append("README 변경 기록 절")
    if "changelog" in {k.lower() for k in ckeys} or _filled(dkeys.get("adms:versionNotes")):
        chg.append("메타데이터 변경 이력 속성")
    out.append(_res("AIR13", "ok" if chg else "fail", ("변경 이력이 있습니다: " + ", ".join(chg) + ".") if chg else "CHANGELOG, changelog 키, adms:versionNotes 를 찾지 못했습니다."))
    # AIR14
    hashes = list(s["checksum"])
    if cro and re.search(r'"(sha256|sha512)"', json.dumps(cro[1])):
        hashes.append("Croissant distribution 해시")
    out.append(_res("AIR14", "ok" if hashes else "fail", ("해시가 있습니다: " + ", ".join(hashes) + ".") if hashes else "sha256 등 파일 해시를 찾지 못했습니다."))
    return out


def check(path) -> dict:
    p = Path(path).expanduser()
    if not p.exists():
        raise InputError(f"경로를 찾을 수 없습니다: {path}")
    s = _scan(p)
    items = _check_rules(s)
    req = [i for i in items if i["level"] == "필수" and i["status"] != "na"]
    rec = [i for i in items if i["level"] == "권장" and i["status"] != "na"]
    summary = {
        "required_auto_total": len(req), "required_auto_ok": sum(i["status"] == "ok" for i in req),
        "required_auto_fail": [i["id"] for i in req if i["status"] == "fail"],
        "recommended_auto_total": len(rec), "recommended_auto_ok": sum(i["status"] == "ok" for i in rec),
        "manual_count": len(MANUAL),
    }
    return {
        "tool": "ontocraft-check", "version": __version__, "feature": "ai-ready", "path": str(p),
        "basis": "행정안전부·NIA 공공데이터의 인공지능 친화적 관리 가이드라인 V1.0 (2026-03-31) 부록 자가진단",
        "disclaimer": DISCLAIMER, "files": s["files"], "summary": summary, "items": items,
        "manual": [{"title": t, "why": w, "status": "manual", "status_ko": STATUS_KO["manual"]} for t, w in MANUAL],
    }


def render(res: dict, fmt: str = "md") -> str:
    if fmt == "json":
        return json.dumps(res, ensure_ascii=False, indent=1) + "\n"
    sm = res["summary"]
    head = (f"필수 자동 점검 {sm['required_auto_total']}개 가운데 적정 {sm['required_auto_ok']}개, "
            f"권장 자동 점검 {sm['recommended_auto_total']}개 가운데 적정 {sm['recommended_auto_ok']}개입니다. "
            f"사람 확인 필요 {sm['manual_count']}개는 점검하지 않았습니다.")
    if fmt == "html":
        e = html.escape
        rows = "".join(
            f"<tr><td>{e(i['id'])}</td><td>{e(i['level'])}</td><td>{e(i['severity'])}</td><td>{e(i['title'])}</td>"
            f"<td><b>{e(i['status_ko'])}</b></td><td>{e(i['message'])}</td><td>{e(i['fix'])}</td></tr>" for i in res["items"])
        man = "".join(f"<tr><td>{e(m['title'])}</td><td>{e(m['why'])}</td></tr>" for m in res["manual"])
        return ("<!doctype html><html lang=\"ko\"><head><meta charset=\"utf-8\"><title>AI 레디 자가진단</title>"
                "<style>body{font-family:sans-serif;max-width:60rem;margin:2rem auto;padding:0 1rem}table{border-collapse:collapse;width:100%}"
                "td,th{border:1px solid #888;padding:.3rem .5rem;text-align:left;vertical-align:top}</style></head><body>"
                f"<h1>AI 레디 자가진단 보고서</h1><p>{e(res['disclaimer'])}</p><p>대상: {e(res['path'])}<br>"
                f"도구: ontocraft-check {e(res['version'])}</p><h2>1. 요약</h2><p>{e(head)}</p>"
                "<h2>2. 자동 점검 결과</h2><table><tr><th>규칙</th><th>구분</th><th>심각도</th><th>항목</th><th>판정</th><th>내용</th><th>고치는 법</th></tr>"
                f"{rows}</table><h2>3. 사람 확인 필요</h2><table><tr><th>항목</th><th>이유</th></tr>{man}</table></body></html>\n")
    lines = ["# AI 레디 자가진단 보고서", "", f"> {res['disclaimer']}", "",
             f"- 대상: `{res['path']}`", f"- 도구: ontocraft-check {res['version']}", f"- 근거: {res['basis']}", "",
             "## 1. 요약", "", head, ""]
    if sm["required_auto_fail"]:
        lines += ["필수 미흡: " + ", ".join(sm["required_auto_fail"]) + ".", ""]
    lines += ["## 2. 자동 점검 결과", "", "| 규칙 | 구분 | 심각도 | 항목 | 판정 | 내용 |", "|---|---|---|---|---|---|"]
    for i in res["items"]:
        lines.append(f"| {i['id']} | {i['level']} | {i['severity']} | {i['title']} | {i['status_ko']} | {i['message'].replace('|', '/')} |")
    fails = [i for i in res["items"] if i["status"] == "fail"]
    if fails:
        lines += ["", "## 3. 고치는 법", ""]
        lines += [f"- {i['id']} {i['title']}: {i['fix']}" for i in fails]
    lines += ["", f"## {4 if fails else 3}. 사람 확인 필요", "", "다음 문항은 기계로 확인할 수 없어 목록만 보입니다. 가이드라인의 문항 번호가 아니라 이 도구가 묶은 이름입니다.", "",
              "| 항목 | 이유 |", "|---|---|"]
    lines += [f"| {m['title']} | {m['why']} |" for m in res["manual"]]
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="ontocraft-check ai-ready",
                                 description="데이터 묶음의 AI 레디 자가진단. 기계로 확인할 수 있는 항목만 점검하며 공식 진단이 아닙니다.")
    ap.add_argument("path", help="데이터 묶음 폴더 또는 파일")
    ap.add_argument("--format", choices=("md", "html", "json"), default="md", help="보고서 형식(기본 md)")
    ap.add_argument("--out", help="보고서를 쓸 파일. 없으면 표준 출력")
    args = ap.parse_args(argv)
    try:
        res = check(args.path)
    except InputError as exc:
        print(f"ontocraft-check: {exc}", file=sys.stderr)
        return 2
    text = render(res, args.format)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 1 if res["summary"]["required_auto_fail"] else 0
