"""CQ 커버리지입니다(0.6, 선택).

역량 질문(CQ, Competency Question) 목록의 질의(Cypher 또는 SPARQL)가 온톨로지의 어느 클래스, 객체 속성,
데이터 속성에 닿는지 셉니다. 심각도가 없는 정보 검사입니다. 결과는 report.cq(사전)와 정보 항목 CQ01 로 냅니다.

입력 JSON 은 최상위 items[](또는 목록 자체)에 CQ 를 둡니다. CQ 마다 id, q(질문), 질의 필드를 읽습니다.
질의 필드는 query_field 를 주면 그 필드, 주지 않으면 cypher, 없으면 sparql 입니다.

이름 맞추기 규칙
1. Cypher 관계 타입(ARRIVED_AT)은 객체 속성의 rdfs:label@en 과 맞춥니다. @en 레이블로 맞는 속성이 없을 때만
   IRI 로컬 이름을 SCREAMING_SNAKE 로 바꾼 이름(arrivedAt -> ARRIVED_AT)과 맞춥니다.
2. Cypher 노드 라벨은 클래스의 IRI 로컬 이름이나 rdfs:label@en 과 맞춥니다(대소문자 구별).
3. 속성 접근(v.draft, {unlocode: ...})은 그 변수의 라벨이 맞은 클래스에서 시작해 rdfs:subClassOf 를 한 단계씩
   올라가며, 그 클래스가 주인인 데이터 속성 가운데 이름이 같은 것을 찾습니다. 가장 가까운 단계에서 찾은 것만 셉니다.
   데이터 속성의 주인은 rdfs:domain(owl:unionOf 의 구성원 포함)과 로컬 이름 「클래스_속성」의 앞쪽 클래스입니다.
   데이터 속성의 이름은 rdfs:label@en, 로컬 이름, 「클래스_속성」의 뒤쪽입니다. domain 이 없는 데이터 속성은
   어느 클래스에서도 찾지 못했을 때 마지막으로 맞춥니다.
   변수에 라벨이 없으면((x), YIELD 로 받은 변수, 목록 변수) 그 이름을 가진 데이터 속성 모두를 「모호」로 셉니다.
   모호한 접근은 「닿음」에 넣지 않고 따로 셉니다. 그 이름의 데이터 속성이 온톨로지 전체에 하나뿐이면 「후보 1개」로
   표시하고 그 속성을 unique_candidate 에 적습니다. 이것도 「닿음」에 넣지 않고 사람이 판단하도록 둡니다.
5. labels(n) 를 리터럴 목록과 비교하는 꼴(any(l IN labels(n) WHERE l IN ['A','B']), [l IN labels(n) WHERE
   l IN [...]], 'A' IN labels(n), l = 'A')은 목록 안의 이름을 변수 n 의 라벨로 읽습니다. NOT 이나 none() 안의
   비교는 읽지 않습니다. 이렇게 읽은 라벨은 CQ 별 표의 labels_from_list 에 적습니다.
4. 관계 변수의 속성(r.since)은 OWL 에 데이터 속성으로 없으므로 세지 않고 CQ 별 표에만 적습니다.

SPARQL 은 rdflib 으로 파싱해 질의 대수에 쓰인 IRI 를 모읍니다. 온톨로지의 접두어를 미리 넣어 두므로 PREFIX 를
생략한 질의도 읽습니다.
"""

from __future__ import annotations

import fnmatch
import json
import re
from collections import defaultdict
from pathlib import Path

from rdflib import BNode, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from ..graph import Inventory, LoadError, has_lang, local_name, rdf_list, short
from ..model import Finding, Report

CAT = "cq"

NOT_DELETE_NOTE = ("CQ가 닿지 않음은 지워도 된다는 뜻이 아닙니다. 데이터 적재, 화면, 외부 연계, 표준 대응처럼 "
                   "CQ 밖의 근거가 있을 수 있습니다. 지우기 전에 그런 근거가 없는지 사람이 확인합니다.")
NOT_FIT_NOTE = "CQ를 모두 덮어도 질문이 업무에 맞는지는 판정하지 못합니다. 질문 목록이 업무를 대표하는지는 사람이 봅니다."
CANNOT_SAY_CQ = [
    NOT_DELETE_NOTE,
    NOT_FIT_NOTE,
    "Cypher는 가벼운 정규식 파서로 읽습니다. labels(n)를 문자열 목록과 비교하는 꼴은 목록 안의 이름을 n의 라벨로 읽지만, "
    "NOT이나 none() 안의 비교, 변수에 담은 목록, 동적 라벨은 보지 않습니다. "
    "라벨이 없는 변수의 속성 접근은 「모호」로 따로 세고 「닿음」에 넣지 않습니다. 후보가 하나뿐인 모호 접근도 "
    "「닿음」에 넣지 않습니다. 그 속성을 뜻했는지는 사람이 판단합니다.",
]

KIND_KO = {"class": "클래스", "object_property": "관계(객체 속성)", "data_property": "데이터 속성"}
KINDS = ("class", "object_property", "data_property")

# ---------------------------------------------------------------- 입력


def split_list(value) -> list[str]:
    if not value:
        return []
    items = value.split(",") if isinstance(value, str) else list(value)
    out = []
    for x in items:
        x = str(x).strip()
        if x and x not in out:
            out.append(x)
    return out


CQ_FORMATS = ("auto", "default", "ontoflow")
PROFILES = ("default", "ontoflow")
ONTOFLOW_KINDS = ("label-exists", "cypher-nonzero", "cypher-expect", "project-object-count",
                  "project-link-nonzero", "project-property-filled")
DEFAULT_ONTOFLOW_BASE = "https://ontocraft.com/ontology/{project}/"


def _read_doc(p: Path):
    if not p.is_file():
        raise LoadError(f"CQ 파일이 없습니다: {p}")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LoadError(f"CQ 파일을 JSON 으로 읽지 못했습니다(마크다운 표는 읽지 않습니다): {p}: {exc}") from exc


def is_ontoflow_doc(doc) -> bool:
    """ONTOFLOW CQ 카탈로그 모양인지 봅니다. 최상위가 사전이고 items[] 가운데 check 사전이 하나라도 있으면 참입니다."""
    items = doc.get("items") if isinstance(doc, dict) else None
    return isinstance(items, list) and any(isinstance(it, dict) and isinstance(it.get("check"), dict) for it in items)


