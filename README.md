# Datasheet2Symbol

单用户、本地运行的 PDF 引脚审核工作区。React + TypeScript / FastAPI / SQLite / 本地文件。当前交付重点是 **PDF → 分页解析 → 原文核对 → 编辑与 Part 预览 → 通用 Excel**，并提供 **AMD/Xilinx ASCII Pinout → OrCAD Capture 粘贴表** 工具。不生成 `.olb` 或 PCB 封装。

## Windows 启动

需要 Python 3.11+、Node.js 22+（含 npm）。在项目目录运行：

```powershell
./scripts/setup.ps1
./scripts/start.ps1
```

浏览器打开 http://127.0.0.1:8000 。已安装好本项目依赖时，只需第二条命令。不要在公网监听；当前没有多用户鉴权。

## PDF 视觉解析配置

默认模型为 `qwen3-vl-plus`（专门的视觉理解模型），候选识别和引脚提取使用同一模型。功能分组已停用，`Function Group` 导出列固定留空。所有 Qwen 模型均关闭思考模式（`enable_thinking: false`）以加速。读取后端进程环境变量：

| 变量 | 用途 |
|---|---|
| `DASHSCOPE_API_KEY` | 百炼密钥，仅后端读取 |
| `DASHSCOPE_BASE_URL` | 百炼控制台对应地域的 OpenAI 兼容地址，以 `/compatible-mode/v1` 结尾，不包含 `/chat/completions` |
| `DASHSCOPE_MODEL` | 可选，默认 `qwen3-vl-plus` |
| `D2S_DATA_DIR` | 可选，默认项目下 `data` |

API 地址请从自己工作空间的控制台复制，地域与密钥必须匹配。当前官方文档已有工作空间专属地址示例，所以项目不硬编码地域地址。密钥不写入前端、项目配置、SQLite 或提示词。可以使用 `scripts/start-cloud.ps1` 在隐藏输入提示中临时输入，密钥只保存在该终端进程环境中。不要把真实密钥提交到版本控制或发送到聊天。

无密钥时，上传、PDF 阅读、手动指定目标、人工补录、编辑、预览和导出可用；云端操作返回明确配置错误。左侧四种 DEMO 是明确标注的合成测试项目。

## 使用流程

1. 上传 PDF（最大 80 MB / 2000 页，拒绝加密文件）。
2. 输入相关 **PDF 文件页序号**，例如 `1-4,8`；或留空扫描全文件。扫描每批 2 页、144 DPI，超大页明确报错，绝不把全书压缩成一张图。提取时若引脚数≥20 自动单页分批以降低截断风险。
3. 点击“识别候选与相关页”，检查型号、封装、针数与事实状态。没有默认选择第一个候选。也可依据左侧当前页手动指定目标。
4. 确认目标后点击“提取已确认封装”；留空页码使用模型定位页，允许手动纠正。任务展开可查看每批状态、来源页、模型、提示词版本、用量和原始响应。失败只重试未完成批次。
5. 点击表格行定位 PDF 来源页；展开来源可切换引脚表、图、脚注等多个依据。v1 一律显示“页级依据”，没有虚构精确框。搜索使用 PDF 自带文本层，扫描件没有文本层时不会本地 OCR。
6. 编辑字段失焦自动保存。可改物理脚号、Symbol 名称、电气属性、Part、方向、结构类型；原始模型记录保持不变。可补录漏脚（以当前页为依据），筛选、批量分配 Part/确认审核。机械结构留在记录中，不进入电气引脚预览和 Pins 导出。
7. 创建 Part 后逐脚或批量分配，预览矩形符号。每条物理引脚只能有一个 Part。编辑会撤回该行审核状态。重复脚号修改被拒绝。
8. “检查完整性”显示未确认、未知类型、针数不符、未完成任务等。通用 Excel 允许导出待审数据，并明确保留审核状态，不能将其当成已验证器件库。
9. “保存项目 JSON”含 PDF、哈希、原始结果、人工覆盖、审核状态、任务与历史，支持重新打开。应用也自动保存 SQLite；备份整个 `data` 目录可保留全部项目。

## 导出

