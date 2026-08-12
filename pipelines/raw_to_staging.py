"""
data/raw/{notion,erp,crm,mail} 의 원본/파싱본을 읽어
공통 스키마(date, category_id, project_id, source_id, ...)로 정제해
data/staging/*.csv 로 저장한다.

ERP/CRM은 실제 원본 컬럼명이 회사마다/파일마다 다르므로,
COLUMN_MAP 딕셔너리에서 딱 한 곳만 고치면 되도록 설계했다.
첫 실제 파일이 들어오면 여기 매핑만 채워 넣으면 된다.
"""
import json
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
STAGING_DIR = BASE_DIR / "data" / "staging"

# ---- ERP/CRM 원본 컬럼 -> 표준 컬럼 매핑 (실제 파일 받으면 여기만 수정) ----
COLUMN_MAP = {
    "erp": {
        "date": "일자",          # TODO: 실제 ERP export 컬럼명으로 교체
        "metric_type": "구분",
        "dimension_1": "품번",
        "dimension_2": "거래처",
        "metric_value": "수량",
        "metric_unit": "단위",
    },
    "crm": {
        "date": "일자",          # TODO: 실제 CRM export 컬럼명으로 교체
        "metric_type": "구분",
        "dimension_1": "고객사",
        "dimension_2": "담당자",
        "metric_value": "금액",
        "metric_unit": "단위",
    },
}


def stage_notion_daily_work() -> Path:
    """
    노션 raw JSON(Notion API 응답 원형)을 표준 컬럼으로 정제.
    실제 프로퍼티 이름은 노션 DB 스키마에 맞춰 조정 필요 (TODO 표시).
    """
    rows = []
    for jf in sorted((RAW_DIR / "notion").glob("daily_work_*.json")):
        with open(jf, "r", encoding="utf-8") as f:
            pages = json.load(f)
        for page in pages:
            props = page.get("properties", {})
            # TODO: 아래 4개 프로퍼티명은 실제 "일일 업무" DB 필드명에 맞게 조정
            title = _extract_title(props.get("이름") or props.get("Name"))
            date_val = _extract_date(props.get("날짜") or props.get("Date"))
            category = _extract_select(props.get("카테고리") or props.get("Category"))
            status = _extract_select(props.get("상태") or props.get("Status"))
            if not date_val:
                continue
            rows.append(
                {
                    "date": date_val,
                    "category_id": category or "etc",
                    "project_id": None,
                    "source_id": "notion",
                    "title": title or "(제목 없음)",
                    "status": status,
                    "notion_page_id": page.get("id"),
                }
            )

    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    out_path = STAGING_DIR / "daily_work.csv"
    pd.DataFrame(rows).to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"[raw_to_staging] daily_work {len(rows)}건 -> {out_path}")
    return out_path


def _extract_title(prop) -> str | None:
    if not prop:
        return None
    items = prop.get("title") or prop.get("rich_text") or []
    return "".join(i.get("plain_text", "") for i in items) or None


def _extract_date(prop) -> str | None:
    if not prop:
        return None
    date_obj = prop.get("date")
    return date_obj.get("start") if date_obj else None


def _extract_select(prop) -> str | None:
    if not prop:
        return None
    sel = prop.get("select")
    return sel.get("name") if sel else None


def stage_erp_crm(source: str) -> Path:
    assert source in ("erp", "crm")
    col_map = COLUMN_MAP[source]
    frames = []
    for csv_file in sorted((RAW_DIR / source).glob("*.parsed.csv")):
        df = pd.read_csv(csv_file)
        missing = [c for c in col_map.values() if c not in df.columns]
        if missing:
            print(
                f"[raw_to_staging][경고] {csv_file.name}: 매핑된 컬럼 {missing} 없음 -> "
                f"pipelines/raw_to_staging.py 의 COLUMN_MAP['{source}'] 를 실제 컬럼명으로 수정하세요. 건너뜁니다."
            )
            continue
        std = pd.DataFrame(
            {
                "date": df[col_map["date"]],
                "category_id": f"{source}_supply" if source == "erp" else "crm_sales",
                "project_id": None,
                "source_id": source,
                "metric_type": df[col_map["metric_type"]],
                "dimension_1": df[col_map["dimension_1"]],
                "dimension_2": df[col_map["dimension_2"]],
                "metric_value": pd.to_numeric(df[col_map["metric_value"]], errors="coerce"),
                "metric_unit": df[col_map["metric_unit"]],
                "origin_file": csv_file.name,
            }
        )
        frames.append(std)

    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    out_path = STAGING_DIR / f"{source}.csv"
    result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    result.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"[raw_to_staging] {source} {len(result)}행 -> {out_path}")
    return out_path


def stage_mail_insight() -> Path:
    rows = []
    for jf in sorted((RAW_DIR / "mail").glob("*.parsed.json")):
        with open(jf, "r", encoding="utf-8") as f:
            records = json.load(f)
        for r in records:
            rows.append(
                {
                    "date": r["date"],
                    "category_id": "mail_insight",
                    "project_id": None,
                    "source_id": "mail",
                    "sender_domain": r.get("sender_domain"),
                    "subject": r.get("subject"),
                    "summary": r.get("summary"),
                    "importance": r.get("importance", "중"),
                    "origin_file": jf.name,
                }
            )

    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    out_path = STAGING_DIR / "mail_insight.csv"
    pd.DataFrame(rows).to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"[raw_to_staging] mail_insight {len(rows)}건 -> {out_path}")
    return out_path


def run_all() -> None:
    stage_notion_daily_work()
    stage_erp_crm("erp")
    stage_erp_crm("crm")
    stage_mail_insight()


if __name__ == "__main__":
    run_all()
