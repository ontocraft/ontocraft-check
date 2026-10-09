# ontocraft-check

**English summary.** ontocraft-check is an OWL ontology checker by OntoCraft. It reports modelling pitfalls (approximate re-implementations inspired by the public OOPS! pitfall catalogue), metadata and naming issues, OWL 2 RL consistency, SHACL validation, `skos:exactMatch` candidates against a bundled snapshot of the OntoCraft Korean Industry Term Registry (CC BY 4.0), and competency-question (CQ) coverage: which classes, object properties and data properties your Cypher or SPARQL CQs actually touch. Since 0.7 it also matches English-only labels against the registry, skips tool-generated names from naming rules, and reads ONTOFLOW CQ catalogues. Reports are written in Korean (Markdown, HTML, JSON). It ships a command-line tool, a Python API, an MCP server for AI agents (`ontocraft-check-mcp`), and a Pyodide web worker. Files never leave your machine. Code is Apache-2.0.

OntoCraft 온톨로지 검사기(ontocraft-check)는 OWL 온톨로지를 검사해 한국어 보고서를 냅니다. 현재 버전은 0.7.0입니다. 명령행 도구, 파이썬 API, AI 에이전트용 MCP 서버, 브라우저 실행기(Pyodide)가 있습니다. 검사는 모두 이 컴퓨터 안에서 돌고, 파일을 밖으로 보내지 않습니다.

## 1. 무엇을 검사하는지

검사는 네 종류이고 서로 대신하지 않습니다. 여기에 용어 등록부 대조와 CQ 커버리지를 더할 수 있습니다. 항목마다 심각도(치명·중요·경미), 규칙 id, 대상 IRI, 설명, 고치는 방법을 적습니다.

| 종류 | 규칙 | 쓰는 라이브러리 |
|---|---|---|
| 모델링 함정 | P04, P06, P08, P10, P11, P13, P19, P22, P32, P34, P35, P34-EXT, P35-EXT, P38, P41, DT01 선언되지 않은 데이터 타입, LBL01 종류가 다른 요소의 같은 레이블, LBL02 같은 레이블을 가진 객체 속성 | rdflib |
| 메타데이터·명명 | META01 버전, META02 @ko 없음, META03 @en 없음, META04 레이블 없음 | rdflib |
| 논리 | LOGIC01 owl:Nothing, LOGIC02 서로소 위반, LOGIC03 sameAs·differentFrom 충돌, LOGIC04 그 밖의 OWL 2 RL 모순, LOGIC05 HermiT(선택) | owlrl, 선택 owlready2 |
| 데이터 제약 | SHACL 형상 위반. 심각도는 형상의 sh:resultSeverity를 따릅니다 | pyshacl |
| 용어 등록부 대조(선택) | REG01 skos:exactMatch 후보, REG02 다른 분야에서 같은 이름이 있음, REG03 속성 이름이 개념 용어와 같음 | 표준 라이브러리 |
| CQ 커버리지(선택) | 클래스·관계·데이터 속성별로 CQ가 닿는지 셈, CQ01 CQ 질의가 쓴 이름이 온톨로지에 없음 | rdflib(SPARQL 파싱), 표준 라이브러리 |

