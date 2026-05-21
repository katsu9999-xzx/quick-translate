# クイック翻訳 (Quick Translate)

Windows 常駐型の翻訳ポップアップツール。

## 機能

- **テキスト翻訳ホットキー** (既定 `Alt+Q`)
  選択範囲のテキストを取得 → 翻訳 → ポップアップ表示。`Ctrl+C` で取れない場合は `Ctrl+Shift+C` / `Ctrl+Insert` も自動フォールバック (ターミナル等対応)
- **スクショ翻訳ホットキー** (既定 `Ctrl+Shift+S`)
  マウスドラッグで画面範囲を指定 → OCR (Windows標準) → 翻訳 → ポップアップ表示。**マルチモニタ対応**
- **トレイ常駐**
  トレイメニューから両ホットキー・翻訳先言語・OCR 言語を変更可能
- ポップアップは **クリック / Esc** で閉じる。**Ctrl+C** で訳文をコピー (常時表示 — `popup_timeout_ms: 0`)
- 設定は `config.json` に保存（メニューから即時編集可能）

## 動作対象範囲

| カテゴリ | テキスト翻訳 | スクショ翻訳 |
|---|---|---|
| 一般アプリ (ブラウザ・Word・Slack・メモ帳・VS Code 等) | OK | OK |
| Windows Terminal / PowerShell / CMD | OK (3段フォールバック) | OK |
| サブモニタ上のウィンドウ | OK | OK (マルチモニタ対応) |
| 管理者権限で起動中のアプリ (タスクマネージャ等) | 要 `start_admin.bat` | 要 `start_admin.bat` |
| ゲーム (DirectInput) / DRM保護コンテンツ (Netflix等) | NG | NG (画面が黒くなる) |
| Web で `user-select: none` の文字 | NG | OK |
| ロック画面・UAC ダイアログ | NG | NG (OS制限) |

### 管理者権限版

タスクマネージャやレジストリエディタ等の管理者権限アプリ上で使うときは `start_admin.bat` をダブルクリックして起動 (UAC 確認ダイアログ → 許可)。
通常用途では `start.bat` で十分。

## セットアップ

```cmd
cd C:\Users\katsu\Apps\quick-translate
install.bat
```

- 依存パッケージ (keyboard, pyperclip, requests, pystray, Pillow, mss, winocr) を pip install
- Windows スタートアップに `QuickTranslate.lnk` を登録（次回起動時から自動起動）

## 手動起動 / 停止

- 起動: `start.bat` をダブルクリック
- 停止: トレイアイコン → 終了 (または `stop.bat`)

## 設定ファイル (config.json)

| キー | 既定値 | 説明 |
|------|--------|------|
| `hotkey` | `alt+q` | テキスト翻訳のホットキー (Ctrl/Alt/Win 修飾必須) |
| `screenshot_hotkey` | `ctrl+shift+s` | スクショ翻訳のホットキー |
| `target_lang` | `ja` | 翻訳先言語コード |
| `source_lang` | `auto` | 原文言語コード (自動判定) |
| `ocr_lang` | `en` | OCR の言語 (Windows言語パック必要) |
| `popup_timeout_ms` | `12000` | ポップアップ自動クローズまでのミリ秒 |
| `max_width_px` | `460` | ポップアップ最大幅 |

ホットキー記法: `ctrl+shift+t`, `alt+q`, `ctrl+alt+space`, `f9` など。

## トラブルシューティング

- **ホットキーが効かない**: `keyboard` ライブラリは通常権限で動くが、対象アプリが管理者権限の場合は本ツールも管理者権限で起動が必要。
- **OCR が空文字を返す**: 対象範囲を広めに取る。日本語など特定言語は `OCR言語` を該当コード (例: `ja`, `zh-Hans`) に変更し、Windows設定で該当言語パックを導入。
- **翻訳が失敗**: ネットワーク接続確認。Google 翻訳の非公式エンドポイントを使用。
- **ログ**: `quick-translate.log` を参照

## 配置場所

`C:\Users\katsu\Apps\quick-translate\`
