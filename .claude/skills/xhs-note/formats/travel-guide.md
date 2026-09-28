---
name: travel-guide
title: 旅行攻略
description: 目的地游记、行程分享、景点/交通/住宿/美食打卡等旅行攻略类帖子
---

## 字段说明

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| destination | string | 是 | 目的地（城市/地区/国家） |
| trip_length | string | 否 | 行程天数，如"3 天 2 晚" |
| best_season | string | 否 | 作者建议的出行时间或季节 |
| budget | object | 否 | `{total, per_person, currency, includes}`；includes 说明包含哪些花费 |
| itinerary | array | 是 | 行程，每天一项 `{day, title, stops: [{transfer, time, name, activity, cost}]}`；`transfer` 是从上一站到这一站的交通（如"步行 20 分钟"），第一站或原文没写时填 null；帖子没按天划分时只放一项，day 填 null |
| places | array | 否 | 地点清单，每项 `{name, type, address, price, opening_hours, tips}`；type 取 景点、餐厅、购物、住宿区域、住宿、交通枢纽 之一；行程里的地点也要列入 |
| transport | array | 否 | 抵达和通用交通（机场/车站到市区、地铁线路、交通卡等），每项 `{route, mode, duration, cost}`；站与站之间的交通写在 `stops[].transfer`，不要重复 |
| tips | array | 是 | 注意事项、避坑、预约提醒 |

## JSON 示例

```json
{
  "destination": "京都",
  "trip_length": "2 天",
  "best_season": "11 月中下旬红叶季",
  "budget": {"total": null, "per_person": "约 1500", "currency": "CNY", "includes": "不含机票"},
  "itinerary": [
    {"day": 1, "title": "东山线", "stops": [
      {"transfer": null, "time": "08:00", "name": "清水寺", "activity": "早去避开人流", "cost": "门票 500 日元"},
      {"transfer": "步行 15 分钟", "time": null, "name": "二年坂三年坂", "activity": "逛老街", "cost": "免费"}
    ]}
  ],
  "places": [
    {"name": "清水寺", "type": "景点", "address": null, "price": "500 日元", "opening_hours": "6:00–18:00", "tips": "早上人少"},
    {"name": "四条河原町", "type": "住宿区域", "address": null, "price": null, "opening_hours": null, "tips": "交通方便，适合第一次去"}
  ],
  "transport": [{"route": "关西机场 → 京都站", "mode": "JR Haruka", "duration": "约 75 分钟", "cost": null}],
  "tips": ["红叶季热门寺庙需要提前预约夜间特别参观"]
}
```

## Markdown 模板

```markdown
# {destination} 旅行攻略

📅 行程：{trip_length}
🍂 最佳时间：{best_season}
💰 预算：{budget.per_person} {budget.currency}/人（{budget.includes}）

## 行程

### Day {itinerary[].day}：{itinerary[].title}
| 时间 | 地点 | 安排 | 花费 |
|---|---|---|---|
| {stops[].time} | {stops[].name} | {stops[].activity} | {stops[].cost} |
| ↓ {stops[].transfer} | | | |

## 地点清单

### {places[].type}
| 名称 | 地址 | 价格 | 营业时间 | 备注 |
|---|---|---|---|---|
| {places[].name} | {places[].address} | {places[].price} | {places[].opening_hours} | {places[].tips} |

## 交通
- {transport[].route}：{transport[].mode}，{transport[].duration}，{transport[].cost}

## 注意事项
- {tips[]}

> 信息来自 {source.published_at} 发布的帖子，价格和开放时间可能已变化，出行前请核实。
```

- 行程表中，站与站之间插入一行交通（`↓ 步行 20 分钟`），放在对应的下一站之前；`transfer` 为 null 时不插入。
- 地点清单按 `type` 分成多张表（景点、住宿区域……），类型相同的放在一起。
- 没有内容的小节和表格列整节/整列省略。

## 格式专属规则

- 价格保留原币种和原写法（"500 日元""人均 80""199r"），`currency` 用 ISO 代码（CNY、JPY、USD…）。
- 原文没写币种时，只能依据同一帖子其他价格的写法推定（如其他价格都写"元"），并把推定过程记入 `uncertain`。没有依据就填 null，不要按目的地猜。
- 帖子不同部分对同一地点的建议有冲突时（如总览图写"建议晚上去"、正文写"上午去"），两种都写并记入 `uncertain`。
- 地址、营业时间、门票价格只照录原文或图片里清晰可见的内容，不补充你知道的信息。
- 结尾必须写上帖子发布日期的时效提醒；`published_at` 为 null 时写"发布日期未知"。
- 图片中的地图、路线图、价目表要用 Read 查看，有信息就写进 `places` 或 `transport`。
