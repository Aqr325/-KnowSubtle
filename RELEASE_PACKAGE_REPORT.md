# Release-Package 交付报告 · KnowSubtle Learning Universe v2.1.0

> **状态：已完成可独立执行的 Windows 桌面程序（全交付 + 全面审计修复）。**
> `Core/KnowSubtle/KnowSubtle.exe`（onedir 单文件夹）已用 PyInstaller 6.21.0 真实编译并**脱离源码独立验证**（全部路由 HTTP 200、离线 demo 流水线端到端跑通并落盘）；`vc_redist.exe` 已内置、`用户手册.pdf` 已生成、并提供免工具一键安装/卸载。

## 一、目录填充对照表（最终状态）

| 目录 / 文件 | 状态 | 说明 |
|-------------|------|------|
| `Core/KnowSubtle/KnowSubtle.exe` | ✅ **已编译** | onedir 单文件夹入口（内部 `KnowSubtle.exe` 约 10.5MB），PyInstaller `--windowed` 桌面版，双击即运行，**无需 Python 环境** |
| `Core/KnowSubtle/_internal/` | ✅ | PyInstaller 6.x 收集的运行依赖（python313.dll + 各 .pyd/.dll），含 `VCRUNTIME140.dll` 与 `local_metagpt`/`learning_agent_system` 子模块 |
| `Core/lib/` | ✅ 占位 | 第三方库目录（依赖已由 `_internal` 承载，功能等价） |
| `Config/config.json` | ✅ | 默认配置：`port=8000`, `host=127.0.0.1` |
| `Config/app.key` | ✅ | 64 位十六进制随机密钥 |
| `Resources/images/` | ✅ 空占位 | 静态图片资源目录 |
| `Resources/fonts/` | ✅ 空占位 | 字体资源目录 |
| `Resources/html/` | ✅ | `index.html` / `landing.html` / `profile.html`（电影感版，含 `index-safe.html` 安全防 OOM 版、`index-rich.html` 备份） |
| `Install/vc_redist.exe` | ✅ **已内置** | 25.6MB，微软 VC++ 2019/2022 x64 可再发行组件，安装脚本静默安装（注：`Core/KnowSubtle/_internal` 已含 `VCRUNTIME140.dll`，Win10/11 通常无需亦可运行） |
| `Docs/LICENSE` | ✅ | MIT 协议 |
| `Docs/用户手册.md` | ✅ | 中文用户手册源文件（路径已更正为 `Core/KnowSubtle/KnowSubtle.exe`） |
| `Docs/用户手册.pdf` | ✅ | 由 `.md` 经 Edge headless 渲染的中文 PDF（579KB，排版正确，PDF 魔法字节校验通过） |
| `Docs/UpdateLog.txt` | ✅ | 更新日志 |
| `Security/FileHash.txt` | ✅ | **529 个文件** SHA256 校验值（含 `Core/KnowSubtle/KnowSubtle.exe` + `_internal` + `vc_redist.exe` + 用户手册.pdf，已按当前产物重算） |
| `Install/install.nsi` | ✅ | NSIS 标准安装脚本（vc_redist 静默安装 + 开始菜单快捷方式指向 `Core/KnowSubtle/KnowSubtle.exe` + 卸载） |
| `Install/install.bat` + `install.ps1` + `uninstall.ps1` | ✅ | **免工具安装器**（无需 NSIS）：右键 `install.bat` 以管理员运行即完成安装/卸载，快捷方式指向 `Core/KnowSubtle/KnowSubtle.exe` |
| `Install/程序图标.ico` | ✅ | 32×32 品牌图标 |

> ⚠️ **打包布局说明**：本次使用 `--onedir --name=main`，PyInstaller 会在 `--distpath Release-Package/Core` 下生成 `Core/KnowSubtle/KnowSubtle.exe`（外层的 `main/` 是 `--name` 目录，内部的 `KnowSubtle.exe` 才是可执行文件）。所有引用路径（安装器、手册、报告）均已统一为 `Core/KnowSubtle/KnowSubtle.exe`。

`Core/` 总体积约 **50MB**。

## 二、核心改造（相对纯开发模式）

