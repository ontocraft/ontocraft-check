# ontocraft-check

**English summary.** ontocraft-check is an OWL ontology checker by OntoCraft. It reports modelling pitfalls (approximate re-implementations inspired by the public OOPS! pitfall catalogue), metadata and naming issues, OWL 2 RL consistency, SHACL validation, and `skos:exactMatch` candidates against a bundled snapshot of the OntoCraft Korean Industry Term Registry (CC BY 4.0). Reports are written in Korean (Markdown, HTML, JSON). It ships a command-line tool, a Python API, an MCP server for AI agents (`ontocraft-check-mcp`), and a Pyodide web worker. Files never leave your machine. Code is Apache-2.0.

OntoCraft 온톨로지 검사기(ontocraft-check)는 OWL 온톨로지를 검사해 한국어 보고서를 냅니다. 현재 버전은 0.5.0입니다. 명령행 도구, 파이썬 API, AI 에이전트용 MCP 서버, 브라우저 실행기(Pyodide)가 있습니다. 검사는 모두 이 컴퓨터 안에서 돌고, 파일을 밖으로 보내지 않습니다.

## 1. 무엇을 검사하는지

검사는 네 종류이고 서로 대신하지 않습니다. 여기에 용어 등록부 대조를 더할 수 있습니다. 항목마다 심각도(치명·중요·경미), 규칙 id, 대상 IRI, 설명, 고치는 방법을 적습니다.

| 종류 | 규칙 | 쓰는 라이브러리 |
|---|---|---|
| 모델링 함정 | P04, P06, P08, P10, P11, P13, P19, P22, P32, P34, P35, P34-EXT, P35-EXT, P38, P41, DT01 선언되지 않은 데이터 타입, LBL01 종류가 다른 요소의 같은 레이블, LBL02 같은 레이블을 가진 객체 속성 | rdflib |
| 메타데이터·명명 | META01 버전, META02 @ko 없음, META03 @en 없음, META04 레이블 없음 | rdflib |
| 논리 | LOGIC01 owl:Nothing, LOGIC02 서로소 위반, LOGIC03 sameAs·differentFrom 충돌, LOGIC04 그 밖의 OWL 2 RL 모순, LOGIC05 HermiT(선택) | owlrl, 선택 owlready2 |
| 데이터 제약 | SHACL 형상 위반. 심각도는 형상의 sh:resultSeverity를 따릅니다 | pyshacl |
| 용어 등록부 대조(선택) | REG01 skos:exactMatch 후보, REG02 다른 분야에서 같은 이름이 있음, REG03 속성 이름이 개념 용어와 같음 | 표준 라이브러리 |

