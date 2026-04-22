# restore_claude_binary.ps1
#
# Windows 専用: claude-agent-sdk が同梱する claude.exe を動作確認済みの
# 2.1.81 (JSビルド) にロールバックする。
#
# 背景: claude-agent-sdk 0.1.51 以降は claude.exe 2.1.112+ のネイティブバイナリを
# 同梱するが、Windows 11 上で 0xc0000005 (ACCESS_VIOLATION) クラッシュする
# (upstream: anthropics/claude-code#50640)。誤って `pip install -U claude-agent-sdk`
# を実行して壊れた場合に、本スクリプトで 1コマンド復元する。
#
# Usage:
#   pwsh -File scripts/restore_claude_binary.ps1
#   pwsh -File scripts/restore_claude_binary.ps1 -DryRun
#   pwsh -File scripts/restore_claude_binary.ps1 -BackupPath 'E:\path\to\claude_2.1.81.exe'

[CmdletBinding()]
param(
    [string]$BackupPath = 'E:\OneDriveBiz\Tools\General\claude_code_backup\claude_2.1.81_js_build.exe',
    [string]$VenvPath = 'E:\OneDriveBiz\Tools\General\animaworks\.venv',
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

function Get-BinaryVersion {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    try {
        $out = & $Path --version 2>&1 | Select-Object -First 1
        return [string]$out
    } catch {
        return "ERROR: $($_.Exception.Message)"
    }
}

# 1) バックアップ存在確認
if (-not (Test-Path -LiteralPath $BackupPath)) {
    Write-Error "Backup not found: $BackupPath"
    exit 1
}

# 2) venv 同梱バイナリの場所を解決
$targetPath = Join-Path $VenvPath 'Lib\site-packages\claude_agent_sdk\_bundled\claude.exe'
if (-not (Test-Path -LiteralPath $targetPath)) {
    Write-Error "Target not found: $targetPath (claude-agent-sdk がインストールされていない?)"
    exit 1
}

# 3) バックアップの動作確認
$backupVer = Get-BinaryVersion -Path $BackupPath
if ($backupVer -notmatch '^\d') {
    Write-Error "Backup binary does not respond to --version: $backupVer"
    exit 1
}
Write-Host "Backup version : $backupVer"

# 4) 現在のバージョン
$currentVer = Get-BinaryVersion -Path $targetPath
Write-Host "Current version: $currentVer"
Write-Host "Target path    : $targetPath"

# 5) 既に同一なら何もしない (ファイルサイズ比較で簡易判定)
$backupSize = (Get-Item -LiteralPath $BackupPath).Length
$currentSize = (Get-Item -LiteralPath $targetPath).Length
if ($backupSize -eq $currentSize -and $backupVer -eq $currentVer) {
    Write-Host "Already matches backup. Nothing to do." -ForegroundColor Green
    exit 0
}

if ($DryRun) {
    Write-Host "[DRY-RUN] Would copy $BackupPath -> $targetPath" -ForegroundColor Yellow
    exit 0
}

# 6) 念のため現行バイナリを .broken でリネーム保存 (上書きしない)
$brokenPath = "$targetPath.broken-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
Copy-Item -LiteralPath $targetPath -Destination $brokenPath -Force
Write-Host "Saved current binary to: $brokenPath"

# 7) 復元
Copy-Item -LiteralPath $BackupPath -Destination $targetPath -Force

# 8) 検証
$restoredVer = Get-BinaryVersion -Path $targetPath
Write-Host "Restored version: $restoredVer" -ForegroundColor Green
if ($restoredVer -ne $backupVer) {
    Write-Error "Restore verification failed: expected '$backupVer', got '$restoredVer'"
    exit 1
}

Write-Host ""
Write-Host "Done. 次は Mode S Anima を再起動する必要あり:" -ForegroundColor Cyan
Write-Host "  animaworks anima restart <name>"
