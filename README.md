# DATA-analysis

AI 및 데이터 분석을 통한 상품기획 MD 파일 — 개인 업무/경력/ERP·CRM/메일 인사이트를
하나의 로컬 데이터 웨어하우스로 모아 일/주/월/시장동향 대시보드로 보기 위한 프로젝트.

## 구조

```
DATA-analysis/
├── connectors/        # 소스별 수집기 (원본 -> data/raw)
│   ├── notion_pull.py     # 노션 "일일 업무" DB API pull
│   ├── erp_import.py      # ERP/CRM: PDF/엑셀 원본 -> raw + parsed.csv
│   └── mail_ingest.py     # 메일 아카이빙 시스템 산출물 흡수
├── pipelines/          # Raw -> Staging -> Gold 변환
│   ├── raw_to_staging.py
│   ├── staging_to_gold.py
│   └── run_pipeline.py    # 전체 실행 오케스트레이터
├── db/
│   ├── schema.sql          # dim/fact 테이블 + 일/주/월 요약 뷰
│   └── init_db.py
├── data/
│   ├── raw/{notion,erp,crm,mail}/   # 원본 그대로 보존 (git 추적 안 함)
│   ├── staging/                     # 정제된 중간 CSV (git 추적 안 함)
│   └── warehouse.db                 # 최종 SQLite (git 추적 안 함)
├── dashboard/           # 다음 단계: UI 구현 예정
└── docs/
    └── SCHEMA.md
```

## 데이터 흐름

`Raw(원본 보존)` → `Staging(공통 컬럼으로 정제)` → `Gold(fact 테이블 + 요약 뷰)` → `대시보드`

자세한 스키마 설명은 [docs/SCHEMA.md](docs/SCHEMA.md) 참고.

## 설치

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

`.env` 파일 생성 (노션 연동 시):
```
NOTION_TOKEN=secret_xxx
NOTION_DAILY_WORK_DB_ID=xxxxxxxx
```

## 사용법

### 1) ERP/CRM 원본 넣기 (PDF/엑셀)
```bash
python connectors/erp_import.py --file "공급계획_2608.xlsx" --source erp
python connectors/erp_import.py --file "매출현황.pdf" --source crm
```
> 실제 원본을 받은 뒤 `pipelines/raw_to_staging.py`의 `COLUMN_MAP`에서
> 컬럼명을 실제 파일 헤더에 맞게 한 번만 고쳐주면 됩니다.

### 2) 노션 pull
```bash
python connectors/notion_pull.py --since 2026-08-01
```

### 3) 메일 인사이트 흡수
```bash
python connectors/mail_ingest.py --file "archive_export.json"
```

### 4) 전체 파이프라인 실행 (DB 초기화 + 정제 + 적재)
```bash
python pipelines/run_pipeline.py
```

## 다음 단계

- [x] 폴더 구조 / DB 스키마
- [x] 커넥터 스켈레톤 (notion / erp-crm / mail)
- [x] raw -> staging -> gold 파이프라인
- [ ] 실제 소스 연결 및 COLUMN_MAP 확정
- [ ] 대시보드 UI (dashboard/)