- 모델링 함정과 메타데이터는 온톨로지 파일만 봅니다. 데이터 파일은 논리와 SHACL에만 씁니다.
- DT01(중요)은 데이터 속성의 rdfs:range에 쓴 데이터 타입이 내장 데이터 타입이 아니고 rdfs:Datatype 선언도 없을 때 냅니다. 내장 데이터 타입은 XSD 전부, rdf:langString, rdf:PlainLiteral, rdf:XMLLiteral, rdf:HTML, rdf:JSON, rdfs:Literal, owl:real, owl:rational입니다. 데이터 속성 제약의 값 자리(owl:someValuesFrom, owl:allValuesFrom, owl:onDataRange)와 owl:onDatatype도 봅니다. 예를 들어 geo:wktLiteral을 range로 16곳에서 쓰고 선언이 없으면 한 항목에 쓰인 곳 수(detail.count)를 적습니다. OWL 2 DL 도구가 거부하는 결함이라 중요로 둡니다. 고치는 방법은 `geo:wktLiteral a rdfs:Datatype .` 한 줄입니다. 객체 속성이나 rdf:Property의 range는 지금처럼 P34·P34-EXT가 맡습니다.
- LBL01(경미)은 같은 언어 태그에서 같은 rdfs:label(공백 정규화 후)을 가진 요소의 종류(클래스, 객체 속성, 데이터 속성, 주석 속성)가 다를 때 냅니다. 예를 들어 클래스 PortCall과 객체 속성 arrivedAt이 둘 다 「입항」이면 레이블만 보고는 클래스인지 속성인지 가릴 수 없습니다. 관계 이름은 동사구로(입항함, 정박함) 짓기를 권합니다. 추론과 OWL 2 DL 적합성에는 영향이 없어 경미로 둡니다.
- LBL01의 경계는 이렇습니다. 클래스끼리는 P32가 맡습니다. 데이터 속성끼리는 내지 않습니다. 클래스마다 속성을 따로 두는 설계(Vessel_draft와 ModelShip_draft가 둘 다 「흘수」)가 흔하기 때문입니다. 속성의 rdfs:range가 같은 레이블의 클래스이면(genre의 range가 Genre이고 둘 다 「장르」) range 이름을 그대로 쓴 관계로 보고 뺍니다.
- LBL02(경미)는 객체 속성 둘 이상이 같은 레이블을 쓸 때 냅니다(memberOf와 belongsTo가 둘 다 「소속」). 관계 이름이 겹쳐 구분이 어렵습니다. owl:equivalentProperty로 이은 속성끼리는 내지 않습니다.
- 용어 등록부 대조는 클래스의 @ko 레이블(없으면 로컬 이름)이 등록부 용어의 표제어나 동의어와 표기가 같을 때 후보(REG01)를 냅니다. 표제어와 같으면 일치 신뢰도 높음, 동의어로만 맞으면 낮음입니다. 심각도가 없는 정보 항목이라 종료 코드에 영향을 주지 않습니다.
- 등록부 용어는 대부분 개념(클래스 성격)입니다. 그래서 객체 속성이나 데이터 속성이 개념 용어와 표기가 같으면 후보로 내지 않고 REG03으로 따로 적습니다. 예를 들어 객체 속성 commandedBy의 @ko 레이블이 「선장」이면 사람 용어 「선장」과 맞추지 않습니다. 관계 이름은 동사구로 짓고, 개념과의 연결은 그 속성의 range 클래스에서 합니다.
- 등록부 용어에 선택 필드 `kind`(class, property, relation)가 있으면 같은 종류끼리만 REG01로 맞춥니다. property·relation 용어는 속성과 맞추고 클래스와는 맞추지 않습니다. 지금 내장 사본에는 이 필드가 없습니다.
- 등록부는 패키지에 넣은 사본(`--registry builtin`)이나 같은 형식의 폴더를 씁니다. 기본값은 대조하지 않는 것입니다.

규칙의 세부 정의는 MCP 도구 `explain_rule`이나 소스의 `src/ontocraft_check/rules.py`에 있습니다.

## 2. 설치

파이썬 3.11 이상이 필요합니다.

```bash
pip install ontocraft-check              # 명령행과 파이썬 API
pip install "ontocraft-check[mcp]"       # MCP 서버까지
uv tool install "ontocraft-check[mcp]"   # uv로 명령만 설치
```

PyPI에 올리기 전에는 저장소에서 설치합니다.

```bash
pip install "ontocraft-check[mcp] @ git+https://github.com/ontocraft/ontocraft-check"
```

## 3. 명령행

```bash
ontocraft-check 온톨로지.ttl
ontocraft-check 온톨로지.ttl --data 데이터.ttl --shapes shapes.ttl --format html --out 보고서.html
ontocraft-check 온톨로지.ttl --registry builtin --domains maritime,port
ontocraft-check 온톨로지.ttl --registry builtin --domains maritime --strict-domains
ontocraft-check 온톨로지.ttl --disable P13,P22 --fail-on important
```