def _ontoflow_item(it: dict, cid: str) -> dict:
    """ONTOFLOW 항목 {id, group?, question, note?, check?} 하나를 공통 모양으로 바꿉니다."""
    chk = it.get("check")
    row = {"id": cid, "q": str(it.get("question") or it.get("q") or ""), "query": "", "lang": "manual",
           "field": "check.cypher", "kind": None, "structured": None, "project": None,
           "group": it.get("group")}
    if not isinstance(chk, dict):
        return row  # check 가 없으면 수동 판정입니다
    kind = str(chk.get("kind") or "")
    row["kind"] = kind
    row["project"] = chk.get("projectId") if isinstance(chk.get("projectId"), str) else None
    if kind in ("cypher-nonzero", "cypher-expect"):
        row["query"] = chk.get("cypher") if isinstance(chk.get("cypher"), str) else ""
        row["lang"] = "cypher"
    elif kind == "label-exists":
        row.update(lang="structured", structured={"classes": [str(chk.get("label") or "")]})
    elif kind == "project-object-count":
        row.update(lang="structured", structured={"classes": [str(chk.get("objectType") or "")]})
    elif kind == "project-property-filled":
        ot = str(chk.get("objectType") or "")
        row.update(lang="structured", structured={"classes": [ot], "props": [(ot, str(chk.get("property") or ""))]})
    elif kind == "project-link-nonzero":
        row.update(lang="structured", structured={"rels": [str(chk.get("linkType") or "")]})
    else:
        row["lang"] = "unknown"
    return row


def load_cq_doc(path: str | Path, query_field: str | None = None,
                cq_format: str | None = None) -> tuple[list[dict], str, dict]:
    """CQ JSON 을 읽어 (CQ 목록, 질의 필드 설명, 카탈로그 정보)를 돌려줍니다.

    cq_format 은 auto(기본, items[].check 가 있으면 ontoflow), default, ontoflow 입니다.
    ontoflow 형식은 최상위 {name, description, domain?, source?, items[]} 이고 항목은 {id, group?, question, note?, check?}
    입니다. 질의는 check.cypher, 질문은 question 입니다. check 가 없는 항목은 수동 판정으로 따로 셉니다.
    """
    p = Path(path)
    doc = _read_doc(p)
    fmt = (cq_format or "auto").strip().lower()
    if fmt not in CQ_FORMATS:
        raise LoadError(f"--cq-format 은 {', '.join(CQ_FORMATS)} 가운데 하나입니다: {cq_format}")
    if fmt == "auto":
        fmt = "ontoflow" if is_ontoflow_doc(doc) else "default"
    items = doc.get("items") if isinstance(doc, dict) else doc
    if not isinstance(items, list):
        raise LoadError(f"CQ 파일에 items 목록이 없습니다: {p}")
    meta = {"format": fmt}
    if isinstance(doc, dict):
        for k in ("name", "description", "domain", "source"):
            if isinstance(doc.get(k), str) and doc[k]:
                meta[k] = doc[k]
    out = []
    for n, it in enumerate(items, start=1):
        if not isinstance(it, dict):
            continue
        cid = str(it.get("id") or f"#{n}")
        if fmt == "ontoflow":
            out.append(_ontoflow_item(it, cid))
            continue
        if query_field:
            field = query_field
        elif it.get("cypher"):
            field = "cypher"
        elif it.get("sparql"):
            field = "sparql"
        else:
            field = "cypher"
        query = it.get(field)
        query = query if isinstance(query, str) else ""
        lang = detect_lang(field, query)
        out.append({"id": cid, "q": str(it.get("q") or it.get("question") or ""), "query": query,
                    "lang": lang, "field": field})
    if fmt == "ontoflow":
        return out, "check.cypher(ONTOFLOW 형식)", meta
    return out, query_field or "cypher, 없으면 sparql", meta


def load_cq(path: str | Path, query_field: str | None = None) -> tuple[list[dict], str]:
    """CQ JSON 을 읽어 [{id, q, query, lang, field}] 와 읽은 질의 필드 설명을 돌려줍니다(0.6 호환)."""
    items, field_text, _ = load_cq_doc(path, query_field, "default")
    return items, field_text


_SPARQL_HEAD = re.compile(r"^\s*(?:#[^\n]*\n\s*)*(PREFIX|BASE|SELECT|ASK|CONSTRUCT|DESCRIBE)\b", re.I)


def detect_lang(field: str, query: str) -> str:
    f = field.lower()
    if "sparql" in f:
        return "sparql"
    if "cypher" in f:
        return "cypher"
    return "sparql" if _SPARQL_HEAD.match(query or "") else "cypher"


# ---------------------------------------------------------------- Cypher 파서

NAME = r"(?:`[^`]+`|[A-Za-z_][\w]*)"
_NODE = re.compile(
    r"(?<![\w`])\(\s*(" + NAME + r")?\s*((?::\s*" + NAME + r"\s*(?:[|&]\s*:?\s*" + NAME + r"\s*)*)*)\s*(\{[^{}]*\})?\s*\)")
_REL = re.compile(
    r"\[\s*(" + NAME + r")?\s*:\s*(" + NAME + r"(?:\s*\|\s*:?\s*" + NAME + r")*)\s*(\*\s*\d*\s*(?:\.\.\s*\d*)?)?\s*(\{[^{}]*\})?\s*\]")
_LABEL_SPLIT = re.compile(r"\s*[:|&]\s*:?\s*")
_MAP_KEY = re.compile(r"(?:^|[{,])\s*(" + NAME + r")\s*:")
_ACCESS = re.compile(r"(?<![\w$.`])(" + NAME + r")\.(" + NAME + r")(?![\w.`]|\s*\()")
_LABEL_PRED = re.compile(r"(?<![\w$.`])(" + NAME + r")\s*:\s*(" + NAME + r")")


class CypherError(ValueError):
    pass


def _unquote(name: str) -> str:
    return name[1:-1] if name.startswith("`") and name.endswith("`") else name


LIT_MARK = "\x01"


