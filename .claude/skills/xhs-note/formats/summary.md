---
name: summary
title: 通用摘要
description: 任何帖子都适用的兜底格式，包括观点、日常分享、经验总结、资讯，以及其他格式都不合适的内容
---

## 字段说明

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| title | string | 是 | 帖子标题，没有就根据内容概括一个 |
| category | string | 是 | 内容类别，如 美食、旅行、穿搭、美妆、家居、职场、学习、数码、情感、资讯 |
| one_line | string | 是 | 一句话概括帖子讲了什么 |
| key_points | array | 是 | 3–7 条要点，每条一句话 |
| details | array | 否 | 分主题展开，每项 `{heading, content}` |
| mentioned | array | 否 | 提到的具体对象，每项 `{name, type, note}`；type 如 品牌、产品、地点、店铺、人物、App、书 |
| author_view | string | 否 | 作者的观点、结论或推荐态度 |
| tags | array | 否 | 帖子自带的话题标签，不带 # |

## JSON 示例

```json
{
  "title": "Apple Watch 3 个必装 App",
  "category": "数码",
  "one_line": "作者推荐三款 Apple Watch App，分别用于减肥饮食、HRV 压力监测和解压。",
  "key_points": ["HRV 压力监测可以看到每天的压力曲线", "饮食 App 用于减肥监督"],
  "details": [{"heading": "HRV 压力监测", "content": "……"}],
  "mentioned": [{"name": "Apple Watch", "type": "产品", "note": null}],
  "author_view": "三款都值得装",
  "tags": ["AppleWatch", "数码好物"]
}
```

## Markdown 模板

```markdown
# {title}

> {one_line}

**类别：** {category}

## 要点
- {key_points[]}

## 详细内容

### {details[].heading}
{details[].content}

## 提到的
| 名称 | 类型 | 备注 |
|---|---|---|
| {mentioned[].name} | {mentioned[].type} | {mentioned[].note} |

## 作者观点
{author_view}

**标签：** #{tags[]}
```

没有内容的小节整节省略。

## 格式专属规则

- 要点只写帖子里真实出现的信息，不加入你自己的评价或延伸建议。
- `one_line` 要写清"谁/什么 + 做了什么/结论是什么"，不要写成"本帖分享了……"这种空话。
- 帖子本身是某个垂直类型（菜谱、攻略、测评、教程）而用户又选了 summary 时，照常摘要，但在 `key_points` 里保留最关键的数字（用量、价格、时间）。