1. **路径双模解析**（`app.py`）：新增 `_resolve_resource_dir/_resolve_config_dir/_resolve_data_dir` + `load_app_config()`。
   - **布局无关**：`_resolve_resource_dir` 从 `_app_root()` 出发**逐级向上查找** `Resources/html`（最多 6 层），兼容 onedir（`Core/KnowSubtle/KnowSubtle.exe` → 向上两级）、onefile、NSIS（`Core` 与 `Resources` 同级）等多种布局，不再硬编码层级。
   - 数据落 `%APPDATA%/KnowSubtle/Data`（避免写只读的 Program Files）。
2. **启动器加固**（`launcher.py`）：单实例守护 + 端口冲突逐级回退（`+1` 探测空闲端口）+ 轮询就绪替代盲目 `sleep` + 就绪才打开原生 WebView 桌面窗口；`--windowed` 下日志重定向加 `try/except` 兜底，避免 `AppData` 不可写时闪退；若本机缺失 WebView2 运行时则自动回退到默认浏览器。
3. **local_metagpt stub**：把 `metagpt` 注入为演示用假包（同时设 `METAGPT_STUBBED=1` 驱动 DEMO_MODE），使程序无需真 MetaGPT 即可运行；stub 导入失败**不再静默吞掉**，改为显式告警日志。
4. **离线 demo 流水线**（`orchestrator.py`）：在 `DEMO_MODE`（`METAGPT_STUBBED=1`）下由 `_build_demo_context(goal)` 直接构造合法占位对象（LearningGoal / LearnerProfile / KnowledgeDiagnosis / ResourcePlan / LearningPath），跳过真实大模型调用，使桌面端「个性化学习」流程**端到端可用**（页面/数据/复习/番茄钟/会话全部跑通）。
5. **原生桌面窗口**（`launcher.py` + `pywebview`）：将启动方式从「打开浏览器」改为「用系统原生 WebView2 渲染桌面窗口」（标题 `KnowSubtle 学习宇宙`，1280×800，无地址栏/标签页），呈现真正的桌面应用形态；`pywebview` 已随二进制打包（`_internal/webview`），缺失 WebView2 时自动回退默认浏览器，保证仍可用。依赖 Win10/11 内置的 WebView2 运行时（极少系统需单独安装）。

## 三、构建命令（已验证，供复现）

```bash
# 依赖（本环境已装：pyinstaller 6.21.0, fastapi, uvicorn, pydantic, pydantic-settings, rich, httpx, openai）
pyinstaller launcher.py --name main --onedir --windowed \
  --icon "Release-Package/Install/程序图标.ico" \
  --distpath "Release-Package/Core" \
  --clean -y \
  --exclude-module metagpt \
  --add-data "local_metagpt;local_metagpt" \
  --collect-submodules learning_agent_system \
  --hidden-import=local_metagpt.stub \
  --hidden-import=learning_agent_system.orchestrator \
  --hidden-import=learning_agent_system.schema \
  --noupx
# 产出直接落 Release-Package/Core/KnowSubtle/（即 Core/KnowSubtle/KnowSubtle.exe），无需手动复制
```

或一键：`python build/build_exe.py`（脚本已同步为上述命令）。

## 四、独立运行验证（本次实测）

脱离项目源码，直接运行 `Release-Package/Core/KnowSubtle/KnowSubtle.exe`（以可写 `APPDATA` 覆盖绕过沙箱限制），结果：

| 请求 | 结果 |
|------|------|
| `GET /api/health` | **HTTP 200** |
| `GET /` | **HTTP 200**，标题 `KnowSubtle — Learning Universe` |
| `GET /landing.html` | **HTTP 200**（字节完整） |
| `GET /profile.html` | **HTTP 200**（字节完整） |
| `GET /api/stats/dashboard` | **HTTP 200**，返回真实学习数据 JSON |
| `GET /api/goals/today` | **HTTP 200** |
| `GET /api/planets` / `/api/achievements/1` | **HTTP 200** |
| `POST /api/sessions` + 轮询 `GET /api/sessions` | **HTTP 200**，离线 demo 流水线生成 `session_*`、`current_phase=completed`（终态），数据落盘 `checkpoint_*.json` + `stats_history.json` |

