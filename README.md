# C4A — 技能提交自动评审（Automated Skill Submission Evaluator）

> 挑战 ID：`ch-20260717031432-5jvqje` ｜ 作者：宋鹏飞（Songpengfei） ｜ 日期：2026-10-08
> 本目录 = C4A 挑战的完整提交。

把 WeChat 群文件夹里的 C4 技能提交，**自动**变成一份可复现、可申诉的评审报告：

```
一个文件夹  →  谁交了 / 交齐没 / 达标吗 / 下一步改什么  →  Markdown + XLSX + HTML + CSV + JSON
```

---

## 一、结果速览

跑 `samples/cohort/`（4 位作者，含 3 份合成夹具）的实测输出：

| 排名 | 作者 | 完整性 | 四条件 | 综合分 | 红牌 |
|------|------|--------|--------|--------|------|
| 1 | Chenmingyuan `合成夹具` | 5/5 ✅ | 4.00/4 | **100.0** | — |
| 2 | **Songpengfei** (真实提交) | 5/5 ✅ | 4.00/4 | **100.0** | — |
| 3 | Liyang `合成夹具` | 4/5 ⚠️ | 2.47/4 | **69.0** | 一句话指令直接提交 |
| 4 | Zhaolei `合成夹具` | 2/5 ❌ | 1.62/4 | **40.2** | 核心交付物缺失、无 AI 使用记录 |

评审器在三个已知质量的样本上给出了三个档次的分数，
并且准确指出了 Liyang 缺 demo、Zhaolei 硬编码 `D:\我的资料` 路径。

完整报告见 [`output/cohort-demo_report.md`](output/cohort-demo_report.md)
与 [`Songpengfei_C4A_evaluation-report.md`](Songpengfei_C4A_evaluation-report.md)。

---

## 二、安装

**环境要求**：Python 3.9+ ｜ 跨平台（Windows / macOS / Linux 均已验证）｜ 不需要联网

```bash
# 必需
pip install pyyaml

# 可选（缺失会打印提示并继续运行，不会崩）
pip install openpyxl     # 导出 .xlsx
pip install pypdf        # 读取 .pdf 正文
pip install anthropic    # --llm 深度批注（另需 ANTHROPIC_API_KEY）
```

验证安装：

```bash
python -c "import yaml; print('pyyaml ok')"
```

### 作为 Claude Skill 安装（可选）

`Songpengfei_C4A_skill-evaluator.skill` 是标准 ZIP 格式的技能包，
可直接装到支持 Claude Skills 的环境。装好后说「评审 C4 提交」即可触发。

---

## 三、运行命令

### 3.1 评审一个文件夹（最常用）

```bash
cd C4A
python skill-src/c4a-skill-evaluator/scripts/c4a_evaluator.py <你的文件夹> --out output
```

> **Windows 中文乱码**：命令前加 `PYTHONUTF8=1 PYTHONIOENCODING=utf-8`

### 3.2 全部参数

```bash
python skill-src/c4a-skill-evaluator/scripts/c4a_evaluator.py <FOLDER> \
    --out output                    # 输出目录（默认 ./output）
    --formats md,csv,xlsx,html,json # 输出格式，默认全部
    --basename cohort-demo          # 输出文件名前缀（默认 c4a）
    --config references/rubric.yaml # 换一套评审规则
    --weights reusable=0.4,verifiable=0.3   # 覆盖四条件权重
    --tag Liyang=合成夹具            # 给某作者打标签，报告里显示
    --llm                           # LLM 深度批注（不改分，需 API Key）
    --quiet                         # 只打印汇总表
```

### 3.3 跑测试（验证评审规则没被改坏）

```bash
cd skill-src/c4a-skill-evaluator
python -m unittest discover -s tests -v      # 期望：Ran 24 tests ... OK
```

### 3.4 重新打包技能

