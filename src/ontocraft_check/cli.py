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
        description="OWL 온톨로지를 모델링 함정, 메타데이터·명명, OWL 2 RL 논리, SHACL, 용어 등록부 대조로 검사하고 한국어 보고서를 냅니다.",
    )
    p.add_argument("ontology", help="온톨로지 파일(Turtle, RDF/XML .owl/.rdf, JSON-LD, N-Triples)")
    p.add_argument("--data", help="데이터(ABox) 파일. 논리 검사와 SHACL 검증에 씁니다")
    p.add_argument("--shapes", help="SHACL 형상 파일. --data와 함께 줘야 검증합니다")
    p.add_argument("--registry", help="용어 등록부 폴더(분야별 <분야>.json). builtin 을 주면 패키지에 넣은 OntoCraft 한국 산업 용어 등록부 공개 분야 사본과 대조합니다. 주지 않으면 대조하지 않습니다")
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
        help="등록부 대조에서 후보로 낼 분야 id(쉼표로 구분, 예: maint,maritime). 다른 분야와만 맞는 것은 정보 항목 REG02로 따로 냅니다",
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
