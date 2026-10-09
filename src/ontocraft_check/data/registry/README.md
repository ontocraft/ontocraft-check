# 내장 용어 등록부 사본

OntoCraft 한국 산업 용어 등록부(OntoCraft Korean Industry Term Registry)의 공개 분야 사본입니다.

- 라이선스: CC BY 4.0(https://creativecommons.org/licenses/by/4.0/). 코드의 Apache-2.0과 다릅니다.
- 출처 표시: 「OntoCraft 한국 산업 용어 등록부」, OntoCraft.
- 용어 주소: https://w3id.org/ontocraft/terms/<id>
- 스냅샷 날짜와 분야별 용어 수: `manifest.json`
- 용어마다 id, ko, en, alt, kind, definition, category, broader, related, refs, example만 남겼습니다. kind는 정본에 있을 때만 옮깁니다.
- `manifest.json`의 분야마다 관련 분야 목록(related)이 있습니다. 검사기는 `--domains`로 고른 분야에 이 분야를 한 단계 더해 봅니다.

이 폴더는 `scripts/sync_registry.py` 가 만듭니다. 손으로 고치지 않습니다.
