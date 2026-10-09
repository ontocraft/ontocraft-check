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
    ) -> str:
        """OWL 온톨로지를 모델링 함정, 메타데이터·명명, OWL 2 RL 논리, SHACL, 용어 등록부 대조로 검사합니다.

        ontology, data(ABox), shapes(SHACL)는 파일 경로나 본문 문자열(Turtle, RDF/XML, JSON-LD, N-Triples)입니다.
        있는 파일 경로면 경로로 읽습니다. shapes 는 data 와 함께 줘야 검증합니다.
        domains: 등록부 분야 id(예: ["maritime"]). 관련 분야(maritime 이면 port, defense)를 함께 봅니다.
        strict_domains: 참이면 관련 분야를 더하지 않습니다. disable: 끌 규칙 id(예: ["P13"]).
        format: summary(짧은 요약), json(전체 보고서), markdown(사람이 읽는 보고서).
        """
        return _guard(T.check_ontology, ontology, data=data, shapes=shapes, domains=domains,
                      disable=disable, use_registry=use_registry, format=format, strict_domains=strict_domains)

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
