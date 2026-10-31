# 代码结构

入口是 `main.py`，主窗口在 `src/modules/main/main_window.py`（`SavTool`）。
sf 分析和截图两页在选好 `_storage` 后创建，其他页第一次打开时才创建。

```
src/
  constants.py        版本号、文件名、各类内容总数
  characters.py       角色名对照（日文名 -> 各语言）
  utils/              公用工具
    sav_io.py         .sav 读写
    background.py     后台任务
    translations.py   界面文字（日/简中×2/繁中/英）
  modules/
    main/             主窗口、Steam 路径检测、检查更新、存档变动提示
    save_analysis/
      sf/             sf 存档分析、存档查看/编辑
      tyrano/         游戏内存档槽
    screenshot/       截图管理
    backup/           备份/还原
    runtime_modify/   运行时修改（CDP）
    others/           其他
    common/           多个页面共用的组件
```

每页基本是一个数据文件（不依赖 Tk，有测试）加一个界面文件。

## 存档文件

都在游戏的 `_storage` 目录下，内容是 URL 编码的 JSON。

- `DevilConnection_sf.sav`：全局进度（结局、贴纸、统计）
- `DevilConnection_tyrano_data.sav`：存档槽
- `DevilConnection_photo_*.sav`、`ids.sav`、`all_ids.sav`：相册截图及顺序
- `NEO.sav`

备份存在 `_storage` 同级的 `dcsm_backups/`。

## 注意

- 后台线程不要碰 Tk，用 `run_in_background(widget, work, on_done)`。
- 写存档用 `write_sav` / `write_text_atomic`，写之前重新读一遍，游戏可能同时在存档。
- 新加的文字各语言都要加，测试会检查。`zh_CN` 是古今狐白汉化的叫法，`zh_CN_official` 只覆盖游戏内容（名字、选项），界面文字沿用 `zh_CN`。
- 弹窗用 `create_dialog`，按钮用 `white_button`。

## 开发

```bash
pip install -r requirements.txt ruff pytest
ruff check .
python -m pytest -q
python main.py
```

打包用 `nuitka_build.bat`，推 `v*` tag 会自动发布。
