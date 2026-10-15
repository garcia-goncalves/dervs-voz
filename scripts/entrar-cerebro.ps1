# Abre o Claude Code com a pasta do cerebro do DERVS (%APPDATA%\dervs\cerebro), para o dono
# entrar com a assinatura UMA vez. O login e dele, no navegador: este script nao copia nem le
# credencial nenhuma, so aponta o CLAUDE_CONFIG_DIR para a pasta do DERVS.
# Uso: powershell -ExecutionPolicy Bypass -File scripts\entrar-cerebro.ps1
# (ou o botao ENTRAR do painel, que roda este mesmo arquivo)

$cerebro = Join-Path $env:APPDATA "dervs\cerebro"
$area = Join-Path $env:APPDATA "dervs\area"
New-Item -ItemType Directory -Force -Path $cerebro, $area | Out-Null
$env:CLAUDE_CONFIG_DIR = $cerebro

$claude = Get-Command claude -ErrorAction SilentlyContinue
if (-not $claude) {
    Write-Host "Nao achei o Claude Code neste computador. Instale-o e tente de novo." -ForegroundColor Red
    Read-Host "Aperte Enter para fechar"
    exit 1
}

Write-Host ""
Write-Host "ENTRAR NO CEREBRO DO DERVS" -ForegroundColor Cyan
Write-Host "1. Quando o Claude abrir, digite /login e aperte Enter."
Write-Host "2. Escolha a sua assinatura do Claude e aprove no navegador."
Write-Host "3. Quando aparecer que deu certo, digite /exit e feche esta janela."
Write-Host "Isto so precisa ser feito uma vez." -ForegroundColor Cyan
Write-Host ""

Set-Location $area
& $claude.Source