- 모델링 함정과 메타데이터는 온톨로지 파일만 봅니다. 데이터 파일은 논리와 SHACL에만 씁니다.
- DT01(중요)은 데이터 속성의 rdfs:range에 쓴 데이터 타입이 내장 데이터 타입이 아니고 rdfs:Datatype 선언도 없을 때 냅니다. 내장 데이터 타입은 XSD 전부, rdf:langString, rdf:PlainLiteral, rdf:XMLLiteral, rdf:HTML, rdf:JSON, rdfs:Literal, owl:real, owl:rational입니다. 데이터 속성 제약의 값 자리(owl:someValuesFrom, owl:allValuesFrom, owl:onDataRange)와 owl:onDatatype도 봅니다. 예를 들어 geo:wktLiteral을 range로 16곳에서 쓰고 선언이 없으면 한 항목에 쓰인 곳 수(detail.count)를 적습니다. OWL 2 DL 도구가 거부하는 결함이라 중요로 둡니다. 고치는 방법은 `geo:wktLiteral a rdfs:Datatype .` 한 줄입니다. 객체 속성이나 rdf:Property의 range는 지금처럼 P34·P34-EXT가 맡습니다.
- LBL01(경미)은 같은 언어 태그에서 같은 rdfs:label(공백 정규화 후)을 가진 요소의 종류(클래스, 객체 속성, 데이터 속성, 주석 속성)가 다를 때 냅니다. 예를 들어 클래스 PortCall과 객체 속성 arrivedAt이 둘 다 「입항」이면 레이블만 보고는 클래스인지 속성인지 가릴 수 없습니다. 관계 이름은 동사구로(입항함, 정박함) 짓기를 권합니다. 추론과 OWL 2 DL 적합성에는 영향이 없어 경미로 둡니다.
- LBL01의 경계는 이렇습니다. 클래스끼리는 P32가 맡습니다. 데이터 속성끼리는 내지 않습니다. 클래스마다 속성을 따로 두는 설계(Vessel_draft와 ModelShip_draft가 둘 다 「흘수」)가 흔하기 때문입니다. 속성의 rdfs:range가 같은 레이블의 클래스이면(genre의 range가 Genre이고 둘 다 「장르」) range 이름을 그대로 쓴 관계로 보고 뺍니다.
- LBL02(경미)는 객체 속성 둘 이상이 같은 레이블을 쓸 때 냅니다(memberOf와 belongsTo가 둘 다 「소속」). 관계 이름이 겹쳐 구분이 어렵습니다. owl:equivalentProperty로 이은 속성끼리는 내지 않습니다.
- 용어 등록부 대조는 클래스의 @ko 레이블(없으면 로컬 이름)이 등록부 용어의 표제어나 동의어와 표기가 같을 때 후보(REG01)를 냅니다. 표제어와 같으면 일치 신뢰도 높음, 동의어로만 맞으면 낮음입니다. 심각도가 없는 정보 항목이라 종료 코드에 영향을 주지 않습니다.
- 등록부 용어는 대부분 개념(클래스 성격)입니다. 그래서 객체 속성이나 데이터 속성이 개념 용어와 표기가 같으면 후보로 내지 않고 REG03으로 따로 적습니다. 예를 들어 객체 속성 commandedBy의 @ko 레이블이 「선장」이면 사람 용어 「선장」과 맞추지 않습니다. 관계 이름은 동사구로 짓고, 개념과의 연결은 그 속성의 range 클래스에서 합니다.
- 등록부 용어에 선택 필드 `kind`(class, property, relation)가 있으면 같은 종류끼리만 REG01로 맞춥니다. property·relation 용어는 속성과 맞추고 클래스와는 맞추지 않습니다. 지금 내장 사본에는 이 필드가 없습니다.
- 등록부는 패키지에 넣은 사본(`--registry builtin`)이나 같은 형식의 폴더를 씁니다. 기본값은 대조하지 않는 것입니다.
- 0.7부터 영어 대조를 더합니다(`--registry-match ko|en|both`, 기본 both). 등록부 용어의 영어 표기(en)를 요소의 @en 레이블, 언어 태그 없는 레이블, 로컬 이름을 띄어 쓴 형태(ChemicalAccident는 chemical accident)와 대소문자를 무시하고 맞춥니다. both는 한국어 대조를 먼저 하고, 한국어로 아무것도 맞지 않은 요소만 영어로 맞춥니다. 영어로 맞은 후보는 일치 신뢰도가 늘 낮음이고 「영어 이름으로 맞춤」(JSON `detail.match_lang`이 en)으로 표시합니다. 영어 대조는 REG03을 내지 않습니다. name, status 같은 일반 영어 낱말이 개념 용어와 겹쳐 잡음이 많기 때문입니다.
- 온톨로지에 @ko 레이블이 하나도 없으면 결과 요약의 상태를 「실행(@ko 레이블 0개, 한국어 표기 대조 불가)」로 적고, 건너뛴 검사 표에 「대조할 한국어 표기가 없습니다(@ko 레이블 0개)」를 적습니다. 한국어 대조 0건이 「맞는 용어가 없다」는 뜻으로 읽히지 않게 하려는 것입니다.

