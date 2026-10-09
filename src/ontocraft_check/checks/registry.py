"""용어 등록부 대조입니다(선택).

등록부 폴더의 *.json(domains.json, candidates.json, manifest.json 제외)을 읽어,
클래스·속성의 @ko 레이블(없으면 로컬 이름)이 등록부 용어의 ko·alt와 정확히 같으면
skos:exactMatch 후보를 제안합니다. 심각도가 없는 정보 항목입니다.

0.2: 후보마다 분야(domain, domain_name)와 일치 신뢰도(ko 일치 높음, alt 일치 낮음)를 붙입니다.
분야를 고르면 고르지 않은 분야와만 맞는 것은 REG02(다른 분야에서 같은 이름이 있음)로 나눕니다.

0.3: 등록부 폴더 대신 "builtin" 을 주면 패키지에 넣은 공개 분야 사본(data/registry)을 씁니다.

0.4: 고른 분야에 관련 분야(related)를 한 단계 더합니다(strict 이면 더하지 않음).
온톨로지의 클래스만 REG01 후보로 냅니다. 객체·데이터 속성이 개념 용어와 표기가 같으면 REG03 으로 따로 냅니다.
등록부 용어에 선택 필드 kind(class·property·relation)가 있으면 같은 종류끼리만 REG01 로 맞춥니다.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path


from rdflib import Literal
from rdflib.namespace import RDFS, SKOS

from ..graph import Inventory, has_lang, local_name, split_name
from ..model import Finding, Report
from ..related import default_related

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


def josa_wagwa(word: str) -> str:
    """앞말의 받침에 맞춰 「과」나 「와」를 고릅니다. 한글이 아니면 「와」입니다."""
    last = word.strip()[-1:] if word.strip() else ""
    if "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28:
        return "과"
    return "와"


def norm(s: str) -> str:
    return unicodedata.normalize("NFC", s).strip()


PROPERTY_KINDS = {"property", "relation"}
REG03_ADVICE = "관계 이름은 동사구로, 개념과의 연결은 range 클래스에서 하기를 권합니다."

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

    항목은 (용어 id, 기준 IRI, 분야 id, 맞은 필드 ko|alt, 표제어, 분야 이름, 종류) 입니다.
    종류는 용어의 선택 필드 kind(class·property·relation)이고 없으면 None 입니다(개념 용어로 봄).
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
            kind = t.get("kind") if t.get("kind") in ({"class"} | PROPERTY_KINDS) else None
            entries = [("ko", t.get("ko"))] + [("alt", a) for a in (t.get("alt") or [])]
            for fld, text in entries:
                if isinstance(text, str) and norm(text):
                    key = norm(text)
                    item = (t["id"], base + t["id"], domain, fld, t.get("ko") or "", domain_name, kind)
                    # 같은 용어가 ko 와 alt 에 모두 걸리면 ko 하나만 둡니다.
                    if any(x[1] == item[1] for x in index[key]):
                        continue
                    index[key].append(item)
    return index, files


def _related_from(path: Path) -> dict[str, list[str]] | None:
    """domains.json 이나 manifest.json 의 분야별 related 입니다. 어느 분야에도 related 가 없으면 None 입니다."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    doms = data.get("domains") if isinstance(data, dict) else None
    if not isinstance(doms, list) or not any(isinstance(d, dict) and "related" in d for d in doms):
        return None
    out: dict[str, set[str]] = {}
    for d in doms:
        if not isinstance(d, dict) or not d.get("id"):
            continue
        for r in d.get("related") or []:
            if isinstance(r, str) and r and r != d["id"]:
                out.setdefault(d["id"], set()).add(r)
                out.setdefault(r, set()).add(d["id"])  # 한쪽에만 적어도 양방향으로 씁니다
    return {k: sorted(v) for k, v in out.items()}


def related_map(folder: str | Path) -> tuple[dict[str, list[str]], str]:
    """(분야 id -> 관련 분야 목록, 어디서 읽었는지) 입니다.

    등록부 폴더의 domains.json, manifest.json 순으로 related 를 찾고, 없으면 기본표(related.py)를 씁니다.
    """
    folder = Path(folder)
    for name in ("domains.json", "manifest.json"):
        got = _related_from(folder / name)
        if got is not None:
            return got, name
    return default_related(), "기본표"


