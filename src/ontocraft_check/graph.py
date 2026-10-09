"""그래프 읽기와 온톨로지 요소 목록(인벤토리)입니다."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.collection import Collection
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SKOS, XSD
from rdflib.util import guess_format

DC = Namespace("http://purl.org/dc/elements/1.1/")
CC = Namespace("http://creativecommons.org/ns#")
SCHEMA = Namespace("https://schema.org/")
SCHEMA_HTTP = Namespace("http://schema.org/")

# OWL·RDFS 언어 자체의 어휘입니다. 선언을 요구하지 않습니다.
LANGUAGE_NS = (str(RDF), str(RDFS), str(OWL), str(XSD))

# 이름이 알려진 표준 어휘입니다. 선언이 없으면 「외부 어휘 선언 없음」으로 묶습니다.
STANDARD_NS = LANGUAGE_NS + (
    str(SKOS),
    str(DCTERMS),
    str(DC),
    str(CC),
    "http://www.w3.org/ns/prov#",
    "http://xmlns.com/foaf/0.1/",
    "http://www.w3.org/ns/shacl#",
    "http://purl.org/vocab/vann/",
    "http://www.w3.org/2003/01/geo/wgs84_pos#",
    "http://www.w3.org/2006/time#",
    "http://www.w3.org/ns/sosa/",
    "http://www.w3.org/ns/ssn/",
    "http://www.w3.org/ns/dcat#",
    "http://www.w3.org/ns/org#",
    "http://www.w3.org/2006/vcard/ns#",
    str(SCHEMA),
    str(SCHEMA_HTTP),
)

OBJECT_PROPERTY_TYPES = {
    OWL.ObjectProperty,
    OWL.TransitiveProperty,
    OWL.SymmetricProperty,
    OWL.AsymmetricProperty,
    OWL.ReflexiveProperty,
    OWL.IrreflexiveProperty,
    OWL.InverseFunctionalProperty,
}
DATA_PROPERTY_TYPES = {OWL.DatatypeProperty}
ANNOTATION_PROPERTY_TYPES = {OWL.AnnotationProperty, OWL.OntologyProperty}
ANY_PROPERTY_TYPES = (
    OBJECT_PROPERTY_TYPES
    | DATA_PROPERTY_TYPES
    | ANNOTATION_PROPERTY_TYPES
    | {RDF.Property, OWL.FunctionalProperty, OWL.DeprecatedProperty}
)
CLASS_TYPES = {OWL.Class, RDFS.Class}

LICENSE_PREDICATES = (
    DCTERMS.license,
    DCTERMS.rights,
    DC.rights,
    CC.license,
    SCHEMA.license,
    SCHEMA_HTTP.license,
)

FORMAT_ORDER = ("turtle", "xml", "json-ld", "nt")


class LoadError(Exception):
    pass


def load_graph(path: str | Path) -> tuple[Graph, str]:
    """파일 확장자로 형식을 추정해 읽고, 실패하면 다른 형식을 차례로 시도합니다."""
    p = Path(path)
    if not p.is_file():
        raise LoadError(f"파일이 없습니다: {p}")
    first = guess_format(str(p))
    if p.suffix.lower() in (".jsonld", ".json"):
        first = "json-ld"
    order = [first] if first else []
    order += [f for f in FORMAT_ORDER if f not in order]
    errors = []
    for fmt in order:
        g = Graph()
        try:
            g.parse(str(p), format=fmt)
        except Exception as exc:  # 형식마다 예외 종류가 다릅니다
            errors.append(f"{fmt}: {type(exc).__name__}: {str(exc)[:200]}")
            continue
        return g, fmt
    raise LoadError(f"어떤 형식으로도 읽지 못했습니다: {p}\n" + "\n".join(errors))


def namespace_of(iri: str) -> str:
    if "#" in iri:
        return iri[: iri.rindex("#") + 1]
    return iri[: iri.rindex("/") + 1] if "/" in iri else iri


def local_name(iri: str) -> str:
    ns = namespace_of(iri)
    return iri[len(ns):] or iri


def in_ns(iri: str, namespaces) -> bool:
    return any(iri.startswith(ns) for ns in namespaces)


def is_language_term(node) -> bool:
    return isinstance(node, URIRef) and in_ns(str(node), LANGUAGE_NS)


def rdf_list(g: Graph, head) -> list:
    """RDF 목록을 파이썬 목록으로 바꿉니다. 깨진 목록은 읽은 데까지만 돌려줍니다."""
    if head is None or head == RDF.nil:
        return []
    try:
        return list(Collection(g, head))
    except Exception:
        return []


def has_lang(lit, lang: str) -> bool:
    if not isinstance(lit, Literal) or not lit.language:
        return False
    tag = lit.language.lower()
    return tag == lang or tag.startswith(lang + "-")


@dataclass
class Inventory:
    graph: Graph
    ontologies: list = field(default_factory=list)
    classes: set = field(default_factory=set)
    object_props: set = field(default_factory=set)
    data_props: set = field(default_factory=set)
    annotation_props: set = field(default_factory=set)
    other_props: set = field(default_factory=set)
    declared_props: set = field(default_factory=set)
    individuals: set = field(default_factory=set)
    own_ns: set = field(default_factory=set)
    # 0.7: --ignore-names 로 명명·메타데이터 규칙에서 뺄 요소(클래스·속성)입니다. runner 가 채웁니다.
    ignored: set = field(default_factory=set)

    @property
    def properties(self) -> set:
        """주석 속성을 뺀 속성(객체·데이터·기타 rdf:Property)입니다."""
        return self.object_props | self.data_props | self.other_props

    @property
    def entities(self) -> set:
        return self.classes | self.properties

    def is_own(self, iri: str) -> bool:
        return in_ns(iri, self.own_ns)


def build_inventory(g: Graph) -> Inventory:
    inv = Inventory(graph=g)
    inv.ontologies = sorted({s for s in g.subjects(RDF.type, OWL.Ontology)}, key=str)
    for s, t in g.subject_objects(RDF.type):
        if not isinstance(s, URIRef):
            continue
        if t in CLASS_TYPES:
            inv.classes.add(s)
        if t in ANY_PROPERTY_TYPES:
            inv.declared_props.add(s)
    for p in inv.declared_props:
        types = set(g.objects(p, RDF.type))
        if types & OBJECT_PROPERTY_TYPES:
            inv.object_props.add(p)
        elif types & DATA_PROPERTY_TYPES:
            inv.data_props.add(p)
        elif types & ANNOTATION_PROPERTY_TYPES:
            inv.annotation_props.add(p)
        else:
            inv.other_props.add(p)
    # 언어 어휘를 다시 선언한 경우는 우리 요소로 보지 않습니다.
    for name in ("classes", "object_props", "data_props", "annotation_props", "other_props", "declared_props"):
        setattr(inv, name, {x for x in getattr(inv, name) if not is_language_term(x)})

    inv.individuals = find_individuals(g, inv.classes | inv.declared_props | set(inv.ontologies))

    own = Counter()
    for x in inv.classes | inv.declared_props:
        ns = namespace_of(str(x))
        if not in_ns(ns, STANDARD_NS):
            own[ns] += 1
    inv.own_ns = set(own)
    for o in inv.ontologies:
        if isinstance(o, URIRef):
            iri = str(o)
            if iri.endswith(("#", "/")):
                inv.own_ns.add(iri)
            else:
                inv.own_ns.update({iri + "#", iri + "/"})
    return inv


def relative_names(inv: "Inventory", iri: str) -> list[str]:
    """이름 패턴을 맞출 이름들입니다. 로컬 이름과, 온톨로지 IRI 아래의 상대 경로(있으면)입니다.

    ONTOFLOW 처럼 데이터 속성 IRI 가 「<기준>/<클래스>/<속성>」이면 상대 경로가 「<클래스>/<속성>」이 되어,
    ActionLog_* 같은 패턴이 그 클래스의 속성에도 맞습니다.
    """
    out = [local_name(iri)]
    for o in inv.ontologies:
        if not isinstance(o, URIRef):
            continue
        base = str(o)
        bases = [base] if base.endswith(("/", "#")) else [base + "/", base + "#"]
        for b in bases:
            if iri.startswith(b) and len(iri) > len(b):
                rel = iri[len(b):]
                if rel not in out:
                    out.append(rel)
    return out


def split_name(name: str) -> str:
    """로컬 이름을 띄어 쓴 영어 형태로 바꿉니다(ChemicalAccident -> Chemical Accident, ship_type -> ship type)."""
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", name)
    s = re.sub(r"[_\-\s]+", " ", s)
    return s.strip()


def find_individuals(g: Graph, exclude: set) -> set:
    out = set()
    for s, t in g.subject_objects(RDF.type):
        if not isinstance(s, URIRef) or s in exclude:
            continue
        if t == OWL.NamedIndividual or t == OWL.Thing or not is_language_term(t):
            out.add(s)
    return out


def label_of(g: Graph, node) -> str:
    labels = list(g.objects(node, RDFS.label))
    for lit in labels:
        if has_lang(lit, "ko"):
            return str(lit)
    return str(labels[0]) if labels else ""


def ontology_iri(inv: Inventory) -> str:
    named = [o for o in inv.ontologies if isinstance(o, URIRef)]
    return str(named[0]) if named else ""


def short(iri, g: Graph | None = None) -> str:
    """보고서에 쓸 짧은 이름입니다. 접두어가 있으면 접두어:이름 으로 줄입니다."""
    if isinstance(iri, BNode):
        return "_:" + str(iri)
    s = str(iri)
    if g is not None:
        try:
            pfx, ns, name = g.namespace_manager.compute_qname(s, generate=False)
            if pfx:
                return f"{pfx}:{name}"
        except Exception:
            pass
    return s
