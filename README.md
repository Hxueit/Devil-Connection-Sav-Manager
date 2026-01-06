# Devil Connection .sav Manager

![Tkinter](https://img.shields.io/badge/GUI-Tkinter-blue?logo=python&logoColor=white) [![GitHub release (latest by date)](https://img.shields.io/github/v/release/Hxueit/Devil-Connection-Sav-Manager)](https://github.com/Hxueit/Devil-Connection-Sav-Manager/releases) ![Contains Spoilers](https://img.shields.io/badge/⚠-Contains_Spoilers-yellow) <img src="https://cdn.fastly.steamstatic.com/steamcommunity/public/images/apps/3054820/0cf0cb63d65311ed0b0f6f3cb5a2af88593b7361.jpg" alt="DC" width="20" height="20" style="border-radius: 20%;" />

<details>
<summary>日本語 (Japanese)</summary>

> 日本語が母国語ではなく、非常に苦手なため、説明文はLLMのサポートを受けて書いています。多少のミスは大目に見ていただけると嬉しいです。（ゲーム内のデータは検証済みで、原文と一致しているはずです。）

『でびるコネクショん』の .sav ファイル（スクリーンショットやセーブデータ）を管理、編集できる、シンプルで使いやすいツールです。

このゲームは本当に素晴らしい作品です。[Steamストアページ](https://store.steampowered.com/app/3054820/)はこちら。ぜひ作者さんを応援してください。

## 機能特性

本ツールは複数のタブで構成されています。

### 📊 sfセーブ解析

- `DevilConnection_sf.sav` から一部の詳細情報を自動抽出して一覧表示
  - エンディング、ステッカー、キャラ統計
    - 個人的にまとめた取得条件リストを同梱しています（全エンディング、全ステッカーの取得条件など）。照合や埋め作業に便利です
  - ゲーム統計
  - 狂信徒ルート関連情報
  - ほか多数
- **達成条件表示**：各エンディング、ステッカーの達成条件を一覧表示（未達成はハイライト）
- **セーブデータビューア**：`DevilConnection_sf.sav` 内の情報を閲覧、編集可能

### 📸 アルバム画像管理

- ゲーム内スクリーンショットファイルに対して、以下の操作を手軽に行えます
  - 追加
  - 削除
  - 変更
  - 並び替え
  - 一括エクスポート
- ゲーム内の表示形式に近いプレビューページを用意しており、編集時の確認がしやすいです

### 💾 バックアップ/復元

- `_storage` フォルダ全体を ZIP としてワンクリックでバックアップします。タイムスタンプを付けてローカルに保存し、必要に応じて復元できます
- ディレクトリ内の既存バックアップ一覧を表示し、複数バックアップの切り替えがしやすいです

### 🗂️ tyranoセーブ管理

- `DevilConnection_tyrano_data.sav` 内のセーブスロット（ゲーム内のセーブ枠）を、ゲームに近い形で表示します
  - 単一スロットのインポート、エクスポート
  - 単一スロット内容の編集
  - 並び替え

### 🛠️ 実行時変更

- 起動時に `--remote-debugging-port` パラメータでローカルポートに DevTools を開き、実行中に一部の数値を変更できます

### その他

- Toast 機能

  - デフォルトはオフです。有効にすると `DevilConnection_sf.sav` をリアルタイム監視し、変更があった場合に画面右下へ通知を表示します
  - 通知はデフォルトで15秒後に閉じます。固定表示も可能で、手動で早めに閉じることもできます

## インストール

### 必要環境

- Python 3.8 以上

### インストール手順

※ Windows ユーザーは Releases ページから単体 exe をダウンロードできます。この方法では Python や依存パッケージのインストールは不要です。

1. リポジトリをクローンまたはダウンロード
2. 依存パッケージをインストール

```bash
pip install -r requirements.txt
```

## 使い方

1. プログラム起動

```bash
python main.py
```

2. ゲームディレクトリを選択

- 「参照」ボタンをクリック
- 手動選択、または自動検出でゲームの `_storage` フォルダを指定します
  例：`C:\Program Files (x86)\Steam\steamapps\common\でびるコネクショん\_storage`

3. `_storage` 配下のファイルを自動取得して解析し、各機能が使用できるようになります

## 補足説明

### 共通

#### セーブデータ閲覧、編集ウィンドウ

- ツール内のボタン（例：sfセーブ解析 内の「sf.savセーブファイルを表示」など）から、セーブファイルを URL デコードして JSON 形式で表示できます
- 一部のウィンドウ右上には「編集ON」のチェックがあります。チェックを入れた場合のみ編集可能です。チェックが無いウィンドウはデフォルトで編集可能です
- 編集後は「保存」ボタンで保存できます
  **誤った編集はセーブ破損の原因になります。内容を理解している場合のみ操作してください。バックアップを強く推奨します**
- 折りたたまれている項目（情報量が多く、編集の必要性が低いものが多い）を編集したい場合は、「折りたたみ/横置きを解除」系のチェックを有効にしてください

### アルバム画像管理 タブ

#### ドラッグで並び替え

- 並び替えはドラッグ操作で行えます。右上の「編集ON」をオンにする必要があります
- リスト項目をクリックしてドラッグすると順序変更できます（ゲーム内ギャラリーにもこの順序が反映されます）
- ドラッグ完了後、どのファイルが移動したか矢印インジケーターで表示されます

#### 一括エクスポート

- 選択した画像は ZIP にまとめて一括エクスポートされます

### Q：このツールは何の役に立つの？

- A：大きな実用性はそこまでありません。個人的にはステッカーの埋め作業で抜けをすぐ確認できる点が一番便利だと思います。

## 注意事項

- セーブデータを変更する前に、必ず `_storage` フォルダ全体のバックアップを取ることを強く推奨します（ツール内にバックアップ機能があります）
- 本ツールは現在 Windows 環境でのみ動作確認を行っています。MacOS および Linux での動作は未検証です。
- 本ツールは《でびるコネクショん》公式および開発者とは一切関係ありません。完全に有志による非公式ツールです。ゲーム本体のファイルは変更せず、ローカルに保存されているスクリーンショット保存ファイルおよびセーブデータのみを操作します。もし開発者様にとって不都合がございましたら、GitHub Issues にてご連絡ください。直ちに公開停止など対応いたします。

## ライセンス

MIT License

## 貢献

- 本ツールは個人用途として、ゲームの調査や差分確認のために作成したものです。自分の環境でのテストでは問題は見つかりませんでしたが、見落としがある可能性があります
- 開発では AI の補助も利用しています。機能は特定ゲーム向けに作られており、一部は汎用化していますが、長期的な汎用メンテナンスを目的とした設計ではありません。そのため、コアロジックへの大規模な改造は推奨しません
- ツール内の翻訳文を修正したい場合は、`/src/utils/translations.py` を直接編集してください。ツール内テキストはすべてこのファイルにあります


</details>

<details>
<summary>中文 (Chinese)</summary>

一个用于管理和编辑 でびるコネクショん 游戏部分.sav文件的简单易用小工具。

游戏很棒，这里是 [Steam商店页面](https://store.steampowered.com/app/3054820/)，欢迎支持游戏作者。

## 功能特性

本工具由多个标签页组成：

### 📊 sf存档分析

- **自动提取并列出`DevilConnection_sf.sav`里的一些详细信息**
  - 结局，贴纸，角色统计
    - 集成一份个人总结的获取条件列表，包含**全结局/贴纸获取条件**等，方便核对/完成
  - 游戏统计
  - 狂信徒线相关信息
  - 等等
- **达成条件显示**：一览显示各结局/贴纸的达成条件（未达成结局会高亮显示）
- **存档文件查看器**：便利的查看/修改`DevilConnection_sf.sav`中的信息

### 📸 截图管理

- 便捷的对于游戏内的截图文件进行以下操作
  - 增
  - 删
  - 改
  - 重排序
  - 批量导出
- 提供一个类似游戏内截图展现形式的预览页，方便修改时快速核对

### 💾 备份/还原

- 一键将`_storage`文件夹整体备份为ZIP格式，添加时间戳，并存入本地，需要时可还原
- 罗列出目录下已有的备份，方便多份不同的备份来回切换

### 🗂️ tyrano存档管理

- 以类似游戏内的形式展示出`DevilConnection_tyrano_data.sav`中的存档文件（游戏内的那些存档槽）
  - 快捷的导入/导出单存档
  - 修改单个存档槽内的内容
  - 重排序

### 🛠️ 运行时修改

- 启动时使用 `--remote-debugging-port`参数在本地端口开启devtools，运行时对一些数值做修改

### 其他

- toast功能
  - 默认关闭。开启后实时监听`DevilConnection_sf.sav`并在有改动的时候在屏幕右下角弹出弹窗显示变化
  - 弹窗默认15秒后关闭，可固定也可提前关闭

## 安装

### 前置要求

- Python 3.8 或更高版本

### 安装步骤

> 注意：windows用户也可以前往Releases页面下载单exe文件，该方式无需安装Python或任何依赖

1. 克隆或下载此仓库

2. 安装依赖：

```bash
pip install -r requirements.txt
```

## 使用方法

1. 运行程序：

    ```bash
    python main.py
    ```

2. 选择游戏目录：
   - 点击"浏览目录"按钮
   - 手动选择或者自动检测游戏的 `_storage` 目录（例如：`C:\Program Files (x86)\Steam\steamapps\common\でびるコネクショん\_storage`）

3. 程序会自动获取所有该目录下的文件并解析他们，使用功能。

## 额外说明

### 通用

#### 存档文件查看/编辑框

- 通过程序内的一些按钮（例如，sf存档分析中的"查看存档文件"按钮），可以自动对存档文件进行url解码并以JSON格式查看存档文件内容。
- 有一些窗口的右上角设有"开启修改"的勾选框，勾选其后才可以进行编辑。没有该框的窗口默认可以编辑。
- 编辑后的内容可以通过"保存"按钮保存，**错误的编辑可能导致存档损坏，请务必在知道你在干什么的情况下再做操作**。强烈建议**做好备份**，这样即使发生错误也可以回溯。
- 要编辑折叠的字段（一般为比较冗杂且实际修改意义不大的东西），需要先勾选"取消折叠/横置"复选框。

### 截图管理标签页

#### 拖拽排序

- 此功能支持拖拽重排序图片，需要勾选右上角的"开启修改"才可以进行
- 点击并拖拽列表项可以调整顺序（实际游戏内的画廊中会反映这个顺序）
- 拖拽完成后会显示箭头指示器提示哪个文件被拖拽

#### 批量导出

- 批量导出会将所有选中的图片打包成一个 ZIP 文件。

### Q：这个项目有什么用？

- A：没什么很大的实际用途。我个人认为最实用的大概就是快速的查漏补缺贴纸，可以玩玩。

## 注意事项

- 修改存档文件前，强烈建议先**备份**你的存档文件夹（工具内提供此功能）。
- 当前版本仅在 Windows 环境下测试过，macOS 和 Linux 未验证，可能无法正常运行。
- 本工具与游戏《でびるコネクショん》官方及开发者完全无关，仅为玩家自制工具。工具不涉及修改游戏核心文件，仅操作本地存储的截图保存文件以及存档文件。

## 许可证

MIT License

## 贡献

- 本项目本质上是个人用来调试游戏/查差分制出的，经个人测试未发现使用问题，但难免会有疏漏，请多多包涵。
- 本项目在开发过程中使用了 AI 辅助编写代码，功能实现主要针对该特定游戏。虽然部分功能有做通用化接口，但整体逻辑并非以长期通用维护为目标，因此不建议对核心逻辑代码进行大规模修改。
- 如果想对程序内的翻译进行修改与纠正，请直接查看`/src/utils/translations.py`，工具内所有文本均在该文件中

</details>

<details>
<summary>English</summary>

A small, easy-to-use tool for managing and editing some `.sav` files for the game **でびるコネクショん**.

Honestly fantastic game - here is the [Steam store page](https://store.steampowered.com/app/3054820/). Please consider supporting the developers.

## Features

The tool consists of multiple tabs:

Tab names: **SF Analyzer**, **Screenshots**, **Backup/Restore**, **Tyrano Management**, **Runtime Modify**, **Others**

### 📊 SF Analyzer

- **Automatically extracts and lists detailed information from `DevilConnection_sf.sav`**
  - Endings, stickers, character statistics
    - Includes a personal summary list of requirements, including **unlock requirements for all endings and stickers**, which (I hope) comes in handy for checking and completion
  - Game statistics
  - Fanatic route related info
  - And more
- **Unlock conditions display**: Shows the requirements for all endings and stickers at a glance, and highlights unachieved endings
- **Save file viewer/editor**: Conveniently view and modify the contents of `DevilConnection_sf.sav`

### 📸 Screenshots

- Conveniently manage in-game screenshot files with the following operations
  - Add
  - Delete
  - Modify
  - Reorder
  - Batch export
- Provides a preview page that resembles the in-game screenshot gallery, making it easy to verify changes quickly

### 💾 Backup/Restore

- One-click backup of the entire `_storage` folder into a ZIP file with a timestamp, saved locally, and can be restored when needed
- Lists existing backups in the directory, making it easy to switch between different backups

### 🗂️ Tyrano Management

- Displays save slots from `DevilConnection_tyrano_data.sav` in a way similar to the in-game UI
  - Quick import and export for a single save slot
  - Edit the contents of a single save slot
  - Reorder save slots

### 🛠️ Runtime Modify

- Starts the game with the `--remote-debugging-port` parameter to open DevTools on a local port, allowing you to modify some values at runtime

### Others

- Toast notifications
  - Disabled by default. When enabled, it monitors `DevilConnection_sf.sav` and shows a toast at the bottom-right when changes are detected
  - Toasts disappear after 15 seconds by default, can be pinned or manually closed

## Installation

### Requirements

- Python 3.8 or higher

### Installation steps

> Note: If you are using Windows, you can also download the standalone `.exe` from the Releases page. No Python or dependencies required.

1. Clone or download this repository

2. Install dependencies:

```bash
pip install -r requirements.txt
```

## How to Use

1.Launch the program:

```bash
python main.py
```

2.Select the game folder:

  - Click the “Browse Directory” button
  - Choose or autodetect the game’s `_storage` folder (example: `C:\Program Files (x86)\Steam\steamapps\common\でびるコネクショん\_storage`)

3.The tool will automatically load and parse files under that directory, then you can use the features.

## Additional Notes

### General

#### Save File Viewer/Editor

- Through some buttons in the app (for example, “View sf.sav File” in SF Analyzer), the tool can automatically URL-decode the save file and show its content in JSON format.
- Some windows have an “Enable Edit” checkbox in the top-right. You must check it before editing. Windows without this checkbox are editable by default.
- After editing, click “Save” to write changes. **Incorrect edits may corrupt your save file**, only edit if you know what you are doing. Strongly recommended making a **backup** - so you can roll back if something goes wrong.
- To edit collapsed fields (usually verbose and not very meaningful to modify), first check “Unfold All / Expand Horizontally”.

### Screenshots Tab

#### Drag and Drop Reordering

- Drag and drop reordering is supported, and requires enabling “Enable Edit” in the top-right
- Click and drag list items to change order (the in-game gallery will reflect the new order)
- An arrow indicator shows which file is being moved during drag

#### Batch Export

- Batch export packs all selected images into a single ZIP file.

### Q: What is this tool actually useful for?

- A: It does not have huge practical value. The most useful part IMO is probably checking missing stickers. Feel free to try it out.

## Important Notes

- Before modifying save files, it is strongly recommended to **backup*- your save folder (the tool provides this feature).
- This tool is currently tested only on Windows. MacOS and Linux have not been tested and the tool may not work properly on those platforms.
- This tool is completely unofficial and has no affiliation with the developers of でびるコネクショん. It does not modify core game files, it only operates on locally stored screenshot save files and save files. If the developers have any issues with it, please let me know via GitHub Issues, and I will handle it immediately.

## License

MIT License

## Contributions

- This project was mainly made for personal debugging and diff checking. It works fine in my own testing, but there may be oversights.
- AI assistance was used during development. The implementation mainly targets this specific game. Some parts are generalized, but overall it is not designed for long-term general maintenance, thus large-scale commits to the core logic are not recommended.
- If you want to modify or correct translations in the app, check `/src/utils/translations.py`, all UI text is in that file.

</details>