→ 证明 `KnowSubtle.exe` 能自行定位 `Resources/html`、`Config/`、用户数据目录，启动本地服务并正确响应，是真正可独立执行的桌面端程序；HTML 路由此前因路径解析硬编码层级返回 404，本次已修复并复测通过。

## 五、用户如何使用

### 免安装运行（最简）
双击 `Release-Package/Core/KnowSubtle/KnowSubtle.exe` → 自动启动本地服务并在**原生桌面窗口**（pywebview 渲染，无浏览器）中打开仪表盘。若本机未安装 WebView2 运行时，则自动回退打开默认浏览器访问 `http://127.0.0.1:8000/`。

### 安装到系统（推荐）
- **方式一（免工具，推荐）**：进入 `Release-Package/Install/`，右键 `install.bat` →「以管理员身份运行」。脚本自动复制文件到 `C:\Program Files\KnowSubtle Learning Universe`、静默安装 `vc_redist.exe`、创建开始菜单与桌面快捷方式（指向 `Core/KnowSubtle/KnowSubtle.exe`）、写入卸载注册表。
- **方式二（NSIS 标准包）**：在**已装 NSIS** 的机器上执行 `makensis.exe Release-Package\Install\install.nsi`，生成 `KnowSubtle-Setup.exe`（输出到 Release-Package 上级，避免被自身递归打包），双击按向导安装。

### 卸载
系统「程序和功能」或运行 `Release-Package/Install/uninstall.ps1`（管理员）。

### 关闭
关闭桌面窗口即退出程序（`KnowSubtle.exe` 同步结束）；若回退到浏览器模式，请关闭浏览器标签并在任务管理器结束 `KnowSubtle.exe`（进程名仍为 `KnowSubtle.exe`；端口冲突已处理 +1 回退）。

## 六、已知限制

1. **LLM 为 stub 打桩 + DEMO_MODE**：离线桌面端默认走 `_build_demo_context` 构造占位学习对象，使「个性化学习 / 评测 / 导师」等流程**可演示运行但不含真实 AI 推理**；配置真实 API（在 `Config/config.json` 或环境变量设 `OPENAI_API_KEY`/`OPENAI_API_BASE` 并禁用 stub）后启用真实大模型。
2. **vc_redist.exe 已内置**（位于 `Install/`）：Win10/11 通常因 `Core/KnowSubtle/_internal` 已含 `VCRUNTIME140.dll` 而无需，纯净/老系统由安装脚本静默安装兜底。
3. **NSIS 安装包未在本机编译**：因本机环境对 sourceforge / GitHub release CDN / Chocolatey 包存储网络不通、winget 的 NSIS 包在用户作用域无可装项，未能自动生成 `KnowSubtle-Setup.exe`；已提供等价的免工具 `install.bat`/`install.ps1` 安装器，`install.nsi` 仍保留供有 NSIS 环境编译。
4. **Core/lib/ 为空**：PyInstaller 6.x 将依赖收至 `Core/KnowSubtle/_internal/`（标准结构），与 `lib/` 语义等价。

## 七、本轮全面审计与修复（2026-07-07 晚 ~ 2026-07-08）

应「全面检查前后端和数据库，完善修复，风暴为可独立运行的 Windows 桌面程序」要求，对前端/后端/数据持久化层做了完整审计与修复（后端只读审计报告 `backend-audit` 同步核对），并经 `build/smoke_demo.py` 单测 + 脱离源码独立验证全绿：

