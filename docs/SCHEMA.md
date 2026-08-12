# 스키마 설계 노트

## 왜 Bronze/Silver/Gold로 나눴나
- **Raw (Bronze)**: 소스 원본을 절대 가공하지 않고 그대로 보존. ERP/CRM처럼 PDF·엑셀로
  받는 소스는 특히 원본이 사라지면 재현이 불가능하므로 원칙으로 고정.
- **Staging (Silver)**: 소스마다 다른 컬럼명/구조를 `date`, `category_id`, `project_id`,
  `source_id` 공통 컬럼으로 통일. 여기서부터 소스 차이를 신경 쓰지 않아도 됨.
- **Gold (fact 테이블 + 뷰)**: 대시보드가 바로 읽는 레이어. 소스별 fact 테이블은
  분리 유지하되, `v_activity_union` 뷰로 묶어서 일/주/월 집계.

## 왜 fact 테이블을 소스별로 분리했나
노션 업무일지, 경력·성과, ERP/CRM, 메일 인사이트는 필드 구성이 근본적으로 다릅니다.
억지로 하나의 테이블에 넣으면 컬럼이 대부분 NULL인 넓은 테이블이 되고, 나중에
소스 하나만 스키마가 바뀌어도 전체가 흔들립니다. 대신 공통 컬럼(date_id, category_id,
project_id, source_id)만 맞춰두고, `v_activity_union` 뷰에서 필요할 때만 합칩니다.

## 카테고리 체계
`dim_category`는 기존에 설계된 자비스 로그 카테고리 체계(업무자동화·수익화아이디어·학습·기타)와
겹치지 않게, MD 업무/ERP/CRM/메일/시장동향 축으로 확장했습니다. 카테고리가 늘어나면
`db/init_db.py`의 `DEFAULT_CATEGORIES`에 행만 추가하면 됩니다.

## ERP/CRM 컬럼 매핑을 코드에 하드코딩하지 않은 이유
실제 원본 파일(PDF/엑셀)의 헤더명은 아직 모릅니다. `pipelines/raw_to_staging.py`의
`COLUMN_MAP` 딕셔너리 한 곳에만 실제 컬럼명을 채우면 나머지 파이프라인은 그대로
동작하도록 분리해뒀습니다. 컬럼이 안 맞으면 조용히 죽지 않고 경고를 출력하고
해당 파일만 건너뜁니다.

## PDF vs 엑셀 처리
- 엑셀/CSV: `pandas.read_excel` / `read_csv` 그대로 사용.
- PDF: `pdfplumber`로 페이지별 표를 추출해 세로로 이어 붙임. 표가 없는(스캔 이미지)
  PDF는 별도 OCR이 필요하며 현재 범위 밖 — 에러 메시지로 명확히 안내하도록 처리.

## 메일 인사이트: 아카이빙 시스템 vs Gmail 직접 연동
`mail_ingest.py`(아카이빙 시스템 export 흡수)와 `gmail_pull.py`(Gmail API 직접 수집) 두
경로 모두 `data/raw/mail/*.parsed.json`으로 떨어지고, 이후 파이프라인은 경로를 구분하지
않습니다. 다만 `gmail_pull.py`가 채우는 summary는 Gmail의 본문 미리보기(snippet)일 뿐
사람이 정제한 인사이트가 아니므로, 정말 의미 있는 요약이 필요하면 아카이빙 시스템 쪽
데이터를 우선하는 게 맞습니다. Gmail 경로는 "라벨만 붙여둔 메일을 빠르게 웨어하우스에
넣고 싶을 때"용 보조 수단입니다.

## 전처리(preprocess.py)를 staging_to_gold와 분리한 이유
raw_to_staging이 만든 CSV를 바로 gold에 적재하면, 실제 원본에 흔한 결측치(수량 미기재
등)가 DB의 NOT NULL 제약과 충돌해 파이프라인 전체가 죽는다. 그래서 "판단(버릴지 말지)"과
"적재"를 분리했다: preprocess.py가 필수값 결측/숫자 변환 실패 행을 걸러 사유와 함께
data/staging/rejected/*.csv 로 격리하고, staging_to_gold.py는 이미 검증된 데이터만
받는다는 전제로 단순하게 유지된다. 검증 규칙이 늘어나도 preprocess.py 한 곳만 고치면 됨.

## 다음에 결정할 것
- ERP/CRM 실제 파일 확보 후 `COLUMN_MAP` 확정
- 노션 "일일 업무" DB의 실제 프로퍼티명 확인 후 `raw_to_staging.stage_notion_daily_work()`의
  TODO 부분 수정
- 메일 아카이빙 시스템 산출물 포맷 확정 후 `mail_ingest.py`의 `REQUIRED_FIELDS`/`normalize()` 조정
