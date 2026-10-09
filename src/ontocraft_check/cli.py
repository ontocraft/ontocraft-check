"""명령행 진입점입니다.

종료 코드: 0 기준 미만, 1 --fail-on 기준 이상의 항목이 있음, 2 입력 오류.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .graph import LoadError
from .render import render
from .runner import DEFAULT_GROUP_OVER, run


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ontocraft-check",
        description="OWL 온톨로지를 모델링 함정, 메타데이터·명명, OWL 2 RL 논리, SHACL, 용어 등록부 대조, CQ 커버리지로 검사하고 한국어 보고서를 냅니다.",
    )
    p.add_argument("ontology", help="온톨로지 파일(Turtle, RDF/XML .owl/.rdf, JSON-LD, N-Triples)")
    p.add_argument("--data", help="데이터(ABox) 파일. 논리 검사와 SHACL 검증에 씁니다")
    p.add_argument("--shapes", help="SHACL 형상 파일. --data와 함께 줘야 검증합니다")
    p.add_argument("--registry", help="용어 등록부 폴더(분야별 <분야>.json). builtin 을 주면 패키지에 넣은 OntoCraft 한국 산업 용어 등록부 공개 분야 사본과 대조합니다. 주지 않으면 대조하지 않습니다")
    p.add_argument("--cq", help="CQ(역량 질문) JSON 파일(최상위 items[]: id, q, cypher 또는 sparql). 주면 CQ 커버리지 절과 정보 항목 CQ01을 냅니다")
    p.add_argument("--cq-query-field", help="CQ 질의 필드 이름(기본: cypher, 없으면 sparql). 이름에 sparql이 들어가거나 질의가 SELECT·PREFIX로 시작하면 SPARQL로 읽습니다")
    p.add_argument("--cq-allow-labels", help="OWL에 없어도 정상인 노드 라벨(쉼표로 구분, 끝의 * 와일드카드, 예: KG_*,Concept)")
    p.add_argument("--cq-allow-relations", help="OWL에 없어도 정상인 관계 타입(쉼표로 구분, 예: BROADER,HAS_LEGAL_BASIS)")
    p.add_argument("--cq-format", choices=("auto", "default", "ontoflow"), default="auto",
                   help="CQ 파일 형식. auto(기본)는 items[].check가 있으면 ONTOFLOW 형식({id, question, check:{kind, cypher…}})으로 읽습니다")
    p.add_argument("--cq-profile", choices=("default", "ontoflow"), default="default",
                   help="CQ 이름 대응 방식. default는 라벨·영어 레이블, ontoflow는 (:Object {objectType:'X'})를 <기준>X 클래스로, "
                        "[:T]를 <기준>rel/T로, v.p를 <클래스>/p로 맞춥니다")
    p.add_argument("--cq-base", help="ontoflow 프로필의 기준 IRI 틀(예: https://ontocraft.com/ontology/{project}/). "
                                     "{project}는 질의의 projectId로 채웁니다. 없으면 온톨로지 IRI로 정합니다")
    p.add_argument("--registry-match", choices=("ko", "en", "both"), default="both",
                   help="등록부 대조 방식. ko는 @ko 레이블(없으면 로컬 이름), en은 영어 이름(@en·태그 없는 레이블·로컬 이름), "
                        "both(기본)는 한국어를 먼저 맞추고 맞지 않은 요소만 영어로 맞춥니다")
    p.add_argument("--ignore-names", help="명명·메타데이터 규칙(P08, P22, P32, LBL01, LBL02, META02~04)에서 뺄 이름 glob"
                                          "(쉼표로 구분, 예: ActionLog_*,rel/LoggedEdit_*). 로컬 이름이나 온톨로지 IRI 아래 상대 경로와 맞춥니다")
    p.add_argument("--format", choices=("md", "html", "json"), default="md", help="보고서 형식(기본 md)")
    p.add_argument("--out", help="보고서를 쓸 파일. 없으면 표준 출력")
    p.add_argument(
        "--fail-on",
        choices=("critical", "important", "minor", "none"),
        default="critical",
        help="이 심각도 이상의 항목이 있으면 종료 코드 1(기본 critical, 정보 항목은 세지 않음)",
    )
    p.add_argument(
        "--reasoner",
        choices=("rl", "hermit"),
        default="rl",
        help="논리 검사 방식. rl은 owlrl(OWL 2 RL), hermit은 rl에 더해 Java·owlready2가 있을 때 HermiT 만족불가 클래스 검사",
    )
    p.add_argument(
        "--domains",
        help="등록부 대조에서 후보로 낼 분야 id(쉼표로 구분, 예: maritime,port). 관련 분야를 함께 보고, 다른 분야와만 맞는 것은 정보 항목 REG02로 따로 냅니다",
    )
    p.add_argument(
        "--strict-domains",
        action="store_true",
        help="--domains로 고른 분야만 봅니다. 주지 않으면 등록부에 적힌 관련 분야(예: maritime이면 port)를 함께 봅니다",
    )
    p.add_argument("--disable", help="끌 규칙 id(쉼표로 구분, 예: P13,P22). 보고서 머리에 「사용자가 끈 규칙」으로 적습니다")
    p.add_argument(
        "--group-over",
        type=int,
        default=DEFAULT_GROUP_OVER,
        metavar="N",
        help=f"같은 규칙의 항목이 N개를 넘으면 md·html 보고서에서 한 항목으로 묶습니다(기본 {DEFAULT_GROUP_OVER}, 0이면 묶지 않음)",
    )
    p.add_argument("--version", action="version", version=f"ontocraft-check {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.group_over < 0:
        parser.error("--group-over는 0 이상이어야 합니다")
    try:
        report = run(
            args.ontology,
            data=args.data,
            shapes=args.shapes,
            registry_dir=args.registry,
            reasoner=args.reasoner,
            domains=args.domains,
            disable=args.disable,
            group_over=args.group_over,
            strict_domains=args.strict_domains,
            cq=args.cq,
            cq_query_field=args.cq_query_field,
            cq_allow_labels=args.cq_allow_labels,
            cq_allow_relations=args.cq_allow_relations,
            ignore_names=args.ignore_names,
            registry_match=args.registry_match,
            cq_format=args.cq_format,
            cq_profile=args.cq_profile,
            cq_base=args.cq_base,
        )
    except LoadError as exc:
        print(f"ontocraft-check: {exc}", file=sys.stderr)
        return 2
    text = render(report, args.format)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 1 if report.worst_at_least(args.fail_on) else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
