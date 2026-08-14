<#
.SYNOPSIS
  DATA-analysis ETL 파이프라인을 단계별로 실행한다.

.PARAMETER Step
  notion / staging / repeat / weekly / all 중 하나. 기본값 all.

.PARAMETER DryRun
  이 스위치를 주면 실제로 실행하지 않고, 실행될 python 명령어만 출력한다.

.EXAMPLE
  .\scripts\run_pipeline.ps1 -Step repeat -DryRun
  .\scripts\run_pipeline.ps1 -Step all
#>

param(
    [ValidateSet("notion", "staging", "repeat", "weekly", "all")]
    [string]$Step = "all",

    [switch]$DryRun
)

# 이 스크립트 파일 자신의 위치를 기준으로 프로젝트 루트를 찾는다.
# 어느 폴더에서 실행하든(scripts 안에서든, 루트에서든) 항상 올바른 경로를 잡기 위함.
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Write-Host "[run_pipeline] 프로젝트 루트: $ProjectRoot"
Write-Host "[run_pipeline] Step = $Step, DryRun = $($DryRun.IsPresent)"

function Invoke-Step {
    param(
        [string]$Name,
        [string]$Command
    )
    Write-Host ""
    Write-Host "=== [$Name] ===" -ForegroundColor Cyan
    Write-Host "  실행 명령: $Command"

    if ($DryRun) {
        Write-Host "  (DryRun 모드 — 실제로 실행하지 않음)" -ForegroundColor Yellow
        return
    }

    Invoke-Expression $Command
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [$Name] 단계에서 오류 발생 (exit code $LASTEXITCODE). 파이프라인을 중단합니다." -ForegroundColor Red
        exit $LASTEXITCODE
    }
    Write-Host "  [$Name] 완료" -ForegroundColor Green
}

# 각 단계가 어떤 명령을 실행하는지 여기서 관리한다. 파일 경로가 실제 레포와
# 다르면 이 부분만 고치면 된다.
#
# repeat 단계: 원본 위치 확인됨 -> data\raw\repeat\REPEAT(BR/PT/SL).xlsx
# (파일명에 괄호가 들어있어서 각 경로를 큰따옴표로 감싸야 PowerShell이
#  하나의 인자로 정확히 인식한다. 아래처럼 작은따옴표 문자열 안에
#  큰따옴표를 그대로 쓰면 별도 이스케이프 없이 안전하게 들어간다.)
#
# weekly 단계: 원본 위치 확인됨 -> data\raw\weekly\FY26_주간_군별_실매출_현황.xlsx
# (parse_weekly_group.py는 sys.argv로 경로를 받는 구조라 인자로 그대로 넘긴다.)
#
# notion / staging 단계는 아직 실제 경로를 확인 못 한 상태이니,
# 그대로 실행해보고 파일을 못 찾는다는 에러가 나면 그 경로를 알려주세요 —
# 여기 딱 그 줄만 고쳐서 다시 드리겠습니다.
$RepeatDir = "data\raw\repeat"
$steps = [ordered]@{
    "notion"  = "python connectors\notion_pull.py"
    "staging" = "python pipelines\raw_to_staging.py"
    "repeat"  = 'python pipelines\parse_repeat.py "' + $RepeatDir + '\REPEAT(BR).xlsx" "' + $RepeatDir + '\REPEAT(PT).xlsx" "' + $RepeatDir + '\REPEAT(SL).xlsx" data\warehouse.db'
    "weekly"  = 'python pipelines\parse_weekly_group.py "data\raw\weekly\FY26_주간_군별_실매출_현황.xlsx" data\warehouse.db'
}

if ($Step -eq "all") {
    foreach ($key in $steps.Keys) {
        Invoke-Step -Name $key -Command $steps[$key]
    }
    # staging_to_gold는 raw_to_staging 이후 항상 마지막에 한 번 더 실행
    Invoke-Step -Name "gold" -Command "python pipelines\staging_to_gold.py"
} else {
    Invoke-Step -Name $Step -Command $steps[$Step]
}

Write-Host ""
Write-Host "[run_pipeline] 종료" -ForegroundColor Cyan
