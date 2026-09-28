---
# 格式的唯一英文名，和文件名一致（如 restaurant.md → restaurant）。用于 /xhs-note <链接> restaurant。
name: my-format
# 中文名，也可以用来指定格式（如 /xhs-note <链接> 探店）。
title: 格式中文名
# 什么样的帖子适合这个格式。自动选择格式时只看这一行，请写具体。
description: 适用于哪类帖子，例如：餐厅探店、咖啡店打卡类帖子
---

<!--
新建格式的步骤：
1. 复制本文件，重命名为 <name>.md，放在同一个 formats/ 目录下。
2. 修改上面的 frontmatter。
3. 填写下面四节：字段说明、JSON 示例、Markdown 模板、格式专属规则。
不需要改任何代码。以 _ 开头的文件（比如本模板）不会被自动选择。
-->

## 字段说明

<!--
这里只列 data 的顶层字段。校验脚本会读取这张表：
- 必填 = 是：字段必须出现在 data 中。素材里没有时填 null 或 []，并记入 missing。
- 类型：string / number / boolean / array / object 之一。
嵌套结构写在"说明"列里，并在 JSON 示例中体现。
-->

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| name | string | 是 | 名称 |
| items | array | 是 | 条目列表，每项 `{name, note}` |
| notes | array | 否 | 补充说明 |

## JSON 示例

```json
{
  "name": "示例名称",
  "items": [{"name": "条目", "note": "说明"}],
  "notes": ["补充说明"]
}
```

## Markdown 模板

```markdown
# {name}

## 条目
- {items[].name}：{items[].note}

## 补充
- {notes[]}
```

## 格式专属规则

- 这个格式特有的整理要求。通用规则写在 SKILL.md 里，不用重复。