- **XLSX**：`Pins` 连续数据行；脚号等全部用文本单元格，保留 `01/A1/SH1`。`Function Group` 列固定留空；包括 Part、方向、原始名、结构类型、审核状态、PDF 页序和印刷页码。全部引脚的 `Pin Visibility` 固定为字符串 `1`，Shape 为 `Line`。`Reference` 保存验证问题、目标、原始记录和来源；`History` 保存人工操作。
- **Symbol 名称**：重复的 `Power` 类型名称原样保留；其他同名引脚按物理脚号顺序自动生成 `名称1、名称2…`。手册名称始终保存在 `Original Name`，人工修改的 Symbol 名称不会被重新解析覆盖。
- **TSV**：无表头连续数据，列顺序同 Excel，适合复制。对于公式起始字符或分隔符，明确拒绝并提示使用文本 XLSX，避免隐式改变名称。
- **JSON**：可移植项目快照，包括原始 PDF，按 SHA-256 校验。

当前是通用审核表，尚未实现 OrCAD 的 Section/枚举/多 Part 导入适配。

## 工程结构与验证

```text
backend/models.py     云端数据结构校验
backend/provider.py   百炼调用、分页图像、提示词、有限网络重试
backend/store.py      SQLite、模型版本与人工覆盖合并
backend/main.py       上传、任务状态、人工编辑、项目导入导出 API
backend/exporter.py   独立 Excel/TSV 适配层
frontend/src/         PDF.js 阅读器、审核表、SVG 预览
fixtures/             四种合成 PDF + 模拟模型响应
samples/              真实手册及人工核对基准
tests/                数据保护和端到端 API 测试
docs/                 官方接口核实与验收记录
```

```powershell
.venv/Scripts/python.exe -m pytest -q
cd frontend
npm run build
```

后端同一时刻最多运行一个模型调用；任务、批次和结果持久化，服务中断后标记失败，可手动继续。网络/429/5xx 最多 3 次重试；截断、非法 JSON、结构错误或引用未提交页码不会接纳本批结果。人工修改、预览和重新导出不会调用模型。

## 当前边界

已完成一次真实纵向闭环：TPS7A20 / DBV，上传 63 页手册，扫描前 4 页，确认封装，提取第 4 页，审核 5 脚并拆成 A/B 两个 Part，导出并重新读取 Excel。首轮提取有两处脚号-名称对调；增加封装列转录校验和同模型修正重试后，该样本 5/5 对应人工基准。失败与复测记录分别保留在 samples 下。**这只是一个五脚样本，不代表通用准确率已验证。** NC 电气类型保留 Unknown，通用 Excel 保留这一待定属性。

当前会话的百炼凭据只存在后端进程内存；重启后请重新通过环境变量或 start-cloud.ps1 配置。

## FPGA ASCII Pinout → OrCAD

欢迎页的 `FPGA ASCII Pinout → OrCAD` 工具支持任意 AMD/Xilinx 标准 ASCII Pinout 文件，不绑定某个器件型号或封装。它精确保留官方脚号与名称，自动按配置脚、Bank、控制/模拟、电源、GND 拆分为 Alphabetic Sections；每个 Section 的上限可设置为 1–100，超过上限的 GND 或电源会继续拆为新的 Section。

导出的 `Paste_To_OrCAD` 工作表列顺序与 Capture 的 New Part Creation Spreadsheet 一致：`Number, Name, Type, Pin Visibility, Shape, PinGroup, Position, Section`。`Pin Visibility` 固定为 `1`，`Shape` 固定为 `Line`，`PinGroup` 保持为空，因为 PinGroup 是交换组而不是 Bank。复制时跳过表头，从 OrCAD 的第一个 `Number` 单元格粘贴。

该工具默认只使用确定性规则。可选 AI 会复用现有百炼后端凭据，并通过 `qwen-plus` 给 `CONTROL_ANALOG` 等模糊引脚建议电气类型和方向；它绝不会修改物理脚号、官方名称、Bank 或 Section 上限。`qwen-plus` 是支持结构化输出的文本模型，适合这一小批 JSON 分类任务；不需要为 ASCII 工具再次输入密钥。若部署方需要覆盖模型，可设置 `D2S_ASCII_MODEL`。PDF 图像解析仍保留原来的视觉模型配置。

目前使用页级证据，没有经过验证的区域定位；大幅图纸裁剪工具、可调整批次尺寸、跨批次全局分组优化、Part 删除/重命名 UI、扫描件语义搜索尚未实现。人工补录的原始名称为空，编辑 Symbol 名称作为人工值保存。重新解析保留覆盖值、追加原始版本，发现字段冲突则要求重审；为了避免撤销恢复旧模型数据，解析合并时清空先前的撤销栈，历史记录仍保留。

准确性验证记录见 `docs/acceptance.md`；接口依据见 `docs/interfaces.md`。