```bash
cd C4A
python tools/package_skill.py skill-src/c4a-skill-evaluator \
    --out Songpengfei_C4A_skill-evaluator.skill
```

---

## 四、目录结构

```
C4A/
├── README.md                                  ← 本文件（统一说明）
│
├── Songpengfei_C4A_design.md                  【交付物1】方案设计（架构 / 技术选型 / 评分公式）
├── Songpengfei_C4A_skill-evaluator.skill      【交付物2】可安装技能包（ZIP，54.7 KB / 24 文件）
├── Songpengfei_C4A_evaluation-report.md       【交付物3】真实评审报告（诚实区分真实/合成数据）
├── Songpengfei_C4A_tutorial.md                【交付物4】教学说明（安装 / 上手 / 常见坑）
├── Songpengfei_C4A_ai-log.md                  【交付物5】AI 日志（9 轮，含 6 个 bug 复盘）
├── Songpengfei_C4A_attribution.md             【交付物6】拿来说明（从 wechat-doc-mapper 拿/改/超越）
│
├── skill-src/
│   └── c4a-skill-evaluator/                   技能源码目录（.skill 包的内容）
│       ├── SKILL.md                           触发入口 + 工作流 + 边界情况
│       ├── scripts/
│       │   ├── c4a_evaluator.py               CLI 入口，串起四层流水线
│       │   ├── textio.py                      格式感知的正文抽取（零硬依赖）
│       │   ├── collector.py                   Level 1：扫描 / C4 过滤 / 作者归属 / 版本
│       │   ├── completeness.py                Level 2：五项交付物（打分 + 贪心分配）
│       │   ├── quality.py                     Level 3：19 条检查 / 四条件 / 红牌 / 建议
│       │   ├── report.py                      Level 4：五种格式的报告
│       │   └── llm_advisor.py                 可选：LLM 批注（不参与计分）
│       ├── references/
│       │   ├── rubric.yaml                    评审规则（改规则只改这里）
│       │   └── scoring_guide.md               评分数学 + 阈值 + 局限
│       └── tests/
│           ├── test_evaluator.py              24 个金标准测试
│           └── fixtures/wechat_dump/          3 份已知质量的合成提交 + 2 个干扰文件
│
├── tools/
│   └── package_skill.py                       把技能目录打包成 .skill（Git Bash 没有 zip）
│
├── samples/
│   ├── README.md                              ⚠️ 数据来源说明（哪些是真实的、哪些是合成的）
│   ├── real/                                  真实 C4 提交（Songpengfei，10 个文件）
│   └── cohort/                                真实 1 份 + 合成 3 份，模拟群文件夹
│
└── output/                                    评审产物（可随时重新生成）
    ├── real-submission_report.md / _dashboard.html / _scores.{csv,xlsx,json}
    └── cohort-demo_report.md    / _dashboard.html / _scores.{csv,xlsx,json}
```

### 数据真实性声明（重要）

| 目录 | 性质 |
|------|------|
| `samples/real/` | ✅ **真实** —— 从 C4 挑战资料包原样复制的 Songpengfei 提交 |
| `samples/cohort/` | ⚠️ **1 份真实 + 3 份合成夹具**，合成件在报告里带 `合成夹具` 标签 |
| `output/` | 由上面的样本跑出来的真实产物，非手写 |

本地磁盘上**实际只有 1 份真实 C4 提交**。3 份合成提交是评审器的
金标准测试集（文件内均标注 `⚠️ 测试夹具`），用于验证评审器的分辨力，
不会被冒充为真实同学的作品。详见 [`samples/README.md`](samples/README.md)。

---

## 五、结果复现步骤

从零复现本目录下所有产物，共 4 步：