### 1-1. 도구가 만든 이름 건너뛰기

`--ignore-names "ActionLog_*,rel/LoggedEdit_*"`처럼 이름 glob을 주면, 맞은 요소를 명명·메타데이터 규칙(P08, P22, P32, LBL01, LBL02, META02, META03, META04)에서 뺍니다. 커널이나 도구가 만든 이름처럼 표기와 정의를 사람이 정하지 않는 요소에 씁니다.

- 패턴은 로컬 이름과, 온톨로지 IRI 아래의 상대 경로에 맞춥니다. ONTOFLOW처럼 데이터 속성 IRI가 「<기준>/클래스/속성」이면 상대 경로가 「ActionLog_x/status」이므로 `ActionLog_*` 하나로 그 클래스의 속성까지 빠집니다. 관계는 「rel/이름」으로 맞춥니다.
- 보고서 머리에 「건너뛴 이름 패턴과 건수」(패턴마다 요소 수, 클래스·속성 수)를 적습니다. JSON은 `options.ignore_names`입니다.
- P22는 다수 표기법을 셀 때도 뺀 클래스를 넣지 않습니다.
- 논리, SHACL, 그 밖의 함정 규칙(P04, P11, P13 등)과 등록부 대조, CQ 커버리지에는 쓰지 않습니다.

### 1-2. CQ 커버리지

CQ(Competency Question, 역량 질문)는 온톨로지가 답해야 할 질문입니다. `--cq`로 CQ 목록 JSON을 주면 각 질의(Cypher 또는 SPARQL)가 어느 클래스, 객체 속성(관계), 데이터 속성에 닿는지 셉니다. 클래스 단위를 넘어 관계와 데이터 속성 단위로 보는 것이 목적입니다. 과설계한 요소를 검토할 때 입력으로 씁니다.

```bash
ontocraft-check maritime.ttl --cq cq_catalog.json \
  --cq-allow-labels 'KG_*,Concept' \
  --cq-allow-relations BROADER,HAS_LEGAL_DEFINITION,HAS_LEGAL_BASIS,ANALYZES \
  --format html --out cq-report.html
```

- 입력은 JSON입니다. 최상위 `items[]`(또는 목록 자체)에 CQ마다 `id`, `q`(질문), 질의 필드를 둡니다. 질의 필드는 `cypher`, 없으면 `sparql`입니다. `--cq-query-field`로 다른 이름을 줄 수 있고, 그 이름에 sparql이 들어가거나 질의가 SELECT·PREFIX로 시작하면 SPARQL로 읽습니다. 마크다운 표는 읽지 않습니다.
- `--cq-allow-labels`와 `--cq-allow-relations`는 OWL에 없어도 정상인 라벨과 관계 타입입니다. 끝의 `*`는 접두 와일드카드입니다(`KG_*`).
- 보고서에는 요약(CQ 수, 파싱 성공·실패, 종류별 「CQ가 닿음 n / 전체 m」), 요소별 표(닿는 CQ id와 개수), CQ별 표(닿는 클래스·관계·속성), CQ가 닿지 않는 요소 목록, 파싱하지 못한 CQ가 들어갑니다. 큰 표는 접어 둡니다. JSON의 `cq`에 같은 내용이 있습니다.
- CQ01(정보)은 CQ 질의가 쓴 라벨, 관계 타입, 속성 가운데 온톨로지에도 허용 목록에도 없는 것입니다. 질의와 설계가 어긋난 후보입니다.

이름은 다음 규칙으로 맞춥니다.

| 질의의 이름 | 맞추는 온톨로지 요소 |
|---|---|
| 관계 타입(ARRIVED_AT) | 객체 속성의 rdfs:label@en. 그 레이블로 맞는 속성이 없으면 IRI 로컬 이름을 SCREAMING_SNAKE로 바꾼 이름(arrivedAt은 ARRIVED_AT) |
| 노드 라벨(Vessel) | 클래스의 IRI 로컬 이름이나 rdfs:label@en(대소문자 구별) |
| 속성 접근(v.draft, {unlocode: 'KRPUS'}) | 변수 라벨의 클래스에서 rdfs:subClassOf를 한 단계씩 올라가며, 그 클래스가 주인인 데이터 속성 가운데 이름이 같은 것. 가장 가까운 단계의 것만 셉니다 |

