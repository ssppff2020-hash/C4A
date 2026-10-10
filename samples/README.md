# samples/ — 评审输入样本（数据来源说明）

这个目录是评审器的**输入**。两份样本的用途不同，来源也不同，
**请务必分清**——其中只有 `real/` 是真实数据。

---

## `real/` — 真实 C4 提交（1 位作者）

从相邻的 C4 挑战资料包里原样复制的真实提交：

```
来源：EduSeed挑战资料包/挑战_C4 技能分享与传播_4cdgor_完整资料/C4/
作者：Songpengfei
内容：Songpengfei_C4_* 共 10 个文件（lesson-design-assistant 技能包）
```

**这是本地磁盘上唯一一份真实 C4 提交**，用于证明评审器在非自造数据上可用。
复制过来是为了让报告可以离线复现——原始文件没有被修改。

---

## `cohort/` — 班级队列（1 份真实 + 3 份**合成**）

`cohort/` = `real/` 的副本 + 3 份**合成测试夹具**，平铺在一个目录里，
刻意模拟"从 WeChat 群文件夹直接拖出来"的形态（没有按作者分目录）。

| 作者 | 性质 | 设计质量 | 期望结果 |
|------|------|---------|---------|
| Songpengfei | ✅ **真实** | 优 | 5/5 · 4.00/4 · 100.0 · 无红牌 |
| Chenmingyuan | ⚠️ **合成夹具** | 优（对照组） | 5/5 · 4.00/4 · 100.0 · 无红牌 |
| Liyang | ⚠️ **合成夹具** | 中 | 4/5 · 2.47/4 · 69.0 · 一句话指令 |
| Zhaolei | ⚠️ **合成夹具** | 差 | 2/5 · 1.62/4 · 40.2 · 缺件 + 无 AI 日志 |

另有 2 个非 C4 干扰文件（`Elite20_课表.md`、`群公告.txt`），
用来验证过滤逻辑，它们不应出现在评审结果里。

### 合成夹具的来源与用途

这 3 份合成提交**不是编造的假数据凑数**——它们是评审器的**金标准测试集**：

```
真身（唯一来源）：skill-src/c4a-skill-evaluator/tests/fixtures/wechat_dump/
复制到此处：      samples/cohort/
```

每一份的文件顶部都写了 `⚠️ 测试夹具（虚构提交）` 标注，
评审报告里也全部带 `合成夹具` 标签，**不会被误当成真实同学的作品**。

用途有两个：

1. **验证评审器的分辨力**——优/中/差三档必须被正确区分（100.0 / 69.0 / 40.2）。
2. **让 Level 2–4 的班级级功能真正跑起来**——排名、总览、缺口热力、
   逐人改进建议都需要多个作者，只有 1 份真实提交演示不出来。

`tests/test_evaluator.py` 里的 24 个断言就是钉在这批文件上的期望值：
**如果你改了评审规则，这 3 份的分数变了，测试就会红**——那是提醒你
"你改变了评审器的判断"，而不是"测试坏了"。

---

## 重新生成 cohort/

`cohort/` 是由 `real/` 和测试夹具复制拼成的，没有脚本，两条命令即可重建：

```bash
cd C4A
rm -rf samples/cohort && mkdir -p samples/cohort
cp samples/real/* samples/cohort/
cp skill-src/c4a-skill-evaluator/tests/fixtures/wechat_dump/* samples/cohort/
```

然后重跑评审：

```bash
python skill-src/c4a-skill-evaluator/scripts/c4a_evaluator.py samples/cohort \
    --out output --basename cohort-demo \
    --tag Chenmingyuan=合成夹具 --tag Liyang=合成夹具 --tag Zhaolei=合成夹具
```

---

## 想评审真实的群文件夹？

把 `samples/cohort` 换成你自己的路径即可，技能不关心文件夹叫什么：

```bash
python skill-src/c4a-skill-evaluator/scripts/c4a_evaluator.py "D:/WeChatFiles/群文件" --out output
```
