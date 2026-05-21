# Windows OCR 言語パックを導入するスクリプト
#
# 使い方: 右クリック → PowerShell で実行 (UAC で「はい」をクリック)
#        あるいは アプリのトレイメニュー → 「OCR 言語パックを導入」

$Langs = @(
    @{ Tag = "en-US"; Cap = "Language.OCR~~~en-US~0.0.1.0"; Label = "英語" },
    @{ Tag = "ja-JP"; Cap = "Language.OCR~~~ja-JP~0.0.1.0"; Label = "日本語" }
)

# 管理者権限チェック → 必要なら自己昇格
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "管理者権限が必要なため、UAC で昇格します..." -ForegroundColor Yellow
    Start-Process powershell -Verb RunAs -ArgumentList @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", "`"$PSCommandPath`""
    )
    exit
}

Write-Host "==============================================" -ForegroundColor Cyan
Write-Host " Windows OCR 言語パック導入" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host ""

foreach ($l in $Langs) {
    Write-Host "[$($l.Label)] $($l.Cap)" -ForegroundColor White
    try {
        $cap = Get-WindowsCapability -Online -Name $l.Cap -ErrorAction Stop
        if ($cap.State -eq "Installed") {
            Write-Host "  既に導入済み ($($l.Tag))" -ForegroundColor Green
            continue
        }
        Write-Host "  インストール中..." -ForegroundColor Yellow
        Add-WindowsCapability -Online -Name $l.Cap -ErrorAction Stop | Out-Null
        Write-Host "  ✔ 完了" -ForegroundColor Green
    } catch {
        Write-Host "  ✘ 失敗: $($_.Exception.Message)" -ForegroundColor Red
    }
    Write-Host ""
}

Write-Host "全処理完了。"
Write-Host ""
Write-Host "アプリ (pythonw) を一旦終了して再起動すると新しい言語が反映されます。"
Write-Host "  トレイ『訳』アイコン → 『終了』 → デスクトップの QuickTranslate を再度ダブルクリック"
Write-Host ""
Read-Host "Enter キーで閉じる"
