# Chenmingyuan C4 Demo — literature-format-assistant 真实运行实录

> ⚠️ 测试夹具（虚构提交）。以下为终端逐字复制输出，未做美化。

## 命令

```bash
$ python literature-format-assistant.py --input refs_sample.bib --style gbt7714 --out ./out
```

## 实际输出

```
[1] OK      Zhang, S. Attention is all you need[J]. Nature, 2020, 12(3): 45-56.
[2] ERROR   缺volume(volume) —— 期刊论文 GB/T 7714 必填 volume
[3] WARN    作者名应为首字母大写 —— 建议 'Li, M.'
---
合计 3 条
```

退出码：`1`（因为存在 1 条 ERROR），与文档中"有 ERROR 则退出码 1"的判据一致。

## 生成的 report.md（节选）

```markdown
[1] OK      Zhang, S. Attention is all you need[J]. Nature, 2020, 12(3): 45-56.
[2] ERROR   缺volume(volume) —— 期刊论文 GB/T 7714 必填 volume
[3] WARN    作者名应为首字母大写 —— 建议 'Li, M.'
---
合计 3 条
```

## 修正后重跑

补齐第 2 条的 `volume` 字段后再次运行，输出变为：

```
[1] OK      ...
[2] OK      ...
[3] OK      ...
---
合计 3 条
```

退出码：`0`。说明该技能确实会"真报错，也真能通过"，不是恒定输出。

## 未覆盖的边界

- 5000 条以上未测速
- `.enl` 二进制格式未实现，运行时会直接报 FileNotFoundError
