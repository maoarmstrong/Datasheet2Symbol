# 接口核实记录

核实日期：2026-09-09 / 2026-09-10。以下是文档核实，不等同于本账号在线实测。

## 百炼

当前默认模型的官方页面：[qwen3.8-max](https://help.aliyun.com/zh/model-studio/qwen3-8-max)。官方列出的输入模态为 Image / Text / Video，支持结构化输出；没有列出保留视觉内容的 PDF 输入。因此第一版从用户 PDF 本地渲染为 JPEG 再提交；不使用纯文本文件提取路径替代视觉内容，不引入本地 OCR。

官方：[图像与视频理解](https://help.aliyun.com/en/model-studio/vision)。支持 OpenAI 兼容请求中的 `image_url` + `data:image/jpeg;base64,...`。文档的本地 Base64 输入要求原文件小于 7 MB。Qwen3-VL 公网图片可达 20 MB，但项目不上传到对象存储；采用更保守的 Base64 路径。Base64 图片数量上限 250 且总 Token 仍受限，应用只提交 2 页/批。180 DPI、JPEG 质量 92，原始文件小于 7,000,000 bytes、渲染像素不超过 16,000,000；这两个数是本应用保护阈值，并非宣称它们是精确模型上限。超限报错而不偷偷降清晰度。未传未经验证的 `max_pixels` 等优化参数。

官方：[结构化输出](https://help.aliyun.com/en/model-studio/qwen-structured-output)。Qwen3.8-Max 支持 JSON Object 和 JSON Schema。当前沿用 JSON Object，提示词含 JSON，随后用 Pydantic `extra=forbid` 校验。官方 Qwen3.8-Max 非流式 JSON Object 示例未设置 `enable_thinking`，应用对该模型也不发送此参数；用户切回 Qwen3-VL 时仍显式使用非思考模式。未使用 JSON Schema constrained decoding，不能把本地校验说成服务端严格生成。

2026-09-10 用户要求将默认模型切换到 `qwen3.8-max`，并停用功能分组。模型提示要求 `group` 为空；后端在接纳结果前将该兼容字段归一为空，Excel 的 `Function Group` 固定导出空单元格，审核界面不显示或编辑该字段。

在线验证：2026-09-10 已通过用户指定的 https://dashscope.aliyuncs.com/compatible-mode/v1 调用 qwen3-vl-plus，Base64 JPEG / enable_thinking=false / JSON Object 路径工作正常；后端成功校验输出并记录用量。五脚样本首轮有两处映射错误，经封装列校验反馈后更正，详见 acceptance.md。默认别名实际快照、广泛密集表格准确度、不同尺寸用量/耗时、真实限流与错误码仍待进一步验证；不报告未经实测的通用准确率或成本。

## Excel / OrCAD

按用户最新要求，当前只实现通用审核 Excel，OrCAD 延后。

已查看 Cadence 社区：[Part from Spreadsheet Copy/Paste](https://community.cadence.com/cadence_technology_forums/pcb-design/f/allegro-x-capture-cis/50925/part-from-spreadsheet-copy-paste)。讨论中说明 Capture 需要预先设置 Part Number / Sections / Numbering Type，文本脚号及枚举粘贴有版本相关行为。这只是适配风险记录，不能据此证明本应用多 Part 导入可用。
