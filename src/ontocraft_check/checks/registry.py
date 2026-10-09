"""용어 등록부 대조입니다(선택).

등록부 폴더의 *.json(domains.json, candidates.json, manifest.json 제외)을 읽어,
클래스·속성의 @ko 레이블(없으면 로컬 이름)이 등록부 용어의 ko·alt와 정확히 같으면
skos:exactMatch 후보를 제안합니다. 심각도가 없는 정보 항목입니다.

0.2: 후보마다 분야(domain, domain_name)와 일치 신뢰도(ko 일치 높음, alt 일치 낮음)를 붙입니다.
분야를 고르면 고르지 않은 분야와만 맞는 것은 REG02(다른 분야에서 같은 이름이 있음)로 나눕니다.

0.3: 등록부 폴더 대신 "builtin" 을 주면 패키지에 넣은 공개 분야 사본(data/registry)을 씁니다.
"""

from __future__ import annotations

import json
import unicodedata
from collections import defaultdict
from pathlib import Path


from rdflib.namespace import RDFS, SKOS

from ..graph import Inventory, has_lang, local_name
from ..model import Finding, Report

CAT = "registry"
EXCLUDE = {"domains.json", "candidates.json", "manifest.json"}
DEFAULT_BASE = "https://w3id.org/ontocraft/terms/"
BUILTIN = "builtin"
BUILTIN_REGISTRY = Path(__file__).resolve().parents[1] / "data" / "registry"


def builtin_manifest() -> dict:
    """내장 사본의 manifest.json(스냅샷 날짜, 분야별 용어 수)입니다."""
    return json.loads((BUILTIN_REGISTRY / "manifest.json").read_text(encoding="utf-8"))


def resolve_registry(value: str | None) -> tuple[str | None, str | None]:
    """--registry 값을 (실제 폴더, 보고서에 적을 이름)으로 바꿉니다. "builtin" 이면 내장 사본입니다."""
    if not value:
        return None, None
    if str(value).strip().lower() == BUILTIN:
        snap = builtin_manifest().get("snapshot", "?")
        return str(BUILTIN_REGISTRY), f"builtin(내장 사본, 공개 분야, 스냅샷 {snap}, CC BY 4.0)"
    return str(value), str(value)


def josa_iga(word: str) -> str:
    """앞말의 받침에 맞춰 「이」나 「가」를 고릅니다. 한글이 아니면 「가」입니다."""
    last = word.strip()[-1:] if word.strip() else ""
    if "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28:
        return "이"
    return "가"


def norm(s: str) -> str:
    return unicodedata.normalize("NFC", s).strip()


CONFIDENCE_HIGH = "높음"
CONFIDENCE_LOW = "낮음"
LOW_NOTE = "동의어로 맞은 것이라 상위·하위 개념일 수 있습니다(예: Tanker와 유조선)."


def _read_files(folder: Path):
    """(파일 이름, 내용) 을 차례로 돌려줍니다. 등록부 모양이 아닌 파일은 건너뜁니다."""
    for p in sorted(folder.glob("*.json")):
        if p.name in EXCLUDE:
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or not isinstance(data.get("terms"), list):
            continue
        yield p, data


def _domain_of(p: Path, data: dict) -> tuple[str, str]:
    d = data.get("domain") or {}
    did = d.get("id") or p.stem
    return did, d.get("name") or did


def list_domains(folder: str | Path) -> list[dict]:
    """등록부 폴더의 분야 목록 [{id, name, file}] 입니다. 화면의 분야 고르기에 씁니다."""
    out = []
    for p, data in _read_files(Path(folder)):
        did, name = _domain_of(p, data)
        out.append({"id": did, "name": name, "file": p.name})
    return out


def load_registry(folder: str | Path) -> tuple[dict, list[str]]:
    """정규화한 표기 -> [항목] 사전과 읽은 파일 목록을 돌려줍니다.

    항목은 (용어 id, 기준 IRI, 분야 id, 맞은 필드 ko|alt, 표제어, 분야 이름) 입니다.
    """
    folder = Path(folder)
    index: dict = defaultdict(list)
    files = []
    for p, data in _read_files(folder):
        files.append(p.name)
        base = data.get("base_uri") or DEFAULT_BASE
        domain, domain_name = _domain_of(p, data)
        for t in data["terms"]:
            if not isinstance(t, dict) or not t.get("id"):
                continue
            if t.get("status") not in (None, "active"):
                continue
            entries = [("ko", t.get("ko"))] + [("alt", a) for a in (t.get("alt") or [])]
            for fld, text in entries:
                if isinstance(text, str) and norm(text):
                    key = norm(text)
                    item = (t["id"], base + t["id"], domain, fld, t.get("ko") or "", domain_name)
                    # 같은 용어가 ko 와 alt 에 모두 걸리면 ko 하나만 둡니다.
                    if any(x[1] == item[1] for x in index[key]):
                        continue
                    index[key].append(item)
    return index, files


