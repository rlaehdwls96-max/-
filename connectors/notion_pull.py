"""
노션 "MD 업무 아카이브 > 일일 업무" DB를 API로 읽어와
data/raw/notion/{date}.json 형태로 원본 그대로 적재한다.

사전 준비:
  1) .env 파일에 NOTION_TOKEN=secret_xxx, NOTION_DAILY_WORK_DB_ID=xxxx 설정
  2) pip install notion-client python-dotenv

실행: python connectors/notion_pull.py --since 2026-08-01
"""
import argparse
import json
import os
from datetime import date, datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw" / "notion"


def _load_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(BASE_DIR / ".env")
    except ImportError:
        pass  # dotenv 없으면 시스템 환경변수만 사용


def pull_daily_work(since: str | None = None) -> Path:
    """
    노션 일일 업무 DB를 조회해 raw JSON으로 저장.
    NOTION_TOKEN / NOTION_DAILY_WORK_DB_ID 미설정 시 명확히 에러를 낸다.
    """
    _load_env()
    token = os.environ.get("NOTION_TOKEN")
    db_id = os.environ.get("NOTION_DAILY_WORK_DB_ID")
    if not token or not db_id:
        raise RuntimeError(
            "NOTION_TOKEN / NOTION_DAILY_WORK_DB_ID가 .env에 설정되어 있지 않습니다. "
            "노션 통합(integration) 생성 후 DB에 연결하고 .env를 채워주세요."
        )

    from notion_client import Client  # pip install notion-client

    client = Client(auth=token)

    filter_payload = None
    if since:
        filter_payload = {
            "property": "날짜",
            "date": {"on_or_after": since},
        }

    results = []
    cursor = None
    while True:
        kwargs = {"database_id": db_id, "page_size": 100}
        if filter_payload:
            kwargs["filter"] = filter_payload
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = client.databases.query(**kwargs)
        results.extend(resp["results"])
        if not resp.get("has_more"):
            break
        cursor = resp["next_cursor"]

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / f"daily_work_{date.today().isoformat()}_{datetime.now().strftime('%H%M%S')}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"[notion_pull] {len(results)}건 저장 -> {out_path}")
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", help="YYYY-MM-DD, 이 날짜 이후 항목만", default=None)
    args = parser.parse_args()
    pull_daily_work(since=args.since)
