# Devil Connection Screenshot Tool

<details>
<summary>日本語 (Japanese)</summary>

> [!WARNING]
> 本READMEはLLMによって翻訳されています。不正確な部分がある場合はご容赦ください。

『でびるコネクショん』のゲーム内スクリーンショット保存ファイルを管理・編集するための、シンプルで扱いやすい小さなツールです。

ゲーム本体もとても素晴らしいので、[Steam ストアページ](https://store.steampowered.com/app/3054820/) からぜひ開発者の方を応援してください。

GUI は tkinter と [Sun Valley theme](https://github.com/rdbende/Sun-Valley-ttk-theme) を使って構築しています。

## 機能

* 🖼️ **スクリーンショットプレビュー**：`.sav` ファイル内の base64 画像を自動的にデコードしてプレビュー表示
* ➕ **スクリーンショットの追加・置換・削除**：ゲームギャラリーに任意の画像を追加したり、既存のスクリーンショットを置き換え／削除したりできます
* 📤 **画像のエクスポート**：スクリーンショットを png/jpeg/webp 形式の画像ファイルとして書き出し
* 🔀 **並べ替え機能**：ギャラリー内でのスクリーンショットの表示順を自由に変更
* ☑️ **複数選択機能**：チェックボックスで複数選択に対応し、まとめて操作が可能
* ❇️ **セーブデータ分析（ベータ）**：未解放のエンディング／キャラクター／ステッカーの数と番号、その他いくつかのセーブデータ情報を表示（まだ網羅的ではありません）

## インストール

### 前提条件

* Python 3.8 以上

### インストール手順

* ※Python や依存パッケージをインストールしたくない場合は、Releases ページから単体の exe ファイルをダウンロードして利用することもできます。

1. このリポジトリをクローンまたはダウンロードします。

2. 依存パッケージをインストールします：

```bash
pip install -r requirements.txt
```

## 使い方

1. プログラムを実行します：

```bash
python main.py
```

2. ゲームのディレクトリを選択します：

   * 「フォルダを参照」ボタンをクリック
   * ゲームの `_storage` ディレクトリを選択
     （例：`C:\Program Files (x86)\Steam\steamapps\common\でびるコネクショん\_storage`）

3. 指定したディレクトリ内の `DevilConnection_photo_XXXXXXXX.sav` 形式のファイルと `DevilConnection_sf.sav` ファイルを自動的に取得し、各機能で利用します。

## 補足説明

### ドラッグによる並べ替え

* リスト項目をクリックしてドラッグすることで順番を変更できます（実際のゲーム内ギャラリーにもこの順番が反映されます）。
* ドラッグが完了すると、どのファイルをドラッグしたかを示す矢印インジケーターが表示されます。

### 一括エクスポート

* 一括エクスポートでは、選択されているすべての画像を 1 つの ZIP ファイルにまとめて出力します。

### Q：このプロジェクトは何の役に立ちますか？

* A：そこまで大きな実用目的があるわけではありませんが、ゲーム内スクリーンショットのインポート／エクスポートを手軽に行えるようになります。また、任意の画像にゲーム内スクショを素早く追加したい場合、画像をいったんゲームに取り込み、ゲーム内で編集してから再度取り出す、といった遊び方もできます。ちょっとしたおもちゃとして楽しんでください。

## 注意事項

* 操作はゲームのスクリーンショット保存ファイルを直接変更します。不安な場合は、事前に `_storage` ディレクトリをバックアップしておくことをおすすめします。
* 並べ替え操作は、ゲーム内ギャラリーにおけるスクリーンショットの表示順にも影響します。
* ⚠️ 削除操作はスクリーンショットファイルとインデックス情報の両方を削除します。元に戻すことはできないため、十分ご注意ください。
* 本ツールはゲーム『でびるコネクショん』の公式・開発者とは一切関係のないファンメイドツールです。ゲームのコアファイルを変更することはなく、ユーザーのローカル環境で生成されたスクリーンショット保存ファイルのみを操作します。

## ライセンス

MIT License

## コントリビュートについて

* 本プロジェクトは空き時間に作成したもので、個人の環境では問題なく動作することを確認していますが、どうしても見落としなどがあるかもしれません。issue や pull request をいただけると非常に助かります。

* 理論上、少し手を加えれば Tyrano で作成され、スクリーンショットを .sav ファイルとして保存するすべてのゲームをサポートできるはずですが、現在は使いやすさのため『でびるコネクショん』特化のツールとして作成しています。

</details>

<details>
<summary>中文 (Chinese)</summary>

一个用于管理和编辑 でびるコネクショん 游戏截图保存文件的简单易用小工具。

游戏很棒，这里是 [Steam商店页面](https://store.steampowered.com/app/3054820/)，欢迎支持游戏作者。

使用tkinter/[Sun Valley theme](https://github.com/rdbende/Sun-Valley-ttk-theme)构建GUI。

## 功能特性

- 🖼️ **截图预览**：自动解码.sav文件中的base64图像并预览
- ➕ **新增，替换，删除截图**：添加新的自定义图片到游戏画廊，替换或删除已有截图
- 📤 **导出图片**：导出截图为png/jpeg/webp图片文件
- 🔀 **排序功能**：自由调整截图在画廊中显示的顺序
- ☑️ **多选功能**：支持复选框多选，方便批量操作
- ❇️ **存档分析（Beta）**：显示未解锁的结局/角色/贴纸数量及具体编号，以及游戏存档中的其他一些信息。暂不全面。

## 安装

### 前置要求

- Python 3.8 或更高版本

### 安装步骤

- 注意：你也可以前往Releases页面下载单exe文件，该方式无需安装Python或任何依赖

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
   - 选择游戏的 `_storage` 目录（例如：`C:\Program Files (x86)\Steam\steamapps\common\でびるコネクショん\_storage`）

3. 程序会自动获取所有该目录下形如`DevilConnection_photo_XXXXXXXX.sav`的文件以及`DevilConnection_sf.sav`文件，使用功能。

## 额外说明

### 拖拽排序

- 点击并拖拽列表项可以调整顺序（实际游戏内画廊会反映这个顺序）
- 拖拽完成后会显示箭头指示器提示哪个文件被拖拽

### 批量导出

- 批量导出会将所有选中的图片打包成一个 ZIP 文件。

### Q：这个项目有什么用？

- A：没什么很大的实际用途。方便导入导出游戏内截图。同时如果你想快速往图片中添加一个游戏内的截图可以将图片导入进去，在游戏中修改，再提取出来。可以玩玩。

## 注意事项

- 操作会直接修改游戏的截图保存文件，若有担心建议先备份 `_storage` 目录
- 排序操作会改变截图在游戏画廊中的显示顺序
- ⚠️删除操作会同时删除截图文件和索引信息，无法撤销，请谨慎操作
- 本工具与游戏《でびるコネクショん》官方及开发者完全无关，仅为玩家自制工具。工具不涉及修改游戏核心文件，仅操作用户本地生成的截图保存文件。

## 许可证

MIT License

## 贡献

- 本项目是利用闲暇时间写出的，经个人测试未发现使用问题，但难免会有疏漏。非常欢迎提交issue或者pull request。

- 理论上该项目经过一些小改动应该就可以支持所有使用Tyrano构建且以.sav文件保存截图的游戏，但目前为了方便使用是 でびるコネクショん 特化。

</details>

<details>
<summary>English</summary>

A small, easy-to-use tool for managing and editing screenshot save files for the game **でびるコネクショん**.

Honestly fantastic game – here is the [Steam store page](https://store.steampowered.com/app/3054820/). Please consider supporting the developer.

The GUI is built with tkinter and the [Sun Valley theme](https://github.com/rdbende/Sun-Valley-ttk-theme).

## Features

* 🖼️ **Screenshot preview**: Automatically decodes base64 images stored in `.sav` files and displays them.
* ➕ **Add, replace, delete screenshots**: Add custom images to the in-game gallery, or replace / delete existing screenshots.
* 📤 **Export images**: Export screenshots as PNG/JPEG/WebP image files.
* 🔀 **Sorting**: Freely adjust the order in which screenshots appear in the in-game gallery.
* ☑️ **Multi-select**: Checkbox multi-selection for convenient batch operations.
* ❇️ **Save analysis (Beta)**: Shows the number and IDs of endings/characters/stickers that are still locked, plus some other information in the save file. (Not yet complete.)

## Installation

### Requirements

* Python 3.8 or higher

### Steps

> Note: You can also download the standalone EXE from the Releases page. With that version you do **not** need to install Python or any dependencies.

1. Clone or download this repository.

2. Install dependencies:

```bash
pip install -r requirements.txt
```

## Usage

1. Run the program:

```bash
python main.py
```

2. Select the game directory:

   * Click the **“Browse directory”** button.
   * Select the game’s `_storage` folder (for example:
     `C:\Program Files (x86)\Steam\steamapps\common\でびるコネクショん\_storage`)

3. The program will automatically load all files in that folder matching
   `DevilConnection_photo_XXXXXXXX.sav` as well as `DevilConnection_sf.sav`,
   and you can then use all features.

## Extra Notes

### Drag-and-drop sorting

* Click and drag list items to change their order (the in-game gallery will reflect this order).
* After dragging, an arrow indicator will show which file was moved.

### Batch export

* Batch export packs all selected images into a single ZIP file.

### Q: What’s the point of this project?

* A: It doesn’t have any big practical purpose. It just makes importing and exporting in-game screenshots easier.
  For example, if you want to quickly add an in-game-style screenshot to an image, you can import the image, tweak it in the game, then extract it again. It’s something fun to play with.

## Notes / Warnings

* Operations directly modify the game’s screenshot save files. If you’re worried, back up the `_storage` folder first.
* Sorting will change the display order of screenshots in the in-game gallery.
* ⚠️ Deleting will remove both the screenshot file **and** its index entry. This cannot be undone, so please be careful.
* This tool is completely unofficial and not affiliated with the developers of **でびるコネクショん**.
  It does not modify any core game files; it only works on screenshot save files generated locally by the user.

## License

MIT License

## Contributing

* This project was written in spare time. I haven’t run into issues in my own testing, but there may still be oversights. Issues and pull requests are very welcome.

* In theory, with a few small tweaks this tool should work for any game built with Tyrano that stores screenshots in `.sav` files. For now, however, it is tailored specifically to **でびるコネクショん** for ease of use.


</details>
