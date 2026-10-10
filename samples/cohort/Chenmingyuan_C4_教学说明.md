# Chenmingyuan C4 教学说明：怎么上手 literature-format-assistant

> ⚠️ 测试夹具（虚构提交）。

## 一、三分钟上手

### 步骤 1：装依赖

```bash
pip install bibtexparser
```

> 注意：本脚本第一版其实只用标准库，`bibtexparser` 是我后来为解析复杂嵌套字段加的。
> 如果你只想跑最小示例，把 `parse_bib` 换成自带的简易解析器即可，无需安装。

### 步骤 2：跑第一条

```bash
python literature-format-assistant.py --input refs.bib --style gbt7714 --out ./out
```

看到 `[1] OK` 就说明环境通了。

### 步骤 3：看懂输出

| 前缀 | 含义 | 你要做什么 |
|------|------|-----------|
| `OK` | 格式正确 | 不用管 |
| `WARN` | 能过但不规范 | 有空再改 |
| `ERROR` | 会被退稿 | 必须改 |

## 二、常见坑

1. **BibTeX 字段用花括号嵌套时解析不全** —— 把 `author = {Zhang, {San}}` 改成 `author = {Zhang, San}`。
2. **中文期刊没有 volume** —— 中文期刊很多只给年期，这时可以直接忽略该条 ERROR，或用 `--style apa`。
3. **Windows 下中文输出乱码** —— 在命令前加 `chcp 65001`，或把输出重定向到文件再打开。
4. **路径带空格** —— 用引号包起来：`--input "我的资料/refs.bib"`，并始终使用相对路径。

## 三、优化技巧

- 把 `--out` 指到 git 仓库外，避免每次运行污染提交记录。
- 想接 CI：`python literature-format-assistant.py --input refs.bib; echo $?` 非 0 就拦截。

## 四、注意事项

本技能只做**格式**校验，不判断文献内容是否真实存在、是否被引用过。撤稿检测不在范围内。
