"""
사내 ERP/CRM은 API 연동이 안 되고 PDF 또는 엑셀(행 단위 원본)로 제공된다는 전제.
이 커넥터는:
  1) 원본 파일을 data/raw/{erp|crm}/ 로 손대지 않고 그대로 보존 (원본 무결성)
  2) 엑셀/CSV는 표를 그대로, PDF는 표를 추출해서
     같은 폴더에 <원본이름>.parsed.csv 로 파싱본을 나란히 저장
     -> staging 단계는 이 .parsed.csv만 읽는다.

지원 포맷: .xlsx, .xls, .csv, .pdf

실행 예:
  python connectors/erp_import.py --file "공급계획_2608.xlsx" --source erp
  python connectors/erp_import.py --file "매출현황.pdf" --source crm
"""
import argparse
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _raw_dir(source: str) -> Path:
    if source not in ("erp", "crm"):
        raise ValueError("source는 'erp' 또는 'crm' 이어야 합니다.")
    d = BASE_DIR / "data" / "raw" / source
    d.mkdir(parents=True, exist_ok=True)
    return d


def _parse_excel_or_csv(path: Path):
    import pandas as pd

    if path.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(path)
    return pd.read_csv(path)


def _parse_pdf(path: Path):
    """PDF 내 표를 추출해 하나의 DataFrame으로 합친다 (페이지별 표를 세로로 concat)."""
    import pandas as pd

    try:
        import pdfplumber
    except ImportError as e:
        raise RuntimeError(
            "PDF 파싱에는 pdfplumber가 필요합니다. pip install pdfplumber"
        ) from e

    frames = []
    with pdfplumber.open(path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            for table in page.extract_tables():
                if not table or len(table) < 2:
                    continue
                header, *rows = table
                df = pd.DataFrame(rows, columns=header)
                df["__source_page"] = page_num
                frames.append(df)

    if not frames:
        raise RuntimeError(f"{path.name}에서 표를 찾지 못했습니다. 스캔본(이미지) PDF일 수 있습니다.")

    return pd.concat(frames, ignore_index=True)


def import_file(file_path: str, source: str) -> Path:
    """원본 보존 + 파싱본 생성. 반환값은 파싱본(.parsed.csv) 경로."""
    src_path = Path(file_path).expanduser().resolve()
    if not src_path.exists():
        raise FileNotFoundError(src_path)

    raw_dir = _raw_dir(source)

    # 1) 원본 그대로 복사 (raw layer 원칙: 원본 불변)
    dest_original = raw_dir / src_path.name
    if dest_original.resolve() != src_path:
        shutil.copy2(src_path, dest_original)

    # 2) 파싱본 생성
    suffix = src_path.suffix.lower()
    if suffix in (".xlsx", ".xls", ".csv"):
        df = _parse_excel_or_csv(src_path)
    elif suffix == ".pdf":
        df = _parse_pdf(src_path)
    else:
        raise ValueError(f"지원하지 않는 포맷: {suffix} (xlsx/xls/csv/pdf만 지원)")

    parsed_path = raw_dir / f"{src_path.stem}.parsed.csv"
    df.to_csv(parsed_path, index=False, encoding="utf-8-sig")

    print(f"[erp_import] 원본 보존 -> {dest_original}")
    print(f"[erp_import] 파싱본({len(df)}행) -> {parsed_path}")
    return parsed_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True, help="ERP/CRM 원본 파일 경로 (xlsx/xls/csv/pdf)")
    parser.add_argument("--source", required=True, choices=["erp", "crm"])
    args = parser.parse_args()
    import_file(args.file, args.source)
