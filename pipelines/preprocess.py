"""
전처리(검증/정제) 서브 모듈.

raw_to_staging.py 가 만든 data/staging/*.csv 를 읽어
  1) 필수 컬럼 결측/NaN/형변환 실패 행을 걸러내고
  2) 걸러진 행은 이유(reject_reason)와 함께 data/staging/rejected/*.csv 로 별도 보관 (버리지 않음)
  3) 통과한 행만 같은 파일명으로 data/staging/*.csv 를 덮어쓴다.

staging_to_gold.py 는 이 단계를 통과한(=검증된) 데이터만 받는다는 전제로 동작한다.
이렇게 분리해두면:
  - "이 값이 왜 빠졌는지"를 rejected 로그로 바로 확인 가능
  - staging_to_gold.py 는 적재 로직에만 집중 (검증 책임을 안 짐)
  - 나중에 검증 규칙이 늘어나도 이 파일 하나만 건드리면 됨

실행: python pipelines/preprocess.py  (보통은 run_pipeline.py 가 자동으로 호출)
"""
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
STAGING_DIR = BASE_DIR / "data" / "staging"
REJECTED_DIR = STAGING_DIR / "rejected"

# 소스별 "이 컬럼이 비어있으면(NaN/빈문자열) 못 씀" 필수 컬럼 정의.
# 검증 규칙이 늘어나면 여기만 수정하면 된다.
REQUIRED_NON_NULL = {
    "daily_work.csv": ["date", "title"],
    "erp.csv": ["date", "metric_type", "metric_value"],
    "crm.csv": ["date", "metric_type", "metric_value"],
    "mail_insight.csv": ["date", "summary"],
}

# 숫자여야 하는 컬럼: 문자/빈값이면 reject
NUMERIC_COLUMNS = {
    "erp.csv": ["metric_value"],
    "crm.csv": ["metric_value"],
}


def _is_blank(series: pd.Series) -> pd.Series:
    """NaN이거나, 문자열 strip 후 빈 문자열이면 True."""
    return series.isna() | series.astype(str).str.strip().eq("")


def clean_file(filename: str) -> tuple[int, int]:
    """
    data/staging/{filename} 을 검증해서 정상 행만 남기고 덮어쓴다.
    반환값: (통과 건수, 반려 건수)
    """
    path = STAGING_DIR / filename
    if not path.exists() or path.stat().st_size == 0:
        return 0, 0

    try:
        df = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return 0, 0
    if df.empty:
        return 0, 0

    df["reject_reason"] = ""

    # 1) 필수 컬럼 결측 체크
    for col in REQUIRED_NON_NULL.get(filename, []):
        if col not in df.columns:
            df["reject_reason"] += f"컬럼없음:{col};"
            continue
        blank = _is_blank(df[col])
        df.loc[blank, "reject_reason"] += f"필수값누락:{col};"

    # 2) 숫자 컬럼 형변환 체크 (raw_to_staging에서 이미 coerce했으므로 NaN이면 실패로 간주)
    for col in NUMERIC_COLUMNS.get(filename, []):
        if col in df.columns:
            still_bad = pd.to_numeric(df[col], errors="coerce").isna()
            df.loc[still_bad, "reject_reason"] += f"숫자변환실패:{col};"

    rejected = df[df["reject_reason"] != ""].copy()
    clean = df[df["reject_reason"] == ""].drop(columns=["reject_reason"])

    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    clean.to_csv(path, index=False, encoding="utf-8-sig")

    if not rejected.empty:
        REJECTED_DIR.mkdir(parents=True, exist_ok=True)
        rejected_path = REJECTED_DIR / filename
        rejected.to_csv(rejected_path, index=False, encoding="utf-8-sig")
        print(
            f"[preprocess] {filename}: 통과 {len(clean)}건 / 반려 {len(rejected)}건 "
            f"-> {rejected_path} (사유 확인 후 원본 수정 or COLUMN_MAP 재확인)"
        )
    else:
        print(f"[preprocess] {filename}: 통과 {len(clean)}건 / 반려 0건")

    return len(clean), len(rejected)


def run_all() -> None:
    total_clean = total_rejected = 0
    for filename in REQUIRED_NON_NULL:
        c, r = clean_file(filename)
        total_clean += c
        total_rejected += r
    print(f"[preprocess] 전체 통과 {total_clean}건 / 반려 {total_rejected}건")


if __name__ == "__main__":
    run_all()