- 입력은 Turtle, RDF/XML(.owl, .rdf), JSON-LD, N-Triples입니다. 확장자로 형식을 추정하고, 실패하면 다른 형식을 차례로 시도합니다.
- `--format`은 md(기본), html, json입니다.
- 종료 코드는 0(기준 미만), 1(`--fail-on` 기준 이상의 항목이 있음), 2(입력 파일을 읽지 못함)입니다. `--fail-on`의 기본값은 critical입니다.
- `--registry builtin`은 내장 등록부와 대조합니다. 폴더 경로를 주면 그 폴더의 `<분야>.json`을 씁니다.
- `--domains`는 후보(REG01)로 낼 분야 id입니다. 고르지 않은 분야와만 표기가 같은 것은 REG02로 따로 냅니다.
- 고른 분야에는 관련 분야를 한 단계 더해 함께 봅니다. 해사 온톨로지에는 정박지, 선석, 위험물, 적하, 양하, 항만시설, 하역 같은 항만 용어가 흔하기 때문입니다. 예를 들어 `--domains maritime`이면 port와 defense를 함께 보고, 보고서 머리와 JSON `options.related_domains`에 「관련 분야로 함께 봄: defense, port」처럼 적습니다. 관련의 관련은 더하지 않습니다.
- 관련 분야는 maritime과 port, maritime과 defense, maint와 mfg-ai, mfg-ai와 semiconductor, mfg-ai와 physical-ai입니다. 양방향으로 씁니다. 표는 내장 사본의 `manifest.json`에 있고, 폴더를 주면 그 폴더의 `domains.json`이나 `manifest.json`에 적힌 `related`를 씁니다. 둘 다 없으면 같은 기본표를 씁니다.
- `--strict-domains`를 주면 관련 분야를 더하지 않고 고른 분야만 봅니다. 해사 온톨로지라도 항만 용어를 따로 보고 싶을 때 씁니다. 처음부터 두 분야를 보려면 `--domains maritime,port`처럼 직접 고릅니다.
- `--disable`은 끌 규칙 id입니다. 끈 규칙은 보고서 머리에 적고 요약과 종료 코드에서 뺍니다. 속성 그래프(LPG) 기반 설계처럼 역관계를 일부러 두지 않으면 P13을 끕니다.
- `--group-over N`은 같은 규칙의 항목이 N개를 넘으면 md·html 보고서에서 한 항목으로 묶습니다(기본 10, 0이면 묶지 않음). JSON의 `findings`는 묶지 않습니다.
- `--reasoner hermit`은 실행 가능한 Java와 owlready2(`pip install "ontocraft-check[hermit]"`)가 있을 때만 HermiT 만족불가 검사를 더합니다. 없으면 보고서에 건너뜀으로 적습니다.

## 4. 파이썬

```python
from ontocraft_check.runner import run
from ontocraft_check.render import render

report = run("온톨로지.ttl", data="데이터.ttl", shapes="shapes.ttl",
             registry_dir="builtin", domains=["maritime"], disable=["P13"])
# 관련 분야를 더하지 않으려면 strict_domains=True 를 줍니다.
print(report.summary())
open("보고서.md", "w", encoding="utf-8").write(render(report, "md"))
```

에이전트용 함수는 `ontocraft_check.tools`에 있습니다. `check_ontology`는 파일 경로와 본문 문자열을 모두 받고, `format="summary"`면 짧은 요약 사전을 돌려줍니다. `search_terms`와 `get_term`은 내장 등록부에서 용어를 찾습니다.

## 5. MCP 서버

`ontocraft-check-mcp`는 stdio로 도는 MCP 서버입니다. 도구는 다섯 개입니다.

