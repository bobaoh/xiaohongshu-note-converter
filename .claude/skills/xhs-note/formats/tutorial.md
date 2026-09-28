---
name: tutorial
title: 教程
description: 分步骤的方法教学类帖子，如化妆、穿搭、手工、软件操作、健身动作、学习方法、生活技巧；做菜类优先用 recipe
---

## 字段说明

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| title | string | 是 | 教程标题 |
| goal | string | 是 | 学完能做到什么 |
| difficulty | string | 否 | 难度，照原文或根据作者描述（如"新手友好"） |
| duration | string | 否 | 所需时间 |
| audience | string | 否 | 适合人群 |
| prerequisites | array | 否 | 前置条件或需要先掌握的内容 |
| tools | array | 否 | 工具/材料/软件，每项 `{name, note}` |
| steps | array | 是 | 步骤，每项 `{title, detail, tip}` |
| common_mistakes | array | 否 | 常见错误及避免方法 |
| tips | array | 否 | 其他技巧 |

## JSON 示例

```json
{
  "title": "微波炉万能糯米皮",
  "goal": "2 分钟做出放三天不硬的糯米皮，用于糯米糍、冰皮月饼、雪媚娘",
  "difficulty": null,
  "duration": "微波炉加热 2 分钟",
  "audience": null,
  "prerequisites": [],
  "tools": [{"name": "微波炉", "note": "高火"}, {"name": "陶瓷碟", "note": "作者担心玻璃器皿爆裂"}],
  "steps": [
    {"title": "混合过筛", "detail": "糯米粉、玉米淀粉、牛奶、白糖搅匀后过筛", "tip": null}
  ],
  "common_mistakes": ["不戴手套会非常粘手"],
  "tips": ["油多是放三天不发硬的关键"]
}
```

## Markdown 模板

```markdown
# {title}

🎯 目标：{goal}
📶 难度：{difficulty}　⏱️ 用时：{duration}　👤 适合：{audience}

## 准备
- 前置：{prerequisites[]}
- 工具/材料：{tools[].name}（{tools[].note}）

## 步骤
1. **{steps[].title}**：{steps[].detail}
   > 💡 {steps[].tip}

## 常见错误
- {common_mistakes[]}

## 技巧
- {tips[]}
```

没有内容的小节和字段省略。

## 格式专属规则

- 步骤顺序以视频时间轴或图片编号为准，不要重新排序。
- 每一步写清动作和判断标准（如"看不到白色粉点即熟透"），参数（时间、温度、数值、快捷键）照录。
- 只用画面展示、没有文字说明的步骤，可以根据图片描述，但要标 `[不确定]`。
- 视频里说的"一碗""三圈"这类非标准用量照原文写，不换算。