def check(inv: Inventory, folder: str | None, report: Report, domains: list[str] | None = None) -> None:
    """domains 를 주면 그 분야 용어만 REG01 후보로 내고, 다른 분야와만 맞는 것은 REG02 로 냅니다."""
    if not folder:
        report.skip(CAT, "용어 등록부 대조", "--registry가 주어지지 않았습니다.")
        return
    if not Path(folder).is_dir():
        report.skip(CAT, "용어 등록부 대조", f"등록부 폴더가 없습니다: {folder}")
        return
    index, files = load_registry(folder)
    if not files:
        report.skip(CAT, "용어 등록부 대조", f"읽을 수 있는 등록부 파일이 없습니다: {folder}")
        return
    known = {d["id"]: d["name"] for d in list_domains(folder)}
    chosen = set(domains or [])
    g = inv.graph
    for e in sorted(inv.entities, key=str):
        ko = [str(l) for l in g.objects(e, RDFS.label) if has_lang(l, "ko")]
        keys = ko if ko else [local_name(str(e))]
        source = "@ko 레이블" if ko else "로컬 이름"
        existing = {str(o) for o in g.objects(e, SKOS.exactMatch)}
        inside, outside = [], []
        for key in keys:
            for item in index.get(norm(key), []):
                if item[1] in existing:
                    continue
                if not chosen or item[2] in chosen:
                    inside.append((key, item))
                else:
                    outside.append((key, item))
        for key, (term_id, iri, domain, fld, term_ko, dname) in inside:
            conf = CONFIDENCE_HIGH if fld == "ko" else CONFIDENCE_LOW
            how = "표제어(ko)" if fld == "ko" else "동의어(alt)"
            msg = (f"skos:exactMatch 후보: {iri} ({source} 「{key}」{josa_iga(key)} 등록부 {domain}({dname}) 분야 용어 "
                   f"「{term_ko}」의 {how}와 같습니다). 일치 신뢰도는 {conf}입니다.")
            if conf == CONFIDENCE_LOW:
                msg += " " + LOW_NOTE
            report.add(Finding(
                CAT, "REG01", "info", str(e), msg,
                f"뜻이 같은지 정의를 읽고 확인한 뒤 <{e}> skos:exactMatch <{iri}>를 더합니다. 표기만 같고 뜻이 다르면 넣지 않습니다.",
                {"term_id": term_id, "term_iri": iri, "domain": domain, "domain_name": dname,
                 "matched_field": fld, "matched_text": key, "confidence": conf},
            ))
        if inside:
            continue  # 고른 분야에 후보가 있으면 다른 분야의 같은 이름은 싣지 않습니다
        for key, (term_id, iri, domain, fld, term_ko, dname) in outside:
            conf = CONFIDENCE_HIGH if fld == "ko" else CONFIDENCE_LOW
            report.add(Finding(
                CAT, "REG02", "info", str(e),
                f"다른 분야에서 같은 이름이 있습니다(뜻이 다를 수 있음): {source} 「{key}」{josa_iga(key)} 고르지 않은 "
                f"{domain}({dname}) 분야 용어 「{term_ko}」({iri})와 표기만 같습니다.",
                "고른 분야의 개념이 맞다면 넣지 않습니다. 그 분야의 개념을 뜻한 것이 맞을 때만 정의를 읽고 skos:exactMatch를 검토합니다.",
                {"term_id": term_id, "term_iri": iri, "domain": domain, "domain_name": dname,
                 "matched_field": fld, "matched_text": key, "confidence": conf},
            ))
    report.stats["registry_files"] = files
    report.stats["registry_keys"] = len(index)
    report.stats["registry_domains"] = [{"id": k, "name": v} for k, v in known.items()]
    if chosen:
        report.stats["registry_selected_domains"] = sorted(chosen)
        unknown = sorted(chosen - set(known))
        if unknown:
            report.stats["registry_unknown_domains"] = unknown
    report.ran.append("registry")