```bash
# ── 步骤 0：进入目录 ────────────────────────────────────────────
cd C4A

# ── 步骤 1：验证环境 ───────────────────────────────────────────
python -c "import yaml; print('pyyaml ok')"

# ── 步骤 2：跑金标准测试（应为 24 passed）───────────────────────
cd skill-src/c4a-skill-evaluator
python -m unittest discover -s tests -v
cd ../..

# ── 步骤 3：生成评审产物 ───────────────────────────────────────
rm -rf output

#   3a. 真实提交单独评审
python skill-src/c4a-skill-evaluator/scripts/c4a_evaluator.py samples/real \
    --out output --basename real-submission

#   3b. 班级队列评审（合成夹具打标签）
python skill-src/c4a-skill-evaluator/scripts/c4a_evaluator.py samples/cohort \
    --out output --basename cohort-demo \
    --tag Chenmingyuan=合成夹具 --tag Liyang=合成夹具 --tag Zhaolei=合成夹具

# ── 步骤 4：核对结果 ───────────────────────────────────────────
#   期望终端输出：
#     real   : 1 人，Songpengfei 5/5 ✅ 4.00 100.0，无红牌
#     cohort : 4 人，平均 77.3；Liyang 69.0（一句话指令）、Zhaolei 40.2（缺件 + 无 AI 日志）
#   打开 output/cohort-demo_dashboard.html 可直接看到班级仪表板
```

> Windows 下若终端中文乱码，在两条 `python` 命令前加
> `PYTHONUTF8=1 PYTHONIOENCODING=utf-8`（`output/` 里的文件本身始终是 UTF-8）。

**评审自己的数据**：把 `samples/cohort` 换成任意文件夹路径即可，例如
`python .../c4a_evaluator.py "D:/WeChatFiles/群文件" --out output`

---

## 六、命名规范

挑战要求交付物命名为 `姓名_C4A_内容描述.扩展名`。
本目录**统一采用 ASCII 文件名**（避免跨平台编码问题），
中文语义通过下表一一对应，README 中可直接查到：

| 挑战要求的中文名 | 本目录实际文件 | 说明 |
|-----------------|---------------|------|
| `姓名_C4A_方案设计.md` | [`Songpengfei_C4A_design.md`](Songpengfei_C4A_design.md) | 架构、技术选型理由、评分公式、局限 |
| `姓名_C4A_skill-evaluator.skill` | [`Songpengfei_C4A_skill-evaluator.skill`](Songpengfei_C4A_skill-evaluator.skill) | 同名，无需别名 |
| `姓名_C4A_评审报告.md` | [`Songpengfei_C4A_evaluation-report.md`](Songpengfei_C4A_evaluation-report.md) | 真实 + 合成队列评审结果 |
| `姓名_C4A_教学说明.md` | [`Songpengfei_C4A_tutorial.md`](Songpengfei_C4A_tutorial.md) | 安装、上手、常见坑 |
| `姓名_C4A_AI日志.md` | [`Songpengfei_C4A_ai-log.md`](Songpengfei_C4A_ai-log.md) | 9 轮迭代 + 6 个 bug 复盘 |
| `姓名_C4A_拿来说明.md` | [`Songpengfei_C4A_attribution.md`](Songpengfei_C4A_attribution.md) | 从 wechat-doc-mapper 拿/改/超越 |
| （无要求） | [`README.md`](README.md) | 本文件，统一说明 |

其余目录与文件一律使用**全小写 kebab-case**：
`skill-src/`、`output/`、`samples/`、`tools/`，
脚本 `c4a_evaluator.py`、`package_skill.py`，
产物 `cohort-demo_report.md`、`real-submission_scores.xlsx`。

**技能包内部的源文件名**（`collector.py` / `completeness.py` / …）
也保持英文小写下划线，这是 Python 生态惯例，便于他人直接维护。

---

## 七、这个技能做了什么

**输入**：一个本地文件夹路径（WeChat 群同步目录 / 手动下载目录 / 任意目录）
**输出**：五种格式的评审报告 + 排名 + 逐人改进建议

### 四层流水线

