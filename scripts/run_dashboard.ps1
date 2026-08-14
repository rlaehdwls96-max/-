<#
.SYNOPSIS
  DATA-analysis Streamlit 대시보드를 실행한다.

.EXAMPLE
  .\scripts\run_dashboard.ps1
#>

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Write-Host "[run_dashboard] 프로젝트 루트: $ProjectRoot"

$VenvActivate = Join-Path $ProjectRoot ".venv\Scripts\Activate.ps1"
if (Test-Path $VenvActivate) {
    Write-Host "[run_dashboard] 가상환경 활성화 중..."
    & $VenvActivate
} else {
    Write-Host "[run_dashboard] .venv를 찾을 수 없습니다 ($VenvActivate). 이미 활성화된 환경으로 계속 진행합니다." -ForegroundColor Yellow
}

Write-Host "[run_dashboard] streamlit 실행 (종료하려면 Ctrl+C)"
streamlit run dashboard\app.py
