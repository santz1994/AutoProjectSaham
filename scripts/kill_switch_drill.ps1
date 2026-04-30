param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string]$ActivateReason = "weekly chaos rehearsal",
    [string]$DeactivateReason = "drill rollback completed",
    [string]$Actor = "ops-drill",
    [string]$ChallengeCode = "",
    [string]$AuthToken = "",
    [switch]$AllowIfAlreadyActive
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-JsonRequest {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Method,
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [object]$Body,
        [string]$AuthToken = ""
    )

    $headers = @{}
    if (-not [string]::IsNullOrWhiteSpace($AuthToken)) {
        $headers["Cookie"] = "auth_token=$AuthToken"
    }

    if ($null -eq $Body) {
        return Invoke-RestMethod -Method $Method -Uri $Url -ContentType "application/json" -Headers $headers
    }

    $jsonBody = $Body | ConvertTo-Json -Depth 10
    return Invoke-RestMethod -Method $Method -Uri $Url -Body $jsonBody -ContentType "application/json" -Headers $headers
}

function Assert-True {
    param(
        [Parameter(Mandatory = $true)]
        [bool]$Condition,
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    if (-not $Condition) {
        throw $Message
    }
}

$killSwitchPath = "$BaseUrl/api/system/kill-switch"
$activatePath = "$BaseUrl/api/system/kill-switch/activate"
$deactivatePath = "$BaseUrl/api/system/kill-switch/deactivate"

Write-Host "[drill] Querying kill-switch state: $killSwitchPath"
$before = Invoke-JsonRequest -Method "GET" -Url $killSwitchPath -AuthToken $AuthToken
$beforeActive = [bool]$before.killSwitchActive

if ($beforeActive -and -not $AllowIfAlreadyActive.IsPresent) {
    throw "Kill switch is already active. Resolve active incident first or rerun with -AllowIfAlreadyActive."
}

Write-Host "[drill] Activating kill switch"
$activatePayload = @{
    reason = $ActivateReason
    actor = $Actor
}
if (-not [string]::IsNullOrWhiteSpace($ChallengeCode)) {
    $activatePayload.challengeCode = $ChallengeCode
}
$activateResp = Invoke-JsonRequest -Method "POST" -Url $activatePath -Body $activatePayload -AuthToken $AuthToken

Assert-True -Condition ($activateResp.status -eq "activated") -Message "Activation response status is not 'activated'."
Assert-True -Condition ([bool]$activateResp.killSwitch.killSwitchActive) -Message "Kill switch is not active after activation call."

$runtimeActions = $activateResp.runtimeActions
if ($null -ne $runtimeActions) {
    Write-Host "[drill] Runtime actions captured from API response"
}

Write-Host "[drill] Deactivating kill switch"
$deactivatePayload = @{
    reason = $DeactivateReason
    actor = $Actor
}
if (-not [string]::IsNullOrWhiteSpace($ChallengeCode)) {
    $deactivatePayload.challengeCode = $ChallengeCode
}
$deactivateResp = Invoke-JsonRequest -Method "POST" -Url $deactivatePath -Body $deactivatePayload -AuthToken $AuthToken

Assert-True -Condition ($deactivateResp.status -eq "deactivated") -Message "Deactivate response status is not 'deactivated'."
Assert-True -Condition (-not [bool]$deactivateResp.killSwitch.killSwitchActive) -Message "Kill switch still active after deactivation call."

$after = Invoke-JsonRequest -Method "GET" -Url $killSwitchPath -AuthToken $AuthToken
Assert-True -Condition (-not [bool]$after.killSwitchActive) -Message "Final kill-switch state must be inactive after drill."

$summary = [ordered]@{
    status = "ok"
    drill = "kill-switch"
    baseUrl = $BaseUrl
    startedWithActiveState = $beforeActive
    activatedAt = $activateResp.killSwitch.activatedAt
    activatedBy = $activateResp.killSwitch.activatedBy
    runtimeActions = $runtimeActions
    finalState = $after
}

Write-Host "[drill] Completed successfully"
$summary | ConvertTo-Json -Depth 10
