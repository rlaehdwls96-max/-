"""
Gmail에서 특정 라벨(기본값: '인사이트')이 붙은 메일을 API로 읽어와
data/raw/mail/ 에 원본(raw) + 정규화본(parsed.json)으로 저장한다.

*** 중요: 이 커넥터가 채우는 'summary'는 Gmail이 주는 본문 미리보기(snippet)일 뿐,
사람이 직접 쓰거나 LLM이 요약한 '인사이트'가 아니다. 별도로 개발 중인 메일
아카이빙 시스템(진짜 요약을 생성하는 쪽)을 대체하는 게 아니라, 라벨링만 해둔
메일을 빠르게 웨어하우스에 넣는 보조 경로로 설계했다. ***

사전 준비:
  1) Google Cloud Console에서 프로젝트 생성 -> "Gmail API" 사용 설정
  2) OAuth 클라이언트 ID(애플리케이션 유형: 데스크톱 앱) 생성 -> JSON 다운로드 후
     프로젝트 루트에 credentials.json 으로 저장 (git에 커밋하지 말 것 -> .gitignore 처리됨)
  3) pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
  4) 최초 실행 시 브라우저가 열리며 구글 로그인/동의 -> token.json 자동 생성
     (이후 실행부터는 refresh token으로 자동 재인증, 브라우저 안 뜸)
  5) (선택) .env에 GMAIL_INSIGHT_LABEL=인사이트 로 기본 라벨명을 지정 가능

실행:
  python connectors/gmail_pull.py                       # 기본 라벨 전체
  python connectors/gmail_pull.py --label "인사이트/중요"
  python connectors/gmail_pull.py --since 2026-08-01
  python connectors/gmail_pull.py --body                # snippet 대신 본문 앞부분(500자)까지 가져옴
"""
import argparse
import base64
import json
import os
import sys
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw" / "mail"
CREDENTIALS_PATH = BASE_DIR / "credentials.json"
TOKEN_PATH = BASE_DIR / "token.json"
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mail_ingest import normalize  # noqa: E402  기존 검증 로직 재사용


def _load_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(BASE_DIR / ".env")
    except ImportError:
        pass


def _get_service():
    """Gmail API 서비스 객체 생성 (최초 1회 브라우저 인증, 이후 token.json 재사용/자동 갱신)."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_PATH.exists():
                raise RuntimeError(
                    f"{CREDENTIALS_PATH} 이(가) 없습니다. Google Cloud Console에서 OAuth 클라이언트"
                    "(데스크톱 앱)를 만들고 credentials.json 으로 저장하세요."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")

    return build("gmail", "v1", credentials=creds)


def _header(headers: list, name: str) -> str | None:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value")
    return None


def _extract_domain(from_header: str | None) -> str:
    """'홍길동 <name@example.com>' 또는 'name@example.com' 모두에서 도메인만 추출."""
    if not from_header:
        return ""
    if "<" in from_header and ">" in from_header:
        email_part = from_header.split("<", 1)[1].split(">", 1)[0]
    else:
        email_part = from_header.strip()
    return email_part.split("@")[-1].strip().lower() if "@" in email_part else ""


def _decode_body_text(payload: dict, max_chars: int = 500) -> str | None:
    """multipart 구조를 순회해 text/plain 파트를 찾아 base64url 디코딩."""

    def _walk(part):
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return part["body"]["data"]
        for sub in part.get("parts", []) or []:
            found = _walk(sub)
            if found:
                return found
        return None

    data = _walk(payload)
    if not data:
        return None
    try:
        text = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")
    except Exception:
        return None
    return text.strip()[:max_chars]


def gmail_message_to_record(msg: dict, use_body: bool = False) -> dict:
    """
    Gmail API messages.get() 응답 1건을 mail_ingest.normalize()가 기대하는
    {date, subject, summary, sender_domain, importance} 형태로 변환.
    실제 API 호출 없이 단위 테스트 가능한 순수 함수.
    """
    payload = msg.get("payload", {})
    headers = payload.get("headers", [])
    subject = _header(headers, "Subject") or "(제목 없음)"
    from_header = _header(headers, "From")
    date_header = _header(headers, "Date")

    dt = None
    if date_header:
        try:
            dt = parsedate_to_datetime(date_header)
        except (TypeError, ValueError):
            dt = None
    date_str = dt.date().isoformat() if dt else None
    if not date_str and msg.get("internalDate"):
        # Date 헤더 파싱 실패 시 Gmail이 주는 internalDate(ms epoch)로 대체
        date_str = datetime.fromtimestamp(int(msg["internalDate"]) / 1000).date().isoformat()

    summary = None
    if use_body:
        summary = _decode_body_text(payload)
    if not summary:
        summary = msg.get("snippet", "")

    return {
        "date": date_str,
        "subject": subject,
        "summary": summary,
        "sender_domain": _extract_domain(from_header),
        "importance": "중",  # TODO: 라벨을 '인사이트/상' 식으로 세분화하면 여기서 매핑
    }


def pull_labeled_mail(label: str, since: str | None = None, use_body: bool = False) -> Path:
    _load_env()
    service = _get_service()

    query_parts = [f'label:"{label}"']
    if since:
        query_parts.append(f"after:{since.replace('-', '/').replace('.', '/')}")
    query = " ".join(query_parts)

    message_ids = []
    page_token = None
    while True:
        resp = service.users().messages().list(
            userId="me", q=query, pageToken=page_token, maxResults=100
        ).execute()
        message_ids.extend(m["id"] for m in resp.get("messages", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    fmt = "full" if use_body else "metadata"
    metadata_headers = None if use_body else ["Subject", "From", "Date"]

    raw_messages = []
    for mid in message_ids:
        kwargs = {"userId": "me", "id": mid, "format": fmt}
        if metadata_headers:
            kwargs["metadataHeaders"] = metadata_headers
        raw_messages.append(service.users().messages().get(**kwargs).execute())

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    stamp = f"{date.today().isoformat()}_{datetime.now().strftime('%H%M%S')}"

    raw_path = RAW_DIR / f"gmail_raw_{stamp}.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(raw_messages, f, ensure_ascii=False, indent=2)

    normalized = []
    skipped = 0
    for msg in raw_messages:
        record = gmail_message_to_record(msg, use_body=use_body)
        if not record["date"]:
            skipped += 1
            continue
        try:
            normalized.append(normalize(record))
        except ValueError:
            skipped += 1

    parsed_path = RAW_DIR / f"gmail_{stamp}.parsed.json"
    with open(parsed_path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)

    print(f"[gmail_pull] 라벨 '{label}' 원본 {len(raw_messages)}건 -> {raw_path}")
    print(f"[gmail_pull] 정규화 {len(normalized)}건(스킵 {skipped}건) -> {parsed_path}")
    return parsed_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--label",
        default=os.environ.get("GMAIL_INSIGHT_LABEL", "인사이트"),
        help="수집할 Gmail 라벨명 (기본값: 환경변수 GMAIL_INSIGHT_LABEL 또는 '인사이트')",
    )
    parser.add_argument("--since", help="YYYY-MM-DD, 이 날짜 이후 메일만", default=None)
    parser.add_argument(
        "--body", action="store_true",
        help="snippet 대신 본문 앞부분(500자)을 summary로 사용 (API 호출량 증가)",
    )
    args = parser.parse_args()
    pull_labeled_mail(label=args.label, since=args.since, use_body=args.body)