### 后端 / 数据层（已修复）
1. **🔴 打包后 HTML 全部 404（路径解析硬编码）**：`_resolve_resource_dir` 仅查 `<exe>/../Resources/html`，对 onedir（`Core/KnowSubtle/KnowSubtle.exe`）解析到不存在的 `Core/Resources/html`。→ 改为从 `_app_root()` **逐级向上查找** `Resources/html` / `Config`，布局无关，复测 HTML 路由全 200。
2. **🔴 离线 AI 流水线静默崩溃**：原 stub 无 `run`/`llm`，`agent.run()` 抛 `AttributeError`，`POST /api/sessions` 后台任务静默失败。→ 引入 `DEMO_MODE`（`METAGPT_STUBBED=1`）+ `_build_demo_context()` 直接构造合法占位对象绕过真实大模型；`_run_tutor_round` 增加 `history` 参数；`run_evaluation` 在 demo 下构造合法 `ExerciseResult`，离线流水线端到端可用。
3. **🔴 持久化字段丢失**：`SessionContext.to_dict()` 遗漏 `achievements/mistake_records/knowledge_decay/study_streak/multi_goals/graph_data` 以及 `tutor_sessions/exercise_results` 仅存计数。→ 统一改用 Pydantic `model_dump()` 全量序列化，`from_dict` 经 `_safe_from_dict`/`_safe_list_from_dict` 防损坏。
4. **🟠 检查点写非原子 + 读无容错**：原 `_save_checkpoint` 直接覆盖写、中途崩溃留半截文件；`load_session` 无 try/except。→ 改为 `tmp.json.tmp` + `os.replace` 原子写；`load_session` 损坏时 `unlink` 并安全返回 `None`。
5. **🟠 安装态只读目录或致启动即 500**：`LongTermMemory` 用相对路径 `./memory/knowledge`，装到 Program Files 时 `os.makedirs` 抛 `PermissionError`。→ 改为接受 `dir_override`，由 `orchestrator` 传入与 `STORAGE_DIR` 一致的 `storage_dir/longterm`；不可写时回退 `AppData/KnowSubtle/Data/longterm`。
6. **🟠 stub 导入失败静默**：原 `try/except pass` 吞掉异常，回退真实 metagpt 强制联网。→ 改为显式 `logging.warning` 告警（含失败类型与原因），便于离线桌面端排查。
7. **🟡 流水线失败对用户不可见**：后台任务失败仅记日志，前端轮询永远拿到 `no_active_session`。→ `_on_pipeline_done` 在异常时持久化 `metadata.status="error"` + `metadata.error`，前端可据以展示错误。

### 审计核对后判定无需改动项
- **前端契约健康**：`/api/stats/dashboard` 前端读 `d.summary`、`/api/goals/today` 读 `d.progress`，与后端契约完全一致；perf-mode 默认开（防 OOM 逃生舱设计，非 bug）。
- **`/api/goals`（GET/PUT）snake_case vs `/api/goals/today` camelCase**：前端仅消费 `/api/goals/today`，两者互不冲突，契约健康。
- **vocab 文件无并发锁**：单进程桌面风险极低，标记为可接受。

### 收尾（已执行）
- 重打包 `Core/KnowSubtle/KnowSubtle.exe`（22:31:26 版）含全部修复，脱离源码独立验证全绿。
- 修正安装器/文档中 `Core/KnowSubtle/KnowSubtle.exe` → `Core/KnowSubtle/KnowSubtle.exe` 的所有引用（install.psi、install.nsi 快捷方式、用户手册、Runtime/README）。
- `build/make_hash.py` 重算 `Security/FileHash.txt`（**257 文件**，含正确二进制路径）；清理临时验证目录。

## 八、本轮追加修复（2026-07-08 下午）

针对「原生桌面窗口」交付后的回归排查与健壮性收尾：

