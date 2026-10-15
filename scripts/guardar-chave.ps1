# Guarda uma chave de API em %APPDATA%\dervs\.env sem ela passar pelo chat nem pela tela.
# Uso: powershell -ExecutionPolicy Bypass -File scripts\guardar-chave.ps1 -Nome GROQ_API_KEY
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("GROQ_API_KEY", "GEMINI_API_KEY", "AZURE_SPEECH_KEY", "OPENAI_API_KEY")]
    [string]$Nome
)

# Gemini sem prefixo: as chaves novas do AI Studio (2026) nao comecam mais com "AIza".
$prefixos = @{ "GROQ_API_KEY" = "gsk_"; "OPENAI_API_KEY" = "sk-" }
$pasta = Join-Path $env:APPDATA "dervs"
$arquivo = Join-Path $pasta ".env"

Write-Host ""
Write-Host "Cole a chave $Nome e aperte Enter (ela nao aparece enquanto voce cola):" -ForegroundColor Cyan
$segura = Read-Host -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($segura)
try { $valor = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr).Trim() }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }

if ([string]::IsNullOrWhiteSpace($valor) -or $valor -match "\s") {
    Write-Host "Nada foi colado (ou veio com espaco no meio). Nada foi gravado. Feche e tente de novo." -ForegroundColor Red
    exit 1
}
$esperado = $prefixos[$Nome]
if ($esperado -and -not $valor.StartsWith($esperado)) {
    Write-Host "Essa chave nao parece ser de $Nome (deveria comecar com $esperado). Nada foi gravado." -ForegroundColor Red
    exit 1
}

New-Item -ItemType Directory -Force -Path $pasta | Out-Null
$linhas = @()
if (Test-Path $arquivo) { $linhas = @(Get-Content $arquivo | Where-Object { -not $_.StartsWith("$Nome=") }) }
$linhas += "$Nome=$valor"
# sem BOM: o Windows PowerShell 5 poe BOM com -Encoding UTF8, e o BOM grudaria na 1a chave
[IO.File]::WriteAllLines($arquivo, [string[]]$linhas, (New-Object Text.UTF8Encoding($false)))
$valor = $null

Write-Host ""
Write-Host "PRONTO: chave $Nome guardada no DERVS. Pode fechar esta janela." -ForegroundColor Green