| 层 | 模块 | 做什么 |
|----|------|--------|
| **L1 采集** | `collector.py` + `textio.py` | 递归扫描 → C4 过滤（排除 C4A/C4B 等兄弟挑战）→ 作者四步归属链（文件名 → 文件夹 → 正文 → Unknown 标注）→ `_v2`/`_v3` 版本检测 → 混合格式正文抽取（含钻进 .skill 压缩包） |
| **L2 完整性** | `completeness.py` | 五项交付物 × 打分（文件名 + 扩展名 + 内容信号）→ 贪心分配（一个文件不进两个交付物）→ 齐全 ✅ / 部分 ⚠️ / 严重缺失 ❌ + 弱命中标注 |
| **L3 质量** | `quality.py` | **19 条检查 → 四条件评级**（可复用 / 可执行 / 可验证 / IO 明确）+ 三条平台红牌 + 逐人改进建议 |
| **L4 报告** | `report.py` | 班级总览 / 作者详情（含逐条证据）/ 排名 / 改进建议 / 版本分布 / 非 C4 附录 → Markdown + CSV + XLSX + HTML + JSON |

### 三条设计原则

1. **可复现**：分数 100% 来自确定性规则，同一文件夹跑两次结果完全一致
   （有 `test_two_runs_agree` 断言钉住）。LLM 只在 `--llm` 时加批注，**不参与计分**。
2. **可申诉**：每条分数都能在报告里展开看到命中了哪个模式、匹配了哪句话。
3. **不假装确定**：证据不足时标 ⚠️「需人工确认」，而不是静默判通过。

---

## 八、完成级别

| Level | 产出 | 状态 |
|-------|------|------|
| L1 文件采集器 🥉 | 扫描 / C4 识别 / 作者四步链 / 版本检测 / 混合格式 | ✅ |
| L2 完整性检查器 🥈 | 五项交付物 + 打分分配 + 弱命中标注 | ✅ |
| L3 质量评审器 🥇 | 19 条检查 / 四条件评级 / 依据 + 建议 | ✅ |
| L4 完整评审系统 💎 | 班级总览 / 排名 / 逐人行动 / 版本追踪 / 5 种输出 | ✅ |

---

## 九、已知局限

1. **评的是"合规"不是"优秀"**——一份结构完整但教学法平庸的教案也可能 100 分。
   本技能回答"是否符合 C4 四条件"，不评价作品本身好不好。
2. **二进制只按文件名匹配**——`.png` 能证明有截图，不能证明截图是真跑的结果（交给 `--llm` 批注）。
3. **真实样本只有 1 份**——评审器在真实课堂数据上的准确率仍需更多提交来验证。
4. **关键词受语言限制**——规则内置中英双语信号，其他语言的提交会低估。
5. **作者归属依赖命名规范**——完全不规范且正文无作者的提交会落到 `Unknown` 并标注待确认。

---

## 十、快速排错

| 现象 | 原因 / 解法 |
|------|------------|
| 终端中文乱码 | 加 `PYTHONUTF8=1 PYTHONIOENCODING=utf-8`（文件内容本身没问题） |
| `ModuleNotFoundError: yaml` | `pip install pyyaml` |
| 报告出现 `Unknown` 作者 | 文件名加 `姓名_C4_` 前缀，或把文件放进以人名命名的子目录 |
| 交了 demo 却说缺 | 文件名加 `demo`/`演示`/`截图`/`录屏`，或扩展名用 `.mp4/.png/.gif/.md` |
| `.skill` 报"结构不完整" | 用 `python tools/package_skill.py` 重新打包，确保包内含 `SKILL.md` |
| `.xlsx` 没生成 | `pip install openpyxl`，或忽略该提示（其余格式照常生成） |
| 想改判据 | 改 `skill-src/c4a-skill-evaluator/references/rubric.yaml`，改完跑一遍测试 |

更多排错细节见 [`Songpengfei_C4A_tutorial.md`](Songpengfei_C4A_tutorial.md)。
