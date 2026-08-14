"""
db.py — SQLite 연결 + 스키마 introspection 헬퍼

설계 원칙:
- fact_dept_metric 표준 컬럼(date_id/category_id/project_id/source_id/metric_type/
  dimension_1/dimension_2/metric_value/metric_unit/origin_sheet)은 PROJECT_HANDOFF.md에
  명시되어 있으므로 그대로 사용.
- dim_date / fact_daily_work / fact_mail_insight 는 정확한 컬럼명이 인수인계 문서에
  없으므로, PRAGMA table_info로 실제 컬럼을 읽어 "그럴듯한 이름"을 추론해서 사용한다.
  실제 DB에서 다르면 CANDIDATE_* 리스트에 실제 컬럼명을 추가하면 됨.

캐시 무효화 정책:
- 모든 DB 조회 함수는 st.cache_data로 캐시되는데, 캐시 키에 db_path(문자열)만 들어가면
  pipelines/*.py를 다시 돌려서 warehouse.db "내용"이 바뀌어도 경로 문자열 자체는 그대로라
  캐시가 무효화되지 않는다 (노션에서 상태를 바꿔도 대시보드에 반영 안 되는 원인이었음).
  그래서 모든 캐시 함수는 내부적으로 파일 수정시각(get_db_mtime)을 숨은 캐시 키로 같이
  넣어서, DB 파일이 바뀌면 다음 화면 상호작용 때 자동으로 새로 읽어오도록 한다.
  주의: st.cache_data는 인자 이름이 밑줄(_)로 시작하면 그 인자를 캐시 키에서 아예
  제외해버리므로(DB 커넥션처럼 해시 불가능한 객체를 넘길 때 쓰라고 만든 기능), 무효화용
  키 인자 이름은 절대 밑줄로 시작하면 안 된다 — 그래서 mtime_key라는 이름을 쓴다.
"""

import re
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

# db.py는 항상 <프로젝트 루트>/dashboard/db.py 위치에 있다고 가정하고,
# 그 기준으로 <프로젝트 루트>/data/warehouse.db 절대경로를 자동 계산한다.
_THIS_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = str((_THIS_DIR.parent / "data" / "warehouse.db"))

CANDIDATE_DATE_COLS = [
    "date", "full_date", "date_value", "the_date", "calendar_date", "일자", "날짜",
]
CANDIDATE_WORK_NAME_COLS = ["업무명", "task_name", "title", "name"]
CANDIDATE_WORK_STATUS_COLS = ["상태", "status"]
CANDIDATE_LABEL_COLS = [
    "name", "category_name", "label", "카테고리", "카테고리명", "업무_카테고리",
    "source_name", "value",
]


def get_connection(db_path: str) -> sqlite3.Connection:
    p = Path(db_path)
    if not p.exists():
        raise FileNotFoundError(
            f"DB 파일을 찾을 수 없습니다: {db_path}\n"
            f"사이드바에서 실제 warehouse.db 경로를 확인해주세요."
        )
    return sqlite3.connect(str(p), check_same_thread=False)


def get_db_mtime(db_path: str) -> float:
    """DB 파일의 마지막 수정 시각. 캐시 무효화용 숨은 키로 사용."""
    try:
        return Path(db_path).stat().st_mtime
    except OSError:
        return 0.0


def clear_all_caches() -> None:
    st.cache_data.clear()


# ---------------------------------------------------------------------------
# 캐시된 내부 구현(mtime_key를 명시적으로 받음) + 외부에 노출되는 얇은 래퍼.
# 래퍼는 get_db_mtime(db_path)를 자동으로 계산해서 내부 구현에 넘겨준다.
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def _list_tables_cached(db_path: str, mtime_key: float) -> list[str]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def list_tables(db_path: str) -> list[str]:
    return _list_tables_cached(db_path, get_db_mtime(db_path))


