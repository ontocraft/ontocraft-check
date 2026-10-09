"""MCP 서버입니다(stdio). 설치: pip install "ontocraft-check[mcp]", 실행: ontocraft-check-mcp

도구 다섯 개를 냅니다: check_ontology, explain_rule, list_rules, search_terms, get_term.
"""

from __future__ import annotations

import json
import sys
from typing import Literal

from . import TOOL_NAME, TOOL_TITLE, __version__
from . import tools as T
from .graph import LoadError
from .terms import list_builtin_domains

try:
    from mcp.server.mcpserver import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # pragma: no cover - mcp 가 없을 때
    MCPServer = None
    ToolError = None

INSTRUCTIONS = f"""{TOOL_TITLE} {__version__}: OWL 온톨로지를 검사하고 OntoCraft 한국 산업 용어 등록부에서 용어를 찾습니다.
- 파일은 이 컴퓨터 밖으로 보내지 않습니다. 검사와 용어 찾기는 모두 이 컴퓨터 안에서 돕니다.
- check_ontology 는 파일 경로나 Turtle 등 본문 문자열을 받습니다. 기본 format=summary 는 짧은 요약입니다.
- 모델링 함정(Pxx)은 OOPS! 공개 설명을 참고해 다시 구현한 근사 검사입니다. 논리 검사는 OWL 2 RL 수준이라 모순이 없다는 결과가 OWL 2 DL 일관성을 뜻하지 않습니다. 의미 판단이 필요한 함정은 검사하지 않습니다.
- 등록부 후보(REG01)는 클래스만, 표기만 같은 것입니다. 속성이 개념 용어와 같으면 REG03 입니다. get_term 으로 정의를 읽고 뜻이 같을 때만 skos:exactMatch 를 제안합니다.
- check_ontology 에 cq(역량 질문 JSON)를 주면 관계·데이터 속성 단위 CQ 커버리지를 셉니다. 닿지 않은 요소는 지워도 된다는 뜻이 아닙니다. ONTOFLOW 카탈로그는 cq_profile="ontoflow" 로 읽습니다.
- 레이블이 영어뿐인 온톨로지도 등록부와 영어 이름으로 맞춥니다(신뢰도 낮음). 도구가 만든 이름은 ignore_names 로 명명 규칙에서 뺍니다.
- 등록부는 공개 분야 사본이고 CC BY 4.0 입니다. 용어를 인용할 때 출처 「OntoCraft 한국 산업 용어 등록부」와 주소를 적습니다."""


def _dump(x) -> str:
    return x if isinstance(x, str) else json.dumps(x, ensure_ascii=False, indent=1)


def _guard(fn, *a, **kw) -> str:
    try:
        return _dump(fn(*a, **kw))
    except (T.InputError, LoadError) as exc:
        raise ToolError(str(exc)) from exc


