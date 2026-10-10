# C4A 教学说明 —— 怎么用这个评审器

> 作者：宋鹏飞（Songpengfei） ｜ 对应挑战文件：`姓名_C4A_教学说明.md`
> 目标读者：想用这个技能评审 C4 提交的老师 / 助教 / 同学本人

---

## 一、三分钟上手

### 步骤 1：确认环境

```bash
python --version          # 需要 3.9+
python -c "import yaml; print('ok')"
```

`yaml` 报 `ModuleNotFoundError` 就装一下：

```bash
pip install pyyaml
```

> **环境要求**：Python 3.9+，必需 `PyYAML`。
> 可选：`openpyxl`（导出 .xlsx）、`pypdf`（读 PDF 正文）、`anthropic`（`--llm` 批注）。
> 三者缺失都会**打印提示并继续运行**，不会崩。不需要联网。

### 步骤 2：把 C4 提交放进一个文件夹

技能只要求**一个本地文件夹路径**。文件怎么来的不重要——
手动从群文件下载、WeChat 桌面端同步目录、别人发给你的压缩包解压后的目录都行。

```
我的C4提交/
├── Songpengfei_C4_skill说明.md
├── Songpengfei_C4_lesson-design-assistant.skill
├── Songpengfei_C4_demo.png
├── Songpengfei_C4_教学说明.md
└── Songpengfei_C4_AI日志.md
```

命名按 `姓名拼音_C4_内容描述.扩展名` 最省事，但**不规范也能用**：
技能会依次退回「上级文件夹名 → 正文里的『作者：』→ 标注为 Unknown 待人工确认」。

### 步骤 3：跑

```bash
cd C4A
python skill-src/c4a-skill-evaluator/scripts/c4a_evaluator.py <你的文件夹> --out output
```

看到这样一张表就成功了：

```
------------------------------------------------------------------------------
C4A 自动评审 · samples\cohort
提交 4 人 ｜ 完整 2 ｜ 部分 1 ｜ 严重缺失 1 ｜ 平均综合分 77.3
------------------------------------------------------------------------------
作者                 完整性      四条件     综合分    红牌
Chenmingyuan       5/5 ✅    4.00    100.0  —
Songpengfei        5/5 ✅    4.00    100.0  —
Liyang             4/5 ⚠️   2.47    69.0   一句话指令直接提交
Zhaolei            2/5 ❌    1.62    40.2   核心交付物缺失、无 AI 使用记录
```

### 步骤 4：看报告

`output/` 下会生成五种格式，按需取用：

| 文件 | 什么时候看它 |
|------|-------------|
| `*_report.md` | **发群里的主报告**。含班级总览、逐人详情、19 条检查的逐条证据（折叠块） |
| `*_dashboard.html` | 想一眼看完排名和分布。**单文件、无 CDN、离线双击就开** |
| `*_scores.xlsx` | 要排序、筛选、自己算加权。两张表：Scores 汇总 + Detail 逐条检查 |
| `*_scores.csv` | 要喂给别的脚本 |
| `*_scores.json` | 要接平台 API 或做二次开发 |

---

## 二、看懂输出的三个要点

### 要点 1：⚠️ 不等于"有问题"，等于"我看不准"

完整性表里出现 ⚠️ 表示**弱命中**：文件确实像这个交付物，但证据不够强
（比如只靠扩展名+内容信号匹配上，文件名没提）。

**这是设计选择，不是 bug。** 我宁可标出来让人看一眼，
也不愿意静默判通过、让一个缺件的人以为自己齐了。

### 要点 2：分数点得开

Markdown 报告里每条条件的证据都折叠在 `<details>` 里，展开能看到：

```
- ✅ 无硬编码绝对路径 — 未发现硬编码/敏感内容
- ❌ 有安装/上手步骤 — 未命中任何模式（11 条）
```

**每一分都能追溯到具体判据**。学生问"凭什么"，直接把这一行发给他。

### 要点 3：不适用项不扣分

某同学根本没交 Python，那"代码能否通过语法检查"这一项对他**不适用**，
会记为 `—` 并从分母里剔除。

```
可执行 0.67 ⚠️  fail=['workflow_described']  na=['package_structure', 'skill_frontmatter']
```

他不会因为"没交 Python"被扣分，但会因为有 Python 却编译不过被扣分。

---

## 三、常用命令

