"""
전체 파이프라인 실행: DB 초기화 -> Raw to Staging -> Preprocess(검증/정제) -> Staging to Gold

실행: python pipelines/run_pipeline.py
"""
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "db"))
sys.path.insert(0, str(BASE_DIR / "pipelines"))

from init_db import init_db  # noqa: E402
import raw_to_staging  # noqa: E402
import preprocess  # noqa: E402
import staging_to_gold  # noqa: E402


def main() -> None:
    print("=== 1. DB 초기화 ===")
    init_db()

    print("\n=== 2. Raw -> Staging ===")
    raw_to_staging.run_all()

    print("\n=== 3. 전처리(검증/정제) ===")
    preprocess.run_all()

    print("\n=== 4. Staging -> Gold ===")
    staging_to_gold.run_all()

    print("\n파이프라인 완료. data/warehouse.db 확인하세요.")
    print("반려된 행이 있었다면 data/staging/rejected/ 를 확인하세요.")


if __name__ == "__main__":
    main()
