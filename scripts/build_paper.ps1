param(
    [string]$Tectonic = ""
)

$ErrorActionPreference = "Stop"
$repo = Split-Path $PSScriptRoot -Parent
$source = Join-Path $repo "paper\MASGuardEval_SAIS27.tex"
$build = Join-Path $repo "reports\paper-build\standalone"
New-Item -ItemType Directory -Path $build -Force | Out-Null

if (-not $Tectonic) {
    $installed = Get-Command tectonic -ErrorAction SilentlyContinue
    if ($installed) {
        $Tectonic = $installed.Source
    } else {
        $Tectonic = Join-Path $repo ".tools\tectonic-0.17.0\tectonic.exe"
    }
}
if (-not (Test-Path -LiteralPath $Tectonic)) {
    throw "Tectonic was not found. Install it or pass -Tectonic <path>."
}

# The source embeds a XeTeX-compatible copy of the venue style for a
# single-file build. Remove only that generated copy so it tracks the source.
$generatedStyle = Join-Path $build "usenix2019_v3.sty"
if (Test-Path -LiteralPath $generatedStyle) {
    Remove-Item -LiteralPath $generatedStyle
}
Copy-Item -LiteralPath $source -Destination (Join-Path $build "MASGuardEval_SAIS27.tex") -Force
Push-Location $build
try {
    & $Tectonic --keep-logs "MASGuardEval_SAIS27.tex"
    if ($LASTEXITCODE -ne 0) { throw "Tectonic failed with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}
Write-Output (Join-Path $build "MASGuardEval_SAIS27.pdf")