def strip_cypher(text: str, keep_strings: bool = False, table: list | None = None) -> str:
    """문자열 리터럴의 내용과 주석을 지웁니다. 따옴표는 남겨 '' 로 둡니다. keep_strings 면 주석만 지웁니다.

    table(목록)을 주면 문자열 내용을 지우는 대신 table 에 넣고 그 자리에 '\x01<번호>' 를 둡니다(0.7, ontoflow 프로필).
    괄호 구조는 '' 로 지운 것과 같아서 패턴을 찾는 정규식의 결과가 바뀌지 않습니다.
    """
    out = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch in ("'", '"'):
            q = ch
            start = i
            i += 1
            while i < n and text[i] != q:
                i += 2 if text[i] == "\\" else 1
            if i >= n:
                raise CypherError("닫히지 않은 문자열 리터럴이 있습니다")
            if table is not None:
                table.append(_unescape(text[start + 1:i]))
                out.append(f"'{LIT_MARK}{len(table) - 1}'")
            else:
                out.append(text[start:i + 1] if keep_strings else q + q)
            i += 1
        elif ch == "`":
            j = text.find("`", i + 1)
            if j < 0:
                raise CypherError("닫히지 않은 역따옴표가 있습니다")
            out.append(text[i:j + 1])
            i = j + 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            if j < 0:
                raise CypherError("닫히지 않은 주석이 있습니다")
            i = j + 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _unescape(text: str) -> str:
    return re.sub(r"\\(.)", r"\1", text)


def _check_balance(text: str) -> None:
    pairs = {")": "(", "]": "[", "}": "{"}
    stack = []
    for ch in text:
        if ch in "([{":
            stack.append(ch)
        elif ch in pairs:
            if not stack or stack.pop() != pairs[ch]:
                raise CypherError(f"괄호가 맞지 않습니다({ch})")
    if stack:
        raise CypherError(f"괄호가 닫히지 않았습니다({stack[-1]})")


def _map_keys(body: str | None) -> list[str]:
    if not body:
        return []
    inner = body.strip()[1:-1]
    return [_unquote(m.group(1)) for m in _MAP_KEY.finditer(inner)]


# ontoflow 프로필에서 OWL 요소가 아닌 운영 이름입니다. 노드 라벨 Object 와 속성 projectId·objectType 은 세지 않습니다.
ONTOFLOW_INFRA_LABELS = ("Object",)
ONTOFLOW_INFRA_KEYS = ("projectId", "objectType")
_LIT = "'" + LIT_MARK + r"(\d+)'"
_MAP_LIT = re.compile(r"(?:^|[{,])\s*(" + NAME + r")\s*:\s*" + _LIT)
_WHERE_TYPE = re.compile(r"(\bNOT\s+)?(?<![\w$.`])(" + NAME + r")\.objectType\s*(?:=\s*" + _LIT + r"|IN\s*\[([^\]]*)\])", re.I)
_TYPE_FN = re.compile(r"(\bNOT\s+)?\btype\s*\(\s*(" + NAME + r")\s*\)\s*(?:=\s*" + _LIT + r"|IN\s*\[([^\]]*)\])", re.I)


def _lits(table: list, single: str | None, listed: str | None) -> list[str]:
    if single is not None:
        return [table[int(single)]]
    return [table[int(n)] for n in re.findall(LIT_MARK + r"(\d+)", listed or "")]


def parse_cypher(text: str, profile: str = "default") -> dict:
    """Cypher 에서 노드 라벨, 관계 타입, 변수별 속성 접근을 뽑습니다.

    돌려주는 사전: labels(쓰인 라벨), rel_types(쓰인 관계 타입), node_vars{변수: 라벨 집합},
    rel_vars(관계 변수 집합), accesses[(변수 또는 None, 라벨 집합, 속성 이름)], rel_props[(변수, 속성)],
    labels_from_list{변수: labels() 목록에서 읽은 라벨}.
    파싱하지 못하면 CypherError 를 냅니다.
    """
    if not text or not text.strip():
        raise CypherError("질의가 비었습니다")
    ontoflow = profile == "ontoflow"
    table: list = []
    body = strip_cypher(text, table=table) if ontoflow else strip_cypher(text)
    _check_balance(body)
    node_lits: dict[str, dict] = defaultdict(lambda: defaultdict(list))  # ontoflow: 변수 -> 키 -> 문자열 값
    node_vars: dict[str, set] = defaultdict(set)
    rel_vars: set = set()
    labels: list[str] = []
    rel_types: list[str] = []
    accesses: list[tuple] = []
    rel_props: list[tuple] = []
    anon = 0
    found = False

    for m in _REL.finditer(body):
        found = True
        var = _unquote(m.group(1)) if m.group(1) else None
        types = [_unquote(t) for t in _LABEL_SPLIT.split(m.group(2).strip()) if t]
        rel_types += [t for t in types if t not in rel_types]
        if var:
            rel_vars.add(var)
        for k in _map_keys(m.group(4)):
            rel_props.append((var, k))
    for m in _NODE.finditer(body):
        var = _unquote(m.group(1)) if m.group(1) else None
        labs = [_unquote(t) for t in _LABEL_SPLIT.split(m.group(2).strip()) if t] if m.group(2) else []
        if labs or m.group(3) or _is_pattern_context(body, m):
            found = True
        if var is None:
            anon += 1
            var = f"(익명{anon})"
        node_vars[var].update(labs)
        labels += [x for x in labs if x not in labels]
        for k in _map_keys(m.group(3)):
            accesses.append((var, k))
        if ontoflow and m.group(3):
            for km in _MAP_LIT.finditer(m.group(3).strip()[1:-1]):
                node_lits[var][_unquote(km.group(1))].append(table[int(km.group(2))])
    # WHERE v:Label 같은 라벨 조건입니다. 알려진 노드 변수에만 씁니다.
    masked = _NODE.sub(" ", _REL.sub(" ", body))
    masked = re.sub(r"\{[^{}]*\}", " ", masked)
    for m in _LABEL_PRED.finditer(masked):
        var, lab = _unquote(m.group(1)), _unquote(m.group(2))
        if var in node_vars and not var.startswith("("):
            node_vars[var].add(lab)
            if lab not in labels:
                labels.append(lab)
    from_list: dict[str, list[str]] = {}
    for var, labs in labels_list_reads(text).items():
        if var in node_vars and not var.startswith("("):
            new = [x for x in labs if x not in node_vars[var]]
            if new:
                from_list[var] = new
                node_vars[var].update(new)
                labels += [x for x in new if x not in labels]
    for m in _ACCESS.finditer(body):
        var, prop = _unquote(m.group(1)), _unquote(m.group(2))
        if var in rel_vars and var not in node_vars:
            rel_props.append((var, prop))
        else:
            accesses.append((var, prop))
    infra_labels: list[str] = []
    object_types: dict[str, list[str]] = {}
    projects: list[str] = []
    if ontoflow:
        # objectType 값(노드 맵과 WHERE v.objectType = / IN [...])을 그 변수의 라벨로 읽습니다. NOT 이 붙은 비교는 읽지 않습니다.
        for var, lits in node_lits.items():
            for v in lits.get("objectType", []):
                object_types.setdefault(var, [])
                if v not in object_types[var]:
                    object_types[var].append(v)
            for v in lits.get("projectId", []):
                if v not in projects:
                    projects.append(v)
        for m in _WHERE_TYPE.finditer(body):
            var = _unquote(m.group(2))
            if m.group(1) or var not in node_vars:
                continue
            for v in _lits(table, m.group(3), m.group(4)):
                object_types.setdefault(var, [])
                if v not in object_types[var]:
                    object_types[var].append(v)
        for m in _TYPE_FN.finditer(body):
            if m.group(1):
                continue
            found = True
            for v in _lits(table, m.group(3), m.group(4)):
                if v not in rel_types:
                    rel_types.append(v)
        for var, types in object_types.items():
            node_vars[var].update(types)
            labels += [x for x in types if x not in labels]
        for var in node_vars:
            for lab in ONTOFLOW_INFRA_LABELS:
                if lab in node_vars[var]:
                    node_vars[var].discard(lab)
                    if lab not in infra_labels:
                        infra_labels.append(lab)
        labels = [x for x in labels if x not in ONTOFLOW_INFRA_LABELS]
        accesses = [(v, k) for v, k in accesses if k not in ONTOFLOW_INFRA_KEYS]
    if not found and re.search(r"\bMATCH\s*\(", body, re.I):
        found = True  # MATCH (n) 처럼 라벨 없는 노드 하나만 있는 질의
    if not found:
        raise CypherError("MATCH 패턴((v:Label), [:TYPE])을 찾지 못했습니다")
    resolved = []
    seen = set()
    for var, prop in accesses:
        labs = frozenset(node_vars.get(var, set()))
        key = (var, labs, prop)
        if key not in seen:
            seen.add(key)
            resolved.append((var if var in node_vars else None, labs, prop))
    return {"labels": labels, "rel_types": rel_types, "node_vars": {k: sorted(v) for k, v in node_vars.items()},
            "rel_vars": sorted(rel_vars), "accesses": resolved, "rel_props": sorted(set(rel_props), key=str),
            "labels_from_list": from_list, "infra_labels": infra_labels,
            "object_types": {k: v for k, v in object_types.items()}, "projects": projects}