def expand_domains(folder: str | Path | None, chosen: list[str], strict: bool = False) -> list[str]:
    """고른 분야에 더할 관련 분야 id 목록입니다. 등록부에 있는 분야만 더하고, 한 단계만 따라갑니다."""
    if strict or not chosen or not folder or not Path(folder).is_dir():
        return []
    rel, _ = related_map(folder)
    known = {d["id"] for d in list_domains(folder)}
    picked = set(chosen)
    return sorted({r for d in chosen for r in rel.get(d, []) if r in known and r not in picked})


def _kind_ko(inv: Inventory, e) -> str:
    if e in inv.object_props:
        return "객체 속성"
    if e in inv.data_props:
        return "데이터 속성"
    return "속성"


def norm_en(s: str) -> str:
    """영어 대조용 정규화입니다. 대소문자를 무시하고 _·- 와 연속 공백을 한 칸으로 줄입니다."""
    s = unicodedata.normalize("NFC", str(s)).casefold()
    return " ".join(re.sub(r"[_\-]+", " ", s).split())


def load_registry_en(folder: str | Path) -> dict:
    """정규화한 영어 표기(en) -> [항목] 사전입니다. 항목 모양은 load_registry 와 같고 맞은 필드는 en 입니다."""
    index: dict = defaultdict(list)
    for p, data in _read_files(Path(folder)):
        base = data.get("base_uri") or DEFAULT_BASE
        domain, domain_name = _domain_of(p, data)
        for t in data["terms"]:
            if not isinstance(t, dict) or not t.get("id") or t.get("status") not in (None, "active"):
                continue
            en = t.get("en")
            if not isinstance(en, str) or not norm_en(en):
                continue
            kind = t.get("kind") if t.get("kind") in ({"class"} | PROPERTY_KINDS) else None
            item = (t["id"], base + t["id"], domain, "en", t.get("ko") or "", domain_name, kind, en)
            if not any(x[1] == item[1] for x in index[norm_en(en)]):
                index[norm_en(en)].append(item)
    return index


def en_keys(inv: Inventory, e) -> list[tuple[str, str]]:
    """영어 대조에 쓸 (표기, 출처) 목록입니다. @en 레이블, 언어 태그 없는 레이블, 로컬 이름을 띄어 쓴 형태 순입니다."""
    g = inv.graph
    out, seen = [], set()
    labels = [x for x in g.objects(e, RDFS.label) if isinstance(x, Literal)]
    cands = ([(str(x), "@en 레이블") for x in labels if has_lang(x, "en")]
             + [(str(x), "언어 태그 없는 레이블") for x in labels if not x.language]
             + [(split_name(local_name(str(e))), "로컬 이름")])
    for text, source in cands:
        key = norm_en(split_name(text))
        if key and key not in seen:
            seen.add(key)
            out.append((text.strip(), source, key))
    return out


MATCH_MODES = ("ko", "en", "both")
EN_NOTE = ("영어 이름으로 맞춘 후보입니다. 영어 낱말은 뜻이 넓어(Item, Link, Status 같은 이름) 다른 개념과 겹치기 쉬우니 "
           "정의를 꼭 읽습니다.")
NO_KO_REASON = ("대조할 한국어 표기가 없습니다(@ko 레이블 0개). 등록부와 맞는 용어가 없다는 뜻이 아닙니다. "
                "한국어 표제어와는 로컬 이름으로만 맞춰 봤습니다.")