| 도구 | 하는 일 |
|---|---|
| `check_ontology` | ontology, data, shapes(파일 경로나 Turtle 등 본문), domains, strict_domains(기본 거짓), disable, use_registry(기본 참), format(summary, json, markdown)을 받아 검사합니다. summary는 종류별 개수, 치명·중요 항목 상위 20개, 건너뛴 검사, 이 도구로 말할 수 없는 것을 담습니다 |
| `explain_rule` | 규칙의 뜻, 심각도, 고치는 법 |
| `list_rules` | 규칙 목록 |
| `search_terms` | 내장 등록부에서 한국어 표제어·동의어, 영어, id로 찾아 id, ko, en, definition, uri, domain을 돌려줍니다 |
| `get_term` | id로 용어 하나의 공개 필드 전부와 출처를 돌려줍니다 |

Claude Code에는 다음처럼 더합니다.

```bash
claude mcp add ontocraft-check -- uvx --from "ontocraft-check[mcp]" ontocraft-check-mcp
```

Claude Desktop은 설정 파일(`claude_desktop_config.json`)에 다음을 넣습니다.

```json
{
  "mcpServers": {
    "ontocraft-check": {
      "command": "uvx",
      "args": ["--from", "ontocraft-check[mcp]", "ontocraft-check-mcp"]
    }
  }
}
```

PyPI에 올리기 전에는 `--from` 값을 `ontocraft-check[mcp] @ git+https://github.com/ontocraft/ontocraft-check`로 바꿉니다. 서버는 파일을 이 컴퓨터 밖으로 보내지 않습니다. 에이전트가 파일 경로를 주면 그 경로를 읽고, 본문을 주면 임시 파일에 써서 검사한 뒤 지웁니다.

## 6. 브라우저 실행

