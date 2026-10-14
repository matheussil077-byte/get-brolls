param(
    [switch]$Check
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Invoke-Native {
    param(
        [string]$Label,
        [string]$File,
        [string[]]$Arguments
    )
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Label falhou com código $LASTEXITCODE."
    }
}

function Test-PythonCandidate {
    # Executa o candidato de verdade: o atalho da Microsoft Store (WindowsApps\python.exe
    # ou python3.exe) existe no PATH mas só imprime um aviso e sai com 9009.
    param([string]$File, [string[]]$Prefix)
    $Previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $File @Prefix -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $Previous
    }
}

function Resolve-Python {
    # Ordem: python e python3 que executam de fato; depois o launcher py com 3.13-3.11.
    foreach ($Name in @('python', 'python3')) {
        foreach ($Found in @(Get-Command $Name -CommandType Application -All -ErrorAction SilentlyContinue)) {
            if (Test-PythonCandidate -File $Found.Source -Prefix @()) {
                return @{ File = $Found.Source; Prefix = @() }
            }
        }
    }
    $Launcher = Get-Command 'py' -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($Launcher) {
        foreach ($Version in @('-3.13', '-3.12', '-3.11')) {
            if (Test-PythonCandidate -File $Launcher.Source -Prefix @($Version)) {
                return @{ File = $Launcher.Source; Prefix = @($Version) }
            }
        }
    }
    return $null
}

$Root = Split-Path -Parent $PSScriptRoot
$Missing = $false
$Python = Resolve-Python
if ($null -eq $Python) {
    Write-Host 'MISSING: python (3.11+; o atalho da Microsoft Store em WindowsApps não conta)'
    $Missing = $true
} else {
    Write-Host ("Python: $($Python.File) $($Python.Prefix -join ' ')").TrimEnd()
}
foreach ($Tool in @('ffmpeg', 'ffprobe', 'curl', 'node', 'npm', 'npx')) {
    if (-not (Get-Command $Tool -CommandType Application -ErrorAction SilentlyContinue)) {
        Write-Host "MISSING: $Tool"
        $Missing = $true
    }
}
if ($Missing) {
    throw 'Instale os executáveis conforme docs/GUIDE.md e repita.'
}

Invoke-Native -Label 'Verificação do Python' -File $Python.File -Arguments ($Python.Prefix + @('-c', 'import sys; assert sys.version_info >= (3,11), ''Python 3.11+ obrigatório'''))

$Previous = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    $Filters = (& ffmpeg -hide_banner -filters 2>$null | Out-String)
} finally {
    $ErrorActionPreference = $Previous
}
if ($Filters -notmatch ' drawtext ') {
    Write-Host 'AVISO: FFmpeg sem o filtro drawtext (libfreetype): o contact sheet sai sem número e timecode nas células. Instale um build com freetype (gyan.dev ou BtbN) e coloque no PATH.'
}

$NodeVersion = (& node --version).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Não foi possível consultar a versão do Node.' }
$NodeMajor = [int](($NodeVersion -replace '^v', '').Split('.')[0])
if ($NodeMajor -lt 22) { throw "Node 22+ obrigatório (encontrado $NodeVersion)." }

if ($Check) {
    Write-Host 'Pré-requisitos do instalador encontrados; check não instala nem testa rede/login.'
    exit 0
}

Invoke-Native -Label 'Criação da venv' -File $Python.File -Arguments ($Python.Prefix + @('-m', 'venv', (Join-Path $Root '.venv')))
$VenvPython = Join-Path $Root '.venv\Scripts\python.exe'
$PythonVersion = (& $VenvPython -c 'import sys; print(''%d.%d.%d'' % sys.version_info[:3])').Trim()
try {
    Invoke-Native -Label 'Instalação Python' -File $VenvPython -Arguments @('-m', 'pip', 'install', '-r', (Join-Path $Root 'requirements.txt'))
} catch {
    Write-Host "Falha ao instalar as dependências Python: seu Python é $PythonVersion; o conjunto fixado foi validado em Python 3.11-3.13."
    Write-Host 'Crie a venv com um interpretador dessa faixa ou atualize requirements.txt como um conjunto revisado.'
    throw
}
Invoke-Native -Label 'Importação yt-dlp/EJS' -File $VenvPython -Arguments @('-c', 'import yt_dlp, yt_dlp_ejs; print(''yt-dlp e EJS importados'')')
$Tools = Join-Path $Root '.tools'
New-Item -ItemType Directory -Path $Tools -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $Root 'package.json'), (Join-Path $Root 'package-lock.json') -Destination $Tools -Force
Invoke-Native -Label 'Instalação Playwright CLI' -File 'npm' -Arguments @('--cache', (Join-Path $Root '.tools\npm-cache'), 'ci', '--prefix', $Tools, '--ignore-scripts', '--no-audit', '--no-fund')
Invoke-Native -Label 'Verificação Playwright CLI' -File 'powershell' -Arguments @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $Root 'scripts\playwright.ps1'), '--version')
$env:PATH = "$(Join-Path $Root '.venv\Scripts');$env:PATH"
Invoke-Native -Label 'Doctor' -File $VenvPython -Arguments @((Join-Path $Root 'scripts\gb.py'), 'doctor')

Write-Host "`nDependências instaladas em .venv\ e .tools\; não fazem parte do repositório."
Write-Host 'Navegador existente: siga docs/GUIDE.md para reutilizar a sessão autorizada.'
