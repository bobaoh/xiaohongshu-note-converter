---
name: product-review
title: 好物测评
description: 好物推荐、购物分享、开箱、单品测评、多款对比、避雷清单类帖子
---

## 字段说明

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| topic | string | 是 | 清单主题，如"油皮洗发水测评""宿舍好物" |
| products | array | 是 | 产品列表，每项 `{name, brand, category, price, where_to_buy, pros: [], cons: [], verdict, suitable_for}`；verdict 如 推荐、一般、避雷 |
| comparison | string | 否 | 多款产品之间的对比结论 |
| buying_advice | array | 否 | 作者给出的购买建议 |
| disclosure | string | 否 | 广告/合作/赞助情况，照原文注明；没有标注就填 null |

## JSON 示例

```json
{
  "topic": "控油蓬松洗发水",
  "products": [
    {
      "name": "控油蓬松洗发水 茶花香",
      "brand": "卡厘",
      "category": "洗发水",
      "price": "几十块钱",
      "where_to_buy": null,
      "pros": ["发根蓬松", "效果堪比定型喷雾"],
      "cons": [],
      "verdict": "推荐",
      "suitable_for": "油性头皮、头发扁塌"
    }
  ],
  "comparison": null,
  "buying_advice": [],
  "disclosure": null
}
```

## Markdown 模板

```markdown
# {topic}

| 产品 | 品牌 | 价格 | 评价 | 适合 |
|---|---|---|---|---|
| {products[].name} | {products[].brand} | {products[].price} | {products[].verdict} | {products[].suitable_for} |

## 详细

### {products[].name}
- 👍 {pros[]}
- 👎 {cons[]}
- 🛒 购买渠道：{where_to_buy}

## 对比结论
{comparison}

## 购买建议
- {buying_advice[]}

> ⚠️ {disclosure}
```

没有内容的小节整节省略。只有一款产品时不需要汇总表。

## 格式专属规则

- 优缺点只写作者说过或图中文字写明的，不补充你自己知道的产品信息，也不评价作者的判断。
- 价格照原文写（"几十块""到手 89"），注明是否为活动价、哪个平台；原文没说就不写。
- `verdict` 反映作者的态度，不是你的评价；作者态度不明确时填 null。
- 正文或标签出现"合作""广告""赞助""小红书市集"，或 @ 了品牌官方账号时，写进 `disclosure`，照原文措辞，不下结论。
- 图片里的产品包装文字可以用来确认品牌和产品名，但宣传语不算作者评价。
