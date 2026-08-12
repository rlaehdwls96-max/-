"""
별도로 개발 중인 메일 인사이트 아카이빙 시스템의 산출물을 흡수하는 커넥터.

전제: 아카이빙 시스템이 레코드 단위 JSON(list of dict)을 뱉는다고 가정.
      각 레코드는 최소한 date, subject, summary를 포함해야 함.
      실제 산출 포맷이 확정되면 REQUIRED_FIELDS와 normalize()만 수정하면 된다.

실행: python connectors/mail_ingest.py --file "path/to/archive_export.json"
"""
import argparse
import json
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw" / "mail"

REQUIRED_FIELDS = {"date", "subject", "summary"}


def normalize(record: dict) -> dict:
    """아카이빙 시스템 산출물의 필드명이 다르면 여기서 매핑."""
    missing = REQUIRED_FIELDS - record.keys()
    if missing:
        raise ValueError(f"필수 필드 누락: {missing} (record={record})")
    return {
        "date": record["date"],
        "sender_domain": record.get("sender_domain") or record.get("sender", ""),
        "subject": record["subject"],
        "summary": record["summary"],
        "importance": record.get("importance", "중"),
    }


def import_export(file_path: str) -> Path:
    src_path = Path(file_path).expanduser().resolve()
    if not src_path.exists():
        raise FileNotFoundError(src_path)

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    # 원본 보존
    dest_original = RAW_DIR / src_path.name
    if dest_original.resolve() != src_path:
        shutil.copy2(src_path, dest_original)

    with open(src_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    normalized = [normalize(r) for r in records]

    parsed_path = RAW_DIR / f"{src_path.stem}.parsed.json"
    with open(parsed_path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)

    print(f"[mail_ingest] 원본 보존 -> {dest_original}")
    print(f"[mail_ingest] 정규화({len(normalized)}건) -> {parsed_path}")
    return parsed_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True, help="메일 아카이빙 시스템 export 파일 (JSON)")
    args = parser.parse_args()
    import_export(args.file)