def check(inv: Inventory, folder: str | None, report: Report, domains: list[str] | None = None,
          related: list[str] | None = None, match: str = "both") -> None:
    """domains(와 related)를 주면 그 분야 용어만 후보로 내고, 다른 분야와만 맞는 것은 REG02 로 냅니다.

    related 는 runner 가 관련 분야로 더한 분야 id 입니다. 후보를 고를 때는 domains 와 똑같이 봅니다.
    클래스만 REG01 로 냅니다. 속성이 개념 용어(kind 없음이나 class)와 같으면 REG03 입니다.
    용어에 kind 가 property·relation 이면 속성끼리 REG01 로 맞추고, 클래스와는 맞추지 않습니다.

    0.7: match 는 ko(@ko 레이블, 없으면 로컬 이름), en(영어 이름), both(기본) 입니다. both 는 한국어 대조를 먼저 하고,
    한국어로 아무것도 맞지 않은 요소만 영어로 맞춥니다. 영어 대조는 등록부 용어의 en 과 요소의 @en 레이블,
    언어 태그 없는 레이블, 로컬 이름을 띄어 쓴 형태를 대소문자를 무시하고 맞춥니다. 신뢰도는 늘 낮음이고,
    REG03(속성과 개념 용어)은 내지 않습니다(name·status 같은 일반 영어 낱말이 겹쳐 잡음이 많음).
    """
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
    match = match if match in MATCH_MODES else "both"
    use_ko = match in ("ko", "both")
    use_en = match in ("en", "both")
    en_index = load_registry_en(folder) if use_en else {}
    known = {d["id"]: d["name"] for d in list_domains(folder)}
    picked = set(domains or [])
    chosen = picked | set(related or [])
    g = inv.graph
    kind_skipped = 0
    ko_labelled = sum(1 for e in inv.entities if any(has_lang(l, "ko") for l in g.objects(e, RDFS.label)))
    counts = {"ko": 0, "en": 0}

    def classify(e, is_class, keyed, idx, existing, lang):
        nonlocal kind_skipped
        inside, outside, concept = [], [], []
        seen = set()
        for key, source, nkey in keyed:
            for item in idx.get(nkey, []):
                if item[1] in existing:
                    continue
                if lang == "en" and item[1] in seen:
                    continue
                in_scope = not chosen or item[2] in chosen
                term_is_prop = item[6] in PROPERTY_KINDS
                if is_class and term_is_prop:
                    kind_skipped += 1  # 관계 용어와 클래스는 맞추지 않습니다
                    continue
                if not is_class and not term_is_prop:
                    if in_scope and lang == "ko":
                        concept.append((key, source, item))  # 속성과 개념 용어: REG03
                    continue
                seen.add(item[1])
                (inside if in_scope else outside).append((key, source, item))
        return inside, outside, concept

    for e in sorted(inv.entities, key=str):
        is_class = e in inv.classes
        existing = {str(o) for o in g.objects(e, SKOS.exactMatch)}
        ko_hit = False
        if use_ko:
            ko = [str(l) for l in g.objects(e, RDFS.label) if has_lang(l, "ko")]
            source = "@ko 레이블" if ko else "로컬 이름"
            keyed = [(k, source, norm(k)) for k in (ko if ko else [local_name(str(e))])]
            inside, outside, concept = classify(e, is_class, keyed, index, existing, "ko")
            ko_hit = bool(inside or outside or concept)
            counts["ko"] += len(inside)
            _emit(report, inv, e, inside, outside, concept, chosen, picked, lang="ko")
        if use_en and not ko_hit:
            inside, outside, _ = classify(e, is_class, en_keys(inv, e), en_index, existing, "en")
            counts["en"] += len(inside)
            _emit(report, inv, e, inside, outside, [], chosen, picked, lang="en")
    report.stats["registry_files"] = files
    report.stats["registry_keys"] = len(index)
    report.stats["registry_domains"] = [{"id": k, "name": v} for k, v in known.items()]
    report.stats["registry_match"] = match
    report.stats["registry_ko_labels"] = ko_labelled
    report.stats["registry_reg01_by_lang"] = counts
    if use_ko and ko_labelled == 0:
        report.stats["registry_no_ko"] = True
        report.skip(CAT, "한국어 표기 대조", NO_KO_REASON + (" 영어 이름 대조는 따로 했습니다." if use_en else
                                                          " 영어 이름 대조를 하려면 --registry-match en이나 both를 줍니다."))
    if kind_skipped:
        report.stats["registry_kind_skipped"] = kind_skipped
    if picked:
        report.stats["registry_selected_domains"] = sorted(picked)
        unknown = sorted(picked - set(known))
        if unknown:
            report.stats["registry_unknown_domains"] = unknown
    if related:
        report.stats["registry_related_domains"] = sorted(related)
    report.ran.append("registry")