@st.cache_data(show_spinner=False)
def _get_columns_cached(db_path: str, table: str, mtime_key: float) -> list[str]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return [r[1] for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def get_columns(db_path: str, table: str) -> list[str]:
    return _get_columns_cached(db_path, table, get_db_mtime(db_path))


def resolve_column(db_path: str, table: str, candidates: list[str]) -> str | None:
    """table의 실제 컬럼 중 candidates에 있는 것을 우선순위대로 찾아 반환. 없으면 None."""
    cols = get_columns(db_path, table)
    for c in candidates:
        if c in cols:
            return c
    return None


def table_exists(db_path: str, table: str) -> bool:
    return table in list_tables(db_path)


@st.cache_data(show_spinner=False)
def _run_query_cached(db_path: str, sql: str, params: tuple, mtime_key: float) -> pd.DataFrame:
    conn = get_connection(db_path)
    try:
        return pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()


def run_query(db_path: str, sql: str, params: tuple = ()) -> pd.DataFrame:
    return _run_query_cached(db_path, sql, params, get_db_mtime(db_path))


@st.cache_data(show_spinner=False)
def _get_dim_lookup_cached(db_path: str, dim_table: str, id_col: str, label_candidates: tuple, mtime_key: float) -> dict:
    if not table_exists(db_path, dim_table):
        return {}
    cols = get_columns(db_path, dim_table)
    if id_col not in cols:
        return {}
    label_col = resolve_column(db_path, dim_table, list(label_candidates))
    if not label_col:
        return {}
    df = run_query(db_path, f"SELECT {id_col} AS _id, {label_col} AS _label FROM {dim_table}")
    return dict(zip(df["_id"], df["_label"]))


def get_dim_lookup(db_path: str, dim_table: str, id_col: str, label_candidates: list[str]) -> dict:
    return _get_dim_lookup_cached(db_path, dim_table, id_col, tuple(label_candidates), get_db_mtime(db_path))


def attach_report_date(df: pd.DataFrame, db_path: str, date_id_col: str = "date_id") -> pd.DataFrame:
    """date_id 컬럼을 실제 날짜(report_date)로 변환해서 붙여준다.

    - date_id 값이 이미 'YYYY-MM-DD' 문자열이면 그대로 사용.
    - 정수 FK면 dim_date 테이블과 조인해서 실제 날짜 컬럼을 찾는다.
    - dim_date에서 날짜 컬럼을 못 찾으면 report_date는 전부 NaT.
    """
    if df.empty or date_id_col not in df.columns:
        df = df.copy()
        df["report_date"] = pd.NaT
        return df

    df = df.copy()
    non_null = df[date_id_col].dropna()
    sample_val = non_null.iloc[0] if not non_null.empty else None

    if isinstance(sample_val, str):
        df["report_date"] = pd.to_datetime(df[date_id_col], errors="coerce")
        return df

    if table_exists(db_path, "dim_date"):
        dim_cols = get_columns(db_path, "dim_date")
        id_col = "date_id" if "date_id" in dim_cols else (resolve_column(db_path, "dim_date", ["id"]) or "date_id")
        date_col = resolve_column(db_path, "dim_date", CANDIDATE_DATE_COLS)
        if date_col:
            dim = run_query(db_path, f"SELECT {id_col} AS {date_id_col}, {date_col} AS report_date FROM dim_date")
            df = df.merge(dim, on=date_id_col, how="left")
            df["report_date"] = pd.to_datetime(df["report_date"], errors="coerce")
            return df

    df["report_date"] = pd.NaT
    return df


def attach_dim_label(
    df: pd.DataFrame, db_path: str, fk_col: str, dim_table: str, dim_id_col: str,
    label_candidates: list[str], out_col: str,
) -> pd.DataFrame:
    """fk_col(예: category_id)을 dim_table과 매핑해서 out_col(예: 카테고리)로 붙여준다."""
    df = df.copy()
    if fk_col not in df.columns:
        df[out_col] = None
        return df
    lookup = get_dim_lookup(db_path, dim_table, dim_id_col, label_candidates)
    if not lookup:
        df[out_col] = df[fk_col]  # 매핑 실패 시 원래 id라도 보여줌
        return df
    df[out_col] = df[fk_col].map(lookup)
    return df


# ---------------------------------------------------------------------------
# fact_dept_metric 전용 헬퍼 (스키마가 확정돼 있으므로 직접 사용)
# ---------------------------------------------------------------------------

DEPT_METRIC_TABLE = "fact_dept_metric"

STANDARD_COLS = [
    "date_id", "category_id", "project_id", "source_id", "metric_type",
    "dimension_1", "dimension_2", "metric_value", "metric_unit", "origin_sheet",
]


@st.cache_data(show_spinner=False)
def _get_dept_metric_df_cached(
    db_path: str,
    source_ids: tuple | None,
    metric_types: tuple | None,
    date_from: str | None,
    date_to: str | None,
    mtime_key: float,
) -> pd.DataFrame:
    where = []
    params: list = []

    if source_ids:
        where.append(f"source_id IN ({','.join(['?'] * len(source_ids))})")
        params.extend(source_ids)
    if metric_types:
        where.append(f"metric_type IN ({','.join(['?'] * len(metric_types))})")
        params.extend(metric_types)

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    sql = f"SELECT * FROM {DEPT_METRIC_TABLE} {where_sql}"
    df = run_query(db_path, sql, tuple(params))

    if df.empty:
        # 필터 조건에 맞는 행이 0건이어도, 이후 로직(dropna(subset=["report_date"]) 등)이
        # 안전하게 동작하도록 report_date 컬럼을 항상 보장한다.
        df["report_date"] = pd.Series(dtype="datetime64[ns]")
        return df

    df = attach_report_date(df, db_path, "date_id")

    if date_from:
        df = df[df["report_date"] >= pd.to_datetime(date_from)]
    if date_to:
        df = df[df["report_date"] <= pd.to_datetime(date_to)]

    return df


def get_dept_metric_df(
    db_path: str,
    source_ids: list[str] | None = None,
    metric_types: list[str] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> pd.DataFrame:
    """fact_dept_metric을 조건에 맞게 조회. dim_date 조인이 가능하면 실제 date 컬럼을 붙인다."""
    return _get_dept_metric_df_cached(
        db_path,
        tuple(source_ids) if source_ids else None,
        tuple(metric_types) if metric_types else None,
        date_from,
        date_to,
        get_db_mtime(db_path),
    )


@st.cache_data(show_spinner=False)
def _get_fact_with_dims_cached(db_path: str, table: str, mtime_key: float) -> pd.DataFrame:
    if not table_exists(db_path, table):
        return pd.DataFrame()
    df = run_query(db_path, f"SELECT * FROM {table}")
    if df.empty:
        df["report_date"] = pd.Series(dtype="datetime64[ns]")
        df["카테고리"] = pd.Series(dtype="object")
        return df
    df = attach_report_date(df, db_path, "date_id")
    df = attach_dim_label(df, db_path, "category_id", "dim_category", "category_id", CANDIDATE_LABEL_COLS, "카테고리")
    return df


def get_fact_with_dims(db_path: str, table: str) -> pd.DataFrame:
    """fact_daily_work / fact_mail_insight처럼 date_id + category_id FK 패턴을 쓰는
    테이블을 통째로 읽고, report_date(dim_date)와 카테고리(dim_category) 라벨을 붙여 반환."""
    return _get_fact_with_dims_cached(db_path, table, get_db_mtime(db_path))


@st.cache_data(show_spinner=False)
def _get_distinct_values_cached(db_path: str, table: str, column: str, mtime_key: float) -> list:
    if not table_exists(db_path, table):
        return []
    cols = get_columns(db_path, table)
    if column not in cols:
        return []
    df = run_query(db_path, f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL ORDER BY {column}")
    return df[column].tolist()


def get_distinct_values(db_path: str, table: str, column: str) -> list:
    return _get_distinct_values_cached(db_path, table, column, get_db_mtime(db_path))


# ---------------------------------------------------------------------------
# 대시보드 전용 파생 테이블 (pipelines/parse_repeat.py가 REPEAT 원본에서 직접 만듦)
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def _get_dash_table_cached(db_path: str, table: str, mtime_key: float) -> pd.DataFrame:
    if not table_exists(db_path, table):
        return pd.DataFrame()
    return run_query(db_path, f"SELECT * FROM {table}")


def get_dash_repeat_sku(db_path: str) -> pd.DataFrame:
    """품번(+색상)별 1행 와이드 포맷 — 현재고/전년실매출/추가생산이 옆으로 나란히 있음."""
    return _get_dash_table_cached(db_path, "dash_repeat_sku", get_db_mtime(db_path))


def get_dash_set_ratio(db_path: str) -> pd.DataFrame:
    """세트(브라+팬티) 그룹별 판매비/재고비."""
    return _get_dash_table_cached(db_path, "dash_set_ratio", get_db_mtime(db_path))


def get_dash_group_kpi(db_path: str) -> pd.DataFrame:
    """부서 KPI(매출실적/실매출실적) — 목표/실적/달성비/전년비, 스냅샷별."""
    return _get_dash_table_cached(db_path, "dash_group_kpi", get_db_mtime(db_path))


def get_dash_group_sales_cumulative(db_path: str) -> pd.DataFrame:
    """군별(BR/PT/임부복) 품목 상세 — 월중 누적 스냅샷 원본 그대로."""
    return _get_dash_table_cached(db_path, "dash_group_sales_cumulative", get_db_mtime(db_path))


def get_dash_group_sales_weekly(db_path: str) -> pd.DataFrame:
    """군별 품목 상세 — 스냅샷 간 차감으로 계산한 실제 주간 증분값."""
    return _get_dash_table_cached(db_path, "dash_group_sales_weekly", get_db_mtime(db_path))


def extract_core_sku(sku) -> str:
    """품번에서 세트 매칭용 코어를 추출한다: 앞 3글자(브랜드 접두사, 예 VBR/VPT/VAC)를
    제거한 뒤 선행 영문자(선택)+숫자 블록까지만 남기고, 뒤에 붙는 색상/사이즈 문자는 버린다.
    예: VBRS119 -> "S119", VPTS119H -> "S119"  (같은 코어라 세트로 매칭됨)
        VPTQ379A, VPTQ379H -> 둘 다 "Q379" (BR에 Q379가 없으면 매칭 실패 = 단품으로 간주)."""
    body = str(sku)[3:]
    m = re.match(r"^[A-Za-z]*\d+", body)
    return m.group() if m else body
