# 变更记录 / 交接说明（2026-09-10）

本文件记录 2026-09-10 会话中对 Datasheet2Symbol 项目的全部代码变更，供后续维护与交接参考。

---

## 一、本次会话做了什么

围绕「识别太慢、提取失败率高、模型选型」三个问题做了优化，并落地了 5 项用户需求：

1. **识别加速**（核心问题：qwen3.8-max 开着思考模式，单页提取 3 分钟）
2. **提取失败率优化**（多引脚截断、表格转录校验过严）
3. **模型选型纠正**（qwen3.8-max → qwen3-vl-plus）
4. 用户需求：引脚可见性锁定、Excel 文件名用芯片名、项目历史单独入口、Section 数字编号

---

## 二、详细改动清单（按文件）

### backend/provider.py

| 改动 | 旧值 | 新值 | 说明 |
|---|---|---|---|
| `PROMPT_VERSION` | `datasheet-v1.2-no-function-group` | `datasheet-v1.3-relaxed-row-validation` | 提示词版本号 |
| `max_tokens` | `8192` | `16384` | 解决 40+ 引脚输出截断 |
| `enable_thinking` 判断 | 仅 `qwen3-vl-`/`qwen-vl-` 前缀关闭 | 所有 `qwen` 前缀关闭 | **关键加速**：qwen3.8-max 默认开思考模式，是慢的根因 |
| `config()` 默认模型 | `qwen3.8-max` | `qwen3-vl-plus` | 换专门的视觉模型 |
| `render()` DPI | `180` | `144` | 图片体积减小约 35% |
| `render()` JPEG 质量 | `92` | `85` | 传输更快 |
| table_row 校验 | 不一致直接 `raise` 拒绝 | 不一致追加 `[warning: ...]` 到 observation 接受 | 降低无谓失败 |

### backend/models.py

| 改动 | 说明 |
|---|---|
| `Pin` 加 `visibility: Literal['Visible'] = 'Visible'` | 引脚可见性锁定，类型上只有 Visible 一个值，从数据层杜绝"不可见" |
| `Pin.part` 默认值 `'A'` → `'1'` | Section 默认数字编号 |

### backend/main.py

| 改动 | 说明 |
|---|---|
| 全局线程池 `max_workers` 1 → 3 | 支持多项目/多批次并行 |
| `worker` 拆为 `_process_batch` + `worker` | 单 job 内批次并发执行（原串行 N×T → 约 N/3×T） |
| `run()` 批次大小 | extract 且引脚 ≥20 时自动单页分批（`batch_size=1`），降低截断风险 |
| `run()` 默认提取页 | extract 默认用 `relevant_pages`（原逻辑重构） |
| `new_project` parts | `['A']` → `['1']` |
| `download()` Content-Disposition | 固定 `datasheet2symbol.{kind}` → 芯片名（`target.model`，回退 PDF 名），过滤非法文件名字符 |

### backend/exporter.py

| 改动 | 说明 |
|---|---|
| `rows()` 的 Pin Visibility 列 | 硬编码 `'Visible'` → `q.get('visibility','Visible')`，从数据模型读取 |

### frontend/src/main.tsx

| 改动 | 说明 |
|---|---|
| 侧边栏项目列表 | 删除常驻列表，改为「🕘 历史项目」按钮点击展开（新增 `showHistory` state） |
| `download()` 文件名 | `Datasheet2Symbol.{kind}` → 芯片名（`target.model`，回退 PDF 名），含非法字符过滤 |
| Parts 创建 | 原「非空才可加」改为「留空自动数字递增（1,2,3...），可手动输入字母」 |
| 解析按钮提示 | 增加「引脚≥20 单页分批 / 失败可重试」文案 |
| 导出引导横幅 | 真实项目顶部加导出 Excel 说明 |

### frontend/src/style.css

新增 `.history-list`、`.history-empty` 两个样式（历史项目展开列表用）。

### README.md

同步更新三处：默认模型、`DASHSCOPE_MODEL` 默认值、DPI/分批策略说明。

### tests/