_LABELS_ITER = re.compile(r"(?<![\w$.`])(" + NAME + r")\s+IN\s+labels\s*\(\s*(" + NAME + r")\s*\)\s*WHERE\b", re.I)
_LIT_IN_LABELS = re.compile(r"(\bNOT\s+)?('(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\")\s+IN\s+labels\s*\(\s*(" + NAME + r")\s*\)", re.I)
_STR_LIT = re.compile(r"'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\"")
_NEGATED_HEAD = re.compile(r"(?:\bNOT\s+(?:any|all|single)\s*\(|\bnone\s*\()\s*$", re.I)


def _str_items(text: str) -> list[str]:
    return [m.group(1) if m.group(1) is not None else m.group(2) for m in _STR_LIT.finditer(text)]


def _group_end(text: str, start: int) -> int:
    """start 부터 읽어 둘러싼 괄호가 닫히는 자리(닫는 괄호의 위치)를 돌려줍니다."""
    depth = 0
    i, n = start, len(text)
    while i < n:
        ch = text[i]
        if ch in ("'", '"'):
            j = i + 1
            while j < n and text[j] != ch:
                j += 2 if text[j] == "\\" else 1
            i = j + 1
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                return i
            depth -= 1
        i += 1
    return n


def labels_list_reads(text: str) -> dict[str, list[str]]:
    """labels(n) 를 리터럴 목록과 비교하는 꼴에서 {변수: [라벨]} 을 읽습니다. 부정 비교는 읽지 않습니다."""
    body = strip_cypher(text, keep_strings=True)
    out: dict[str, list[str]] = defaultdict(list)

    def add(var, labs):
        for lab in labs:
            if lab and lab not in out[var]:
                out[var].append(lab)

    for m in _LABELS_ITER.finditer(body):
        it, var = _unquote(m.group(1)), _unquote(m.group(2))
        if _NEGATED_HEAD.search(body[:m.start()]):
            continue
        seg = body[m.end():_group_end(body, m.end())]
        name = re.escape(it)
        for c in re.finditer(r"(\bNOT\s+)?(?<![\w$.`])" + name + r"\s+IN\s*\[", seg, re.I):
            if c.group(1):
                continue
            end = _group_end(seg, c.end())
            add(var, _str_items(seg[c.end():end]))
        for c in re.finditer(r"(\bNOT\s+)?(?<![\w$.`])" + name + r"\s*=\s*('(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\")", seg, re.I):
            if not c.group(1):
                add(var, _str_items(c.group(2)))
    for m in _LIT_IN_LABELS.finditer(body):
        if not m.group(1) and not _NEGATED_HEAD.search(body[:m.start()]):
            add(_unquote(m.group(3)), _str_items(m.group(2)))
    return dict(out)


def _is_pattern_context(body: str, m) -> bool:
    """라벨 없는 (x) 가 관계 패턴에 붙어 있으면 패턴으로 봅니다."""
    before = body[:m.start()].rstrip()
    after = body[m.end():].lstrip()
    return before.endswith(("-", ">", "<")) or after.startswith(("-", "<", ">"))


# ---------------------------------------------------------------- 온톨로지 색인


def screaming_snake(name: str) -> str:
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "_", name)
    return re.sub(r"[^0-9A-Za-z]+", "_", s).strip("_").upper()


def _en_labels(g, node) -> list[str]:
    return [str(x).strip() for x in g.objects(node, RDFS.label) if has_lang(x, "en")]


def _classes_in(g, node, classes) -> set:
    if isinstance(node, URIRef):
        return {node} if node in classes else set()
    out = set()
    for key in (OWL.unionOf, OWL.intersectionOf):
        for head in g.objects(node, key):
            for x in rdf_list(g, head):
                out |= _classes_in(g, x, classes)
    return out