def _emit(report: Report, inv: Inventory, e, inside, outside, concept, chosen, picked, lang: str) -> None:
    by_en = lang == "en"
    for key, source, item in inside:
        term_id, iri, domain, fld, term_ko, dname, tkind = item[:7]
        if by_en:
            conf = CONFIDENCE_LOW
            msg = (f"skos:exactMatch 후보(영어 이름으로 맞춤): {iri} ({source} 「{key}」{josa_iga(key)} 등록부 {domain}({dname}) "
                   f"분야 용어 「{term_ko}」의 영어 표기(en) 「{item[7]}」와 대소문자를 빼고 같습니다). 일치 신뢰도는 {conf}입니다. "
                   + EN_NOTE)
        else:
            conf = CONFIDENCE_HIGH if fld == "ko" else CONFIDENCE_LOW
            how = "표제어(ko)" if fld == "ko" else "동의어(alt)"
            msg = (f"skos:exactMatch 후보: {iri} ({source} 「{key}」{josa_iga(key)} 등록부 {domain}({dname}) 분야 용어 "
                   f"「{term_ko}」의 {how}와 같습니다). 일치 신뢰도는 {conf}입니다.")
            if conf == CONFIDENCE_LOW:
                msg += " " + LOW_NOTE
        detail = {"term_id": term_id, "term_iri": iri, "domain": domain, "domain_name": dname,
                  "matched_field": fld, "matched_text": key, "confidence": conf}
        if by_en:
            detail.update({"match_lang": "en", "match_note": "영어 이름으로 맞춤", "matched_source": source,
                           "term_en": item[7]})
        if tkind:
            detail["term_kind"] = tkind
        if domain in chosen - picked:
            detail["via_related"] = True
        report.add(Finding(
            CAT, "REG01", "info", str(e), msg,
            f"뜻이 같은지 정의를 읽고 확인한 뒤 <{e}> skos:exactMatch <{iri}>를 더합니다. 표기만 같고 뜻이 다르면 넣지 않습니다.",
            detail,
        ))
    for key, source, item in concept:
        term_id, iri, domain, fld, term_ko, dname, tkind = item[:7]
        what = _kind_ko(inv, e)
        report.add(Finding(
            CAT, "REG03", "info", str(e),
            f"속성 이름이 개념 용어와 같습니다: {what}의 {source} 「{key}」{josa_iga(key)} 등록부 {domain}({dname}) 분야 "
            f"개념 용어 「{term_ko}」{josa_wagwa(term_ko)} 표기가 같습니다({iri}). {REG03_ADVICE}",
            f"속성 이름을 「~에 입항함」, 「~의 지휘를 받음」처럼 동사구로 바꿉니다. 「{term_ko}」 개념과의 skos:exactMatch는 "
            "이 속성의 rdfs:range 클래스에 둡니다. 속성 자체에는 넣지 않습니다.",
            {"term_id": term_id, "term_iri": iri, "domain": domain, "domain_name": dname,
             "matched_field": fld, "matched_text": key, "entity_kind": what,
             **({"term_kind": tkind} if tkind else {})},
        ))
    if inside:
        return  # 고른 분야에 후보가 있으면 다른 분야의 같은 이름은 싣지 않습니다
    for key, source, item in outside:
        term_id, iri, domain, fld, term_ko, dname, tkind = item[:7]
        conf = CONFIDENCE_LOW if by_en else (CONFIDENCE_HIGH if fld == "ko" else CONFIDENCE_LOW)
        tail = f"영어 표기(en) 「{item[7]}」" if by_en else f"용어 「{term_ko}」"
        detail = {"term_id": term_id, "term_iri": iri, "domain": domain, "domain_name": dname,
                  "matched_field": fld, "matched_text": key, "confidence": conf}
        if by_en:
            detail.update({"match_lang": "en", "match_note": "영어 이름으로 맞춤", "matched_source": source,
                           "term_en": item[7]})
        report.add(Finding(
            CAT, "REG02", "info", str(e),
            f"다른 분야에서 같은 이름이 있습니다(뜻이 다를 수 있음{', 영어 이름으로 맞춤' if by_en else ''}): {source} "
            f"「{key}」{josa_iga(key)} 고르지 않은 {domain}({dname}) 분야 「{term_ko}」의 {tail}{josa_wagwa(tail)} "
            f"표기만 같습니다({iri})." if by_en else
            f"다른 분야에서 같은 이름이 있습니다(뜻이 다를 수 있음): {source} 「{key}」{josa_iga(key)} 고르지 않은 "
            f"{domain}({dname}) 분야 용어 「{term_ko}」{josa_wagwa(term_ko)} 표기만 같습니다({iri}).",
            "고른 분야의 개념이 맞다면 넣지 않습니다. 그 분야의 개념을 뜻한 것이 맞을 때만 정의를 읽고 skos:exactMatch를 검토합니다.",
            detail,
        ))