def build_server():
    if MCPServer is None:
        raise RuntimeError('mcp 패키지가 없습니다. pip install "ontocraft-check[mcp]" 로 설치합니다.')
    domains = ", ".join(d["id"] for d in list_builtin_domains())
    server = MCPServer(TOOL_NAME, title=TOOL_TITLE, version=__version__, instructions=INSTRUCTIONS,
                       website_url="https://github.com/ontocraft/ontocraft-check")

    @server.tool()
    def check_ontology(
        ontology: str,
        data: str | None = None,
        shapes: str | None = None,
        domains: list[str] | None = None,
        disable: list[str] | None = None,
        use_registry: bool = True,
        format: Literal["summary", "json", "markdown"] = "summary",
        strict_domains: bool = False,
        cq: str | None = None,
        cq_query_field: str | None = None,
        cq_allow_labels: list[str] | None = None,
        cq_allow_relations: list[str] | None = None,
        ignore_names: list[str] | None = None,
        registry_match: Literal["ko", "en", "both"] = "both",
        cq_format: Literal["auto", "default", "ontoflow"] = "auto",
        cq_profile: Literal["default", "ontoflow"] = "default",
        cq_base: str | None = None,
    ) -> str:
        """OWL 온톨로지를 모델링 함정, 메타데이터·명명, OWL 2 RL 논리, SHACL, 용어 등록부 대조, CQ 커버리지(선택)로 검사합니다.

        ontology, data(ABox), shapes(SHACL)는 파일 경로나 본문 문자열(Turtle, RDF/XML, JSON-LD, N-Triples)입니다.
        있는 파일 경로면 경로로 읽습니다. shapes 는 data 와 함께 줘야 검증합니다.
        domains: 등록부 분야 id(예: ["maritime"]). 관련 분야(maritime 이면 port, defense)를 함께 봅니다.
        strict_domains: 참이면 관련 분야를 더하지 않습니다. disable: 끌 규칙 id(예: ["P13"]).
        format: summary(짧은 요약), json(전체 보고서), markdown(사람이 읽는 보고서).
        cq: CQ(역량 질문) JSON 파일 경로나 본문(items[]: id, q, cypher 또는 sparql). 주면 CQ 커버리지를 셉니다.
        cq_query_field: 질의 필드 이름(기본 cypher, 없으면 sparql).
        cq_allow_labels, cq_allow_relations: OWL 에 없어도 정상인 라벨·관계 타입(예: ["KG_*", "Concept"]).
        CQ가 닿지 않는 요소는 지워도 된다는 뜻이 아닙니다(데이터·화면·외부 연계 근거가 있을 수 있음).
        ignore_names: 명명·메타데이터 규칙(P08, P22 등)에서 뺄 이름 glob(예: ["ActionLog_*"]). 도구가 만든 이름에 씁니다.
        registry_match: 등록부 대조 방식. ko, en(영어 이름, 신뢰도 낮음), both(기본, 한국어가 먼저).
        cq_format: auto(기본, items[].check 가 있으면 ONTOFLOW 형식), default, ontoflow.
        cq_profile: ontoflow 면 (:Object {objectType:'X'})를 <기준>X, [:T]를 <기준>rel/T, v.p 를 <클래스>/p 로 맞춥니다.
        cq_base: ontoflow 프로필의 기준 IRI 틀(예: "https://ontocraft.com/ontology/{project}/").
        """
        return _guard(T.check_ontology, ontology, data=data, shapes=shapes, domains=domains,
                      disable=disable, use_registry=use_registry, format=format, strict_domains=strict_domains,
                      cq=cq, cq_query_field=cq_query_field, cq_allow_labels=cq_allow_labels,
                      cq_allow_relations=cq_allow_relations, ignore_names=ignore_names,
                      registry_match=registry_match, cq_format=cq_format, cq_profile=cq_profile, cq_base=cq_base)

    @server.tool()
    def explain_rule(rule_id: str) -> str:
        """규칙(예: P11, META02, LOGIC02, REG01)의 뜻, 심각도, 고치는 법을 돌려줍니다."""
        return _guard(T.explain_rule, rule_id)

    @server.tool()
    def list_rules() -> str:
        """검사 규칙 목록(id, 제목, 검사 종류, 심각도)을 돌려줍니다."""
        return _guard(T.list_rules)

    @server.tool(description=(
        "내장 OntoCraft 한국 산업 용어 등록부에서 한국어 표제어·동의어, 영어, id 로 용어를 찾습니다. "
        f"id, ko, en, definition, uri, domain 을 돌려줍니다. domain 은 다음 가운데 하나입니다: {domains}."))
    def search_terms(query: str, domain: str | None = None, limit: int = 10) -> str:
        return _guard(T.search_terms, query, domain=domain, limit=limit)

    @server.tool()
    def get_term(id: str) -> str:  # noqa: A002
        """용어 id(또는 https://w3id.org/ontocraft/terms/<id>)로 정의, 동의어, 상위·관련 용어, 참고 표준, 쓰임 예를 돌려줍니다."""
        return _guard(T.get_term, id)

    return server


def main() -> int:
    try:
        server = build_server()
    except RuntimeError as exc:
        print(f"{TOOL_NAME}-mcp: {exc}", file=sys.stderr)
        return 2
    server.run("stdio")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
