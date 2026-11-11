# Block Story Character Save Editor

A local desktop-style save editor for **Block Story** (Steam 14.x, Mono build), built with Streamlit.
It reads the game's plain-JSON `.chr` character saves, lets you inspect and edit them with type
validation and automatic backups, then writes changes atomically.

**English** · [简体中文](#简体中文)

> Unofficial fan tool. Not affiliated with Mindblocks or the Block Story rights holders.
> No game assets, textures, audio or localisation files are bundled.

## Features

- **Overview** — character summary, level, per-mode data counts and the current validation report.
- **Fields** — every save key grouped by category, with type-aware editors and search. Unknown keys
  are preserved verbatim instead of being dropped.
- **Items & containers** — inventory, quickslot, equipment, pet bag, pet gear and placed containers
  rendered as grids. Drag to reorder or click-to-move between slots; the first four inventory slots
  are shown separately because the game reserves them.
- **Quests & achievements** — main-story stage slider (19 chapters), side quests, dailies and
  achievements, with optional synchronisation of recipes and of side/daily states.
- **Mode data** — choose Story, Survival, Creative, Hardcore or Sandbox from the sidebar and edit
  only that mode. A dedicated page can copy one mode into an empty mode, or clear a mode, with
  guards against overwriting data and against clearing the last populated mode.
- **Tidy** — normalise slot keys, drop empty slots and compact numbering.
- **Reset paths** — level/skills, items, quests, pets and a full reset, each previewed as a key-level
  diff before it is applied.
- **Review & save** — validation gate, key-level diff, timestamped backup, atomic replace and
  read-back verification. Backups can be restored from the UI.
- **Five UI languages** — English, 简体中文, Русский, Português (Brasil), Español. Game item, mob and
  quest names follow the language set in the game files.

## Requirements

| Item | Requirement |
|---|---|
| OS | Windows 10/11 (tested). The app is plain Python + Streamlit and can be started manually elsewhere. |
| Game | Block Story from Steam, 14.x line, unencrypted `.chr` saves |
| Python | 3.12 or newer (developed on 3.14) |
| Disk | About 1 GB free for `.venv` and the local catalog cache |
| Network | Required on first run to download the pinned dependencies |

## Run on a new PC (Windows)

### From the release RAR

1. Extract the **whole archive** to a writable folder, for example
   `D:\Games\BlockStory-ChrEditor`. Do not run it from inside the RAR, and avoid
   `C:\Program Files` — the launcher creates `.venv` next to itself.
2. Install **Python 3.12+** from <https://www.python.org/downloads/>.
   Tick **Add python.exe to PATH** during installation.
3. Double-click **`start.bat`** (or `启动.bat`).
   - First run: creates `.venv`, installs the pinned packages (roughly 150 MB; a slow
     connection can take several minutes), then opens <http://localhost:8501>.
   - Later runs: starts in a few seconds.
4. If Windows SmartScreen appears, choose **More info → Run anyway**. The launcher is a
   plain-text `.bat` file and can be inspected.
5. Pick your save in the sidebar. The editor opens saves read-only until you enable editing.

The launcher checks every pinned package, not just Streamlit. If one is missing or has the
wrong version, it runs `pip install -r requirements.txt` before starting.

### From the source repository

```bat
git clone https://gitee.com/rainxinxy/BlockStory-ChrEditor.git
cd BlockStory-ChrEditor
start.bat
```

The same launcher and dependency check apply.

### Manual start

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe bootstrap.py
```

`bootstrap.py --check` only verifies dependencies. `bootstrap.py --no-browser` starts the
server without opening a browser.

### Troubleshooting

| Symptom | Fix |
|---|---|
| `Python 3.12+ was not found` | Install Python 3.12+, tick “Add python.exe to PATH”, then reopen the folder. |
| `The existing .venv uses Python older than 3.12, or it is broken` | Delete the `.venv` folder and run `start.bat` again. |
| Dependency installation fails | Check the network/proxy, or retry with a mirror: `.venv\Scripts\python.exe -m pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/` |
| Browser does not open | Read the URL printed in the console (`http://localhost:8501`, or the next free port) and open it manually. |
| `Catalog unavailable` | Point the editor at the game data: `set BS_GAME_DATA_DIR=D:\Games\BlockStory\Block Story_Data` |
| Save not listed | Use “Browse” or type the full path. A custom save folder can be set with `set BS_SAVE_DIR=D:\path\to\characters`. |
| Antivirus blocks the `.bat` | Allow the extracted folder; the launcher only creates `.venv` and runs Python. |

Offline installation: on a networked machine run
`pip download -r requirements.txt -d wheels`, copy the `wheels` folder with the release,
then set `PIP_NO_INDEX=1` and `PIP_FIND_LINKS=D:\path\to\wheels` before `start.bat`.

### What the release package contains

Included: runtime Python sources, `ui/`, `views/`, `locales/`, `.streamlit/config.toml`,
`requirements.txt`, `bootstrap.py`, `start.bat` / `启动.bat`, `README.md`, `LICENSE`,
`BUILD.txt` (build date and commit).

Excluded: `.venv/`, `.cache/`, `tests/`, Git history, personal saves, labels, and any game
assets. The catalog is rebuilt from the game installation on first use. Tests and development
files live in the source repository.

### Finding the game data

The editor derives item, mob and quest names from your own installation. It scans common Steam
locations automatically. If the game lives elsewhere, point it at the `Block Story_Data` folder:

```bat
set BS_GAME_DATA_DIR=D:\Games\BlockStory\Block Story_Data
```

The derived catalog is cached in `.cache/` (git-ignored) and rebuilt when the game files change.

### Where saves live

```
%USERPROFILE%\AppData\LocalLow\Mindblocks\Block Story\characters\*.chr
```

The editor never touches the game installation. It only reads save files you open.

## Safety model

- Saves open **read-only**; editing requires turning on the edit switch.
- Every change stays in memory until you press save.
- Before writing: schema validation → serialisation check → timestamped backup → temp file →
  atomic replace → read-back comparison.
- Edits can be undone in the UI; backups are kept per file and can be restored.
- The test suite only ever writes to temporary copies.

Back up your own saves before the first real use, as you would with any save editor.

## Tests

Tests are not included in the release RAR; run them from the source repository. The suite is
dependency-light and does not need pytest:

```bat
for %f in (tests\test_*.py) do .venv\Scripts\python.exe %f
```

The one test that inspects a real game installation skips itself when the game is absent.
Current status: 9 test files, 300+ assertions. The real-save round-trip count varies with the
number of local backups.

## Project layout

| Path | Purpose |
|---|---|
| `app.py` | Entry point, sidebar, mode selector, page routing |
| `bootstrap.py` | Dependency check, installation, free-port selection and server start |
| `bsjson.py` | Order-preserving JSON reader/writer for the save format |
| `model.py` | Save document, undo stack, dirty tracking |
| `schema.py` | Key catalog, categories, slot and mode suffix parsing |
| `validate.py` | Blocking errors vs. warnings, typed checks |
| `storage.py` | Scanning, backups, atomic writes, restore |
| `itemops.py` | Item snapshots, moves, ordering |
| `questops.py` | Mainline stages, side/daily resets, recipe sync |
| `modeops.py` / `modeview.py` | Mode copy/clear and per-mode views |
| `reset.py` / `tidy.py` | Reset plans and tidying |
| `gamedata.py` | Extracts item/mob/quest metadata from the local game |
| `i18n.py`, `locales/` | UI strings for five languages |
| `ui/`, `views/` | Theme and pages |

## Known limitations

- Creative and Sandbox disable quests in the game itself, so no quest keys are copied into them.
- Only the 14.x plain-JSON format is supported; encrypted or much older saves are rejected.
- Some key semantics are reverse-engineered. Unknown keys are kept and shown, but not type-checked.
- The built-in file dialog uses Tk; running on a headless machine requires the manual upload path.

## License

MIT — see [LICENSE](LICENSE).

---

## 简体中文

**Block Story 角色存档编辑器**，基于 Streamlit 的本地工具，面向 Steam 14.x（Mono、明文 JSON 存档）版本。

### 能做什么

- **概览**：角色概况、等级、各模式数据量与当前校验结果。
- **字段**：按分类浏览全部存档键，带类型化编辑与搜索；未知键原样保留。
- **物品与容器**：背包、快捷栏、装备、宠物背包、宠物装备、放置容器按格子展示，支持拖拽排序与点选移动。背包前 4 格是游戏保留槽，单独一行显示。
- **任务与成就**：19 环主线阶段滑块、支线、日常与成就；可联动同步配方和解锁状态。
- **模式数据**：侧栏切换剧情/生存/创造/硬核/沙盒，只编辑所选模式；独立页面支持“复制到空模式”和“清除模式”，并阻止覆盖已有数据与清除最后一个有数据的模式。
- **整理**：规范化槽位键、删除空槽、压缩编号。
- **重置**：等级与技能、物品、任务、宠物、彻底重置；应用前显示键级差异。
- **校验与保存**：校验闸门、差异预览、带时间戳备份、临时文件原子替换、回读自检；可在界面内还原备份。
- **五种界面语言**：English、简体中文、Русский、Português (Brasil)、Español。

### 在新电脑上运行（Windows）

**从发布包（RAR）**

1. 把压缩包**完整解压**到可写目录，例如 `D:\Games\BlockStory-ChrEditor`。
   不要直接在压缩包内运行，也不要放进 `C:\Program Files`（启动器需要在该目录创建 `.venv`）。
2. 安装 **Python 3.12+**：<https://www.python.org/downloads/>，安装时勾选
   **Add python.exe to PATH**。
3. 双击 **`start.bat`**（或 `启动.bat`）。
   - 首次运行：创建 `.venv`、联网安装固定版本依赖（约 150 MB，慢速网络可能需要几分钟），
     然后打开 <http://localhost:8501>。
   - 以后运行：几秒内启动。
4. 若出现 SmartScreen，选择“更多信息 → 仍要运行”。启动器是纯文本 `.bat`，可以直接查看。
5. 在侧栏选择存档。编辑器默认只读，需手动开启编辑。

启动器会逐项核对 `requirements.txt` 里的所有固定版本，缺包或版本不符才会执行安装；
8501 被占用时会自动选择下一个空闲端口，并在控制台打印实际地址。

**从源码**

```bat
git clone https://gitee.com/rainxinxy/BlockStory-ChrEditor.git
cd BlockStory-ChrEditor
start.bat
```

**常见问题**

| 现象 | 处理 |
|---|---|
| 提示 `Python 3.12+ was not found` | 安装 Python 3.12+，勾选 PATH，重新打开文件夹。 |
| 提示 `.venv` 版本过旧或损坏 | 删除 `.venv` 文件夹，重新运行 `start.bat`。 |
| 依赖安装失败 | 检查网络/代理，或使用镜像：`.venv\Scripts\python.exe -m pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/` |
| 浏览器没有自动打开 | 复制控制台打印的地址（`http://localhost:8501` 或下一个端口）手动打开。 |
| 提示 `Catalog unavailable` | 设置 `set BS_GAME_DATA_DIR=D:\Games\BlockStory\Block Story_Data` |
| 存档列表里没有目标存档 | 用“浏览”选择文件；也可用 `set BS_SAVE_DIR=D:\path\to\characters` 指定目录。 |

离线安装：在有网的机器执行 `pip download -r requirements.txt -d wheels`，把 `wheels`
目录随发布包一起拷贝，运行前设置 `PIP_NO_INDEX=1` 和 `PIP_FIND_LINKS=D:\path\to\wheels`。

发布包只含运行所需文件，不含 `.venv`、`.cache`、测试、Git 历史、个人存档或游戏资源；
物品目录会在首次运行时从本机游戏文件重建。

游戏目录通常会自动探测；不在默认 Steam 目录时，按上表设置 `BS_GAME_DATA_DIR`。
存档位置：`%USERPROFILE%\AppData\LocalLow\Mindblocks\Block Story\characters\*.chr`。
编辑器只读取你主动打开的存档，不会修改游戏安装目录。

### 安全约定

默认只读，需手动开启编辑；所有改动留在内存，直到你点击保存。写入前依次做校验、序列化检查、备份、原子替换与回读比对。首次使用前请自行备份存档。

### 说明

- 创造与沙盒模式在游戏内关闭任务系统，因此不会复制任务键。
- 仅支持 14.x 明文 JSON 存档。
- 本项目为玩家工具，与 Mindblocks 及 Block Story 权利人无关，不包含任何游戏原始资源。
- 许可证：MIT。
