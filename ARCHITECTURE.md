# 代码结构（给开发者）

入口：`main.py` → `src/modules/main/main_window.py` 的 `SavTool`，负责主窗口、菜单和 6 个标签页。
选择 `_storage` 文件夹后，「sf 存档分析」和「截图管理」立即创建；其余标签页在第一次切换过去时才创建。

## 目录

```
src/
  constants.py            版本号、存档文件名、游戏内容总数等常量
  utils/                  各标签页共用的工具（不属于某个具体功能）
    sav_io.py             .sav 读写：read_sav / write_sav（原子写入）
    background.py         run_in_background：耗时操作放到后台线程，结果回到主线程
    ui_utils.py           create_dialog、widget_alive、*_relative 消息框、窗口图标等
    styles.py             字体、Colors、white_button、ttk 样式
    images.py             data URI 与图片互转
    translations.py       界面文本（zh_CN / en_US / ja_JP，三种语言的键必须一致）
    toast.py              右下角的通知窗口
    hint_animation.py     「开启修改」复选框的提示动画
  modules/
    main/                 主窗口、菜单、Steam 目录检测、检查更新、sf 存档变动提示
    save_analysis/sf/     sf 存档分析页、存档查看/编辑窗口（save_file_viewer.py）
    save_analysis/tyrano/ Tyrano 存档（游戏内存档槽）页
    screenshot/           截图管理页
    backup/               备份/还原页
    runtime_modify/       运行时修改页：通过 Chrome DevTools Protocol 连接游戏
    others/               「其他」页
    common/               两个以上标签页共用的组件（图片导出/替换、拖拽排序列表）
```

每个标签页基本分成两部分：

- **数据部分**（不涉及 Tk，有单元测试）：`backups.py`、`fields.py`、`tyrano/analyzer.py`、
  `screenshot_manager.py`、`runtime_modify/service.py` 等。出错时抛出异常。
- **界面部分**：`*_ui.py`、`tab.py`、`save_viewer.py` 等，负责控件和把异常显示成提示框。

标签页的约定：构造参数是 `(parent, [root,] storage_dir 或数据对象, t)`，切换语言时主窗口调用 `update_language()`。

## 游戏的存档文件（`_storage` 文件夹）

| 文件 | 内容 |
|---|---|
| `DevilConnection_sf.sav` | 全局进度：结局、贴纸、统计等 |
| `DevilConnection_tyrano_data.sav` | 游戏内的存档槽（含缩略图） |
| `DevilConnection_photo_*.sav`、`ids.sav`、`all_ids.sav` | 相册截图和它们的顺序 |
| `NEO.sav` | NEO 相关数据 |

`.sav` 的内容都是「URL 编码后的 JSON」，统一用 `src/utils/sav_io.py` 读写。
备份保存在 `_storage` 旁边的 `dcsm_backups/*.zip`。

## 几条规则

1. **不要在后台线程里操作界面**（包括 `after()`、`winfo_exists()`、消息框）。
   耗时操作用 `run_in_background(widget, work, on_done)`，`on_done` 在主线程执行。
2. **写游戏文件一律用 `write_sav` / `write_text_atomic`**，避免写到一半留下损坏的存档。
   修改前重新读取文件（玩家可能开着本工具同时在游戏里存档）。
3. **界面文字都放在 `translations.py`**，新增的键要同时加到三种语言；用 `t("key", 参数=值)` 取文字。
4. 弹窗用 `create_dialog`，按钮用 `white_button`，判断控件是否还在用 `widget_alive`。

## 开发

```bash
pip install -r requirements.txt ruff pytest
ruff check .          # 代码检查
python -m pytest -q   # 测试（部分测试需要图形界面，Linux 上可用 xvfb-run）
python main.py        # 运行
```

Windows 单文件版用 `nuitka_build.bat` 打包；推送 `v*` 标签时 GitHub Actions 会自动打包并发布。