- 데이터 속성의 주인은 rdfs:domain(owl:unionOf 구성원 포함)과 로컬 이름 「클래스_속성」의 앞쪽 클래스입니다(Vessel_draft의 주인은 Vessel). 이름은 rdfs:label@en, 로컬 이름, 「클래스_속성」의 뒤쪽입니다. domain이 없는 데이터 속성은 어느 클래스에서도 찾지 못했을 때 마지막으로 맞춥니다.
- 변수에 라벨이 없으면((x), YIELD로 받은 변수, 목록 변수) 그 이름을 가진 데이터 속성 모두를 「모호」로 셉니다. 모호한 접근은 「닿음」에 넣지 않고 따로 셉니다.
- 하위 클래스에만 있는 속성을 상위 라벨로 읽으면 CQ01로 내고, 하위 클래스의 속성 이름을 참고로 적습니다.
- 관계 변수의 속성(r.since)은 OWL에 데이터 속성으로 없어 세지 않고 CQ별 표에만 적습니다.
- Cypher는 가벼운 정규식 파서로 읽습니다. MATCH 패턴의 (v:Label), [:TYPE], [r:TYPE|OTHER], 가변 길이 [:TYPE*1..3], 변수.속성, {속성: 값}, WHERE v:Label을 봅니다. 문자열 리터럴과 주석 안은 보지 않습니다. 괄호가 맞지 않거나 MATCH 패턴이 없으면 파싱 실패로 목록에 적습니다.
- SPARQL은 rdflib으로 파싱해 질의에 쓰인 IRI를 모읍니다. 온톨로지 파일의 접두어를 미리 넣으므로 PREFIX를 생략한 질의도 읽습니다. 우리 네임스페이스의 IRI가 선언되지 않았으면 CQ01입니다.

CQ가 닿지 않음은 지워도 된다는 뜻이 아닙니다. 데이터 적재, 화면, 외부 연계, 표준 대응처럼 CQ 밖의 근거가 있을 수 있습니다. 또 CQ를 모두 덮어도 질문이 업무에 맞는지는 판정하지 못합니다. 두 문장은 보고서에도 그대로 적습니다.

### 1-3. ONTOFLOW CQ 카탈로그

ONTOFLOW의 CQ 카탈로그 형식을 그대로 읽습니다. 최상위는 `{name, description, domain?, source?, items[]}`이고 항목은 `{id, group?, question, note?, check?}`입니다. `items[].check`가 하나라도 있으면 이 형식으로 알아봅니다. `--cq-format ontoflow`로 정할 수도 있습니다. 질의는 `check.cypher`, 질문 문장은 `question`입니다. `check`가 없는 항목은 수동 판정으로 따로 세고 커버리지 계산에서 뺍니다.

| check.kind | 닿는 요소로 세는 것 |
|---|---|
| label-exists | label을 클래스로 |
| cypher-nonzero, cypher-expect | cypher 질의(아래 프로필로 읽음) |
| project-object-count | objectType 클래스 |
| project-property-filled | objectType 클래스와 그 클래스의 property 데이터 속성 |
| project-link-nonzero | linkType 객체 속성 |

ONTOFLOW 그래프의 Cypher는 OWL IRI가 아니라 속성 그래프 패턴으로 적혀 있습니다. `--cq-profile ontoflow`를 주면 ONTOFLOW 내보내기의 IRI 규칙으로 맞춥니다.

```bash
ontocraft-check ontosafety-ontology.ttl --cq ontosafety-cq.json \
  --cq-profile ontoflow --cq-base 'https://ontocraft.com/ontology/{project}/' \
  --registry builtin --ignore-names 'ActionLog_*,rel/LoggedEdit_*' --disable P13 \
  --format html --out ontosafety-report.html
```