class Index:
    """이름 맞추기에 쓰는 온톨로지 색인입니다."""

    def __init__(self, inv: Inventory):
        g = inv.graph
        self.inv = inv
        self.g = g
        self.class_by_name: dict[str, set] = defaultdict(set)
        for c in inv.classes:
            self.class_by_name[local_name(str(c))].add(c)
            for lab in _en_labels(g, c):
                self.class_by_name[lab].add(c)
        self.rel_by_label: dict[str, set] = defaultdict(set)
        self.rel_by_snake: dict[str, set] = defaultdict(set)
        for p in inv.object_props:
            for lab in _en_labels(g, p):
                self.rel_by_label[lab].add(p)
            self.rel_by_snake[screaming_snake(local_name(str(p)))].add(p)
        class_local = defaultdict(set)
        for c in inv.classes:
            class_local[local_name(str(c))].add(c)
        self.dp_owners: dict = {}
        self.dp_by_name: dict[str, set] = defaultdict(set)
        self.dp_method: dict = {}
        for p in inv.data_props:
            ln = local_name(str(p))
            owners = set()
            how = []
            for d in g.objects(p, RDFS.domain):
                found = _classes_in(g, d, inv.classes)
                if found:
                    owners |= found
                    how.append("domain")
            names = {ln}
            if "_" in ln:
                head, tail = ln.split("_", 1)
                if head in class_local and tail:
                    owners |= class_local[head]
                    names.add(tail)
                    how.append("클래스_속성")
            for lab in _en_labels(g, p):
                names.add(lab)
            self.dp_owners[p] = owners
            self.dp_method[p] = how
            for nm in names:
                self.dp_by_name[nm].add(p)
        self.parents: dict = defaultdict(set)
        self.children: dict = defaultdict(set)
        for c in inv.classes:
            for sup in g.objects(c, RDFS.subClassOf):
                if isinstance(sup, URIRef) and sup in inv.classes and sup != c:
                    self.parents[c].add(sup)
                    self.children[sup].add(c)

    def classes_for(self, label: str) -> set:
        return set(self.class_by_name.get(label, ()))

    def rels_for(self, rtype: str) -> tuple[set, str]:
        if rtype in self.rel_by_label:
            return set(self.rel_by_label[rtype]), "label"
        if rtype in self.rel_by_snake:
            return set(self.rel_by_snake[rtype]), "snake"
        return set(), ""

    def _levels(self, start: set, nxt) -> list[set]:
        levels, seen, cur = [], set(start), set(start)
        while cur:
            levels.append(cur)
            new = set()
            for c in cur:
                new |= nxt[c]
            cur = new - seen
            seen |= cur
        return levels

    def resolve_prop(self, classes: set, name: str) -> tuple[set, str]:
        """(찾은 데이터 속성, 방법)을 돌려줍니다. 방법은 self·ancestor·global·subclass·"" 입니다."""
        cands = self.dp_by_name.get(name, set())
        if not cands:
            return set(), ""
        for depth, level in enumerate(self._levels(classes, self.parents)):
            hit = {p for p in cands if self.dp_owners[p] & level}
            if hit:
                return hit, "self" if depth == 0 else "ancestor"
        glob = {p for p in cands if not self.dp_owners[p]}
        if glob:
            return glob, "global"
        down = set()
        for level in self._levels(classes, self.children)[1:]:
            down |= {p for p in cands if self.dp_owners[p] & level}
        return down, "subclass" if down else ""


def iri_segment(s: str) -> str:
    """ONTOFLOW 내보내기의 IRI 한 마디 규칙입니다. 공백과 <>"{}|^`\\/#?% 만 퍼센트 인코딩하고 한글은 그대로 둡니다."""
    return re.sub(r'[\s<>"{}|^`\\/#?%]', lambda m: "".join(f"%{b:02X}" for b in m.group(0).encode("utf-8")), s)


class DefaultResolver:
    """0.6 의 이름 맞추기(라벨·영어 레이블·SCREAMING_SNAKE·rdfs:domain)입니다."""

    profile = "default"

    def __init__(self, idx: Index):
        self.idx = idx

    def class_for(self, name: str, project: str | None = None) -> tuple[set, str]:
        cs = self.idx.classes_for(name)
        return cs, "name" if cs else ""

    def rel_for(self, rtype: str, project: str | None = None) -> tuple[set, str]:
        return self.idx.rels_for(rtype)

    def prop_for(self, classes: set, name: str, project: str | None = None) -> tuple[set, str]:
        return self.idx.resolve_prop(classes, name)


