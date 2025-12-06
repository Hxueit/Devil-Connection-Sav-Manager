# Devil Connection .sav Manager

![Tkinter](https://img.shields.io/badge/GUI-Tkinter-blue?logo=python&logoColor=white) [![GitHub release (latest by date)](https://img.shields.io/github/v/release/Hxueit/Devil-Connection-Sav-Manager)](https://github.com/Hxueit/Devil-Connection-Sav-Manager/releases) ![Contains Spoilers](https://img.shields.io/badge/⚠-Contains_Spoilers-yellow) <img src="https://cdn.fastly.steamstatic.com/steamcommunity/public/images/apps/3054820/0cf0cb63d65311ed0b0f6f3cb5a2af88593b7361.jpg" alt="DC" width="20" height="20" style="border-radius: 20%;" />

<details>
<summary>日本語 (Japanese)</summary>

> 日本語が母国語ではなく、非常に苦手なため、説明文はLLMのサポートを受けて書いています。多少のミスは大目に見ていただけると嬉しいです。（ゲーム内のデータは検証済みで、原文と一致しているはずです。）

『でびるコネクショん』の .sav ファイル（スクリーンショットやセーブデータ）を管理・編集できる、シンプルで使いやすいツールです。

このゲームは本当に素晴らしい作品です。[Steamストアページ](https://store.steampowered.com/app/3054820/)はこちら。ぜひ作者さんを応援してください。

## 機能一覧

ツールは3つのタブで構成されています。

### 📊 セーブデータ解析

- `DevilConnection_sf.sav` を自動デコードして詳細情報を一覧表示
  - 達成済みエンディング、ステッカー、キャラ統計（未収集リスト）
  - 私の個人的なまとめによる**全エンディング／ステッカーの入手条件**も含まれているので、条件チェックもしやすいかと思います。
  - ゲーム進行統計（MP収集数、判定回数、ループ回数など）
  - 狂信徒ルート関連情報（NEO値、進行状況など）
  - その他多数
- **エンディング達成条件一覧**：各エンディングの解除条件を一覧表示（未達成はハイライト）
- **セーブデータビューア**：`DevilConnection_sf.sav`の内容を閲覧・編集可能

### 📸 スクリーンショット管理

- 🖼️ **画像プレビュー**：.savファイルに埋め込まれたbase64画像を自動デコードしてプレビュー表示
- ➕ **追加・置換・削除**：任意の画像をギャラリーに追加したり、既存のスクショを置き換え・削除
- 📤 **エクスポート**：スクショをpng/jpeg/webp形式で個別または一括保存
- 🔀 **並び替え**：ギャラリー内の表示順を自由に変更可能
- ☑️ **複数選択対応**：チェックボックスで複数選択して一括操作が可能

### 💾 バックアップ・復元

- `_storage`フォルダ全体をZIP形式でバックアップし、ローカルに保存。必要に応じて復元可能

## インストール

### 必要環境

- Python 3.8 以上

### インストール手順

※ Releasesページから単体exeをダウンロードすれば、Pythonも依存パッケージも不要です

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

2. ゲームフォルダを選択

    - 「ディレクトリを選択」ボタンをクリック
    - ゲームの `_storage` フォルダを選択、または自動検出
        （例：`C:\Program Files (x86)\Steam\steamapps\common\でびるコネクショん\_storage`）

3. 自動で `_storage` 内の `DevilConnection_photo_XXXXXXXX.sav` 形式の全ファイルと `DevilConnection_sf.sav` を読み込み、各機能が使用可能になります。

## 補足説明

### セーブデータ解析タブ

#### セーブデータ編集

- 「セーブデータを表示」ボタンで `DevilConnection_sf.sav` の内容をJSON形式で表示
- 「編集モードを有効化」にチェックを入れると編集可能になります
- 編集後は「保存」ボタンで上書き保存可能  
    **※間違った編集をするとセーブデータが破損します。構造を理解している場合のみ操作し、必ずバックアップを取ってください**
- `record`・`_tap_effect`・`initialVars` などの折りたたまれた項目を編集したい場合は「すべて展開/横に展開」のチェックを入れてください

#### 変数名表示

- 「変数名を表示」にチェックを入れると、各項目の横に実際の変数パス（例：`memory.name`、`endings` など）が表示され、セーブデータ内の位置が把握しやすくなります

#### 変更通知（Toast）

- `DevilConnection_sf.sav`セーブファイルが外部で変更された場合、自動的に通知が表示されます
- 変更内容（変数名と値の変化）がリアルタイムで表示されます
- `record`/`initialVars`内の変更はデフォルトで通知対象外です（「その他」タブで検知を有効にできますが、動作が重くなる可能性があるため推奨しません）。

### スクリーンショット管理タブ

#### ドラッグ＆ドロップで並び替え

- リスト項目をクリックしてドラッグで順序変更可能（ゲーム内ギャラリーの表示順にそのまま反映されます）
- ドラッグ中は矢印インジケーターで移動先が表示されます

#### 一括エクスポート

- 複数選択した画像はすべてZIPファイルにまとめてエクスポートされます

### Q: なぜ`DevilConnection_tyrano_data.sav`の読み取り/編集機能がないのですか？

- A: 今後のアップデートで対応する予定です。現在は `tyrano.sav` のデコード・エンコードを行うボタンを追加しましたので、そちらをご利用ください。

### Q：このツールは何の役に立つの？

A：実用性はそこまで高くありません。主にステッカー収集状況やNEO値をすぐに確認できたり、スクリーンショット管理が楽になる点などが便利です。

## 注意事項

- 本ツールはゲームのスクリーンショット保存ファイルとセーブデータを**直接書き換えます**。不安な方は必ず`_storage`フォルダ全体のバックアップを取ってください
- 並び替え操作はゲーム内ギャラリーの表示順にそのまま反映されます
- ⚠️ 削除操作はファイル本体とインデックス情報の両方を削除するため、取り消しはできません
- ⚠️ **セーブデータ編集機能は特に注意が必要です**。JSON形式の破損や必須項目の削除などでセーブデータが読み込めなくなる可能性があります。編集前に必ずバックアップを取ってください
- 本ツールは《でびるコネクショん》公式・開発者とは一切関係ありません。完全に有志による非公式ツールです。ゲーム本体のファイルは一切変更せず、`_storage` 内の保存データのみを操作します。 もし開発者様にとって何か不都合がございましたら、GitHub Issuesにてご連絡いただければ、直ちに対応いたします。

## ライセンス

MIT License

## 貢献

個人の趣味で作成したツールのため、自分の環境では問題ありませんでしたが、予期せぬ不具合があるかもしれません。  
IssueやPull Requestは大歓迎です。

</details>

<details>
<summary>中文 (Chinese)</summary>

一个用于管理和编辑 でびるコネクショん 游戏部分.sav文件的简单易用小工具。

游戏很棒，这里是 [Steam商店页面](https://store.steampowered.com/app/3054820/)，欢迎支持游戏作者。

## 功能特性

本工具由三个标签页组成：

### 📊 存档分析

- **自动解码`DevilConnection_sf.sav`并提取列出一些详细信息**
  - 结局，贴纸，角色统计（未收集列表,包含我个人总结的**全结局/贴纸获取条件**，方便核对/完成）
  - 游戏统计（MP收集量、判定次数、循环次数等）
  - 狂信徒线相关信息（NEO值、狂信徒线进行状况等）
  - 等等一些
- **达成条件显示**：一览显示各结局/贴纸的达成条件（未达成结局会高亮显示）
- **存档文件查看器**：便利的查看/修改`DevilConnection_sf.sav`中的信息

### 📸 截图管理

- 🖼️ **截图预览**：自动解码.sav文件中的base64图像并预览
- ➕ **新增，替换，删除截图**：添加新的自定义图片到游戏画廊，替换或删除已有截图
- 📤 **导出图片**：导出截图为png/jpeg/webp图片文件
- 🔀 **排序功能**：自由调整截图在画廊中显示的顺序
- ☑️ **多选功能**：支持复选框多选，方便批量操作

### 💾 备份/还原

- 将`_storage`文件夹整体备份为ZIP格式并存入本地，需要时可还原

## 安装

### 前置要求

- Python 3.8 或更高版本

### 安装步骤

> 注意：你也可以前往Releases页面下载单exe文件，该方式无需安装Python或任何依赖

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

3. 程序会自动获取所有该目录下形如`DevilConnection_photo_XXXXXXXX.sav`的文件以及`DevilConnection_sf.sav`文件，使用功能。

## 额外说明

### 存档分析标签页

#### 存档文件编辑

- 通过"查看存档文件"按钮，可以以JSON格式查看`DevilConnection_sf.sav`存档文件内容。
- 勾选"开启修改"复选框后，可以进行编辑。
- 编辑后的内容可以通过"保存"按钮保存，但**错误的编辑可能导致游戏损坏，请务必在知道你在干什么的情况下再做操作**。同时**做好备份**
- 要编辑折叠的字段（如`record`、`_tap_effect`、`initialVars`等），需要先勾选"取消折叠/横置"复选框。

#### 变量名显示

- 勾选"显示变量名"复选框后，各信息前会显示变量名（如`memory.name`、`endings`等），方便确认变量在存档文件中的位置。

#### 变更通知（Toast）

- 当`DevilConnection_sf.sav`存档文件在外部被修改时，会自动显示通知
- 实时显示变更内容（变量名和值的变化）
- `record`以及`initialVars` 变量的变动默认被忽略（你可以在“其他”选项卡中开启检测，但不推荐监听`record`，可能会导致卡顿）。

### 截图管理标签页

#### 拖拽排序

- 点击并拖拽列表项可以调整顺序（实际游戏内画廊会反映这个顺序）
- 拖拽完成后会显示箭头指示器提示哪个文件被拖拽

#### 批量导出

- 批量导出会将所有选中的图片打包成一个 ZIP 文件。

### Q: 为什么没有直接读取/修改`DevilConnection_tyrano_data.sav`存档文件的功能

- A: 计划接下来的更新会加入此功能。目前版本已加入了`tyrano.sav`的解码导出/编码导入按钮，可以先使用该功能。

### Q：这个项目有什么用？

- A：没什么很大的实际用途。最重要的大概是速查贴纸和NEO值的数量，同时方便导入导出游戏内截图。可以玩玩。

## 注意事项

- 操作会直接修改游戏的截图保存文件以及存档文件，若有担心建议先**备份** `_storage` 目录
- 排序操作会改变截图在游戏画廊中的显示顺序
- ⚠️删除操作会同时删除截图文件和索引信息，无法撤销，请谨慎操作
- ⚠️ **使用存档文件编辑功能时请特别小心**。错误的编辑（如：无效的JSON格式、删除必需字段等）可能导致存档文件损坏，使游戏无法正常运行。编辑前请务必备份。
- 本工具与游戏《でびるコネクショん》官方及开发者完全无关，仅为玩家自制工具。工具不涉及修改游戏核心文件，仅操作本地存储的截图保存文件以及存档文件。

## 许可证

MIT License

## 贡献

- 本项目是利用闲暇时间写出的，经个人测试未发现使用问题，但难免会有疏漏。非常欢迎提交issue或者pull request。

</details>

<details>
<summary>English</summary>

A small, easy-to-use tool for managing and editing some .sav files for the game **でびるコネクショん**.

Honestly fantastic game – here is the [Steam store page](https://store.steampowered.com/app/3054820/). Please consider supporting the developers.

## Features

The tool consists of three tabs:

### 📊 Save Data Analysis

- Automatically decodes `DevilConnection_sf.sav` and displays detailed information:
  - Achieved endings, stickers, character statistics (including uncollected items list and a personal summary of the **unlock requirements for all endings and stickers**, which should come in handy for checking.)
  - Game statistics (MP collected, judgment count, loop count, etc.)
  - Fanatic route info (NEO value, fanatic route progress, etc.)
  - And some more details
- **Ending/Stickers unlock conditions list**: Shows requirements for every ending at a glance and automatically highlights unachieved ones
- **Save file viewer/editor**: Conveniently view and modify the contents of `DevilConnection_sf.sav`

### 📸 Screenshot Management

- 🖼️ **Preview**: Automatically decodes base64 images inside .sav files and displays them
- ➕ **Add / Replace / Delete**: Freely add custom images to the gallery, replace existing screenshots, or delete them
- 📤 **Export**: Save screenshots as png / jpeg / webp files (individual or batch)
- 🔀 **Reorder**: Freely change the display order in the in-game gallery
- ☑️ **Multi-selection**: Checkbox support for easy batch operations

### 💾 Backup & Restore

- Backup the entire `_storage` folder as a ZIP file and save locally. Restore at any time when needed

## Installation

### Requirements

- Python 3.8 or higher

### Installation steps
>
> Note: You can also download the standalone .exe from the Releases page — no Python or dependencies required

1. Clone or download this repository
2. Install dependencies:

```bash
pip install -r requirements.txt
```

## How to Use

1. Launch the program:

    ```bash
    python main.py
    ```

2. Select the game folder:
    - Click the “Browse Directory” button
    - Choose or autodetect the game's `_storage` folder  
      (example: `C:\Program Files (x86)\Steam\steamapps\common\でびるコネクショん\_storage`)

3. The tool will automatically load all files matching `DevilConnection_photo_XXXXXXXX.sav` and the `DevilConnection_sf.sav` file.

## Additional Notes

### Save Data Analysis Tab

#### Save File Editing

- Click “View Save Data” to display `DevilConnection_sf.sav` content in JSON format
- Check “Enable Editing” to allow modifications
- Changes can be saved with the “Save” button  
  **Warning: Incorrect edits can corrupt your save file. Only edit if you know what you're doing, and always keep a backup**
- To edit collapsed fields (`record`, `_tap_effect`, `initialVars`, etc.), first check “Unfold All / Expand Horizontally”

#### Variable Name Display

- When "Show Variable Names" is checked, the actual variable path (e.g., `memory.name`, `endings`, etc.) is shown next to each item, making it easy to locate values in the save file

#### Change Notifications (Toast)

- When the `DevilConnection_sf.sav` save file is modified externally, notifications are automatically displayed
- Shows real-time change details (variable names and value changes)
- Changes to the `record` and `initialVars` variable are excluded by default. (You can enable those in the 'Others' tab, however it may cause performance issues.)

### Screenshot Management Tab

#### Drag & Drop Reordering

- Click and drag list items to change order (the in-game gallery will reflect the new order)
- An arrow indicator shows which file is being moved during drag

#### Batch Export

- All selected images will be packed into a single ZIP file

### Q: Why is there no feature to directly read/edit the `DevilConnection_tyrano_data.sav` save file?

- A: I plan to add this feature in a future update. For now, I have added a button to decode export/encode import the `tyrano.sav`, so you can use that to handle the file manually.

### Q: What is this tool actually useful for?

A: It doesn't have huge practical value. The most useful parts are probably quickly checking sticker counts and NEO value, and easily importing/exporting gallery screenshots.

## Important Notes

- The tool directly modifies the game's screenshot save files and the main save file. If you're worried, please **back up** the entire `_storage` folder first
- Reordering changes the actual display order in the in-game gallery
- ⚠️ Deletion permanently removes both the file and its index entry — it cannot be undone
- ⚠️ Be careful when editing the save file. Invalid JSON, deleted required fields, etc., can make the save unreadable and break the game. Only edit when you know what you are doing, and always make a backup before editing.
- This tool is completely unofficial and has no affiliation with the developers of 《でびるコネクショん》. It only fetches/edits locally stored save and screenshot files; does not modify core game files. If the developers have any issues with it, please let me know via GitHub Issues, and I will handle it immediately.

## License

MIT License

## Contributions

This was written in spare time and works fine in my own testing, but there may be edge cases. Issues and pull requests are very welcome!

</details>
