#!/usr/bin/env pwsh
param(
  [string]$BaseUrl = 'http://127.0.0.1:8000',
  [switch]$SkipMutatingActions
)

$ErrorActionPreference = 'Stop'

$results = New-Object System.Collections.Generic.List[object]

function Add-CheckResult {
  param(
    [string]$Name,
    [bool]$Passed,
    [string]$Detail
  )

  $results.Add([PSCustomObject]@{
    Check  = $Name
    Passed = $Passed
    Detail = $Detail
  })
}

function Invoke-GetCheck {
  param(
    [string]$Name,
    [string]$Path,
    [scriptblock]$Validate
  )

  try {
    $url = "$BaseUrl$Path"
    $response = Invoke-RestMethod -Uri $url -Method GET -TimeoutSec 20
    $ok = & $Validate $response

    if ($ok) {
      Add-CheckResult -Name $Name -Passed $true -Detail "GET $Path"
    } else {
      Add-CheckResult -Name $Name -Passed $false -Detail "GET $Path returned unexpected payload"
    }
  } catch {
    Add-CheckResult -Name $Name -Passed $false -Detail $_.Exception.Message
  }
}

function Invoke-PostCheck {
  param(
    [string]$Name,
    [string]$Path,
    [scriptblock]$Validate
  )

  try {
    $url = "$BaseUrl$Path"
    $response = Invoke-RestMethod -Uri $url -Method POST -TimeoutSec 20
    $ok = & $Validate $response

    if ($ok) {
      Add-CheckResult -Name $Name -Passed $true -Detail "POST $Path"
    } else {
      Add-CheckResult -Name $Name -Passed $false -Detail "POST $Path returned unexpected payload"
    }
  } catch {
    Add-CheckResult -Name $Name -Passed $false -Detail $_.Exception.Message
  }
}

Write-Host "AutoSaham quick regression check" -ForegroundColor Cyan
Write-Host "Base URL: $BaseUrl" -ForegroundColor Cyan

Invoke-GetCheck -Name 'Health endpoint' -Path '/health' -Validate {
  param($r)
  return $null -ne $r -and $r.status -eq 'ok'
}

Invoke-GetCheck -Name 'Portfolio endpoint' -Path '/api/portfolio' -Validate {
  param($r)
  $totalValue = 0.0
  $hasNumericValue = [double]::TryParse([string]$r.totalValue, [ref]$totalValue)
  return $null -ne $r -and $hasNumericValue -and $r.positions -is [System.Array]
}

Invoke-GetCheck -Name 'Portfolio reconcile endpoint' -Path '/api/portfolio/reconcile' -Validate {
  param($r)
  return $null -ne $r -and $null -ne $r.portfolio -and $null -ne $r.portfolio.balance
}

Invoke-GetCheck -Name 'Multi-market universe endpoint' -Path '/api/market/universe?market=all' -Validate {
  param($r)
  if ($null -eq $r -or $null -eq $r.symbols) { return $false }

  $symbols = @($r.symbols)
  return $symbols.Count -ge 6 -and $symbols -contains 'EURUSD=X' -and $symbols -contains 'GBPUSD=X' -and $symbols -contains 'BTC-USD'
}

Invoke-GetCheck -Name 'Notifications health endpoint' -Path '/api/notifications/health' -Validate {
  param($r)
  return $null -ne $r -and $r.success -eq $true -and $r.status -eq 'healthy'
}

Invoke-GetCheck -Name 'Crypto AI projection endpoint' -Path '/api/ai/projection/BTC-USD?timeframe=1d&horizon=16' -Validate {
  param($r)
  if ($null -eq $r -or $null -eq $r.projection) { return $false }
  $points = @($r.projection)
  return $r.timeframe -eq '1d' -and [int]$r.horizon -eq 16 -and $points.Count -eq 16 -and $r.rationale.Count -ge 1
}

Invoke-GetCheck -Name 'Forex AI projection endpoint' -Path '/api/ai/projection/EURUSD=X?timeframe=1m&horizon=32' -Validate {
  param($r)
  if ($null -eq $r -or $null -eq $r.projection) { return $false }
  $points = @($r.projection)
  return $r.timeframe -eq '1m' -and [int]$r.horizon -eq 32 -and $points.Count -eq 32 -and $r.rationale.Count -ge 1
}

if (-not $SkipMutatingActions) {
  Invoke-PostCheck -Name 'Strategy deploy endpoint' -Path '/api/strategies/1/deploy' -Validate {
    param($r)
    return $null -ne $r -and $r.success -eq $true -and $r.status -eq 'deployed'
  }

  Invoke-PostCheck -Name 'Strategy backtest endpoint' -Path '/api/strategies/1/backtest' -Validate {
    param($r)
    return $null -ne $r -and $r.success -eq $true -and $r.status -eq 'running'
  }
}

Write-Host ''
$results | Format-Table -AutoSize

$passed = @($results | Where-Object { $_.Passed }).Count
$failed = @($results | Where-Object { -not $_.Passed }).Count
$total = $results.Count

Write-Host ''
if ($failed -eq 0) {
  Write-Host "Result: PASS ($passed/$total checks)" -ForegroundColor Green
  exit 0
}

Write-Host "Result: FAIL ($passed/$total checks passed, $failed failed)" -ForegroundColor Red
exit 1