class OntoflowResolver:
    """ONTOFLOW 내보내기 IRI 규칙으로 맞춥니다(0.7).

    objectType X -> <기준>X 클래스, 관계 타입 T -> <기준>rel/T 객체 속성, 클래스 C 의 속성 p -> <C 의 IRI>/p 데이터 속성.
    속성은 C 에서 rdfs:subClassOf 를 따라 올라가며 찾습니다(물려받은 속성은 부모 클래스 IRI 아래에 있습니다).
    기준 IRI 는 틀의 {project} 를 질의의 projectId(또는 check.projectId)로 채웁니다. projectId 가 없으면 온톨로지 IRI 입니다.
    기준 아래에 없으면 다른 프로젝트 기준(틀의 {project} 자리만 다른 IRI)에서 같은 이름을 찾습니다(다른 프로젝트가 선언한
    타입을 참조하는 경우).
    """

    profile = "ontoflow"

    def __init__(self, idx: Index, template: str | None):
        self.idx = idx
        inv = idx.inv
        onto = next((str(o) for o in inv.ontologies if isinstance(o, URIRef)), "")
        self.ontology_base = onto if onto.endswith(("/", "#")) else (onto + "/" if onto else "")
        self.template = template or ""
        self.bases: dict[str, str] = {}
        if "{project}" in self.template:
            head, tail = self.template.split("{project}", 1)
            self.any_base = re.compile(re.escape(head) + r"[^/#]+" + re.escape(tail))
        else:
            self.any_base = None

    def base_for(self, project: str | None) -> str:
        if self.template and "{project}" in self.template:
            base = self.template.replace("{project}", iri_segment(project)) if project else self.ontology_base
        else:
            base = self.template or self.ontology_base
        self.bases[project or "(projectId 없음)"] = base
        return base

    def _other_project(self, pool: set, tail: str) -> set:
        if not self.any_base:
            return set()
        out = set()
        for x in pool:
            sx = str(x)
            if sx.endswith(tail):
                m = self.any_base.match(sx)
                if m and m.end() == len(sx) - len(tail):
                    out.add(x)
        return out

    def class_for(self, name: str, project: str | None = None) -> tuple[set, str]:
        if not name:
            return set(), ""
        seg = iri_segment(name)
        c = URIRef(self.base_for(project) + seg)
        if c in self.idx.inv.classes:
            return {c}, "iri"
        other = self._other_project(self.idx.inv.classes, seg)
        return (other, "other_project") if other else (set(), "")

    def rel_for(self, rtype: str, project: str | None = None) -> tuple[set, str]:
        if not rtype:
            return set(), ""
        tail = "rel/" + iri_segment(rtype)
        p = URIRef(self.base_for(project) + tail)
        if p in self.idx.inv.object_props:
            return {p}, "iri"
        other = self._other_project(self.idx.inv.object_props, tail)
        return (other, "other_project") if other else (set(), "")

    def prop_for(self, classes: set, name: str, project: str | None = None) -> tuple[set, str]:
        dps = self.idx.inv.data_props
        seg = "/" + iri_segment(name)
        for depth, level in enumerate(self.idx._levels(classes, self.idx.parents)):
            hit = {URIRef(str(c) + seg) for c in level} & dps
            if hit:
                return hit, "self" if depth == 0 else "ancestor"
        down = set()
        for level in self.idx._levels(classes, self.idx.children)[1:]:
            down |= {URIRef(str(c) + seg) for c in level} & dps
        return down, "subclass" if down else ""

    def iri_rule_check(self) -> dict:
        """온톨로지가 ONTOFLOW IRI 규칙을 따르는지 셉니다. 클래스는 기준 바로 아래, 관계는 기준/rel/ 아래,
        데이터 속성은 어떤 클래스 IRI 바로 아래(「클래스/속성」)에 있어야 합니다."""
        inv = self.idx.inv
        pattern = self.any_base

        def base_of(x: str) -> str | None:
            if pattern is not None:
                m = pattern.match(x)
                return m.group(0) if m else None
            b = self.template or self.ontology_base
            return b if b and x.startswith(b) else None

        bad = {"class": [], "object_property": [], "data_property": []}
        for c in inv.classes:
            b = base_of(str(c))
            rest = str(c)[len(b):] if b else ""
            if not (b and rest and "/" not in rest):
                bad["class"].append(str(c))
        for p in inv.object_props:
            b = base_of(str(p))
            rest = str(p)[len(b):] if b else ""
            if not (b and rest.startswith("rel/") and "/" not in rest[4:] and rest[4:]):
                bad["object_property"].append(str(p))
        class_iris = {str(c) for c in inv.classes}
        for p in inv.data_props:
            sp = str(p)
            head = sp.rsplit("/", 1)[0] if "/" in sp else ""
            if head not in class_iris:
                bad["data_property"].append(sp)
        totals = {"class": len(inv.classes), "object_property": len(inv.object_props),
                  "data_property": len(inv.data_props)}
        return {"follows": {k: totals[k] - len(v) for k, v in bad.items()}, "total": totals,
                "mismatch": {k: sorted(v)[:20] for k, v in bad.items()},
                "ok": not any(bad.values())}


# ---------------------------------------------------------------- SPARQL


def _walk_iris(obj, out: set, seen: set) -> None:
    if id(obj) in seen:
        return
    if isinstance(obj, URIRef):
        out.add(obj)
        return
    if isinstance(obj, (str, bytes, int, float, BNode)) or obj is None:
        return
    seen.add(id(obj))
    if isinstance(obj, dict):
        for v in obj.values():
            _walk_iris(v, out, seen)
        return
    if isinstance(obj, (list, tuple, set, frozenset)):
        for v in obj:
            _walk_iris(v, out, seen)
        return
    for attr in ("args", "arg", "path"):  # rdflib.paths
        v = getattr(obj, attr, None)
        if v is not None:
            _walk_iris(v, out, seen)


def sparql_iris(text: str, namespaces: dict) -> set:
    from rdflib.plugins.sparql import prepareQuery

    q = prepareQuery(text, initNs=namespaces)
    out: set = set()
    _walk_iris(q.algebra, out, set())
    return out


# ---------------------------------------------------------------- 분석


def _allowed(name: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(name, p) for p in patterns)


def make_resolver(idx: Index, profile: str | None, base: str | None):
    if (profile or "default") == "ontoflow":
        if not base:
            onto = next((str(o) for o in idx.inv.ontologies if isinstance(o, URIRef)), "")
            head = DEFAULT_ONTOFLOW_BASE.split("{project}")[0]
            base = DEFAULT_ONTOFLOW_BASE if onto.startswith(head) else ""
        return OntoflowResolver(idx, base)
    return DefaultResolver(idx)


