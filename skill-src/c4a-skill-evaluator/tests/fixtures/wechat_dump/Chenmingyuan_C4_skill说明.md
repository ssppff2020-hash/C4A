# Chenmingyuan C4 技能说明：literature-format-assistant（参考文献格式校对助手）

> 挑战：C4 技能分享与传播 ｜ 作者：Chenmingyuan ｜ 版本：v1 ｜ 日期：2026-10-03
> ⚠️ 本文件是 c4a-skill-evaluator 的**测试夹具**，内容为演示用虚构提交。

---

## 一、这个技能解决什么问题

写论文最后一步总要手动核对参考文献格式：作者名大小写、期刊名缩写、卷号期号页码标点，
格式错了期刊直接退稿。人工核一条要 1–2 分钟，一篇 40 条文献就是 1 个多小时，而且容易漏。

本技能把"GB/T 7714 与 APA 两套格式规则"封装成可复用的校验流程：**输入一份 BibTeX 或
参考文献列表，输出逐条格式诊断与可一键替换的修正稿。**

## 二、使用场景

| 场景 | 适用 |
|------|------|
| 学位论文定稿前 | 参考文献格式自检 |
| 期刊投稿前 | 按目标期刊格式批量校对 |
| 课程作业 | 学生自查引用格式 |

## 三、输入与输出

**输入：**
- 必填：一个 `.bib` 文件路径，或一段纯文本参考文献列表
- 可选：目标格式（`gbt7714` 或 `apa`，默认 `gbt7714`）

**输出：**
- `report.md`：逐条诊断（条目号 / 问题类型 / 原文 / 建议改法）
- `fixed.bib`：按建议自动修正后的文件
- 终端退出码：0 = 无错误，1 = 存在 ERROR 级问题

**一句话：输入"BibTeX 文件 + 目标格式"，输出"逐条格式诊断报告 + 修正后的 bib 文件"。**

## 四、安装与环境要求

```bash
pip install bibtexparser==1.4.1
```

- 环境要求：Python 3.9+，依赖 `bibtexparser`（纯 Python，无编译依赖）
- 平台：Windows / macOS / Linux 均可运行，已在三者验证
- 不需要联网，不需要 API Key
- 不依赖任何本机绝对路径，所有输入通过命令行参数传入

## 五、使用步骤

1. 安装依赖：`pip install bibtexparser`
2. 运行：
   ```bash
   python literature-format-assistant.py --input refs.bib --style gbt7714 --out ./out
   ```
3. 查看 `./out/report.md`，按 ERROR → WARN 顺序修
4. 用 `./out/fixed.bib` 替换原文件，重跑一次确认退出码为 0

## 六、真实案例

**输入**：一份含 3 条文献的 `refs.bib`，其中第 2 条缺卷号、第 3 条作者名写成 `zhang, san`。

**预期输出**：

```
[1] OK      Zhang, S. (2020). Attention is all you need. Nature, 12(3), 45-56.
[2] ERROR   缺卷号(volume) —— 期刊论文 GB/T 7714 必填 volume
[3] WARN    作者名应为首字母大写 —— 建议 'Zhang, S.'
---
合计 3 条：0 ERROR / 1 ERROR / 1 WARN  → 退出码 1
```

**成功判据**：退出码 0 且 `report.md` 中 ERROR 计数为 0；出现 ERROR 时退出码必须为 1。

**复现命令**：

```bash
python literature-format-assistant.py --input tests/refs_sample.bib --style gbt7714 --out /tmp/o
echo $?   # 期望 1
```

## 七、已知边界

- 只支持 BibTeX 与逐行文本，不支持 EndNote `.enl` 二进制格式
- 超过 5000 条时速度下降，建议分批