설치 없이 검사하려면 브라우저 실행 화면(https://ontocraft.com/tools/ontocheck)을 엽니다. 브라우저 안의 Pyodide가 이 패키지의 wheel을 돌리므로 파일이 서버로 가지 않습니다. 참고 구현은 `web/ontocraft-check-worker.js`와 `web/demo.html`입니다. worker 메시지 형식은 파일 머리의 주석에 있고, `registry`에 문자열 `"builtin"`을 주면 wheel에 든 등록부 사본과 대조합니다. `strict_domains: true`를 주면 관련 분야를 더하지 않습니다. 이 값은 참일 때만 run()에 넘기므로 0.3 wheel을 쓰는 화면도 그대로 돕니다.

## 7. 내장 용어 등록부

`src/ontocraft_check/data/registry/`에 OntoCraft 한국 산업 용어 등록부의 공개 분야 사본을 넣었습니다. 분야와 용어 수, 스냅샷 날짜는 같은 폴더의 `manifest.json`에 있습니다.

- 라이선스는 CC BY 4.0입니다. 코드의 Apache-2.0과 다릅니다. 용어를 인용할 때 출처 「OntoCraft 한국 산업 용어 등록부」와 용어 주소를 적습니다.
- 용어 주소는 `https://w3id.org/ontocraft/terms/<id>`입니다.
- 용어마다 id, ko, en, alt, kind, definition, category, broader, related, refs, example만 남겼습니다. kind는 정본에 있을 때만 옮깁니다.
- `manifest.json`의 분야마다 관련 분야 목록(`related`)이 있습니다. 정본의 `domains.json`에 `related`가 있으면 그것을 옮기고, 없으면 `src/ontocraft_check/related.py`의 기본표를 씁니다.
- 정의는 OntoCraft가 쓴 문장입니다. refs는 같은 개념을 다루는 표준의 이름이며, 정의가 표준과 같다는 뜻이 아닙니다.
- 사본은 개발자가 `python3 scripts/sync_registry.py <aki-space 경로>`로 다시 만듭니다. 손으로 고치지 않습니다.

## 8. 한계

- 모델링 함정(Pxx)은 OOPS! 함정 목록의 공개 설명을 참고해 다시 구현한 근사 검사입니다. OOPS!가 내는 결과와 개수가 다르기도 합니다.
- 논리 검사는 OWL 2 RL 규칙 수준의 일관성만 봅니다. 모순이 없다는 결과는 OWL 2 DL로도 일관하다는 뜻이 아닙니다. HermiT 경로는 Java가 있는 환경에서 실행해 확인하지 못했습니다.
- 의미 판단이 필요한 함정(P01 한 클래스에 여러 뜻, P05 잘못된 역관계, P31 잘못된 동치 관계 등)은 검사하지 않습니다.
- owl:imports를 따라가지 않습니다. 온톨로지 파일 하나만 봅니다.
- SHACL 검증은 형상이 표현한 조건만큼만 말합니다.
- 관련 분야 표는 사람이 정한 짧은 목록입니다. 관련 분야로 더한 후보는 고른 분야의 후보보다 뜻이 어긋날 가능성이 큽니다. 등록부에 kind가 없으므로, 클래스가 사건이나 관계를 뜻하더라도 개념 용어와 REG01로 맞춥니다.
- LBL01·LBL02는 공백만 정규화하고 대소문자는 구별합니다. 「Port」@en과 「port」@en은 다른 레이블로 봅니다. 레이블이 같아도 뜻이 같은지는 보지 않습니다.
- DT01은 이름 있는 데이터 타입만 봅니다. owl:imports로 가져온 어휘에 선언이 있어도 따라가지 않으므로, 이 파일에 선언을 두어야 풀립니다. 데이터 속성의 range가 클래스로 선언된 이름이면 DT01로 내지 않습니다.
- 등록부 대조는 표기만 비교합니다. 후보를 넣기 전에 정의를 읽고 뜻이 같은지 사람이 확인해야 합니다. 내장 사본은 스냅샷 날짜 이후의 등록부 변경을 담지 않습니다.

## 9. 앞으로

- 대칭(owl:SymmetricProperty)·추이(owl:TransitiveProperty) 속성 후보 제안을 검토합니다. 넣는다면 정보 수준의 제안으로 두고 기본으로 끕니다. 0.5.0에는 넣지 않았습니다.

## 10. OOPS! 고지

Pxx 번호는 OOPS!(OntOlogy Pitfall Scanner!) 함정 목록(https://oops.linkeddata.es/catalogue.jsp)의 번호를 따릅니다. DT01, LBL01, LBL02는 OOPS! 번호가 아닌 이 도구의 규칙입니다. OOPS!의 코드는 보지도 옮기지도 않았고, 공개 함정 목록의 설명 수준만 참고했습니다. 이 도구의 결과는 OOPS! 자체의 결과가 아닙니다.

## 11. 의존성과 라이선스

| 패키지 | 라이선스 | 쓰는 곳 |
|---|---|---|
| rdflib 7.6 이상 | BSD-3-Clause | 읽기, 모델링 함정, 메타데이터 |
| owlrl 7.6.2 이상 | W3C Software License(OSI 승인, BSD 계열 허용 라이선스) | OWL 2 RL 폐포 |
| pyshacl 0.40.1 이상 | Apache-2.0 | SHACL 검증 |
| mcp 2.2 이상 3 미만(선택) | MIT | MCP 서버 |
| owlready2(선택) | LGPL-3.0 | HermiT 경로. 기본 설치에 들어가지 않습니다 |

코드는 Apache-2.0입니다(Copyright 2026 OntoCraft). 전문은 `LICENSE`, 고지는 `NOTICE`에 있습니다. 내장 용어 등록부 데이터는 CC BY 4.0입니다.

## 12. 개발

```bash
uv sync --extra mcp
uv run pytest
uv build
```

mcp가 없으면 MCP 시험은 건너뜁니다. 환경 변수 `ONTOCRAFT_REGISTRY_DIR`에 정본 등록부 폴더를 주면 그 폴더로 대조하는 시험 하나가 더 돕니다. GitHub Actions가 파이썬 3.11과 3.12에서 시험을 돌립니다.

## 13. 변경 기록

### 0.5.0 (2026-10-09)

- 새 규칙 DT01(중요, 선언되지 않은 데이터 타입)을 더했습니다. 데이터 속성의 값 자리에 쓴 데이터 타입이 내장도 아니고 rdfs:Datatype 선언도 없으면 냅니다. 쓰인 곳 수를 detail.count에 적습니다.
- 새 규칙 LBL01(경미, 종류가 다른 요소의 같은 레이블)과 LBL02(경미, 같은 레이블을 가진 객체 속성)를 더했습니다. 클래스끼리는 지금처럼 P32가 맡습니다.
- `explain_rule`과 `list_rules`에 DT01, LBL01, LBL02가 있습니다. 보고서의 OOPS! 고지에 세 규칙이 OOPS! 번호가 아니라고 적습니다.
- 기존 규칙의 정의와 결과는 0.4.0과 같습니다. 새 규칙 때문에 같은 온톨로지에서도 항목 수가 늘기도 합니다.

### 0.4.0 (2026-10-09)

- 관련 분야를 함께 봅니다. `--domains`로 고른 분야에 관련 분야를 한 단계 더하고, 보고서 머리와 JSON `options.related_domains`에 밝힙니다. `--strict-domains`(파이썬 `strict_domains=True`)이면 더하지 않습니다. 내장 `manifest.json`의 분야마다 `related`가 생겼습니다.
- 등록부 후보(REG01)는 클래스만 냅니다. 객체·데이터 속성이 개념 용어와 표기가 같으면 새 규칙 REG03(정보)으로 따로 적습니다. 0.3까지는 속성도 REG01 후보로 냈습니다.
- 등록부 용어의 선택 필드 `kind`(class, property, relation)를 읽어 같은 종류끼리 맞춥니다. 지금 내장 사본에는 이 필드가 없습니다.
- MCP `check_ontology`와 브라우저 실행기가 `strict_domains`를 받습니다. `explain_rule`과 `list_rules`에 REG03이 있습니다.
- REG02와 REG03 설명의 조사를 앞말 받침에 맞춥니다(「기항」과, 「선박」과).
- 모델링 함정, 메타데이터, 논리, SHACL 검사의 규칙과 결과는 0.3.0과 같습니다.

### 0.3.0 (2026-10-09)

- 이름을 바꿨습니다. 배포 이름은 `ontocraft-check`, import 패키지는 `ontocraft_check`, 명령은 `ontocraft-check`입니다. PyPI에 다른 곳의 OntoCheck가 있어 겹치지 않게 했습니다. 보고서 머리의 도구 이름은 「OntoCraft 온톨로지 검사기(ontocraft-check)」입니다. 0.2.0 이전 이름은 `ontocheck`입니다.
- OntoCraft 한국 산업 용어 등록부의 공개 분야 사본을 넣고 `--registry builtin`(파이썬 `registry_dir="builtin"`)으로 대조합니다. 기본값은 지금처럼 대조하지 않는 것입니다.
- MCP 서버 `ontocraft-check-mcp`를 더했습니다(선택 의존성 `mcp`). 도구는 check_ontology, explain_rule, list_rules, search_terms, get_term입니다.
- 브라우저 실행기 파일 이름을 `web/ontocraft-check-worker.js`로 바꿨습니다. 메시지 형식은 0.2.0과 같고, 값을 준 선택지만 run()에 넘깁니다. `registry: "builtin"`을 받습니다.
- 검사 규칙과 결과는 0.2.0과 같습니다.

### 0.2.0 (2026-10-09)

- 등록부 대조에 분야를 구분합니다(`--domains`, REG02). 후보에 일치 신뢰도(높음·낮음)를 붙입니다.
- 같은 규칙의 항목이 많으면 보고서에서 묶습니다(`--group-over`).
- `--disable`로 규칙을 끕니다. P13 설명에 속성 그래프 기반 설계의 사정을 더했습니다.

### 0.1.0

첫 버전입니다. 모델링 함정, 메타데이터·명명, OWL 2 RL 논리, SHACL, 용어 등록부 대조를 냅니다.
