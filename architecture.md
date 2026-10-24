# 架构

## 一句话

一个**单文件网页应用** + **四份可编辑数据** + **两段提示词**，把非遗知识、教案、材料判断都放在本地，让模型只负责「组织语言」而不是「编内容」。

```
┌─────────────────────────── web/index.html ───────────────────────────┐
│  UI 层        对话区 / 稿纸区 / 主题与班次选择 / 导出                │
│  ─────────────────────────────────────────────────────────────────   │
│  编排层       system 组装 · 工具调用解析 · 结果落盘(localStorage)     │
│  ─────────────────────────────────────────────────────────────────   │
│  工具层       read_resource / search_kb / read_full / gen_* / audit   │
│  ─────────────────────────────────────────────────────────────────   │
│  数据层       themes.json · kb-card.json · plans.json · materials     │
└──────────────────────────────────────────────────────────────────────┘
                    │ 可选
                    ▼
        DeepSeek / 任意 OpenAI 兼容接口（浏览器直连，Key 存本地）
```

## 为什么是单文件

目标用户是幼儿园老师，不是开发者。单文件 = 双击就能用、能拷到 U 盘、能在没有内网的教室里跑。

代价是文件较大（本仓库 `web/index.html` 约 500 KB），所以把**可编辑的部分**拆到了 `data/` 与 `prompts/`，方便二次开发；生产构建时再合并回单文件。

## 请求链路

1. `sysPrompt()` 组装 system：
   - `SOUL`（人设）
   - `TRAIN`（年龄特点 / 速查表 / 输出模板 / 工具规矩 / 自检 / 红线）
   - 当前槽位（主题 + 班次）
   - **知识卡摘要**（当前主题的来历、工艺、材料、安全、分龄）
2. 用户消息 + 历史 → `POST /chat/completions`
3. 模型如需取料，在回答末尾输出动作块：

```json
<action>{"tool":"read_resource","params":{"theme":"daur","field":"safety"}}</action>
```

4. 前端执行工具，把结果作为下一条消息回灌，让模型继续组织语言。

## 工具清单

| 工具 | 作用 | 关键参数 |
|---|---|---|
| `read_resource` | 取教案原文或知识卡 | `theme`、`age`、`field` |
| `search_kb` | 全库关键词检索 | `q` |
| `read_full` | 读���主题课程包全文，可带关键词只取相关段 | `theme`、`q` |
| `gen_lesson` | 生成完整教案 | `theme`、`age`、`brief` |
| `gen_decor` | 生成环创方案 | `theme`、`age`、`brief` |
| `gen_pair` | 生成家长任务卡 | `theme`、`age` |
| `audit_lesson` | 教案六环节体检 | `text` |
| `export_doc` | 导出 word / md / txt | `fmt` |

`read_resource` 的 `field` 分两类：

- **教案字段**：`lesson` `story` `riddle` `decor` `art` `gameIn` `gameOut` `qa` `note` `task` `read`
- **知识卡字段**：`history` `steps` `motifs` `materials` `safety` `ageFit` `mistakes` `phrases` `toParent` `extend` `faq` `kb`

中英文别名都认（例如 `家长` = `toParent`、`安全` = `safety`）。

## 降级策略

| 场景 | 行为 |
|---|---|
| 没填 Key | 只用本地库：查资料、拼教案、导出，全部可用 |
| 模型超时 / 失败 | 自动回落本地生成，界面提示「已按本库资料生成」 |
| 模型说了本库没有的内容 | `train.md` 规定：不许编年代与传承人，直接说「这个我得查一查」 |
| 材料与工艺冲突 | 前端 `judge()` 先拦，红色材料不进入生成请求 |

## 一个设计取舍

**知识卡既进 system，也可单独取。** 只进 system 会让长对话上下文膨胀；只靠按需取，模型又容易不知道有哪些字段可用。所以：system 里放「摘要 + 字段清单」，具体内容按需 `read_resource` 取。