| 文件 | 改动 |
|---|---|
| `test_failures.py` | 原「列不匹配触发重试」测试改为「放宽校验后接受并记 warning」 |
| `test_workflow.py` | 模型断言 `qwen3.8-max` → `qwen3-vl-plus`；`enable_thinking` 断言改为 `is False` |

测试结果：**17/17 全部通过**。

---

## 三、模型选型的背景说明（重要）

- **qwen3.8-max 不是"器件专用模型"**，是阿里通义的通用旗舰大模型（2.4 万亿参数 MoE），视觉只是附带能力。
- 本项目任务（Datasheet 引脚表格精确转录）更适合**专门的视觉模型**。
- 当前默认 `qwen3-vl-plus`：视觉专用、实测 TPS7A20 提取 5/5 准确率、比 max 快约 3 倍、便宜约 12 倍。
- 可通过环境变量 `DASHSCOPE_MODEL` 切换（无需改代码重启后生效）。可选备选：智谱 GLM-4.6V、百度 ERNIE-4.5-VL、Google Gemini 2.5 Pro、GPT-4o。

---

## 四、当前已知状态与限制

1. **批量上传/自动流水线**：尚未实现。当前仍是"单项目手动操作"。多项目后台并行底层已支持（全局 3 线程），但前端无批量上传、无自动触发扫描、无状态总览。用户已提出此需求，待后续实现。
2. **DEMO 合成数据**：Part 仍用字母 A/B（配合字母脚号主题），未随 Section 数字编号统一。
3. **并发结构**：当前是「全局 3 线程 + 单 job 内 3 线程」的嵌套结构，若同时跑多项目理论并发可达 9，需注意百炼限流。做批量功能时应收敛为统一全局并发池。
4. **思考模式**：所有 qwen 模型已强制 `enable_thinking=False`。若未来接入其他厂商模型（GLM/Gemini），需确认其思考模式参数是否也要关闭。

---

## 五、运行与配置速查

```powershell
# 安装
./scripts/setup.ps1

# 启动（需已配置环境变量）
./scripts/start.ps1

# 带云密钥启动（隐藏输入，仅存于进程内存）
./scripts/start-cloud.ps1
```

环境变量：`DASHSCOPE_API_KEY`（必填）、`DASHSCOPE_BASE_URL`（必填，以 `/compatible-mode/v1` 结尾）、`DASHSCOPE_MODEL`（可选，默认 `qwen3-vl-plus`）、`D2S_DATA_DIR`（可选，默认 `data`）。

测试：`.venv/Scripts/python.exe -m pytest -q`
前端构建：`cd frontend && npm run build`

---

## 六、用户新增功能（2026-09-10 晚，代码审查通过）

| 功能 | 文件 | 说明 |
|---|---|---|
| FPGA ASCII Pinout → OrCAD | `backend/orcad_ascii.py`（新）、`frontend/src/ascii.css`（新）、`AsciiOrcadTool` 组件、`/api/orcad/ascii/convert` | 解析 AMD/Xilinx 六列 Pinout，规则分类（Power/Ground/Input/Output/Bidirectional），按 Bank/配置/电源/GND 拆 Section（字母编号，每段 1–100 脚），生成 Paste_To_OrCAD / Section_Summary / Source_Audit 三表 |
| 紧凑提取 CompactExtraction | `models.py`、`provider.py`（v1.4） | 共享 evidence/table_rows，引脚用 `evidence_ids` 引用，降低 token 根治多引脚截断 |
| Symbol 名称自动去重 | `store.py` `normalize_symbol_names`、`exporter.py` | 重复非 Power 名按脚号顺序加后缀（NAME1/2…），Power 保留重名，人工编辑优先 |
| Pin Visibility 改 '1' | `models.py`、`exporter.py` | 对齐 OrCAD Capture 可见性约定 |
| AI 运行时配置 | `provider.py`、`/api/ai/config`、`suggest_ascii_roles` | 支持 DeepSeek / OpenAI-compatible；密钥仅存进程内存；AI 只对 CONTROL_ANALOG 模糊引脚建议，不改官方脚号/名称/Bank/Section |

审查结论：**19 项测试通过、前端构建通过**。

## 七、前端 API 配置表单（本次新增）