```bash
# 只出 Markdown，最省事
python .../c4a_evaluator.py <FOLDER> --formats md

# 给合成/测试数据打标签，报告里会显眼标注
python .../c4a_evaluator.py <FOLDER> --out output --tag Liyang=合成夹具

# 这次作业更看重"可验证"，调权重（四条件相对权重）
python .../c4a_evaluator.py <FOLDER> --weights reusable=0.2,executable=0.2,verifiable=0.5,clear_io=0.1

# 换一套规则（比如另一门课的标准）
python .../c4a_evaluator.py <FOLDER> --config references/my_rubric.yaml

# 加 LLM 深度批注（需要 ANTHROPIC_API_KEY；只加批注，不改分）
python .../c4a_evaluator.py <FOLDER> --llm
```

---

## 四、常见坑

### 坑 1：Windows 下中文输出乱码

```
鍏ㄧ彮鏈€寮辩淮搴??
```

**原因**：Windows 控制台默认不是 UTF-8。
**解法**：命令前加环境变量（Git Bash / PowerShell 都行）：

```bash
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 python .../c4a_evaluator.py <FOLDER>
```

或者干脆不看终端，直接打开 `output/*_report.md`（文件本身始终是 UTF-8）。

### 坑 2：报告里出现了 `Unknown` 作者

**原因**：文件名没有 `_C4_` 前缀，上级文件夹也不是人名，正文里也没有"作者："。
**解法**：两种都行——

1. 把文件重命名为 `姓名_C4_xxx` 再跑；
2. 或者按目录分组：`我的提交/张三/各种文件`，技能会用文件夹名当作者。

`Unknown` 是**故意的设计**：认不出来的东西标出来让人处理，
比猜一个错名字塞进报告里好。

### 坑 3：明明交了 demo，为什么说缺？

先看报告里的"匹配文件"列。常见原因：

- demo 文件名里既没有 `demo`/`演示`/`截图`/`录屏`，扩展名也不在
  `.mp4/.mov/.png/.jpg/.gif/.md` 里 → 改文件名加上 `_demo_` 即可；
- 文件超过 60 MB → 只做文件名匹配，如果名字里没有 demo 关键字就认不出。

### 坑 4：`.skill` 包说"结构不完整"

评审器会**真的解压**你的 `.skill`，检查里面有没有 `SKILL.md`。
打包时多套了一层目录（`我的技能/我的技能/SKILL.md`）也可能触发。
用 `C4A/tools/package_skill.py` 打包就不会：

```bash
python tools/package_skill.py skill-src/c4a-skill-evaluator \
    --out Songpengfei_C4A_skill-evaluator.skill
```

### 坑 5：想改判据（"我不同意这条检查"）

**别改代码，改 YAML。** `references/rubric.yaml` 里 14 条检查是声明式的：

```yaml
      - id: install_instructions
        label: "有安装/上手步骤"
        detector: regex
        any: ['安装', '导入', '加载', 'install', 'setup']
        suggestion: "在说明里加一段明确的『安装/导入』小节"
```

加一个关键词就多一条判据；删掉一条就少一条。改完重跑即可，
**报告和 Excel 会自动跟着变**。

> 改完请跑一遍金标准测试确认没改坏别的东西：
> `cd skill-src/c4a-skill-evaluator && python -m unittest discover -s tests`

---

## 五、想把它当 Claude Skill 用

`.skill` 包可以直接装到支持 Claude Skills 的环境：

```
Songpengfei_C4A_skill-evaluator.skill   （ZIP 格式，顶层是 c4a-skill-evaluator/）
```

装好后对 AI 说这些就会触发：

> 「评审 C4 提交」「检查技能提交」「C4 评审报告」
> 「evaluate C4 submissions」「review skill submissions」

然后给它一个文件夹路径。它会按 `SKILL.md` 里写的四步工作流走完，
并把五种格式的报告写到你指定的输出目录。

**注意**：装成 Skill 后，AI 是在**引导你运行同一个 Python 脚本**，
不是重新用模型评一遍。分数依然来自那 19 条规则——这样你在终端跑、
在 Claude 里跑、下周再跑，结果都一样。

---

## 六、这类技能最容易做错的地方（写给下一个做评审器的人）

1. **别让 LLM 直接给分。** 同一份提交两次两个分，学生一质疑你就没法答。
2. **别用"子串命中即通过"。** 一定会出现"6/5 个文件"这种结果。
   要么打分+分配，要么就承认自己会误判。
3. **一定要有"不适用"。** 布尔值会冤枉没提交某类内容的人。
4. **一定要建一个已知答案的测试集。** 否则你没法知道改一个规则是变好了还是变坏了。
   我的测试集只有 3 份合成提交，但已经抓出了至少 3 个真 bug。
5. **负向检查和正向检查的扫描范围要分开。** AI 日志里出现绝对路径是正常的，
   把它算进"文档里有硬编码路径"是误伤。