| Cypher에서 | 내보낸 OWL에서 |
|---|---|
| `(:Object {objectType:'Substance'})`, `WHERE s.objectType = 'Substance'`, `IN [...]` | `<기준>Substance` 클래스 |
| `-[:REFERS_TO]->`, `type(r) = 'REFERS_TO'` | `<기준>rel/REFERS_TO` 객체 속성 |
| `s.cas`, `{cas: ...}` (s의 objectType이 Substance) | `<기준>Substance/cas` 데이터 속성. 없으면 rdfs:subClassOf로 부모 클래스 IRI 아래에서 찾습니다 |

- 기준 IRI 틀의 `{project}`는 질의의 `projectId`(구조화된 check는 `check.projectId`)로 채웁니다. projectId가 없으면 온톨로지 IRI를 씁니다. `--cq-base`를 주지 않고 온톨로지 IRI가 `https://ontocraft.com/ontology/`로 시작하면 위 틀을 씁니다.
- 기준 아래에 없으면 `{project}` 자리만 다른 IRI에서 같은 이름을 찾습니다. 다른 프로젝트가 선언한 타입을 참조하는 경우입니다.
- 노드 라벨 `Object`와 속성 `projectId`, `objectType`은 운영 이름이라 세지 않습니다. NOT이 붙은 objectType·type() 비교(`WHERE NOT type(r) IN [...]`)는 읽지 않습니다.
- IRI 조각은 ONTOFLOW와 같이 공백, 꺾쇠, 큰따옴표, 중괄호, 세로줄, 캐럿, 역따옴표, 역슬래시와 `/`, `#`, `?`, `%`만 퍼센트 인코딩하고 한글은 그대로 둡니다.
- 보고서에 「ONTOFLOW IRI 규칙과 맞는 요소」(클래스, 관계, 데이터 속성 각각 맞는 수 / 전체)를 적고, 규칙과 다른 요소가 있으면 몇 개를 보입니다.
- ONTOFLOW 형식을 기본 프로필로 읽으면 `Object` 라벨이 CQ01로 나오고, 보고서에 `--cq-profile ontoflow`를 쓰라는 안내를 적습니다. 기본 프로필(라벨·영어 레이블 대응)은 0.6과 같습니다.

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
ontocraft-check 온톨로지.ttl --cq cq.json --cq-allow-labels 'KG_*'
ontocraft-check 내보내기.ttl --registry builtin --registry-match both --ignore-names 'ActionLog_*'
ontocraft-check 내보내기.ttl --cq ontoflow-cq.json --cq-profile ontoflow --cq-base 'https://ontocraft.com/ontology/{project}/'
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
- `--cq`, `--cq-query-field`, `--cq-allow-labels`, `--cq-allow-relations`는 CQ 커버리지 선택지입니다(1-2절). `--cq-format`(auto, default, ontoflow), `--cq-profile`(default, ontoflow), `--cq-base`는 ONTOFLOW 카탈로그용입니다(1-3절).
- `--registry-match`는 등록부 대조 방식(ko, en, both)입니다. 기본 both입니다.
- `--ignore-names`는 명명·메타데이터 규칙에서 뺄 이름 glob입니다(1-1절).
- `--reasoner hermit`은 실행 가능한 Java와 owlready2(`pip install "ontocraft-check[hermit]"`)가 있을 때만 HermiT 만족불가 검사를 더합니다. 없으면 보고서에 건너뜀으로 적습니다.

## 4. 파이썬

```python
from ontocraft_check.runner import run
from ontocraft_check.render import render

report = run("온톨로지.ttl", data="데이터.ttl", shapes="shapes.ttl",
             registry_dir="builtin", domains=["maritime"], disable=["P13"],
             cq="cq.json", cq_allow_labels=["KG_*"],
             registry_match="both", ignore_names=["ActionLog_*"])
# ONTOFLOW 카탈로그는 cq_profile="ontoflow", cq_base="https://ontocraft.com/ontology/{project}/" 를 더합니다.
# report.cq 에 CQ 커버리지(coverage, elements, per_cq, unreached, unresolved)가 담깁니다.
# 관련 분야를 더하지 않으려면 strict_domains=True 를 줍니다.
print(report.summary())
open("보고서.md", "w", encoding="utf-8").write(render(report, "md"))
```

에이전트용 함수는 `ontocraft_check.tools`에 있습니다. `check_ontology`는 파일 경로와 본문 문자열을 모두 받고, `format="summary"`면 짧은 요약 사전을 돌려줍니다. `search_terms`와 `get_term`은 내장 등록부에서 용어를 찾습니다.