在 `AsciiOrcadTool` 的「AI 分类设置」里新增配置表单：provider 下拉（DeepSeek / OpenAI-compatible）、Base URL、模型名、API Key（password 输入）+「保存并测试」按钮。调用 `/api/ai/config`，密钥仅存后端进程内存。已验证：接口参数校验（非 https 拒绝）与表单渲染（DeepSeek 默认值）均正常。

### 已知注意点
1. ~~`/api/ai/config` 配置 DeepSeek 后 PDF 视觉解析会被拦截~~ **已解决**（见第九节 provider 解耦）。
2. 网页前端跑在浏览器、经 `127.0.0.1:8000` 与本项目后端通信，与桌面软件基本无干涉。端口 8000 被其他软件占用时会冲突（可用 `--port` 改）。

## 八、安全加固（本次新增）

`main.py` 的 `local_only` middleware 升级，两道防护：

1. **Host 校验（防 DNS rebinding）**：只接受发往 `127.0.0.1` / `localhost` / `::1` 的请求，恶意域名解析到本机也会被拒绝。
2. **GET 读接口跨源防护**：此前只有写操作校验 Origin，现在**读操作（GET）也校验**——带外部 Origin 的跨源请求一律 403，杜绝恶意网页读取本地项目数据。

实测：正常 GET=200、跨源 Origin=403、恶意 Host=403、同源 Origin=200；19 项测试通过、前端正常加载。

## 九、provider 配置解耦（本次新增）

`provider.py` 将原本全局的 `config()` 拆成两个独立配置：

- **`config()`** = PDF 视觉解析配置（DashScope `qwen3-vl-plus`，或环境变量 `AI_API_KEY` 指定的 OpenAI-compatible 视觉模型）。**不再受 runtime 配置影响**。
- **`ascii_config()`** = ASCII 分类配置（runtime 覆盖 > `DEEPSEEK_API_KEY` 环境变量 > 复用视觉配置）。

配套改动：`invoke()` 用 `config()`（视觉），`suggest_ascii_roles()` / `test_connection()` 用 `ascii_config()`；`/api/config` 返回 `ascii` 子字段；前端 `AsciiOrcadTool` 读取 `ascii` 字段显示分类供应商。

效果：配置 DeepSeek 做 ASCII 分类后，**PDF 视觉解析仍用 DashScope**，两者独立工作。实测验证通过。

## 十、批量上传（本次新增，后调整为手动扫描）

- 后端 `project_status()` 计算项目工作流状态（待扫描/扫描中/提取中/待确认目标/待提取/待审核/已完成），`/api/projects` 返回 `status` 字段。
- 前端上传框支持多选 PDF，`uploadBatch` 逐个上传并打开项目；侧边栏项目列表显示实时状态（2.5 秒轮询）。
- **重要调整**：上传后**不自动扫描**。用户打开项目后手动输入页码范围，再点「① 识别候选」触发扫描（避免空页码误扫全书）。

## 十一、PyInstaller 打包成 EXE（本次新增）

- 新增 `launcher.py` 入口：`uvicorn.run(app)` + 自动打开浏览器。
- `main.py` 前端路径、`store.py` data 目录兼容打包（`sys._MEIPASS` 临时目录；data 放 exe 同目录可写）。
- 重新打包：`./scripts/build.ps1`（先构建前端再打包）。
- 产物：`dist/Datasheet2Symbol.exe`（约 37 MB），实测启动正常、前端加载正常、data 目录正确生成。

### 分发说明
- 把 `Datasheet2Symbol.exe` 发给对方即可，双击运行自动开浏览器。
- 首次运行在 exe 同目录生成 `data/` 保存项目；备份该目录即备份全部数据。
- **端口自动避开冲突**：8000 被占用时自动尝试 8001、8002…（`launcher.py` 的 `find_free_port`）。
- **密钥界面输入**：欢迎页「配置百炼密钥」可直接填 Base URL / 模型 / API Key（存进程内存，无需环境变量）。无密钥时上传/编辑/导出/ASCII 转换仍可用。
- 注意：部分杀毒软件可能对 PyInstaller 单文件误报，需加白名单。

## 十二、打包体验优化（本次新增）

