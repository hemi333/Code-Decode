# Code Decode

AI가 써준 코드를 붙여넣으면, 무엇을 모르고 있는지 짚어주는 도구.

코드를 "설명"하지 않습니다. 공식 문서에서 근거를 가져와 **무엇을 / 왜 / 어디에 적혀 있는지**를
보여주고, 마지막에 스스로 확인할 질문을 남깁니다. 도구가 해석하지 못한 부분은
감추지 않고 "여기는 당신이 직접 물어봐야 한다"고 말합니다.

---

## 5분 만에 돌려보기

```bash
git clone <이 저장소>
cd code-decode

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env      # ANTHROPIC_API_KEY 를 채우세요
python run.py             # → http://127.0.0.1:5001
```

API 키가 없어도 **AST만 보기** 버튼은 동작합니다. 정적 분석이 어디까지 해내고
어디서 막히는지 먼저 보고 싶다면 이쪽부터 눌러보세요.

---

## 구조

```
decoder/
  analyzer.py   AST 파싱 + 심볼 해석      ← 4~5주차
  docs.py       공식 문서 조회            ← 6~7주차
  tools.py      Tool 스키마와 디스패치     ← 1~2주차
  agent.py      Tool Calling 루프         ← 1~2주차
  prompts.py    What/Why/Source/Example/Check   ← 3주차
  server.py     Flask + SSE
web/            화면
benchmarks/     고정 스니펫 5개와 실행기   ← 3주차에 확정
tests/          해석 동작 명세
```

각 파일이 커리큘럼의 어느 주차에 대응하는지 주석에 적어뒀습니다.

---

## 이 프로젝트의 핵심 문제

`sorted(GEN_IMAGES_DIR.glob("*.png"))` 를 AST로 파싱하면 이만큼만 나옵니다.

```
Call(func=Name('sorted'), args=[
  Call(func=Attribute(value=Name('GEN_IMAGES_DIR'), attr='glob'))
])
```

**"GEN_IMAGES_DIR 이라는 이름의 무언가에 .glob 을 호출했다"**가 전부입니다.
이게 `pathlib.Path.glob` 인지 AST는 모릅니다. 타입을 알아야 하기 때문입니다.

`analyzer.py` 는 4단계로 이 문제를 풉니다.

| 단계 | 방법 | 예시 |
| --- | --- | --- |
| import 맵 | `from pathlib import Path` | `Path` → `pathlib.Path` |
| 리터럴 | `out = []` | `out` → `list` |
| 클래스 호출 | `d = Path(...)` + 런타임 `isclass` 확인 | `d.glob` → `pathlib.Path.glob` |
| 반환 어노테이션 | `df = pd.read_csv(...)` 의 반환 타입 조회 | `df.groupby` → `pandas.DataFrame.groupby` |

여기까지 해도 안 되면 **해석 실패로 남기고 단서를 붙입니다.**

```json
{ "source": "r.json", "qualname": null,
  "receiver_origin": "r = client.get(...) 의 반환값" }
```

이 단서가 LLM에게 넘어가면, LLM은 아는 척하는 대신 "이 변수가 무엇인지 확인하려면
어디를 보라"고 답합니다. 실패를 감추지 않는 것이 설계 원칙입니다.

현재 벤치마크 5개 기준 해석률은 **85%** 입니다.

```bash
python -m benchmarks.run_bench --ast
```

---

## 매주 하는 일

3주차에 고정한 스니펫 5개를 매주 같은 방식으로 돌리고 결과를 비교합니다.

```bash
python -m benchmarks.run_bench --label w06     # 6주차 결과 저장
python -m benchmarks.run_bench --diff w06 w07  # 두 주차 비교
```

숫자는 출발점일 뿐입니다. 실제 비교는 `benchmarks/results/` 의 JSON을 나란히 열고
`what` / `why` / `gotcha` 를 읽으면서 합니다. **항목 수가 늘었다고 좋아진 게 아닙니다.**

프롬프트를 바꿔 비교하려면 `prompts.py` 의 `SYSTEM` 을 복사해 `SYSTEM_V2` 를 만들고
같은 스니펫에 돌린 뒤 두 결과를 나란히 놓으세요.

---

## 비용

Sonnet 5 기준 스니펫 하나 해독에 **약 $0.035** 입니다. 화면 상단에 매 실행의
토큰 수와 추정 비용이 표시됩니다.

시스템 프롬프트에 캐시를 걸어뒀습니다 (`agent.py` 의 `cache_control`). 같은
프롬프트로 연속해서 돌리는 3주차 작업에서 두 번째 호출부터 입력 비용이 1/10이 됩니다.

문서 조회 결과는 `docs.py` 의 `MAX_DOC_CHARS` 로 잘라서 넣습니다. 문서 전문을
컨텍스트에 밀어넣으면 토큰이 훅 뜁니다. 이건 비용 문제이자 품질 문제입니다 —
관련 없는 문서가 길게 붙으면 설명이 오히려 흐려집니다.

---

## 지원 범위

표준 라이브러리 전체 + `docs.py` 의 `ALLOWED_THIRD_PARTY` 에 등록된 패키지만
조회합니다. 기본값은 PIL, httpx, pandas, numpy, requests 입니다.

```python
ALLOWED_THIRD_PARTY = {
    "PIL": "https://pillow.readthedocs.io/en/stable/reference/",
    ...
}
```

**허용 목록은 지우지 마세요.** 문서 조회는 해당 모듈을 실제로 임포트합니다.
임포트는 남의 코드를 실행하는 일이고, 아무거나 임포트하게 두면 붙여넣은 코드가
곧 실행 권한이 됩니다.

"모든 파이썬 라이브러리 지원"은 스터디 기간에 불가능합니다. 범위를 좁게 잡고
남는 시간을 설명 품질에 쓰는 편이 낫습니다.

---

## 테스트

```bash
python tests/test_analyzer.py     # pytest 없이도 실행됨
pytest tests/                     # 있으면 이쪽으로
```

해석되는 케이스만 테스트하지 않았습니다. **해석되지 않아야 하는 케이스**도 함께
고정해뒀습니다. 컨텍스트 없는 스니펫이 조용히 성공하기 시작하면 그건 어딘가에서
추측이 들어갔다는 뜻이기 때문입니다.

---

## 이 코드를 그대로 쓰지 마세요

스터디의 목적은 도구를 갖는 것이 아니라 만들면서 이해하는 것입니다.
이 저장소는 참고용 구현이고, 다음 두 곳은 일부러 결론을 열어뒀습니다.

**5주차의 선택.** 심볼 해석을 (a) LLM 추론 / (b) jedi·pyright 정적 해석 /
(c) 런타임 inspect 중 무엇으로 할지는 스터디가 정할 문제입니다. 여기서는
(b)+(c) 혼합을 골랐지만, (a)가 더 나은 팀도 있습니다. `analyzer.py` 의
`_resolve` 를 통째로 갈아끼우면 됩니다.

**3주차의 프롬프트.** `prompts.py` 의 `SYSTEM` 은 초안입니다. 좋은 설명이
무엇인지는 팀이 정의해야 하고, 그 정의가 벤치마크 5개의 기대 결과
(`benchmarks/snippets.py` 의 `expect`)에 적혀야 합니다.

커밋 전에 자기가 만진 코드에 What/Why 한 줄을 남기는 규칙을 권합니다.
AI가 만든 코드를 이해하자는 도구를, AI가 만들어준 코드를 이해하지 않은 채
만들게 되는 게 이 프로젝트의 가장 흔한 실패입니다.
