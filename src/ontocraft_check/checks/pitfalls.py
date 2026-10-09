"""모델링 함정 검사입니다.

OOPS! 함정 목록(https://oops.linkeddata.es/catalogue.jsp)의 공개 설명 수준만 참고해
다시 구현한 근사 검사입니다. OOPS! 코드는 쓰지 않았고 OOPS! 자체의 결과가 아닙니다.
검사 범위는 온톨로지 파일(TBox)입니다. --data로 준 데이터 그래프는 보지 않습니다.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

from rdflib import Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS

from ..graph import (
    LICENSE_PREDICATES,
    Inventory,
    in_ns,
    is_language_term,
    local_name,
    namespace_of,
    ontology_iri,
    rdf_list,
    STANDARD_NS,
)
from ..model import Finding, Report

CAT = "pitfall"

CLASS_LIST_PREDICATES = (OWL.unionOf, OWL.intersectionOf, OWL.disjointUnionOf)
PROPERTY_PAIR_PREDICATES = (
    RDFS.subPropertyOf,
    OWL.inverseOf,
    OWL.equivalentProperty,
    OWL.propertyDisjointWith,
)


def _named(x) -> bool:
    return isinstance(x, URIRef)


def class_usage(inv: Inventory) -> set:
    """클래스 자리에 쓰인 이름 있는 노드를 모읍니다(공리와 개체의 타입)."""
    g = inv.graph
    used = set()
    for s, o in g.subject_objects(RDFS.subClassOf):
        used.update((s, o))
    for p in (OWL.equivalentClass, OWL.disjointWith):
        for s, o in g.subject_objects(p):
            used.update((s, o))
    for o in g.objects(None, OWL.complementOf):
        used.add(o)
    for p in CLASS_LIST_PREDICATES:
        for s, head in g.subject_objects(p):
            if p == OWL.disjointUnionOf:
                used.add(s)
            used.update(rdf_list(g, head))
    for node in g.subjects(RDF.type, OWL.AllDisjointClasses):
        used.update(rdf_list(g, g.value(node, OWL.members)))
    for o in g.objects(None, RDFS.domain):
        used.add(o)
    for p, o in g.subject_objects(RDFS.range):
        if p in inv.data_props or p in inv.annotation_props:
            continue
        if (o, RDF.type, RDFS.Datatype) in g:
            continue
        used.add(o)
    for r in set(g.subjects(OWL.onProperty, None)):
        prop = g.value(r, OWL.onProperty)
        for p in (OWL.someValuesFrom, OWL.allValuesFrom):
            v = g.value(r, p)
            if v is not None and prop not in inv.data_props and (v, RDF.type, RDFS.Datatype) not in g:
                used.add(v)
        v = g.value(r, OWL.onClass)
        if v is not None:
            used.add(v)
    for ind in inv.individuals:
        for t in g.objects(ind, RDF.type):
            if t != OWL.NamedIndividual:
                used.add(t)
    return {x for x in used if _named(x) and not is_language_term(x)}


def property_usage(inv: Inventory, include_predicates: bool = True) -> set:
    """속성 자리에 쓰인 이름 있는 노드를 모읍니다."""
    g = inv.graph
    used = set()
    if include_predicates:
        used.update(g.predicates())
    used.update(g.objects(None, OWL.onProperty))
    for p in PROPERTY_PAIR_PREDICATES:
        for s, o in g.subject_objects(p):
            used.update((s, o))
    used.update(g.subjects(RDFS.domain, None))
    used.update(g.subjects(RDFS.range, None))
    for head in g.objects(None, OWL.propertyChainAxiom):
        used.update(rdf_list(g, head))
    for node in g.subjects(RDF.type, OWL.AllDisjointProperties):
        used.update(rdf_list(g, g.value(node, OWL.members)))
    return {x for x in used if _named(x) and not is_language_term(x)}


def structurally_connected_properties(inv: Inventory) -> set:
    g = inv.graph
    out = property_usage(inv, include_predicates=False)
    # 온톨로지 파일 안의 개체가 실제로 쓰는 속성도 연결된 것으로 봅니다.
    for s, p, _ in g:
        if s in inv.individuals:
            out.add(p)
    return out


def check(inv: Inventory, report: Report) -> None:
    _p04(inv, report)
    _p06(inv, report)
    _p08(inv, report)
    _p10(inv, report)
    _p11_p19(inv, report)
    _p13(inv, report)
    _p22(inv, report)
    _p32(inv, report)
    _p34_p35(inv, report)
    _p38_p41(inv, report)
    report.ran.append("pitfall")


def _p04(inv: Inventory, report: Report) -> None:
    used_c = class_usage(inv)
    for c in sorted(inv.classes - used_c, key=str):
        report.add(Finding(
            CAT, "P04", "minor", str(c),
            "클래스가 상위·하위 관계, 도메인·레인지, 제약, 개체 타입 어디에도 쓰이지 않습니다.",
            "상위 클래스(rdfs:subClassOf)를 주거나 속성의 도메인·레인지로 연결합니다. 쓰지 않는 클래스라면 지웁니다.",
        ))
    used_p = structurally_connected_properties(inv)
    for p in sorted(inv.properties - used_p, key=str):
        report.add(Finding(
            CAT, "P04", "minor", str(p),
            "속성에 도메인·레인지·상위 속성·역관계가 없고 제약에도 쓰이지 않아 어떤 클래스와도 이어지지 않습니다.",
            "rdfs:domain과 rdfs:range를 주어 클래스와 연결합니다.",
        ))


def _p06(inv: Inventory, report: Report) -> None:
    g = inv.graph
    edges = defaultdict(set)
    for s, o in g.subject_objects(RDFS.subClassOf):
        if _named(s) and _named(o) and s != o:
            edges[s].add(o)
    for comp in strongly_connected(edges):
        if len(comp) > 1:
            members = sorted(comp, key=str)
            report.add(Finding(
                CAT, "P06", "critical", ", ".join(str(m) for m in members),
                f"rdfs:subClassOf가 순환합니다({len(members)}개 클래스). 순환 안의 클래스는 추론으로 모두 같은 클래스가 됩니다.",
                "순환을 이루는 상하위 관계 가운데 잘못 넣은 하나를 지웁니다. 같은 개념이라면 owl:equivalentClass로 바꿉니다.",
                {"members": [str(m) for m in members]},
            ))


def strongly_connected(edges: dict) -> list:
    """Tarjan 알고리즘을 반복문으로 구현했습니다(깊은 계층에서도 재귀 한도에 걸리지 않음)."""
    index, low, on_stack, stack, comps = {}, {}, set(), [], []
    counter = [0]
    nodes = set(edges) | {v for vs in edges.values() for v in vs}
    for root in sorted(nodes, key=str):
        if root in index:
            continue
        work = [(root, iter(sorted(edges.get(root, ()), key=str)))]
        index[root] = low[root] = counter[0]
        counter[0] += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            v, it = work[-1]
            advanced = False
            for w in it:
                if w not in index:
                    index[w] = low[w] = counter[0]
                    counter[0] += 1
                    stack.append(w)
                    on_stack.add(w)
                    work.append((w, iter(sorted(edges.get(w, ()), key=str))))
                    advanced = True
                    break
                if w in on_stack:
                    low[v] = min(low[v], index[w])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[v])
            if low[v] == index[v]:
                comp = set()
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    comp.add(w)
                    if w == v:
                        break
                comps.append(comp)
    return comps


def _p08(inv: Inventory, report: Report) -> None:
    g = inv.graph
    for e in sorted(inv.entities, key=str):
        if (e, RDFS.label, None) not in g:
            continue  # 레이블이 없는 경우는 메타데이터 검사가 따로 잡습니다
        if (e, RDFS.comment, None) in g or (e, SKOS.definition, None) in g:
            continue
        kind = "클래스" if e in inv.classes else "속성"
        report.add(Finding(
            CAT, "P08", "minor", str(e),
            f"{kind}에 rdfs:label은 있지만 rdfs:comment와 skos:definition이 모두 없어 뜻을 사람이 확인할 수 없습니다.",
            "skos:definition(또는 rdfs:comment)으로 한두 문장의 정의를 붙입니다.",
        ))


def count_disjoint_axioms(g) -> int:
    n = len(set(g.subject_objects(OWL.disjointWith)))
    n += len(set(g.subjects(RDF.type, OWL.AllDisjointClasses)))
    n += len(set(g.subject_objects(OWL.disjointUnionOf)))
    return n


def _p10(inv: Inventory, report: Report) -> None:
    n = count_disjoint_axioms(inv.graph)
    report.stats["disjoint_axioms"] = n
    if n == 0 and len(inv.classes) >= 2:
        report.add(Finding(
            CAT, "P10", "important", ontology_iri(inv) or report.source,
            "온톨로지 전체에 서로소 공리(owl:disjointWith, owl:AllDisjointClasses, owl:disjointUnionOf)가 하나도 없습니다. "
            "추론기가 서로 배타적인 클래스에 동시에 속한 개체를 모순으로 잡지 못합니다.",
            "같은 상위 클래스 아래에서 겹칠 수 없는 형제 클래스를 owl:AllDisjointClasses로 묶습니다.",
        ))


def _p11_p19(inv: Inventory, report: Report) -> None:
    g = inv.graph
    for p in sorted(inv.properties, key=str):
        domains = set(g.objects(p, RDFS.domain))
        ranges = set(g.objects(p, RDFS.range))
        missing = [n for n, v in (("rdfs:domain", domains), ("rdfs:range", ranges)) if not v]
        if missing:
            report.add(Finding(
                CAT, "P11", "important", str(p),
                f"속성에 {' 와 '.join(missing)}가 없습니다.",
                "이 속성이 어떤 클래스에서 출발해 어떤 클래스(또는 데이터 타입)로 가는지 rdfs:domain·rdfs:range로 적습니다.",
                {"missing": missing},
            ))
        for name, vals in (("rdfs:domain", domains), ("rdfs:range", ranges)):
            if len(vals) > 1:
                report.add(Finding(
                    CAT, "P19", "critical", str(p),
                    f"한 속성에 {name}가 {len(vals)}개 있습니다. OWL은 이것을 합집합이 아니라 교집합으로 해석하므로, "
                    "값이 모든 클래스에 동시에 속해야 합니다.",
                    f"뜻한 것이 「어느 하나」라면 owl:unionOf로 만든 클래스 하나를 {name}로 둡니다.",
                    {"values": sorted(str(v) for v in vals)},
                ))


def _p13(inv: Inventory, report: Report) -> None:
    g = inv.graph
    has_inverse = set()
    for s, o in g.subject_objects(OWL.inverseOf):
        has_inverse.update((s, o))
    for p in sorted(inv.object_props, key=str):
        if p in has_inverse or (p, RDF.type, OWL.SymmetricProperty) in g:
            continue
        report.add(Finding(
            CAT, "P13", "minor", str(p),
            "객체 속성에 owl:inverseOf로 선언한 역관계가 없습니다. 역관계를 모두 선언하는 것이 늘 맞지는 않습니다. "
            "속성 그래프(LPG) 기반 설계에서는 역관계를 일부러 두지 않는 경우가 흔합니다.",
            "질의나 화면에서 반대 방향으로 자주 따라가는 속성만 골라 역관계를 선언합니다. 일부러 두지 않는 설계라면 --disable P13으로 이 규칙을 끕니다.",
        ))


STYLE_KO = {"UpperCamel": "UpperCamel", "lowerCamel": "lowerCamel", "snake": "snake_case", "kebab": "kebab-case"}


def name_style(name: str) -> str:
    if "_" in name and "-" not in name and re.fullmatch(r"[A-Za-z0-9_]+", name):
        return "snake"
    if "-" in name and "_" not in name and re.fullmatch(r"[A-Za-z0-9-]+", name):
        return "kebab"
    if re.fullmatch(r"[A-Z][A-Za-z0-9]*", name):
        return "UpperCamel"
    if re.fullmatch(r"[a-z][a-z0-9]*[A-Z][A-Za-z0-9]*", name):
        return "lowerCamel"
    if re.fullmatch(r"[a-z][a-z0-9]*", name):
        return "lower"  # 한 단어 소문자는 lowerCamel·snake·kebab 어느 쪽과도 맞습니다
    return "other"


def _p22(inv: Inventory, report: Report) -> None:
    styles = {}
    for c in inv.classes:
        if inv.own_ns and not inv.is_own(str(c)):
            continue
        styles[c] = name_style(local_name(str(c)))
    definite = Counter(s for s in styles.values() if s in STYLE_KO)
    if not definite:
        return
    major, _ = sorted(definite.items(), key=lambda kv: (-kv[1], list(STYLE_KO).index(kv[0])))[0]
    if major == "UpperCamel":
        odd = {c for c, s in styles.items() if s in ("lowerCamel", "snake", "kebab", "lower")}
    else:
        odd = {c for c, s in styles.items() if s in STYLE_KO and s != major}
    if not odd:
        return
    for c in sorted(odd, key=str):
        report.add(Finding(
            CAT, "P22", "minor", str(c),
            f"클래스 이름 표기법이 {STYLE_KO.get(styles[c], '한 단어 소문자')}입니다. 이 온톨로지 클래스 대부분은 {STYLE_KO[major]}를 씁니다.",
            f"클래스 로컬 이름을 {STYLE_KO[major]}로 맞춥니다. 이미 공개한 IRI 라면 새 IRI를 만들고 owl:equivalentClass와 owl:deprecated로 옛 이름을 남깁니다.",
            {"style": styles[c], "majority": major, "counts": dict(definite)},
        ))


def _p32(inv: Inventory, report: Report) -> None:
    g = inv.graph
    groups = defaultdict(set)
    for c in inv.classes:
        for lit in g.objects(c, RDFS.label):
            if isinstance(lit, Literal):
                groups[(str(lit).strip(), (lit.language or "").lower())].add(c)
    for (text, lang), members in sorted(groups.items()):
        if len(members) > 1:
            ms = sorted(members, key=str)
            report.add(Finding(
                CAT, "P32", "minor", ", ".join(str(m) for m in ms),
                f"클래스 {len(ms)}개가 같은 레이블 「{text}」{'@' + lang if lang else ''}를 씁니다. 사람이 둘을 구별할 수 없습니다.",
                "같은 개념이면 하나로 합치거나 owl:equivalentClass로 잇고, 다른 개념이면 레이블을 구별되게 고칩니다.",
                {"label": text, "lang": lang, "members": [str(m) for m in ms]},
            ))


def _p34_p35(inv: Inventory, report: Report) -> None:
    g = inv.graph
    declared_any = inv.classes | inv.declared_props
    used_c = class_usage(inv)
    used_p = property_usage(inv)
    ext_classes, ext_props = set(), set()
    for c in sorted(used_c - declared_any, key=str):
        if (c, RDF.type, RDFS.Datatype) in g:
            continue
        if _is_own(inv, c):
            report.add(Finding(
                CAT, "P34", "important", str(c),
                "클래스 자리에 쓰였지만 owl:Class로 선언되지 않았습니다. OWL 2 DL 도구는 이 이름의 종류를 알 수 없습니다.",
                "owl:Class 선언과 레이블을 추가합니다. 오타라면 선언된 클래스 이름으로 고칩니다.",
            ))
        else:
            ext_classes.add(c)
    for p in sorted(used_p - declared_any, key=str):
        if _is_own(inv, p):
            report.add(Finding(
                CAT, "P35", "important", str(p),
                "속성 자리에 쓰였지만 owl:ObjectProperty·owl:DatatypeProperty·owl:AnnotationProperty·rdf:Property 어느 것으로도 선언되지 않았습니다.",
                "알맞은 속성 종류로 선언하고 도메인·레인지를 줍니다. 오타라면 선언된 속성 이름으로 고칩니다.",
            ))
        else:
            ext_props.add(p)
    for kind, items, rule in (("클래스", ext_classes, "P34-EXT"), ("속성", ext_props, "P35-EXT")):
        for x in sorted(items, key=str):
            report.add(Finding(
                CAT, rule, "minor", str(x),
                f"외부 어휘 선언 없음: 외부 어휘의 {kind}를 쓰면서 이 파일에 종류 선언이 없습니다. RDF 로는 문제가 없지만 OWL 2 DL 도구는 선언을 요구합니다.",
                "owl:imports로 외부 어휘를 가져오거나, 쓰는 항목만 owl:Class·owl:AnnotationProperty 등으로 선언합니다.",
                {"external": True},
            ))


def _is_own(inv: Inventory, x) -> bool:
    iri = str(x)
    if inv.own_ns:
        return inv.is_own(iri)
    return not in_ns(namespace_of(iri), STANDARD_NS)


def _p38_p41(inv: Inventory, report: Report) -> None:
    g = inv.graph
    if not inv.ontologies:
        report.add(Finding(
            CAT, "P38", "important", report.source,
            "owl:Ontology 선언이 없습니다. 온톨로지 IRI·버전·라이선스를 적을 자리가 없습니다.",
            "<온톨로지 IRI> a owl:Ontology ; rdfs:label ... ; owl:versionInfo ... ; dcterms:license <...> . 를 추가합니다.",
        ))
        return
    for o in inv.ontologies:
        if any((o, p, None) in g for p in LICENSE_PREDICATES):
            return
    report.add(Finding(
        CAT, "P41", "important", ontology_iri(inv) or str(inv.ontologies[0]),
        "온톨로지 선언에 라이선스(dcterms:license, dcterms:rights, dc:rights, cc:license)가 없습니다. 남이 재사용할 수 있는지 알 수 없습니다.",
        "온톨로지 선언에 dcterms:license <https://creativecommons.org/licenses/by/4.0/>처럼 라이선스 IRI를 붙입니다.",
    ))


__all__ = ["check", "class_usage", "property_usage", "strongly_connected", "name_style", "count_disjoint_axioms"]
