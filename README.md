# MD Data Analysis

사내 ERP 데이터를 직접 분석해 **원가관리, REPEAT(리피트) 물량 소진율·발주타이밍 추적, 부서 KPI 관리**를
자동화하기 위한 개인 데이터 웨어하우스 + 대시보드 프로젝트입니다.

> 이 레포의 핵심은 ERP 기반 정량 분석입니다. Notion/Gmail 연동은 업무 맥락을 보강하는 보조 커넥터이며,
> 대시보드의 주 기능(REPEAT 소진율, 발주타이밍, 군별 KPI)과는 별개로 동작합니다.

## 무엇을 하는 프로젝트인가

1. **REPEAT SKU 발주타이밍 관리**: 품번×색상별 현재고와 전년동기 판매추이로 소진예상개월을 계산하고,
   군별 최소 리드타임(브라 3개월 / 팬티 2개월)을 반영해 "지금 발주해야 하는 SKU"를 자동으로 표시합니다.
2. **군별 KPI 추적**: VBR/VPT/HBR/HPT/VFS/VDW/VHS 7개 군 기준으로 목표 대비 달성률, 주간 실적 증분을 확인합니다.
3. **원가/공급계획 통합 뷰**: 공급계획서, 상판수량, 생산계획 등 ERP 추출 데이터를 하나의 웨어하우스로 모아
   부서 실적 추이(전년대비 포함)를 시계열로 봅니다.

## 아키텍처

ERP/Notion/Gmail 원본 데이터 → Bronze(`data/raw`) → Silver(`data/staging`) → Gold(SQLite `data/warehouse.db`)
→ Streamlit 대시보드(`dashboard/app.py`)

3계층 구조를 쓰는 이유는, 원본 파일 포맷이 바뀌거나 파싱 로직에 문제가 생겼을 때 어느 단계에서 깨졌는지
바로 추적하기 위함입니다.

## 데이터 소스

| 구분 | 소스 | 용도 |
|---|---|---|
| 메인 | ERP 추출 파일 (공급계획서, REPEAT_BR/PT/SL, 상판수량, 생산계획 등) | 원가관리, REPEAT 소진율, 군별 실적 |
| 보조 | Notion (일일업무 DB) | 업무 로그 요약 |
| 보조 | Gmail (라벨링된 업무 메일) | 메일 기반 업무 인사이트 요약 |

## 폴더 구조

```
connectors/   외부 소스 연결 (notion_pull.py, gmail_pull.py) — 보조 데이터용
pipelines/    ERP 원본 파서 + Bronze→Silver→Gold 변환 로직 (프로젝트의 핵심)
dashboard/    Streamlit 대시보드 (app.py, db.py)
db/           SQLite 스키마/마이그레이션
data/         raw / staging / warehouse.db (Gold)
docs/         설계 문서, 용어 정의 (군/대분류 매핑 등)
scripts/      PowerShell 실행 스크립트 (run_pipeline.ps1, run_dashboard.ps1)
```

## 대시보드 구성

- **Tab1 일/주/월 리포트**: 업무 로그 + ERP 지표 요약
- **Tab2 실적 추이**: 부서 지표 시계열, 전년대비(YoY) 비교
- **Tab3 REPEAT SKU 관리**: 현재고, 소진예상개월, 소진상태, **군별 최소 리드타임 반영 발주타이밍 알림**
- **Tab4 군별 실적**: 목표 대비 달성률 KPI, 군별 주간 실적 증분

## 실행 방법 (PowerShell)

```powershell
cd DATA-analysis-with-git\DATA-analysis
.\.venv\Scripts\Activate.ps1

# 파이프라인 전체 실행 (혹은 -Step notion / staging / repeat / weekly / all)
.\scripts\run_pipeline.ps1 -Step all

# 대시보드 실행
.\scripts\run_dashboard.ps1
```

각 스크립트는 `-DryRun` 옵션으로 실제 실행 전 명령어만 미리 확인할 수 있습니다.

## 참고

- 노션/엑셀 원본이 바뀌면 파이프라인 3단계(`notion_pull.py` → `raw_to_staging.py` → `staging_to_gold.py`)를
  다시 돌려야 Gold 테이블과 대시보드에 반영됩니다. 배치 방식이며 실시간 동기화는 아닙니다.
- 리드타임/안전마진 등 발주타이밍 계산에 쓰이는 상수는 `pipelines/parse_repeat.py` 상단에서 관리합니다.