def analyze(inv: Inventory, items: list[dict], allow_labels=None, allow_relations=None,
            profile: str | None = None, base: str | None = None) -> tuple[dict, list[dict]]:
    """커버리지 사전과 CQ01 후보 목록을 돌려줍니다."""
    allow_labels = split_list(allow_labels)
    allow_relations = split_list(allow_relations)
    idx = Index(inv)
    resolver = make_resolver(idx, profile, base)
    manual, infra_seen = [], []
    g = inv.graph
    namespaces = {pfx: ns for pfx, ns in g.namespaces() if pfx}
    hits = {k: defaultdict(list) for k in KINDS}      # 요소 -> 확실히 닿은 CQ id
    vague = defaultdict(list)                          # 데이터 속성 -> 모호하게 닿은 CQ id
    misses: dict[tuple, dict] = {}                     # (종류, 이름) -> {cq: [...], hint}
    per_cq, failed, rel_by_snake_used = [], [], set()

    def add_hit(kind, el, cid):
        if cid not in hits[kind][el]:
            hits[kind][el].append(cid)

    def miss(kind, name, cid, hint=""):
        m = misses.setdefault((kind, name), {"cq": [], "hint": hint})
        if cid not in m["cq"]:
            m["cq"].append(cid)
        if hint and not m["hint"]:
            m["hint"] = hint

    for it in items:
        cid = it["id"]
        if it["lang"] == "manual":
            manual.append({"id": cid, "q": it["q"]})
            continue
        row = {"id": cid, "q": it["q"], "lang": it["lang"], "parsed": True, "classes": [], "object_properties": [],
               "data_properties": [], "ambiguous": [], "unique_candidate": [], "unresolved": [],
               "relationship_properties": [], "allowed": [], "labels_from_list": []}
        if it.get("kind"):
            row["kind"] = it["kind"]
        project = it.get("project")
        touched = {k: set() for k in KINDS}
        if it["lang"] == "unknown":
            failed.append({"id": cid, "q": it["q"], "reason": f"알 수 없는 check.kind 입니다: {it.get('kind') or '(없음)'}"})
            row["parsed"] = False
            per_cq.append(row)
            continue
        if it["lang"] == "structured":
            st = it["structured"] or {}
            cls_of = {}
            for name in st.get("classes", []):
                cs, _ = resolver.class_for(name, project)
                cls_of[name] = cs
                if cs:
                    touched["class"] |= cs
                elif _allowed(name, allow_labels):
                    row["allowed"].append(name)
                else:
                    miss("label", name, cid)
                    row["unresolved"].append(f"라벨 {name}")
            for rt in st.get("rels", []):
                ps, how = resolver.rel_for(rt, project)
                if ps:
                    touched["object_property"] |= ps
                elif _allowed(rt, allow_relations):
                    row["allowed"].append(rt)
                else:
                    miss("relation", rt, cid)
                    row["unresolved"].append(f"관계 {rt}")
            for owner, prop in st.get("props", []):
                classes = cls_of.get(owner) or resolver.class_for(owner, project)[0]
                if not classes:
                    continue
                found, how = resolver.prop_for(classes, prop, project)
                if found and how != "subclass":
                    touched["data_property"] |= found
                else:
                    hint = ("하위 클래스에만 있음: " + ", ".join(sorted(short(p, g) for p in found))) if found else ""
                    miss("property", f"{owner}.{prop}", cid, hint)
                    row["unresolved"].append(f"속성 {owner}.{prop}")
        elif it["lang"] == "sparql":
            try:
                iris = sparql_iris(it["query"], namespaces) if it["query"].strip() else None
                if iris is None:
                    raise ValueError("질의가 비었습니다")
            except Exception as exc:  # rdflib 은 파싱 오류마다 예외 종류가 다릅니다
                failed.append({"id": cid, "q": it["q"], "reason": f"SPARQL 파싱 실패: {type(exc).__name__}: {str(exc)[:160]}"})
                row["parsed"] = False
                per_cq.append(row)
                continue
            for iri in iris:
                if iri in inv.classes:
                    touched["class"].add(iri)
                elif iri in inv.object_props:
                    touched["object_property"].add(iri)
                elif iri in inv.data_props:
                    touched["data_property"].add(iri)
                elif (inv.is_own(str(iri)) and iri not in inv.individuals and iri not in inv.declared_props
                      and iri not in set(inv.ontologies)):
                    ln = local_name(str(iri))
                    if _allowed(ln, allow_labels) or _allowed(ln, allow_relations):
                        row["allowed"].append(ln)
                    else:
                        miss("iri", short(iri, g), cid)
                        row["unresolved"].append(short(iri, g))
        else:
            try:
                parsed = parse_cypher(it["query"], profile=resolver.profile)
            except CypherError as exc:
                failed.append({"id": cid, "q": it["q"], "reason": f"Cypher 파싱 실패: {exc}"})
                row["parsed"] = False
                per_cq.append(row)
                continue
            if parsed.get("projects"):
                project = parsed["projects"][0]
            for lab in parsed.get("infra_labels") or []:
                if lab not in infra_seen:
                    infra_seen.append(lab)
            label_classes: dict[str, set] = {}
            list_labels = {lab for labs in parsed["labels_from_list"].values() for lab in labs}
            row["labels_from_list"] = [f"{v}:{lab}" for v, labs in sorted(parsed["labels_from_list"].items())
                                       for lab in labs]
            for lab in parsed["labels"]:
                cs, _ = resolver.class_for(lab, project)
                label_classes[lab] = cs
                if cs:
                    touched["class"] |= cs
                elif _allowed(lab, allow_labels):
                    row["allowed"].append(lab)
                else:
                    miss("label", lab, cid, "labels() 목록에서 읽음" if lab in list_labels else "")
                    row["unresolved"].append(f"라벨 {lab}")
            for rt in parsed["rel_types"]:
                ps, how = resolver.rel_for(rt, project)
                if ps:
                    touched["object_property"] |= ps
                    if how == "snake":
                        rel_by_snake_used.add(rt)
                elif _allowed(rt, allow_relations):
                    row["allowed"].append(rt)
                else:
                    miss("relation", rt, cid)
                    row["unresolved"].append(f"관계 {rt}")
            for var, labs, prop in parsed["accesses"]:
                classes = set()
                for lab in labs:
                    classes |= label_classes.get(lab) or resolver.class_for(lab, project)[0]
                if labs and not classes:
                    continue  # 허용 라벨이나 없는 라벨의 속성은 세지 않습니다(라벨 쪽에서 이미 적었습니다)
                if not labs:
                    cands = idx.dp_by_name.get(prop, set())
                    if cands:
                        for p in cands:
                            if cid not in vague[p]:
                                vague[p].append(cid)
                        if len(cands) == 1:
                            only = short(next(iter(cands)), g)
                            row["ambiguous"].append(f"{var or '?'}.{prop}(후보 1개: {only})")
                            row["unique_candidate"].append({"access": f"{var or '?'}.{prop}", "property": only})
                        else:
                            row["ambiguous"].append(f"{var or '?'}.{prop}({len(cands)}개 후보)")
                    else:
                        miss("property", f"?.{prop}", cid, "라벨 없는 변수이고, 이 이름의 데이터 속성이 없습니다")
                        row["unresolved"].append(f"속성 ?.{prop}")
                    continue
                found, how = resolver.prop_for(classes, prop, project)
                owner = "|".join(sorted(lab for lab in labs if label_classes.get(lab) or resolver.class_for(lab, project)[0]))
                if found and how != "subclass":
                    touched["data_property"] |= found
                else:
                    hint = ""
                    if found:
                        hint = "하위 클래스에만 있음: " + ", ".join(sorted(short(p, g) for p in found))
                    miss("property", f"{owner}.{prop}", cid, hint)
                    row["unresolved"].append(f"속성 {owner}.{prop}")
            row["relationship_properties"] = [f"{v or '?'}.{p}" for v, p in parsed["rel_props"]]
        for kind in KINDS:
            for el in touched[kind]:
                add_hit(kind, el, cid)
        row["classes"] = sorted(short(x, g) for x in touched["class"])
        row["object_properties"] = sorted(short(x, g) for x in touched["object_property"])
        row["data_properties"] = sorted(short(x, g) for x in touched["data_property"])
        row["allowed"] = sorted(set(row["allowed"]))
        per_cq.append(row)

    universe = {"class": inv.classes, "object_property": inv.object_props, "data_property": inv.data_props}
    coverage, elements, unreached = {}, [], {}
    for kind in KINDS:
        total = universe[kind]
        hit = {e for e in total if hits[kind].get(e)}
        vague_only = {e for e in total if kind == "data_property" and vague.get(e) and e not in hit}
        coverage[kind] = {"name": KIND_KO[kind], "touched": len(hit), "total": len(total),
                          "ambiguous_only": len(vague_only)}
        for e in sorted(total, key=str):
            cqs = hits[kind].get(e, [])
            amb = vague.get(e, []) if kind == "data_property" else []
            if cqs or amb:
                elements.append({"iri": str(e), "short": short(e, g), "kind": kind, "kind_ko": KIND_KO[kind],
                                 "cq": cqs, "count": len(cqs), "ambiguous_cq": amb})
        unreached[kind] = [{"iri": str(e), "short": short(e, g), "ambiguous_cq": vague.get(e, []) if kind == "data_property" else []}
                           for e in sorted(total - hit, key=str)]
    elements.sort(key=lambda x: (KINDS.index(x["kind"]), -x["count"], x["short"]))

    kind_ko = {"label": "라벨", "relation": "관계", "property": "속성", "iri": "IRI"}
    cq01 = [{"kind": k, "kind_ko": kind_ko[k], "name": name, "cq": v["cq"], "hint": v["hint"]}
            for (k, name), v in sorted(misses.items(), key=lambda kv: (-len(kv[1]["cq"]), kv[0]))]
    dp_methods = defaultdict(int)
    for p, how in idx.dp_method.items():
        dp_methods["+".join(sorted(set(how))) or "로컬 이름·레이블만"] += 1
    result = {
        "total": len(items),
        "profile": resolver.profile,
        "manual": manual,
        "check_kinds": {k: sum(1 for it in items if it.get("kind") == k) for k in
                        sorted({it.get("kind") for it in items if it.get("kind")})},
        "parsed": sum(1 for r in per_cq if r["parsed"]),
        "failed": failed,
        "languages": {lang: sum(1 for it in items if it["lang"] == lang) for lang in ("cypher", "sparql")}
        | ({"structured": n} if (n := sum(1 for it in items if it["lang"] == "structured")) else {}),
        "allow_labels": allow_labels,
        "allow_relations": allow_relations,
        "coverage": coverage,
        "elements": elements,
        "per_cq": per_cq,
        "unreached": unreached,
        "ambiguous_accesses": {
            "total": sum(len(r["ambiguous"]) for r in per_cq),
            "unique_candidate": sum(len(r["unique_candidate"]) for r in per_cq),
            "unique_candidate_items": [{"cq": r["id"], **u} for r in per_cq for u in r["unique_candidate"]],
        },
        "labels_from_list": [{"cq": r["id"], "labels": r["labels_from_list"]} for r in per_cq if r["labels_from_list"]],
        "no_touch": [r["id"] for r in per_cq if r["parsed"] and not (r["classes"] or r["object_properties"] or r["data_properties"])],
        "unresolved": cq01,
        "relation_matched_by_snake": sorted(rel_by_snake_used),
        "data_property_owner_method": dict(dp_methods),
        "notes": [NOT_DELETE_NOTE, NOT_FIT_NOTE],
    }
    if isinstance(resolver, OntoflowResolver):
        result["base_template"] = resolver.template or resolver.ontology_base
        result["bases"] = dict(sorted(resolver.bases.items()))
        result["infra_labels"] = infra_seen
        result["iri_rule"] = resolver.iri_rule_check()
    return result, cq01


