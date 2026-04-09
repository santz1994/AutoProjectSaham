# AutoSaham Full Stack Launcher (canonical wrapper)

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    & $VenvPython "run_fullstack.py"
} else {
    python "run_fullstack.py"
}