- **端口自动避开**：`launcher.py` 用 socket 探测空闲端口，8000 被占用时自动后移，避免与他人软件冲突。
- **百炼密钥界面输入**：后端新增 `_VISION_RUNTIME` + `configure_vision()` + `/api/vision/config` 接口；`config()` 优先读运行时视觉配置。前端欢迎页新增 `VisionConfig` 组件（Base URL / 模型 / API Key + 保存并测试），密钥仅存进程内存。
- 新增 `models.VisionConfigRequest`；`test_connection` 重构出通用 `_test_connection(cfg)` 供视觉/ASCII 共用。
- 实测：密钥接口参数校验（非 https 拒绝）正常、前端配置组件渲染正常（默认值正确）。

## 十三、智能摆放引脚位置（本次新增）

按**功能分组聚类**自动摆放引脚位置，规则（用户确认）：

- **尽量左右**：输入/时钟/控制/电源/地 → 左，输出（Output/OC/OE/3-State）→ 右。
- **双向平衡**：Bidirectional 脚灵活分配，放到数量少的一边，让符号大致对称。
- **底部兜底**：只放 NC/DNC/exposed_pad/shield 等特殊脚，聚在一起。
- **顶部不放**：Top 完全不用。

实现：
- `store.py` 重写 `suggest_position` → `_side_of`（分类）+ `normalize_positions`（全局分配，含双向平衡），只改未手动编辑 position 的引脚；在 merge / lifespan / import 时调用。
- 前端 `SymbolPreview` 加 `groupKey` 排序，边内按「地→电源→时钟→控制→输出→双向→输入」聚类相邻。

验证：demo/power（EP→底部、NC→底部、其余左）、demo/digital（双向 PA0/PA1 平衡到右、DNC 底部）；19 项测试通过。

## 十四、Power 重名修复 + Token 加密存储 + 多模型 + 黑框框 + 进度条（本次新增）

**1. Power 重名 bug 修复**：地脚（PGND 等）因模型误标 `Passive` 被错误去重（PGND1~PGND8）。`store.py` 新增 `_is_power_name()`，`normalize_symbol_names` 判断非 Power 时同时排除电源/地名称（GND/VSS/VCC/VDD/VIN 等）。验证：NC 仍去重、VIN/PGND 正确保留重名。

**2. Token 加密存储**：新增 `backend/configstore.py`，用 Fernet 对称加密（密钥从机器硬件标识派生，机器绑定），存 `data/models.json.enc`。`config()` 启动时自动加载第一个模型，**重启后无需重新输入密钥**。

**3. 多模型配置**：`provider` 加 `list_models/upsert_model/delete_model/select_model`；API `GET/POST /api/models`、`DELETE /api/models/{name}`、`POST /api/models/select`；前端「模型配置」重写为多模型列表 + 添加表单 + 使用/删除按钮。密钥脱敏（`has_key` 标记，api_key 永不出后端）。

**4. 黑框框优化**：PyInstaller `--noconsole` 打包，双击运行无命令行窗口。

**5. 解析进度条**：前端解析任务加进度条（完成批次/总批次）。

验证：加密文件明文不含密钥、重启自动加载、多模型增删改查切换、前端「使用中」状态；19 项测试通过。**并发解析（多模型同时解析对比速度）未实现，作为后续可选项。**

## 十五、并发解析对比（本次新增）

- `provider.invoke` 加 `cfg_override` 可选参数（指定模型配置解析）、`find_model()` 按名称查模型。
- `main.py` 加 `POST /api/benchmark`：`{project_id, pages, stage, models}`，用 `ThreadPoolExecutor` 并发跑多个模型，返回各模型 `duration / count / tokens / error`（按耗时排序）。
- 前端欢迎页新增 `Benchmark` 组件：项目下拉 + 阶段（扫描/提取）+ 页码 + 模型多选 + 「开始对比」，结果列表展示排名、耗时、结果数、token。

验证：接口参数校验正常、前端对比 UI 渲染正常（项目下拉、模型勾选、开始按钮）；19 项测试通过。

## 十六、10 器件标准库对比 + 百炼紧凑格式修复（本次新增）