def check(inv: Inventory, report: Report, cq_path: str | None, query_field: str | None = None,
          allow_labels=None, allow_relations=None, source_label: str | None = None,
          cq_format: str | None = None, profile: str | None = None, base: str | None = None) -> None:
    if not cq_path:
        return
    profile = (profile or "default").strip().lower()
    if profile not in PROFILES:
        raise LoadError(f"--cq-profile 은 {', '.join(PROFILES)} 가운데 하나입니다: {profile}")
    items, field_text, meta = load_cq_doc(cq_path, query_field, cq_format)
    result, cq01 = analyze(inv, items, allow_labels, allow_relations, profile=profile, base=base)
    result["source"] = source_label or str(cq_path)
    result["query_field"] = field_text
    result["format"] = meta.pop("format")
    result["catalog"] = meta
    if result["format"] == "ontoflow" and profile == "default":
        result["profile_hint"] = ("ONTOFLOW 형식 카탈로그를 기본 프로필로 읽었습니다. 질의의 (:Object {objectType:'X'})를 "
                                  "클래스로 읽으려면 --cq-profile ontoflow를 줍니다.")
    report.cq = result
    for m in cq01:
        ids = m["cq"]
        msg = (f"CQ 질의에 쓰였지만 온톨로지에도 허용 목록에도 없는 {m['kind_ko']}입니다: {m['name']}. "
               f"쓰인 CQ {len(ids)}건: {', '.join(ids[:8])}"
               + (" 외" if len(ids) > 8 else "") + ".")
        if m["hint"]:
            msg += f" 참고: {m['hint']}."
        report.add(Finding(
            CAT, "CQ01", "info", f"{m['kind_ko']} {m['name']}", msg,
            "질의가 틀렸으면 질의를 고치고, 온톨로지에 빠졌으면 요소를 더합니다. OWL 밖에서 정상인 이름이면 "
            "허용 목록(명령행 --cq-allow-labels·--cq-allow-relations)에 넣습니다.",
            {"kind": m["kind"], "name": m["name"], "cq": ids, "hint": m["hint"]},
        ))
    report.ran.append(CAT)
