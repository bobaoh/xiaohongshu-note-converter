---
name: recipe
title: 菜谱
description: 美食制作、烘焙、甜品、饮品、家常菜等带配料和做法的帖子
---

## 字段说明

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| title | string | 是 | 菜名 |
| duration | string | 否 | 总用时或关键加热时间，原文没有就填 null |
| servings | string | 否 | 份量，如"3 个""一个 6 寸" |
| ingredient_groups | array | 是 | 配料分组，每组 `{name, items: [{name, amount}]}`；不分组时 name 填 null |
| method | array | 是 | 做法分段，每段 `{section, steps: [string]}`；不分段时 section 填 null |
| variations | array | 否 | 做法变化，每项 `{name, description}` |
| tips | array | 是 | 小贴士 |

## JSON 示例

```json
{
  "title": "焙茶无花果团子",
  "duration": "微波炉加热 2 分钟",
  "servings": "3 个",
  "ingredient_groups": [
    {"name": "团子皮", "items": [{"name": "糯米粉", "amount": "32g"}, {"name": "黄油", "amount": "14g"}]},
    {"name": "内馅", "items": [{"name": "无花果", "amount": "3 颗"}]}
  ],
  "method": [
    {"section": "团子皮", "steps": ["除黄油外所有材料混合到无颗粒，过筛", "微波炉高火 2 分钟"]},
    {"section": "组装", "steps": ["面皮铺进半圆模具，挤一层奶酪馅"]}
  ],
  "variations": [],
  "tips": ["超过一天不吃就冷冻保存"]
}
```

## Markdown 模板

```markdown
# {title}

⏱️ 用时：{duration}
🍽️ 份量：{servings}

## 配料

### {ingredient_groups[].name}
- {items[].name}：{items[].amount}

## 做法

**{method[].section}**
1. {steps[]}

## 做法变化
- **{variations[].name}**：{variations[].description}

## 小贴士
- {tips[]}
```

没有内容的小节（如"做法变化"）整节省略。用时、份量缺失时写"未注明"。

## 格式专属规则

- 用量照原文写，保留原单位（g、ml、勺、碗、个）。不换算，不把"1 碗"改成克数。
- 用量缺失时 `amount` 填 null，Markdown 里写"适量（原文未注明）"。
- 温度、时间、火力必须照录；来源之间有冲突时两个都写并注明来源。
- 原文说"除了 X"但没说 X 何时加入的这类缺口，写进 `uncertain`，不要自行补全。
- 步骤图里能看到、但文字没写的操作，可以写进步骤，但要标 `[不确定]`。