## 5. MCP 서버

`ontocraft-check-mcp`는 stdio로 도는 MCP 서버입니다. 도구는 다섯 개입니다.

| 도구 | 하는 일 |
|---|---|
| `check_ontology` | ontology, data, shapes(파일 경로나 Turtle 등 본문), domains, strict_domains(기본 거짓), disable, use_registry(기본 참), format(summary, json, markdown)을 받아 검사합니다. cq(CQ JSON 경로나 본문), cq_query_field, cq_allow_labels, cq_allow_relations를 주면 CQ 커버리지를 더하고 summary에 cq_coverage를 싣습니다. 0.7부터 ignore_names, registry_match, cq_format, cq_profile, cq_base를 받습니다. summary는 종류별 개수, 치명·중요 항목 상위 20개, 건너뛴 검사, 이 도구로 말할 수 없는 것을 담습니다 |
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

설치 없이 검사하려면 브라우저 실행 화면(https://ontocraft.com/tools/ontocheck)을 엽니다. 브라우저 안의 Pyodide가 이 패키지의 wheel을 돌리므로 파일이 서버로 가지 않습니다. 참고 구현은 `web/ontocraft-check-worker.js`와 `web/demo.html`입니다. worker 메시지 형식은 파일 머리의 주석에 있고, `registry`에 문자열 `"builtin"`을 주면 wheel에 든 등록부 사본과 대조합니다. `strict_domains: true`를 주면 관련 분야를 더하지 않습니다. 0.6.0부터 `cq`(파일 {name, text}), `cq_query_field`, `cq_allow_labels`, `cq_allow_relations`를 받습니다. CQ 선택지도 값을 줄 때만 run()에 넘기므로 0.5 wheel을 쓰는 화면도 그대로 돕니다. 0.7.0부터 `ignore_names`(배열), `registry_match`, `cq_format`, `cq_profile`, `cq_base`를 받고, 역시 값을 줄 때만 넘깁니다. 이 값은 참일 때만 run()에 넘기므로 0.3 wheel을 쓰는 화면도 그대로 돕니다.

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
- CQ 커버리지는 질의 문장에 쓰인 이름만 봅니다. 질의가 실제로 결과를 내는지, 질문이 업무에 맞는지는 판정하지 않습니다. Cypher 파서는 정규식 근사라서 문자열 안의 라벨(labels(n) 비교 목록)이나 동적 라벨, APOC 호출 안의 이름은 놓칩니다. 같은 이름의 변수를 목록 식 안에서 다시 쓰면 바깥 변수의 라벨로 읽기도 합니다.
- 영어 대조는 낱말이 같은지만 봅니다. 영어 낱말은 뜻이 넓어(Item, Link, Status) 다른 개념과 겹치기 쉬우므로 신뢰도를 늘 낮음으로 둡니다. 내장 사본에는 화학물질, 생명과학 같은 분야가 없어 그 분야의 영어 이름은 맞을 용어가 없습니다.
- ONTOFLOW 프로필은 ONTOFLOW 내보내기의 IRI 규칙을 전제로 합니다. 다른 규칙으로 만든 OWL에 쓰면 맞는 요소가 없고, 보고서의 「ONTOFLOW IRI 규칙과 맞는 요소」에서 드러납니다. 질의의 objectType은 문자열 리터럴만 읽습니다(매개변수 `$type`은 읽지 않음).
- `--ignore-names`로 뺀 요소는 명명·메타데이터 규칙에서 보지 않았을 뿐, 이름과 정의에 문제가 없다는 뜻이 아닙니다.
- 등록부 대조는 표기만 비교합니다. 후보를 넣기 전에 정의를 읽고 뜻이 같은지 사람이 확인해야 합니다. 내장 사본은 스냅샷 날짜 이후의 등록부 변경을 담지 않습니다.

## 9. 앞으로

- 대칭(owl:SymmetricProperty)·추이(owl:TransitiveProperty) 속성 후보 제안을 검토합니다. 넣는다면 정보 수준의 제안으로 두고 기본으로 끕니다. 0.7.0에도 넣지 않았습니다.

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

### 0.7.0 (2026-10-09)

ONTOFLOW 시험(2026-10-09)에서 받은 의견 세 가지를 반영했습니다.

- 등록부 대조가 0건인 이유를 나눕니다. @ko 레이블이 하나도 없으면 결과 요약과 건너뜀 사유에 「대조할 한국어 표기가 없음(@ko 레이블 0개)」을 적습니다. 영어 대조를 더했습니다(`--registry-match ko|en|both`, 기본 both, 한국어가 먼저). 영어로 맞은 후보는 신뢰도 낮음과 「영어 이름으로 맞춤」 표시를 답니다. 기본이 both라서 @ko 레이블이 있는 온톨로지에서도 한국어로 맞지 않은 클래스에 영어 후보가 더 나올 수 있습니다. 한국어로 맞은 후보는 0.6과 같습니다.
- `--ignore-names`(로컬 이름이나 상대 경로 glob, 여러 개)를 더했습니다. 맞은 요소를 P08, P22, P32, LBL01, LBL02, META02~04에서 빼고, 보고서 머리에 패턴과 건수를 적습니다. MCP `check_ontology`와 브라우저 실행기도 받습니다.
- ONTOFLOW CQ 카탈로그(`items[].check`, 여섯 가지 kind)를 읽습니다. 자동으로 알아보거나 `--cq-format ontoflow`로 정합니다. `--cq-profile ontoflow`와 `--cq-base`로 Cypher의 objectType, 관계 타입, 속성 접근을 ONTOFLOW 내보내기 IRI에 맞춥니다. 수동 판정 항목과 알 수 없는 kind는 따로 셉니다. 보고서에 IRI 규칙과 맞는 요소 수를 적습니다.
- 기본 프로필의 CQ 결과는 0.6과 같습니다. 해사 온톨로지(flux-platform maritime.ttl 커밋본과 cq_catalog.json)는 클래스 58/203, 관계 55/133, 데이터 속성 137/835로 같습니다.
- `explain_rule`의 P08, P22, P32, META02, META03, REG01, REG02, CQ01 설명을 고쳤습니다.

### 0.6.0 (2026-10-09)

- CQ 커버리지를 더했습니다(`--cq`, `--cq-query-field`, `--cq-allow-labels`, `--cq-allow-relations`). CQ 목록 JSON의 Cypher·SPARQL 질의가 클래스, 객체 속성, 데이터 속성 각각에 닿는지 세고, 요소별 표, CQ별 표, 닿지 않는 요소 목록을 md·html·json에 냅니다. 보고서에 「CQ가 닿지 않음은 지워도 된다는 뜻이 아닙니다」와 「CQ를 모두 덮어도 질문이 업무에 맞는지는 판정하지 못합니다」를 적습니다.
- 새 정보 규칙 CQ01(CQ 질의가 쓴 이름이 온톨로지에 없음)을 더했습니다. `explain_rule`과 `list_rules`에 있습니다.
- MCP `check_ontology`와 브라우저 실행기가 CQ 입력을 받습니다. 값을 줄 때만 넘기므로 예전 화면과 wheel도 그대로 돕니다.
- 라벨 없는 변수의 속성 접근(`MATCH (n) ... n.pagerankScore`)은 계속 「모호」로 셉니다. 그 이름의 데이터 속성이 온톨로지 전체에 하나뿐이면 「후보 1개」로 표시하고 그 속성을 `unique_candidate`에 적습니다. 「닿음」에는 넣지 않고, 요약에 「모호 접근 n개 가운데 후보가 하나뿐인 것 k개」를 냅니다.
- `labels(n)`를 문자열 목록과 비교하는 꼴(`any(l IN labels(n) WHERE l IN ['Vessel','Port'])`, `'Vessel' IN labels(n)`)은 목록 안의 이름을 n의 라벨로 읽어 닿는 요소로 셉니다. CQ별 표에 「labels() 목록에서 읽음」으로 적습니다. NOT과 none() 안의 비교는 읽지 않습니다.
- `--cq`를 주지 않으면 보고서의 절 번호와 기존 규칙의 결과는 0.5.0과 같습니다.

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
