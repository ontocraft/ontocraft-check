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
   모호한 접근은 「닿음」에 넣지 않고 따로 셉니다.
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
    "Cypher는 가벼운 정규식 파서로 읽습니다. 문자열 안의 라벨(labels(n) 비교 목록 등)과 동적 라벨은 보지 않습니다. "
    "라벨이 없는 변수의 속성 접근은 「모호」로 따로 세고 「닿음」에 넣지 않습니다.",
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


def load_cq(path: str | Path, query_field: str | None = None) -> tuple[list[dict], str]:
    """CQ JSON 을 읽어 [{id, q, query, lang, field}] 와 읽은 질의 필드 설명을 돌려줍니다."""
    p = Path(path)
    if not p.is_file():
        raise LoadError(f"CQ 파일이 없습니다: {p}")
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LoadError(f"CQ 파일을 JSON 으로 읽지 못했습니다(마크다운 표는 읽지 않습니다): {p}: {exc}") from exc
    items = doc.get("items") if isinstance(doc, dict) else doc
    if not isinstance(items, list):
        raise LoadError(f"CQ 파일에 items 목록이 없습니다: {p}")
    out = []
    for n, it in enumerate(items, start=1):
        if not isinstance(it, dict):
            continue
        cid = str(it.get("id") or f"#{n}")
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
    return out, query_field or "cypher, 없으면 sparql"


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


def strip_cypher(text: str) -> str:
    """문자열 리터럴의 내용과 주석을 지웁니다. 따옴표는 남겨 '' 로 둡니다."""
    out = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch in ("'", '"'):
            q = ch
            i += 1
            while i < n and text[i] != q:
                i += 2 if text[i] == "\\" else 1
            if i >= n:
                raise CypherError("닫히지 않은 문자열 리터럴이 있습니다")
            out.append(q + q)
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


def parse_cypher(text: str) -> dict:
    """Cypher 에서 노드 라벨, 관계 타입, 변수별 속성 접근을 뽑습니다.

    돌려주는 사전: labels(쓰인 라벨), rel_types(쓰인 관계 타입), node_vars{변수: 라벨 집합},
    rel_vars(관계 변수 집합), accesses[(변수 또는 None, 라벨 집합, 속성 이름)], rel_props[(변수, 속성)].
    파싱하지 못하면 CypherError 를 냅니다.
    """
    if not text or not text.strip():
        raise CypherError("질의가 비었습니다")
    body = strip_cypher(text)
    _check_balance(body)
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
    # WHERE v:Label 같은 라벨 조건입니다. 알려진 노드 변수에만 씁니다.
    masked = _NODE.sub(" ", _REL.sub(" ", body))
    masked = re.sub(r"\{[^{}]*\}", " ", masked)
    for m in _LABEL_PRED.finditer(masked):
        var, lab = _unquote(m.group(1)), _unquote(m.group(2))
        if var in node_vars and not var.startswith("("):
            node_vars[var].add(lab)
            if lab not in labels:
                labels.append(lab)
    for m in _ACCESS.finditer(body):
        var, prop = _unquote(m.group(1)), _unquote(m.group(2))
        if var in rel_vars and var not in node_vars:
            rel_props.append((var, prop))
        else:
            accesses.append((var, prop))
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
            "rel_vars": sorted(rel_vars), "accesses": resolved, "rel_props": sorted(set(rel_props), key=str)}


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


def analyze(inv: Inventory, items: list[dict], allow_labels=None, allow_relations=None) -> tuple[dict, list[dict]]:
    """커버리지 사전과 CQ01 후보 목록을 돌려줍니다."""
    allow_labels = split_list(allow_labels)
    allow_relations = split_list(allow_relations)
    idx = Index(inv)
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
        row = {"id": cid, "q": it["q"], "lang": it["lang"], "parsed": True, "classes": [], "object_properties": [],
               "data_properties": [], "ambiguous": [], "unresolved": [], "relationship_properties": [],
               "allowed": []}
        touched = {k: set() for k in KINDS}
        if it["lang"] == "sparql":
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
                parsed = parse_cypher(it["query"])
            except CypherError as exc:
                failed.append({"id": cid, "q": it["q"], "reason": f"Cypher 파싱 실패: {exc}"})
                row["parsed"] = False
                per_cq.append(row)
                continue
            label_classes: dict[str, set] = {}
            for lab in parsed["labels"]:
                cs = idx.classes_for(lab)
                label_classes[lab] = cs
                if cs:
                    touched["class"] |= cs
                elif _allowed(lab, allow_labels):
                    row["allowed"].append(lab)
                else:
                    miss("label", lab, cid)
                    row["unresolved"].append(f"라벨 {lab}")
            for rt in parsed["rel_types"]:
                ps, how = idx.rels_for(rt)
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
                    classes |= label_classes.get(lab) or idx.classes_for(lab)
                if labs and not classes:
                    continue  # 허용 라벨이나 없는 라벨의 속성은 세지 않습니다(라벨 쪽에서 이미 적었습니다)
                if not labs:
                    cands = idx.dp_by_name.get(prop, set())
                    if cands:
                        for p in cands:
                            if cid not in vague[p]:
                                vague[p].append(cid)
                        row["ambiguous"].append(f"{var or '?'}.{prop}({len(cands)}개 후보)")
                    else:
                        miss("property", f"?.{prop}", cid, "라벨 없는 변수이고, 이 이름의 데이터 속성이 없습니다")
                        row["unresolved"].append(f"속성 ?.{prop}")
                    continue
                found, how = idx.resolve_prop(classes, prop)
                owner = "|".join(sorted(lab for lab in labs if label_classes.get(lab) or idx.classes_for(lab)))
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
        "parsed": sum(1 for r in per_cq if r["parsed"]),
        "failed": failed,
        "languages": {lang: sum(1 for it in items if it["lang"] == lang) for lang in ("cypher", "sparql")},
        "allow_labels": allow_labels,
        "allow_relations": allow_relations,
        "coverage": coverage,
        "elements": elements,
        "per_cq": per_cq,
        "unreached": unreached,
        "no_touch": [r["id"] for r in per_cq if r["parsed"] and not (r["classes"] or r["object_properties"] or r["data_properties"])],
        "unresolved": cq01,
        "relation_matched_by_snake": sorted(rel_by_snake_used),
        "data_property_owner_method": dict(dp_methods),
        "notes": [NOT_DELETE_NOTE, NOT_FIT_NOTE],
    }
    return result, cq01


def check(inv: Inventory, report: Report, cq_path: str | None, query_field: str | None = None,
          allow_labels=None, allow_relations=None, source_label: str | None = None) -> None:
    if not cq_path:
        return
    items, field_text = load_cq(cq_path, query_field)
    result, cq01 = analyze(inv, items, allow_labels, allow_relations)
    result["source"] = source_label or str(cq_path)
    result["query_field"] = field_text
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
            "--cq-allow-labels나 --cq-allow-relations에 넣습니다.",
            {"kind": m["kind"], "name": m["name"], "cq": ids, "hint": m["hint"]},
        ))
    report.ran.append(CAT)
