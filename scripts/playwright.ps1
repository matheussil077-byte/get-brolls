$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
# Run the package entry point with node.exe directly: the playwright-cli.cmd shim goes
# through cmd.exe, which splits an unquoted URL at '&' (e.g. ?a=1&b=2).
$Entry = Join-Path $Root '.tools\node_modules\@playwright\cli\playwright-cli.js'
$Cli = Join-Path $Root '.tools\node_modules\.bin\playwright-cli.cmd'
if (Test-Path -LiteralPath $Entry -PathType Leaf) {
    $Node = Get-Command node -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $Node) {
        throw 'Node ausente no PATH. Instale o Node 22+ conforme docs/GUIDE.md.'
    }
    & $Node.Source $Entry @args
    exit $LASTEXITCODE
}
if (-not (Test-Path -LiteralPath $Cli -PathType Leaf)) {
    throw "Playwright CLI ausente. Execute scripts\install.ps1."
}
& $Cli @args
exit $LASTEXITCODE