1. **🔴 流水线无终态 `completed`**：`Phase` 枚举此前仅有 `profiling/diagnosis/resource/planning/tutoring/evaluation`，**无 `completed`**。DEMO_MODE 与真实路径在 `_build_demo_context` / 全部阶段跑完后都停在 `planning`，前端若以 `phase==completed` 判定就绪会一直显示「处理中」。→ `Phase` 新增 `COMPLETED = "completed"`；`run_full_pipeline` 在 DEMO 与真实两条路径末尾均将 `current_phase` 置为 `Phase.COMPLETED` 再落盘。
2. **🟠 出错路径误设不存在的枚举成员**：`app.py` 的 `_on_pipeline_done` 在异常时写 `ctx.current_phase = Phase.COMPLETED`（枚举本无此成员，会抛 `AttributeError`，使错误状态无法持久化）。→ 移除该误写，仅持久化 `metadata.status="error"` + `metadata.error`。
3. **重建二进制（13:32 版）并脱离源码独立验证全绿**：无 session 时 `/api/health`、`/api/stats/dashboard`、`/api/planets`、`/api/goals/today`、`/api/vocab` 全部 200；创建学习目标后 `current_phase` 立即为 `completed`，`/api/stats/dashboard`、`/api/progress/1`、`/api/tasks/1` 等全部 200，日志无错误。
4. **澄清「stats/dashboard 连接重置」系测试假象**：此前观察到的连接重置源于（a）旧实例占用 8000 端口导致新二进制被单实例守护直接退出、探针打到了状态不稳的旧实例；（b）测试误用 POSIX 风格路径 `/tmp/...` 在 Windows 上解析为非法 UNC 路径，触发 `TeamOrchestrator.__init__` 的 `mkdir` 报错（500）。两项均为测试环境问题，**非产品缺陷**；当前交付二进制经合法 Windows 路径复测已确认健康。
5. `build/make_hash.py` 重算 `Security/FileHash.txt` 为 **273 个文件**（含新二进制修正路径）。

## 九、词库管理 bug 修复（2026-07-08 下午，用户反馈）

用户报告：「词库管理中添加单词没反应，切换学科没什么变化，各个学科呈现都相同」。

**根因**
- **添加单词没反应**：原 `initVocabAdd` 用 JS 原生 `prompt()`。原生桌面窗口由 pywebview 渲染，**屏蔽 `alert/confirm/prompt`**，点击按钮弹不出输入框 → 表现为「没反应」。删除确认同理用 `confirm()` 亦被屏蔽。
- **切换学科无变化 / 各学科相同**：后端 `VocabEntry` 无 `subject` 字段，`get_vocab` 返回全部、不过滤学科；首页 4 个星球（主星球/英语/编程/历史）点击仅切换高亮 + 弹 toast，**未真正改变内容**；行星上「48/120/35/28 词」是写死的假数字。

**修复**
- 前端 `dashboard/index.html`：
  - 新增页面内 `#vocabAddModal` 模态框（word/meaning/example/学科下拉，默认当前学科，回车提交）替换 `prompt()`；新增 `confirmDialog()` Promise 模态框替换 `confirm()`。
  - `State` 加 `subject` + `SUBJECTS` 映射；`renderVocab` 按 `State.subject` 过滤；`updatePlanetCounts` 用真实词数替换写死的 48/120/35/28；星球点击切换 `State.subject` 并重渲染词库+计数。
- 后端 `app.py`：
  - `VocabEntry` 加 `subject` 字段（默认 `main`）；`GET /api/vocab` 支持 `?subject=` 过滤；`POST /api/vocab` 持久化 `subject` 并**按学科去重**（同词不同学科允许并存）。
  - 连带修复 `_resolve_data_dir`：设 `LAS_DATA_DIR` 环境变量时原不建目录（测试环境触发 500），改为任何分支均 `mkdir(parents=True, exist_ok=True)`。

**验证**
- `app.py` `py_compile` 通过；前端内联 script `node --check` 通过（无原生 `prompt`/`confirm` 残留）。
- 后端功能测试全绿：`english=1` / `programming=2` / `all=4`；同词同科去重返回 `exists`；跨学科学科允许同词。
- 重建二进制（**14:32 版**）headless 验证 `/api/vocab` 学科过滤与去重全部 PASS。
- `dashboard/index.html` 同步至 `Release-Package/Resources/html/index.html`；`build/make_hash.py` 重算 `Security/FileHash.txt` 为 **529 个文件**（干净重建含完整 `_internal`）；清理临时验证产物。

**结论**：Windows 桌面版已完整交付并经过全面审计修复 —— 可独立运行的 `Core/KnowSubtle/KnowSubtle.exe`（原生 WebView 桌面窗口，非浏览器）+ 内置运行库 + 中文 PDF 手册 + 一键安装/卸载（免工具方案落地，NSIS 方案脚本并存），词库管理已支持学科维度与页面内模态交互。