**1. 10 器件标准库对比**：从 TI 官网下载 10 个标准器件 datasheet（lm1117/lm2596/lm317/lm358/ne555/sn74hc00/sn74hc245/sn74hc595/tl431/tps5430），建立 ground truth 基准（`data/bench_truth.json`），双模型提取对比准确率和速度。结果见 `data/bench_results.json`。

关键发现：**deepseek 全面更快**（15-48s vs 百炼 137-165s），数字逻辑器件（lm317/sn74hc00/sn74hc245/tps5430）准确率 100%；**百炼（qwen3-vl-plus）在紧凑格式上严重不兼容**，10 个器件里 7 个因「evidence_id 引用错误」失败。

**2. 百炼紧凑格式兼容修复**：`provider.invoke` 根据模型选择提取格式——`qwen*` 系列用非紧凑 `Extraction`（每个引脚内嵌完整 evidence），其他模型（deepseek）用 `CompactExtraction`（共享 evidence）。非紧凑格式保留 table_row 放宽校验（mismatch 加 warning 不拒绝）。

验证：百炼提取 lm317 从「失败」变为「11.98s 成功提取 3 引脚」，19 项测试通过。

**3. 环境坑**：本机有 `HTTP_PROXY` 代理环境变量，httpx 自动走代理导致本地请求 404，需 `trust_env=False` 直连。

## 十七、默认模型切换 + 退出按钮（本次新增）

**1. 默认 deepseek + 选择持久化**：`select_model` 把选中的模型移到加密列表首位，`config()` 启动时自动加载第一个模型，实现「选一次、以后默认」。已把 deepseek 设为默认（`deepseek-v4-flash-vision-exp`）。

**2. 退出应用按钮**：解决「关闭网页后后台进程残留、无法主动关闭」的问题。后端新增 `POST /api/shutdown`（后台线程延迟 0.4s 后 `os._exit(0)` 停止服务并退出进程）；前端 header 新增「退出」按钮（confirm 确认后调用）。

验证：`config()` 重启后自动加载 deepseek；19 项测试通过；EXE 已重新打包。

## 十八、pywebview 桌面化 + 界面精简 + 图标（本次新增）

**1. pywebview 桌面化**：新增 `launcher_webview.py`（系统 WebView2 原生窗口）。修复了之前 pywebview 的「交互锁死」——根因是后端 uvicorn 占了主线程，现改为 **daemon 子线程跑后端、`webview.start()` 独占主线程**，关闭窗口即干净退出。

**2. 界面精简**：侧边栏去掉 4 个 demo 按钮和「无密钥体验」区块；品牌图标换成 SVG 芯片图标。

**3. 解析耗时**：`_process_batch` 记录每批 `duration`，前端任务区显示任务总耗时 + 每批耗时。

**4. 应用图标**：生成 `assets/icon.ico`（16~256 多尺寸）+ `frontend/public/icon.svg`（favicon）+ 窗口图标 + EXE 图标。注意 pywebview 图标要传给 `webview.start(icon=...)`，不是 `create_window`。

**5. 打包调整**：`build.ps1` 改为打包 `launcher_webview.py`，加 `--icon` + `--collect-all webview`；`requirements.txt` 增加 `pywebview/pythonnet/clr-loader`。EXE 约 51MB。

验证：19 项测试通过；GUI 需用户本机确认（沙箱无桌面会话，WebView2 无法启动）。

## 十九、模型列表自动获取 + Unknown 规范化（本次新增）

**1. 模型列表自动获取**：输入 Base URL + API Key 后，点「获取模型列表」自动拉取该服务商的可用模型（OpenAI-compatible `GET /models`）。`provider.fetch_model_list()` + `POST /api/models/fetch`；前端模型 ID 输入框在拉到列表后变下拉选择。实测：deepseek 返回 2 个、百炼返回 249 个（含聚合的 GLM/kimi/deepseek 等）。

**2. Unknown → Passive 规范化**：模型提取的 `electrical_type` 为 "Unknown"（不分大小写）统一改为 `Passive`。两层：`provider.invoke` 解析后规范化新数据；`store.normalize_electrical_types()` 在 lifespan 启动时迁移历史数据（只改 raw，不覆盖用户 edits）。验证：迁移后 288 个引脚 Unknown 归零。

验证：19 项测试通过。
