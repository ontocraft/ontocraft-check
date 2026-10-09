"""규칙 설명표입니다. MCP 도구 explain_rule·list_rules 가 씁니다.

제목은 render.RULE_TITLES 와 같고, 심각도는 각 검사 모듈이 항목을 낼 때 쓰는 값과 같습니다.
"""

from __future__ import annotations

from .model import CATEGORY_KO, SEVERITY_KO
from .render import RULE_TITLES

OOPS_CATALOGUE = "https://oops.linkeddata.es/catalogue.jsp"

# id: (검사 종류, 심각도, 뜻, 고치는 법)
_INFO = {
    "P04": ("pitfall", "minor",
            "클래스나 속성이 상위·하위 관계, 도메인·레인지, 제약, 개체 타입 어디에도 쓰이지 않습니다.",
            "상위 클래스를 주거나 속성의 rdfs:domain·rdfs:range 로 연결합니다. 쓰지 않는 요소라면 지웁니다."),
    "P06": ("pitfall", "critical",
            "rdfs:subClassOf 가 길이 2 이상으로 순환합니다. 순환 안의 클래스는 추론으로 모두 같은 클래스가 됩니다.",
            "잘못 넣은 상하위 관계 하나를 지웁니다. 같은 개념이라면 owl:equivalentClass 로 바꿉니다."),
    "P08": ("pitfall", "minor",
            "rdfs:label 은 있지만 rdfs:comment 와 skos:definition 이 모두 없어 뜻을 확인할 수 없습니다.",
            "skos:definition(또는 rdfs:comment)으로 한두 문장의 정의를 붙입니다."),
    "P10": ("pitfall", "important",
            "온톨로지 전체에 서로소 공리가 하나도 없습니다. 추론기가 배타적인 클래스에 동시에 속한 개체를 모순으로 잡지 못합니다.",
            "같은 상위 클래스 아래에서 겹칠 수 없는 형제 클래스를 owl:AllDisjointClasses 로 묶습니다."),
    "P11": ("pitfall", "important",
            "객체 속성이나 데이터 속성에 rdfs:domain 또는 rdfs:range 가 없습니다.",
            "속성이 어떤 클래스에서 출발해 어떤 클래스(또는 데이터 타입)로 가는지 rdfs:domain·rdfs:range 로 적습니다."),
    "P13": ("pitfall", "minor",
            "객체 속성에 owl:inverseOf 로 선언한 역관계가 없습니다. 대칭 속성은 뺍니다. "
            "속성 그래프(LPG) 기반 설계에서는 역관계를 일부러 두지 않는 경우가 흔합니다.",
            "반대 방향으로 자주 따라가는 속성만 역관계를 선언합니다. 일부러 두지 않는 설계라면 이 규칙을 끕니다(--disable P13)."),
    "P19": ("pitfall", "critical",
            "한 속성에 rdfs:domain 이나 rdfs:range 가 둘 이상 있습니다. OWL 은 이것을 교집합으로 해석합니다.",
            "뜻한 것이 「어느 하나」라면 owl:unionOf 로 만든 클래스 하나를 도메인이나 레인지로 둡니다."),
    "P22": ("pitfall", "minor",
            "클래스 이름 표기법(UpperCamel, lowerCamel, snake_case, kebab-case)이 다수와 다릅니다.",
            "온톨로지 안에서 한 가지 표기법으로 맞춥니다. 클래스는 보통 UpperCamel 을 씁니다."),
    "P32": ("pitfall", "minor",
            "서로 다른 클래스가 같은 레이블을 가집니다.",
            "같은 개념이면 하나로 합치거나 owl:equivalentClass 로 잇고, 다른 개념이면 레이블을 구별합니다."),
    "P34": ("pitfall", "important",
            "우리 네임스페이스의 이름이 클래스 자리에 쓰였지만 owl:Class 로 선언되지 않았습니다.",
            "owl:Class 선언과 레이블을 추가합니다. 오타라면 선언된 클래스 이름으로 고칩니다."),
    "P35": ("pitfall", "important",
            "우리 네임스페이스의 이름이 속성 자리에 쓰였지만 어떤 속성 종류로도 선언되지 않았습니다.",
            "알맞은 속성 종류로 선언하고 도메인·레인지를 줍니다. 오타라면 선언된 속성 이름으로 고칩니다."),
    "P34-EXT": ("pitfall", "minor",
                "외부 어휘의 클래스를 쓰면서 이 파일에 종류 선언이 없습니다. RDF 로는 문제가 없지만 OWL 2 DL 도구는 선언을 요구합니다.",
                "owl:imports 로 외부 어휘를 가져오거나 쓰는 항목만 owl:Class 로 선언합니다."),
    "P35-EXT": ("pitfall", "minor",
                "외부 어휘의 속성을 쓰면서 이 파일에 종류 선언이 없습니다. RDF 로는 문제가 없지만 OWL 2 DL 도구는 선언을 요구합니다.",
                "owl:imports 로 외부 어휘를 가져오거나 쓰는 항목만 owl:AnnotationProperty 등으로 선언합니다."),
    "P38": ("pitfall", "important",
            "owl:Ontology 선언이 없습니다. 온톨로지 IRI, 버전, 라이선스를 적을 자리가 없습니다.",
            "<온톨로지 IRI> a owl:Ontology ; rdfs:label ... ; owl:versionInfo ... ; dcterms:license <...> . 를 추가합니다."),
    "P41": ("pitfall", "important",
            "온톨로지 선언에 라이선스(dcterms:license, dcterms:rights, dc:rights, cc:license, schema:license)가 없습니다.",
            "온톨로지 선언에 dcterms:license <https://creativecommons.org/licenses/by/4.0/> 처럼 라이선스 IRI 를 붙입니다."),
    "META01": ("metadata", "minor",
               "온톨로지 선언에 버전 정보(owl:versionInfo 또는 owl:versionIRI)가 없습니다.",
               "owl:versionInfo \"0.1.0\" 이나 owl:versionIRI 를 붙입니다."),
    "META02": ("metadata", "minor",
               "레이블이 있는 클래스·속성 가운데 한국어(@ko) 레이블이 없는 것이 있습니다. 한 항목에 개수와 대상을 모읍니다.",
               "rdfs:label \"...\"@ko 를 더합니다."),
    "META03": ("metadata", "minor",
               "레이블이 있는 클래스·속성 가운데 영어(@en) 레이블이 없는 것이 있습니다. 한 항목에 개수와 대상을 모읍니다.",
               "rdfs:label \"...\"@en 을 더합니다."),
    "META04": ("metadata", "important",
               "클래스나 속성에 rdfs:label 이 하나도 없습니다. 화면과 보고서에 IRI 가 그대로 드러납니다.",
               "rdfs:label 을 한국어(@ko)와 영어(@en)로 붙입니다."),
    "LOGIC01": ("logic", "critical",
                "OWL 2 RL 폐포에서 owl:Nothing 에 속한 개체가 나왔습니다.",
                "그 개체의 타입과 그 타입의 제약을 살펴 서로 맞지 않는 공리나 데이터를 고칩니다."),
    "LOGIC02": ("logic", "critical",
                "서로소로 선언한 두 클래스에 동시에 속한 개체가 있습니다(추론으로 얻은 타입 포함).",
                "개체의 타입을 고치거나, 서로소 공리 또는 그 타입을 만든 도메인·레인지·하위 관계를 고칩니다."),
    "LOGIC03": ("logic", "critical",
                "두 개체가 owl:sameAs 와 owl:differentFrom(또는 owl:AllDifferent)으로 동시에 이어졌습니다.",
                "둘 가운데 잘못된 단언을 지웁니다."),
    "LOGIC04": ("logic", "critical",
                "owlrl 이 보고한 그 밖의 OWL 2 RL 모순입니다.",
                "메시지에 나온 공리와 개체를 확인해 맞지 않는 쪽을 고칩니다."),
    "LOGIC05": ("logic", "critical",
                "HermiT 가 만족불가로 판정한 클래스입니다(--reasoner hermit, Java 와 owlready2 가 있을 때만).",
                "클래스의 상위 클래스와 제약 가운데 서로 맞지 않는 것을 찾아 고칩니다."),
    "SHACL": ("shacl", "critical",
              "데이터가 SHACL 형상을 어겼습니다. 심각도는 형상의 sh:resultSeverity 를 따릅니다(sh:Violation 치명, sh:Warning 중요, sh:Info 경미).",
              "형상이 요구하는 값, 개수, 타입에 맞게 데이터를 고칩니다. 형상이 틀렸다면 형상을 고칩니다."),
    "REG01": ("registry", "info",
              "클래스의 @ko 레이블(없으면 로컬 이름)이 용어 등록부 용어의 표제어(ko)나 동의어(alt)와 표기가 같습니다. "
              "등록부 용어에 kind(property·relation)가 있으면 속성도 같은 종류끼리 맞춥니다. "
              "skos:exactMatch 후보입니다. 표제어와 같으면 일치 신뢰도 높음, 동의어로만 맞으면 낮음입니다.",
              "정의를 읽고 뜻이 같을 때만 skos:exactMatch 를 더합니다. 표기만 같고 뜻이 다르면 넣지 않습니다."),
    "REG02": ("registry", "info",
              "고르지 않은 분야의 등록부 용어와 표기만 같습니다. 뜻이 다를 수 있습니다.",
              "고른 분야의 개념이 맞다면 넣지 않습니다. 그 분야의 개념을 뜻한 것이 맞을 때만 정의를 읽고 검토합니다."),
    "REG03": ("registry", "info",
              "객체 속성이나 데이터 속성의 @ko 레이블(없으면 로컬 이름)이 등록부의 개념 용어와 표기가 같습니다. "
              "등록부 용어는 대부분 개념(클래스 성격)이라 속성과 skos:exactMatch 로 잇지 않습니다. "
              "관계 이름은 동사구로, 개념과의 연결은 range 클래스에서 하기를 권합니다.",
              "속성 이름을 「~에 입항함」처럼 동사구로 바꾸고, 개념 용어와의 skos:exactMatch 는 그 속성의 rdfs:range 클래스에 둡니다."),
}

assert set(_INFO) == set(RULE_TITLES), "규칙 설명표와 RULE_TITLES 가 어긋납니다"


def rule_info(rule_id: str) -> dict | None:
    rid = (rule_id or "").strip().upper()
    if rid not in _INFO:
        return None
    cat, sev, meaning, fix = _INFO[rid]
    out = {
        "rule": rid,
        "title": RULE_TITLES[rid],
        "category": cat,
        "category_ko": CATEGORY_KO[cat],
        "severity": sev,
        "severity_ko": SEVERITY_KO[sev] if rid != "SHACL" else "형상의 sh:resultSeverity 를 따름(기본 치명)",
        "meaning": meaning,
        "fix": fix,
    }
    if rid.startswith("P"):
        out["note"] = (f"OOPS! 함정 목록({OOPS_CATALOGUE})의 공개 설명만 참고해 다시 구현한 근사 검사입니다. "
                       "OOPS! 자체의 결과가 아니며 OOPS! 코드를 쓰지 않았습니다.")
    return out


def all_rules() -> list[dict]:
    return [rule_info(r) for r in RULE_TITLES]
