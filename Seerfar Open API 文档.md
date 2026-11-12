# Seerfar Open API **文档**

base url:http://api.seerfar.cn     key:<YOUR_API_KEY>

## 鉴权

所有开放 API 使用 Bearer Token 鉴权。在请求 Header 中添加 Authorization，值为 Bearer 后拼接空格和访问令牌。

HTTP Header复制

```鉴权流程
Authorization: Bearer <platform_api_key>
Content-Type: application/json
```



### 鉴权流程

| 顺序 | 校验项                                                       | 失败结果                                          |
| :--- | :----------------------------------------------------------- | :------------------------------------------------ |
| 1    | 检查是否携带 `Authorization` 请求头，且格式为 `Bearer <platform_api_key>` | `401 Unauthorized`                                |
| 2    | 对 API Key 做哈希匹配，定位 `api_key_id` 与 `account_id`     | `401 Unauthorized`                                |
| 3    | 校验 Key 状态必须为 `active`                                 | `401 Unauthorized`                                |
| 4    | 校验客户账号状态、数据使用条款确认状态和积分余额             | `403 Forbidden` 或 `8000 Api Key limit exhausted` |
| 5    | 执行 Key 级和账号级限流检查                                  | `429 Too Many Requests`                           |
| 6    | 按接口所需能力校验 Ozon / Wildberries 授权状态和 Token 类别  | `403 Forbidden`                                   |

每个有效的 API Key 均可调用全部开放接口。接口是否返回数据仍取决于客户账号状态、积分余额、限流、平台授权和数据合规边界。



## 通用响应

接口响应使用统一顶层结构，包含 code、msg 和 data。常见错误包括未授权、无权限、请求过多、服务端错误和 API Key 积分耗尽。

Response复制

```
{
  "code": 200,
  "msg": "SUCCESS",
  "data": {}
}
```

| 状态                           | 含义                    |
| :----------------------------- | :---------------------- |
| 200 / SUCCESS                  | 请求成功。              |
| 401 / Unauthorized             | 鉴权失败或 Token 缺失。 |
| 403 / Forbidden                | 账号或权限不允许访问。  |
| 429 / Too Many Requests        | 请求频率过高。          |
| 500 / Server error             | 服务端错误。            |
| 8000 / Api Key limit exhausted | API Key 积分耗尽。      |

### 响应字段

| 字段   | 类型                    | 说明                                    |
| :----- | :---------------------- | :-------------------------------------- |
| `code` | number                  | 业务状态码。成功通常为 200。            |
| `msg`  | string                  | 响应文字描述。                          |
| `data` | object \| array \| null | 业务数据。无数据或错误时可能为 `null`。 |

Tips：接口级别还会在各 endpoint 下配置 responseFields，用于说明 data 内部字段、示例值和字段含义。



## 查询 API Key 积分

GET/open-api/quota

查询 API Key 的付费积分、已使用积分和免费积分字段。

试一试

### Header 参数

| 参数            | 类型   | 必填 | 示例               | 说明    |
| :-------------- | :----- | :--- | :----------------- | :------ |
| `Authorization` | string | 是   | `Bearer {Api Key}` | API Key |

### 请求示例

cURL复制

```
curl "http://api.seerfar.cn/open-api/quota" \
  -H "Authorization: Bearer <platform_api_key>"
```

### 响应示例

JSON复制

```
{
  "code": 200,
  "msg": "SUCCESS",
  "data": {
    "creditLimit": 100,
    "creditUsed": 23,
    "freeCreditLimitMonth": 0,
    "freeCreditUsedMonth": 0
  }
}
```

### 响应字段

| 字段                        | 类型   | 示例      | 说明                         |
| :-------------------------- | :----- | :-------- | :--------------------------- |
| `code`                      | number | `200`     | 状态码                       |
| `msg`                       | string | `SUCCESS` | 返回文字描述                 |
| `data`                      | object | `-`       | 返回数据                     |
| `data.creditLimit`          | number | `100`     | 付费积分总量                 |
| `data.creditUsed`           | number | `23`      | 付费积分已使用量             |
| `data.freeCreditLimitMonth` | number | `0`       | 月免费积分总量（已弃用）     |
| `data.freeCreditUsedMonth`  | number | `0`       | 月免费积分量已使用（已弃用） |

### 错误响应

| 状态码 | 说明     | 示例                                          |
| :----- | :------- | :-------------------------------------------- |
| `500`  | 失败     | `{ "code": 500, "msg": "Server error" }`      |
| `401`  | 未授权   | `{ "code": 401, "msg": "Unauthorized" }`      |
| `429`  | 请求过多 | `{ "code": 429, "msg": "Too Many Requests" }` |



## Ozon 查店铺

POST/open-api/shop/detail/search/ozon

按店铺 ID 分页查询 Ozon 近 30 天店铺商品及汇总数据。商品列表按上架时间倒序；productCount、rating、totalRevenue、totalSales、dailySales 和 fulfillment 仅在 page.pageNumber=1 时返回。

试一试

### Header 参数

| 参数            | 类型   | 必填 | 示例               | 说明    |
| :-------------- | :----- | :--- | :----------------- | :------ |
| `Authorization` | string | 是   | `Bearer {Api Key}` | API Key |

### Body 参数

| 参数                         | 类型    | 必填 | 示例      | 说明                                                         |
| :--------------------------- | :------ | :--- | :-------- | :----------------------------------------------------------- |
| `id`                         | number  | 是   | `118364`  | 店铺ID                                                       |
| `reviewCount`                | object  | 否   | `-`       | 评论数                                                       |
| `reviewCount.min`            | integer | 否   | `-`       | 最小评论数                                                   |
| `reviewCount.max`            | integer | 否   | `-`       | 最大评论数                                                   |
| `drr`                        | object  | 否   | `-`       | 广告费用份额                                                 |
| `drr.min`                    | number  | 否   | `-`       | 最小广告费用份额                                             |
| `drr.max`                    | number  | 否   | `-`       | 最大广告费用份额                                             |
| `reviewRating`               | object  | 否   | `-`       | 评分                                                         |
| `reviewRating.min`           | number  | 否   | `-`       | 最小评分                                                     |
| `reviewRating.max`           | number  | 否   | `-`       | 最大评分                                                     |
| `questionsAndAnswers`        | object  | 否   | `-`       | qa                                                           |
| `questionsAndAnswers.min`    | integer | 否   | `-`       | 最小qa                                                       |
| `questionsAndAnswers.max`    | integer | 否   | `-`       | 最大qa                                                       |
| `price`                      | object  | 否   | `-`       | 价格，单位卢布                                               |
| `price.min`                  | number  | 否   | `-`       | 最小价格                                                     |
| `price.max`                  | number  | 否   | `-`       | 最大价格                                                     |
| `monthlyRevenue`             | object  | 否   | `-`       | 销售额                                                       |
| `monthlyRevenue.min`         | number  | 否   | `-`       | 最小销售额                                                   |
| `monthlyRevenue.max`         | number  | 否   | `-`       | 最大销售额                                                   |
| `monthlySales`               | object  | 否   | `-`       | 销量                                                         |
| `monthlySales.min`           | integer | 否   | `-`       | 最小销量                                                     |
| `monthlySales.max`           | integer | 否   | `-`       | 最大销量                                                     |
| `monthlySalesRate`           | object  | 否   | `-`       | 销量增长率                                                   |
| `monthlySalesRate.min`       | number  | 否   | `-`       | 最小销量增长率                                               |
| `monthlySalesRate.max`       | number  | 否   | `-`       | 最大销量增长率                                               |
| `weight`                     | object  | 否   | `-`       | 重量，单位g                                                  |
| `weight.min`                 | number  | 否   | `-`       | 最小重量                                                     |
| `weight.max`                 | number  | 否   | `-`       | 最大重量                                                     |
| `volume`                     | object  | 否   | `-`       | 体积，单位L                                                  |
| `volume.min`                 | number  | 否   | `-`       | 最小体积                                                     |
| `volume.max`                 | number  | 否   | `-`       | 最大体积                                                     |
| `grossMargin`                | object  | 否   | `-`       | 毛利率                                                       |
| `grossMargin.min`            | number  | 否   | `-`       | 最小毛利率                                                   |
| `grossMargin.max`            | number  | 否   | `-`       | 最大毛利率                                                   |
| `variants`                   | object  | 否   | `-`       | 变体数                                                       |
| `variants.min`               | integer | 否   | `-`       | 最小变体数                                                   |
| `variants.max`               | integer | 否   | `-`       | 最大变体数                                                   |
| `convToCartPdp`              | object  | 否   | `-`       | 购物车转化率                                                 |
| `convToCartPdp.min`          | number  | 否   | `-`       | 最小购物车转化率                                             |
| `convToCartPdp.max`          | number  | 否   | `-`       | 最大购物车转化率                                             |
| `returnCancellationRate`     | object  | 否   | `-`       | 退货取消率                                                   |
| `returnCancellationRate.min` | number  | 否   | `-`       | 最小退货取消率                                               |
| `returnCancellationRate.max` | number  | 否   | `-`       | 最大退货取消率                                               |
| `creationDate`               | integer | 否   | `-`       | 上架时间，null：不筛选，1：近30天，3：近90天，6：近180天，12：近一年，24：近2年 |
| `categoryIds`                | array   | 否   | `-`       | 类目id数组                                                   |
| `fulfillment`                | array   | 否   | `-`       | 配送方式数组，可传值：OZON，FBO，FBS，RFBS，FBP              |
| `skus`                       | array   | 否   | `-`       | sku数组，最多可传10个sku                                     |
| `brand`                      | object  | 否   | `-`       | 品牌                                                         |
| `brand.type`                 | number  | 否   | `0`       | 0:包含品牌 1:排除品牌 2:无品牌                               |
| `brand.brandName`            | array   | 否   | `-`       | 品牌名称                                                     |
| `labels`                     | array   | 否   | `-`       | 标签数组，0：新品，1：正品，2：畅销品                        |
| `keywords`                   | array   | 否   | ``        | 关键词                                                       |
| `tag`                        | string  | 否   | `-`       | 标签词                                                       |
| `page`                       | object  | 是   | `-`       | 分页参数                                                     |
| `page.pageNumber`            | number  | 是   | `1`       | 分页页码                                                     |
| `page.pageSize`              | number  | 是   | `20`      | 分页每页条数，最大100                                        |
| `page.orders`                | array   | 是   | `-`       | 排序规则                                                     |
| `page.orders.field`          | string  | 是   | `revenue` | 排序字段，支持：revenue,price,sales,grossMargin,views,sessionCountSearch,sessionCount,convToCartPdp,orderConversionRate,drr,returnCancellationRate,missedRevenue,variants,reviewCount,reviewRating,upTime,weight,volume,questionsAndAnswers |
| `page.orders.direction`      | string  | 是   | `DESC`    | DESC：倒序，ASC：正序                                        |

### 请求体

Request Body复制

```
{
  "id": 118364,
  "reviewCount": {
    "min": null,
    "max": null
  },
  "drr": {
    "min": null,
    "max": null
  },
  "reviewRating": {
    "min": null,
    "max": null
  },
  "questionsAndAnswers": {
    "min": null,
    "max": null
  },
  "price": {
    "min": null,
    "max": null
  },
  "monthlyRevenue": {
    "min": null,
    "max": null
  },
  "monthlySales": {
    "min": null,
    "max": null
  },
  "monthlySalesRate": {
    "min": null,
    "max": null
  },
  "weight": {
    "min": null,
    "max": null
  },
  "volume": {
    "min": null,
    "max": null
  },
  "grossMargin": {
    "min": null,
    "max": null
  },
  "variants": {
    "min": null,
    "max": null
  },
  "convToCartPdp": {
    "min": null,
    "max": null
  },
  "returnCancellationRate": {
    "min": null,
    "max": null
  },
  "creationDate": null,
  "categoryIds": null,
  "fulfillment": [],
  "skus": [],
  "brand": {
    "type": 0,
    "brandName": []
  },
  "labels": [],
  "keywords": [],
  "filterRemoveProduct": true,
  "tag": "",
  "page": {
    "pageNumber": 1,
    "pageSize": 20,
    "orders": [
      {
        "field": "revenue",
        "direction": "DESC"
      }
    ]
  }
}
```

### 请求示例

cURL复制

```
curl "http://api.seerfar.cn/open-api/shop/detail/search/ozon" \
  -X POST \
  -H "Authorization: Bearer <platform_api_key>" \
  -H "Content-Type: application/json" \
  -d '{"id":7,"reviewCount":{"min":null,"max":null},"drr":{"min":null,"max":null},"reviewRating":{"min":null,"max":null},"questionsAndAnswers":{"min":null,"max":null},"price":{"min":null,"max":null},"monthlyRevenue":{"min":null,"max":null},"monthlySales":{"min":null,"max":null},"monthlySalesRate":{"min":null,"max":null},"weight":{"min":null,"max":null},"volume":{"min":null,"max":null},"grossMargin":{"min":null,"max":null},"variants":{"min":null,"max":null},"convToCartPdp":{"min":null,"max":null},"returnCancellationRate":{"min":null,"max":null},"creationDate":null,"categoryIds":null,"fulfillment":[],"skus":[],"brand":{"type":0,"brandName":[]},"labels":[],"keywords":[],"filterRemoveProduct":true,"tag":"","page":{"pageNumber":1,"pageSize":20,"orders":[{"field":"revenue","direction":"DESC"}]}}'
```

### 响应示例

JSON复制

```
{
  "code": 200,
  "msg": "SUCCESS",
  "data": {
    "productCount": 156,
    "rating": 4.8,
    "totalRevenue": 167345000,
    "totalSales": 101348,
    "dailySales": 3379,
    "fulfillment": {
      "OZON": 120,
      "FBO": 30,
      "FBS": 6
    },
    "products": [
      {
        "sku": 149222760,
        "title": "SvetoCopy 5 шт A4 500 л Бумага для принтера",
        "productUrl": "https://www.ozon.ru/product/149222760",
        "brandId": 33321059,
        "brandName": "SvetoCopy",
        "brandUrl": "https://www.ozon.ru/brand/33321059",
        "imageUrl": "https://ir.ozone.ru/s3/multimedia-1-9/wc300/7599846609.jpg",
        "sellerId": -2,
        "sellerName": "Ozon Express",
        "sellers": 0,
        "fulfillment": [
          "OZON"
        ],
        "weight": 12520,
        "questionsAndAnswers": 714,
        "upTime": 1334869200000,
        "upDays": 5115,
        "upMonths": 170,
        "price": 1794,
        "grossMargin": 17.3,
        "reviewCount": 649792,
        "reviewRating": 4.8,
        "reviewIncr": null,
        "sales": 75246,
        "salesRate": 7,
        "revenue": 124187644,
        "revenueRate": 11,
        "categoryInfo": {
          "category": {
            "id": "17027492_17029017_91400",
            "enTitle": "Printer Paper",
            "title": "Бумага для принтера",
            "cnTitle": "打印纸",
            "pid": "17027492_17029017",
            "level": 3,
            "disabled": false,
            "crossBorderSellable": true,
            "children": null
          },
          "fullCategoryId": [
            "17027492",
            "17027492_17029017",
            "17027492_17029017_91400"
          ],
          "titlePath": "Канцелярские товары > Бумага > Бумага для принтера",
          "cnTitlePath": "文具 > 纸 > 打印纸",
          "enTitlePath": "Stationery > Paper > Printer Paper"
        },
        "volume": 18.788,
        "dimension": "305×280×220",
        "labels": [
          1,
          2
        ],
        "variants": 3,
        "variationIds": [
          7969279,
          149222760,
          929833643
        ],
        "variationsRelationId": 26792,
        "sellerType": 0,
        "sessionCount": 211521,
        "sessionCountSearch": 343064,
        "drr": 0,
        "convToCartSearch": 10.25,
        "discount": 15.5,
        "promoRevenueShare": 62.4,
        "convViewToOrder": 4.8,
        "convToCartPdp": 14.96,
        "returnCancellationRate": null,
        "orderConversionRate": 209.8,
        "views": 7311433,
        "missedRevenue": 0
      }
    ],
    "hasNextPage": true
  }
}
```

### 响应字段

| 字段                                                      | 类型    | 示例                                                         | 说明                                                         |
| :-------------------------------------------------------- | :------ | :----------------------------------------------------------- | :----------------------------------------------------------- |
| `code`                                                    | number  | `200`                                                        | 状态码                                                       |
| `msg`                                                     | string  | `SUCCESS`                                                    | 返回文字描述                                                 |
| `data`                                                    | object  | `-`                                                          | 返回数据，无数据时返回null                                   |
| `data.productCount`                                       | integer | `156`                                                        | 商品数，仅在 page.pageNumber=1 时返回                        |
| `data.rating`                                             | number  | `4.8`                                                        | 店铺评分，仅在 page.pageNumber=1 时返回                      |
| `data.totalRevenue`                                       | number  | `167345000`                                                  | 销售额，仅在 page.pageNumber=1 时返回                        |
| `data.totalSales`                                         | integer | `101348`                                                     | 销量，仅在 page.pageNumber=1 时返回                          |
| `data.dailySales`                                         | integer | `3379`                                                       | 日均销量（销量除以 30 后向上取整），仅在 page.pageNumber=1 时返回 |
| `data.fulfillment`                                        | object  | `{"OZON":120,"FBO":30,"FBS":6}`                              | 配送方式与对应商品数的映射；组合配送方式以 & 连接。仅在 page.pageNumber=1 时返回 |
| `data.products`                                           | array   | `-`                                                          | 店铺商品数据                                                 |
| `data.products.sku`                                       | number  | `149222760`                                                  | sku                                                          |
| `data.products.title`                                     | string  | `SvetoCopy 5 шт A4 500 л Бумага для принтера`                | 商品标题                                                     |
| `data.products.productUrl`                                | string  | `https://www.ozon.ru/product/149222760`                      | 商品链接                                                     |
| `data.products.brandId`                                   | number  | `33321059`                                                   | 品牌id                                                       |
| `data.products.brandName`                                 | string  | `SvetoCopy`                                                  | 品牌名称                                                     |
| `data.products.brandUrl`                                  | string  | `https://www.ozon.ru/brand/33321059`                         | 品牌链接                                                     |
| `data.products.imageUrl`                                  | string  | `https://ir.ozone.ru/s3/multimedia-1-9/wc300/7599846609.jpg` | 商品图片链接                                                 |
| `data.products.sellerId`                                  | number  | `-2`                                                         | 卖家                                                         |
| `data.products.sellerName`                                | string  | `Ozon Express`                                               | 卖家名称                                                     |
| `data.products.sellers`                                   | number  | `0`                                                          | 卖家数（已弃用）                                             |
| `data.products.fulfillment`                               | array   | `-`                                                          | 配送方式                                                     |
| `data.products.weight`                                    | number  | `12520`                                                      | 重量，单位g                                                  |
| `data.products.questionsAndAnswers`                       | number  | `714`                                                        | qa                                                           |
| `data.products.upTime`                                    | number  | `1334869200000`                                              | 上架时间戳，毫秒                                             |
| `data.products.upDays`                                    | number  | `5115`                                                       | 上架天数                                                     |
| `data.products.upMonths`                                  | number  | `170`                                                        | 上架月数                                                     |
| `data.products.price`                                     | number  | `1794`                                                       | 价格，单位卢布                                               |
| `data.products.grossMargin`                               | number  | `17.3`                                                       | 毛利率                                                       |
| `data.products.reviewCount`                               | number  | `649792`                                                     | 评论数                                                       |
| `data.products.reviewRating`                              | number  | `4.8`                                                        | 评分                                                         |
| `data.products.reviewIncr`                                | number  | `-`                                                          | 评论增长数（已弃用）                                         |
| `data.products.sales`                                     | number  | `75246`                                                      | 销量                                                         |
| `data.products.salesRate`                                 | number  | `7`                                                          | 销量增长率                                                   |
| `data.products.revenue`                                   | number  | `124187644`                                                  | 销售额                                                       |
| `data.products.revenueRate`                               | number  | `11`                                                         | 销售额增长率                                                 |
| `data.products.categoryInfo`                              | object  | `-`                                                          | 类目                                                         |
| `data.products.categoryInfo.category`                     | object  | `-`                                                          | 类目信息                                                     |
| `data.products.categoryInfo.category.id`                  | string  | `17027492_17029017_91400`                                    | 类目id                                                       |
| `data.products.categoryInfo.category.enTitle`             | string  | `Printer Paper`                                              | 类目名称                                                     |
| `data.products.categoryInfo.category.title`               | string  | `Бумага для принтера`                                        | 类目名称                                                     |
| `data.products.categoryInfo.category.cnTitle`             | string  | `打印纸`                                                     | 类目名称                                                     |
| `data.products.categoryInfo.category.pid`                 | string  | `17027492_17029017`                                          | 父类id                                                       |
| `data.products.categoryInfo.category.level`               | number  | `3`                                                          | 类目层级                                                     |
| `data.products.categoryInfo.category.disabled`            | boolean | `false`                                                      | 类目是否可用                                                 |
| `data.products.categoryInfo.category.crossBorderSellable` | boolean | `true`                                                       | 跨境是否可售                                                 |
| `data.products.categoryInfo.category.children`            | array   | `-`                                                          | 子类目信息                                                   |
| `data.products.categoryInfo.fullCategoryId`               | array   | `-`                                                          | 类目id路径                                                   |
| `data.products.categoryInfo.titlePath`                    | string  | `Канцелярские товары > Бумага > Бумага для принтера`         | 类目路径                                                     |
| `data.products.categoryInfo.cnTitlePath`                  | string  | `文具 > 纸 > 打印纸`                                         | 类目路径                                                     |
| `data.products.categoryInfo.enTitlePath`                  | string  | `Stationery > Paper > Printer Paper`                         | 类目路径                                                     |
| `data.products.volume`                                    | number  | `18.788`                                                     | 体积，单位L                                                  |
| `data.products.dimension`                                 | string  | `305×280×220`                                                | 尺寸，单位毫米                                               |
| `data.products.labels`                                    | array   | `-`                                                          | 标签数组，0：新品，1：正品，2：畅销品                        |
| `data.products.variants`                                  | number  | `3`                                                          | 变体数                                                       |
| `data.products.variationIds`                              | array   | `-`                                                          | 变体sku                                                      |
| `data.products.variationsRelationId`                      | number  | `26792`                                                      | 变体关联id                                                   |
| `data.products.sellerType`                                | number  | `0`                                                          | 卖家类型，0：本土，1：跨境                                   |
| `data.products.sessionCount`                              | number  | `211521`                                                     | 产品卡浏览量                                                 |
| `data.products.sessionCountSearch`                        | number  | `343064`                                                     | 曝光量                                                       |
| `data.products.drr`                                       | number  | `0`                                                          | 广告费用                                                     |
| `data.products.convToCartSearch`                          | number  | `10.25`                                                      | 搜索加购率                                                   |
| `data.products.discount`                                  | number  | `15.5`                                                       | 平均折扣                                                     |
| `data.products.promoRevenueShare`                         | number  | `62.4`                                                       | 促销销售占比                                                 |
| `data.products.convViewToOrder`                           | number  | `4.8`                                                        | 展示转化率                                                   |
| `data.products.convToCartPdp`                             | number  | `14.96`                                                      | 加购率                                                       |
| `data.products.returnCancellationRate`                    | number  | `45.2`                                                       | 退货取消率                                                   |
| `data.products.orderConversionRate`                       | number  | `209.8`                                                      | 订单转化率                                                   |
| `data.products.views`                                     | number  | `7311433`                                                    | 展示总量                                                     |
| `data.products.missedRevenue`                             | number  | `0`                                                          | 错失销售额                                                   |
| `data.hasNextPage`                                        | boolean | `true`                                                       | 是否有下一页                                                 |

### 错误响应

| 状态码 | 说明             | 示例                                                 |
| :----- | :--------------- | :--------------------------------------------------- |
| `500`  | 失败             | `{ "code": 500, "msg": "Server error" }`             |
| `401`  | 未授权           | `{ "code": 401, "msg": "Unauthorized" }`             |
| `429`  | 请求过多         | `{ "code": 429, "msg": "Too Many Requests" }`        |
| `403`  | 无权限           | `{ "code": 403, "msg": "Forbidden" }`                |
| `200`  | API Key 积分耗尽 | `{ "code": 8000, "msg": "Api Key limit exhausted" }` |



## Ozon 查店铺品牌

POST/open-api/shop/detail/brand/search/ozon

按店铺 ID 查询 Ozon 店铺的品牌维度销量、销售额、增长率及品牌统计指标，支持分页、筛选和排序；第一页额外返回品牌销售额/销量 Top 列表、汇总和占比。

试一试

### Header 参数

| 参数            | 类型   | 必填 | 示例               | 说明    |
| :-------------- | :----- | :--- | :----------------- | :------ |
| `Authorization` | string | 是   | `Bearer {Api Key}` | API Key |

### Body 参数

| 参数                     | 类型    | 必填 | 示例            | 说明                                                         |
| :----------------------- | :------ | :--- | :-------------- | :----------------------------------------------------------- |
| `id`                     | integer | 是   | `118364`        | 店铺 ID                                                      |
| `date`                   | string  | 否   | `2026-07-01`    | 查询月份参数，可不传；传值时格式为 yyyy-MM-dd 且必须为每月 1 日，查询上一个自然月的数据。例如传 2026-07-01，实际查询 2026 年 6 月数据。 |
| `brand`                  | object  | 否   | `-`             | 品牌筛选                                                     |
| `brand.type`             | integer | 否   | `0`             | 品牌筛选类型：0 包含，1 排除，2 无品牌                       |
| `brand.brandName`        | array   | 否   | `-`             | 品牌名称数组                                                 |
| `brand.brandId`          | array   | 否   | `-`             | 品牌 ID 数组                                                 |
| `products`               | object  | 否   | `-`             | 商品数                                                       |
| `products.min`           | integer | 否   | `-`             | 最小商品数                                                   |
| `products.max`           | integer | 否   | `-`             | 最大商品数                                                   |
| `monthlySales`           | object  | 否   | `-`             | 销量                                                         |
| `monthlySales.min`       | integer | 否   | `-`             | 最小销量                                                     |
| `monthlySales.max`       | integer | 否   | `-`             | 最大销量                                                     |
| `monthlySalesRate`       | object  | 否   | `-`             | 销量增长率                                                   |
| `monthlySalesRate.min`   | number  | 否   | `-`             | 最小销量增长率                                               |
| `monthlySalesRate.max`   | number  | 否   | `-`             | 最大销量增长率                                               |
| `monthlyRevenue`         | object  | 否   | `-`             | 销售额                                                       |
| `monthlyRevenue.min`     | number  | 否   | `-`             | 最小销售额                                                   |
| `monthlyRevenue.max`     | number  | 否   | `-`             | 最大销售额                                                   |
| `monthlyRevenueRate`     | object  | 否   | `-`             | 销售额增长率                                                 |
| `monthlyRevenueRate.min` | number  | 否   | `-`             | 最小销售额增长率                                             |
| `monthlyRevenueRate.max` | number  | 否   | `-`             | 最大销售额增长率                                             |
| `page`                   | object  | 是   | `-`             | 分页参数                                                     |
| `page.pageNumber`        | integer | 是   | `1`             | 页码，从 1 开始                                              |
| `page.pageSize`          | integer | 是   | `20`            | 分页每页条数，最大100                                        |
| `page.orders`            | array   | 否   | `-`             | 排序规则数组                                                 |
| `page.orders.field`      | string  | 否   | `totalRevenues` | 排序字段，支持：products, totalSales, totalRevenues, salesRate, revenueRate |
| `page.orders.direction`  | string  | 否   | `DESC`          | 排序方向：DESC 倒序，ASC 正序                                |

### 请求体

Request Body复制

```
{
  "id": 118364,
  "date": null,
  "brand": {
    "type": 0,
    "brandName": [],
    "brandId": []
  },
  "products": {
    "min": null,
    "max": null
  },
  "monthlySales": {
    "min": null,
    "max": null
  },
  "monthlySalesRate": {
    "min": null,
    "max": null
  },
  "monthlyRevenue": {
    "min": null,
    "max": null
  },
  "monthlyRevenueRate": {
    "min": null,
    "max": null
  },
  "page": {
    "pageNumber": 1,
    "pageSize": 20,
    "orders": [
      {
        "field": "totalRevenues",
        "direction": "DESC"
      }
    ]
  }
}
```

### 请求示例

cURL复制

```
curl "http://api.seerfar.cn/open-api/shop/detail/brand/search/ozon" \
  -X POST \
  -H "Authorization: Bearer <platform_api_key>" \
  -H "Content-Type: application/json" \
  -d '{"id":7,"date":null,"brand":{"type":0,"brandName":[],"brandId":[]},"products":{"min":null,"max":null},"monthlySales":{"min":null,"max":null},"monthlySalesRate":{"min":null,"max":null},"monthlyRevenue":{"min":null,"max":null},"monthlyRevenueRate":{"min":null,"max":null},"page":{"pageNumber":1,"pageSize":20,"orders":[{"field":"totalRevenues","direction":"DESC"}]}}'
```

### 响应示例

JSON复制

```
{
  "code": 200,
  "msg": "SUCCESS",
  "data": {
    "brands": {
      "records": [
        {
          "id": 33321059,
          "totalRevenues": 124187644,
          "totalSales": 75246,
          "revenueRate": 11,
          "salesRate": 7,
          "brandInfo": {
            "brandId": 33321059,
            "brandName": "SvetoCopy",
            "thumbnailUrl": "https://ir.ozone.ru/s3/brand/svetocopy.jpg"
          },
          "products": 18,
          "avgPrice": 1650.41,
          "avgRevenue": 6899313.56,
          "avgSales": 4180,
          "avgRating": 4.8,
          "avgReviewCount": 100.5,
          "productsWithSales": 16,
          "sellers": 1,
          "conversionSharing": 72.35,
          "returnCancellationRate": 3.5
        }
      ],
      "total": 1,
      "size": 20,
      "current": 1,
      "currentSize": 1,
      "totalPages": 1,
      "orders": [
        {
          "field": "totalRevenues",
          "direction": "DESC"
        }
      ]
    },
    "top": {
      "revenues": [
        {
          "id": 33321059,
          "name": "SvetoCopy",
          "quantity": 124187644,
          "scopeShare": 100,
          "topShare": 100
        }
      ],
      "sales": [
        {
          "id": 33321059,
          "name": "SvetoCopy",
          "quantity": 75246,
          "scopeShare": 100,
          "topShare": 100
        }
      ],
      "total": 1,
      "totalRevenue": 124187644,
      "totalSales": 75246,
      "revenueShareTop10": 100,
      "salesShareTop10": 100
    }
  }
}
```

### 响应字段

| 字段                                         | 类型    | 示例                            | 说明                                                         |
| :------------------------------------------- | :------ | :------------------------------ | :----------------------------------------------------------- |
| `code`                                       | integer | `200`                           | 业务状态码                                                   |
| `msg`                                        | string  | `SUCCESS`                       | 响应消息                                                     |
| `data.brands`                                | object  | `-`                             | 分页数据                                                     |
| `data.brands.records`                        | array   | `-`                             | 当前页记录                                                   |
| `data.brands.total`                          | integer | `1`                             | 记录总数                                                     |
| `data.brands.size`                           | integer | `20`                            | 每页条数                                                     |
| `data.brands.current`                        | integer | `1`                             | 当前页码                                                     |
| `data.brands.currentSize`                    | integer | `1`                             | 当前页记录数                                                 |
| `data.brands.totalPages`                     | integer | `1`                             | 总页数                                                       |
| `data.brands.orders`                         | array   | `-`                             | 实际排序规则                                                 |
| `data.brands.orders.field`                   | string  | `totalRevenues`                 | 排序字段                                                     |
| `data.brands.orders.direction`               | string  | `DESC`                          | 排序方向                                                     |
| `data.brands.records.id`                     | string  | `-`                             | 分组 ID                                                      |
| `data.brands.records.totalRevenues`          | number  | `124187644`                     | 销售额                                                       |
| `data.brands.records.totalSales`             | integer | `75246`                         | 销量                                                         |
| `data.brands.records.revenueRate`            | number  | `11`                            | 销售额增长率                                                 |
| `data.brands.records.salesRate`              | number  | `7`                             | 销量增长率                                                   |
| `data.brands.records.products`               | integer | `18`                            | 商品数                                                       |
| `data.brands.records.avgPrice`               | number  | `1650.41`                       | 当前查询范围内销售额 Top100 商品的平均价格                   |
| `data.brands.records.avgRevenue`             | number  | `6899313.56`                    | 当前查询范围内热销商品的平均销售额                           |
| `data.brands.records.avgSales`               | integer | `4180`                          | 当前查询范围内热销商品的平均销量                             |
| `data.brands.records.avgRating`              | number  | `4.8`                           | 当前查询范围内热销商品的平均评分                             |
| `data.brands.records.avgReviewCount`         | number  | `100.5`                         | 当前查询范围内热销商品的平均评论数                           |
| `data.brands.records.productsWithSales`      | integer | `16`                            | 当前查询范围内有销量商品数量                                 |
| `data.brands.records.sellers`                | integer | `1`                             | 当前查询范围内有效店铺数                                     |
| `data.brands.records.conversionSharing`      | number  | `72.35`                         | 当前查询范围内品牌销售额 Top10 / Top100 的百分比，范围 0～100 |
| `data.brands.records.returnCancellationRate` | number  | `3.5`                           | Ozon 当前查询范围内销售额 Top100 商品的平均退回取消率；源数据为 null 时省略 |
| `data.brands.records.brandInfo`              | object  | `-`                             | 品牌信息                                                     |
| `data.brands.records.brandInfo.brandId`      | integer | `33321059`                      | 品牌 ID                                                      |
| `data.brands.records.brandInfo.brandName`    | string  | `SvetoCopy`                     | 品牌名称                                                     |
| `data.brands.records.brandInfo.thumbnailUrl` | string  | `https://example.com/brand.jpg` | 品牌缩略图 URL                                               |
| `data.top`                                   | object  | `-`                             | 品牌销售额/销量 Top 数据，仅在 pageNumber=1 时返回           |
| `data.top.total`                             | integer | `1`                             | 当前查询范围内的有效品牌总数；源数据为 null 时省略           |
| `data.top.totalRevenue`                      | number  | `124187644`                     | 当前查询范围内的总销售额；源数据为 null 时省略               |
| `data.top.totalSales`                        | number  | `75246`                         | 当前查询范围内的总销量；源数据为 null 时省略                 |
| `data.top.revenueShareTop10`                 | number  | `100`                           | 当前查询范围内 Top10 销售额占比，范围 0～100；源数据为 null 时省略 |
| `data.top.salesShareTop10`                   | number  | `100`                           | 当前查询范围内 Top10 销量占比，范围 0～100；源数据为 null 时省略 |
| `data.top.revenues`                          | array   | `-`                             | 销售额 Top 列表                                              |
| `data.top.revenues.id`                       | string  | `-`                             | 品牌 ID                                                      |
| `data.top.revenues.name`                     | string  | `-`                             | 品牌名称                                                     |
| `data.top.revenues.quantity`                 | number  | `124187644`                     | 销售额                                                       |
| `data.top.revenues.scopeShare`               | number  | `100`                           | 占当前查询范围总销售额的百分比，范围 0～100；源数据为 null 时省略 |
| `data.top.revenues.topShare`                 | number  | `100`                           | 相对本销售额榜第一名的百分比，范围 0～100，用于梯形图；源数据为 null 时省略 |
| `data.top.sales`                             | array   | `-`                             | 销量 Top 列表                                                |
| `data.top.sales.id`                          | string  | `-`                             | 品牌 ID                                                      |
| `data.top.sales.name`                        | string  | `-`                             | 品牌名称                                                     |
| `data.top.sales.quantity`                    | integer | `75246`                         | 销量                                                         |
| `data.top.sales.scopeShare`                  | number  | `100`                           | 占当前查询范围总销量的百分比，范围 0～100；源数据为 null 时省略 |
| `data.top.sales.topShare`                    | number  | `100`                           | 相对本销量榜第一名的百分比，范围 0～100，用于梯形图；源数据为 null 时省略 |

### 错误响应

| 状态码 | 说明             | 示例                                                 |
| :----- | :--------------- | :--------------------------------------------------- |
| `500`  | 失败             | `{ "code": 500, "msg": "Server error" }`             |
| `401`  | 未授权           | `{ "code": 401, "msg": "Unauthorized" }`             |
| `429`  | 请求过多         | `{ "code": 429, "msg": "Too Many Requests" }`        |
| `403`  | 无权限           | `{ "code": 403, "msg": "Forbidden" }`                |
| `200`  | API Key 积分耗尽 | `{ "code": 8000, "msg": "Api Key limit exhausted" }` |

品牌统计指标按当前查询范围返回；data.top 仅在 page.pageNumber=1 时返回。WB 的 totalProducts、brandInfo.totalProducts，以及 Ozon 的 returnCancellationRate 按平台提供；这些字段和新增 Top 汇总、占比字段在源数据为 null 时省略，数值 0 保留。

## Ozon 查店铺类目

POST/open-api/shop/detail/category/search/ozon

按店铺 ID 查询 Ozon 店铺的类目维度销量、销售额及增长率，支持分页、筛选和排序；第一页额外返回类目销售额/销量 Top 数据。

试一试

### Header 参数

| 参数            | 类型   | 必填 | 示例               | 说明    |
| :-------------- | :----- | :--- | :----------------- | :------ |
| `Authorization` | string | 是   | `Bearer {Api Key}` | API Key |

### Body 参数

| 参数                     | 类型    | 必填 | 示例            | 说明                                                         |
| :----------------------- | :------ | :--- | :-------------- | :----------------------------------------------------------- |
| `id`                     | integer | 是   | `118364`        | 店铺 ID                                                      |
| `date`                   | string  | 否   | `2026-07-01`    | 查询月份参数，可不传；传值时格式为 yyyy-MM-dd 且必须为每月 1 日，查询上一个自然月的数据。例如传 2026-07-01，实际查询 2026 年 6 月数据。 |
| `categoryIds`            | array   | 否   | `-`             | 类目 ID 数组                                                 |
| `avgPrice`               | object  | 否   | `-`             | 平均价格                                                     |
| `avgPrice.min`           | number  | 否   | `-`             | 最小平均价格                                                 |
| `avgPrice.max`           | number  | 否   | `-`             | 最大平均价格                                                 |
| `products`               | object  | 否   | `-`             | 商品数                                                       |
| `products.min`           | integer | 否   | `-`             | 最小商品数                                                   |
| `products.max`           | integer | 否   | `-`             | 最大商品数                                                   |
| `monthlySales`           | object  | 否   | `-`             | 销量                                                         |
| `monthlySales.min`       | integer | 否   | `-`             | 最小销量                                                     |
| `monthlySales.max`       | integer | 否   | `-`             | 最大销量                                                     |
| `monthlySalesRate`       | object  | 否   | `-`             | 销量增长率                                                   |
| `monthlySalesRate.min`   | number  | 否   | `-`             | 最小销量增长率                                               |
| `monthlySalesRate.max`   | number  | 否   | `-`             | 最大销量增长率                                               |
| `monthlyRevenue`         | object  | 否   | `-`             | 销售额                                                       |
| `monthlyRevenue.min`     | number  | 否   | `-`             | 最小销售额                                                   |
| `monthlyRevenue.max`     | number  | 否   | `-`             | 最大销售额                                                   |
| `monthlyRevenueRate`     | object  | 否   | `-`             | 销售额增长率                                                 |
| `monthlyRevenueRate.min` | number  | 否   | `-`             | 最小销售额增长率                                             |
| `monthlyRevenueRate.max` | number  | 否   | `-`             | 最大销售额增长率                                             |
| `page`                   | object  | 是   | `-`             | 分页参数                                                     |
| `page.pageNumber`        | integer | 是   | `1`             | 页码，从 1 开始                                              |
| `page.pageSize`          | integer | 是   | `20`            | 分页每页条数，最大100                                        |
| `page.orders`            | array   | 否   | `-`             | 排序规则数组                                                 |
| `page.orders.field`      | string  | 否   | `totalRevenues` | 排序字段，支持：products, avgPrice, totalSales, totalRevenues, salesRate, revenueRate |
| `page.orders.direction`  | string  | 否   | `DESC`          | 排序方向：DESC 倒序，ASC 正序                                |

### 请求体

Request Body复制

```
{
  "id": 118364,
  "date": null,
  "categoryIds": [],
  "avgPrice": {
    "min": null,
    "max": null
  },
  "products": {
    "min": null,
    "max": null
  },
  "monthlySales": {
    "min": null,
    "max": null
  },
  "monthlySalesRate": {
    "min": null,
    "max": null
  },
  "monthlyRevenue": {
    "min": null,
    "max": null
  },
  "monthlyRevenueRate": {
    "min": null,
    "max": null
  },
  "page": {
    "pageNumber": 1,
    "pageSize": 20,
    "orders": [
      {
        "field": "totalRevenues",
        "direction": "DESC"
      }
    ]
  }
}
```

### 请求示例

cURL复制

```
curl "http://api.seerfar.cn/open-api/shop/detail/category/search/ozon" \
  -X POST \
  -H "Authorization: Bearer <platform_api_key>" \
  -H "Content-Type: application/json" \
  -d '{"id":7,"date":null,"categoryIds":[],"avgPrice":{"min":null,"max":null},"products":{"min":null,"max":null},"monthlySales":{"min":null,"max":null},"monthlySalesRate":{"min":null,"max":null},"monthlyRevenue":{"min":null,"max":null},"monthlyRevenueRate":{"min":null,"max":null},"page":{"pageNumber":1,"pageSize":20,"orders":[{"field":"totalRevenues","direction":"DESC"}]}}'
```

### 响应示例

JSON复制

```
{
  "code": 200,
  "msg": "SUCCESS",
  "data": {
    "categories": {
      "records": [
        {
          "id": "17027492_17029017_91400",
          "totalRevenues": 124187644,
          "totalSales": 75246,
          "revenueRate": 11,
          "salesRate": 7,
          "categoryInfo": {
            "category": {
              "id": "17027492_17029017_91400",
              "enTitle": "Printer Paper",
              "title": "Бумага для принтера",
              "cnTitle": "打印纸",
              "pid": "17027492_17029017",
              "level": 3,
              "disabled": false,
              "crossBorderSellable": true,
              "children": null
            },
            "fullCategoryId": [
              "17027492",
              "17027492_17029017",
              "17027492_17029017_91400"
            ],
            "titlePath": "Канцелярские товары/Бумага/Бумага для принтера",
            "cnTitlePath": "办公用品/纸张/打印纸",
            "enTitlePath": "Office Supplies/Paper/Printer Paper"
          },
          "products": 18,
          "avgPrice": 1794
        }
      ],
      "total": 1,
      "size": 20,
      "current": 1,
      "currentSize": 1,
      "totalPages": 1,
      "orders": [
        {
          "field": "totalRevenues",
          "direction": "DESC"
        }
      ]
    },
    "top": {
      "revenues": [
        {
          "id": "17027492_17029017_91400",
          "name": "Бумага для принтера",
          "quantity": 124187644
        }
      ],
      "sales": [
        {
          "id": "17027492_17029017_91400",
          "name": "Бумага для принтера",
          "quantity": 75246
        }
      ]
    }
  }
}
```

### 响应字段

| 字段                                                         | 类型    | 示例                  | 说明                                               |
| :----------------------------------------------------------- | :------ | :-------------------- | :------------------------------------------------- |
| `code`                                                       | integer | `200`                 | 业务状态码                                         |
| `msg`                                                        | string  | `SUCCESS`             | 响应消息                                           |
| `data.categories`                                            | object  | `-`                   | 分页数据                                           |
| `data.categories.records`                                    | array   | `-`                   | 当前页记录                                         |
| `data.categories.total`                                      | integer | `1`                   | 记录总数                                           |
| `data.categories.size`                                       | integer | `20`                  | 每页条数                                           |
| `data.categories.current`                                    | integer | `1`                   | 当前页码                                           |
| `data.categories.currentSize`                                | integer | `1`                   | 当前页记录数                                       |
| `data.categories.totalPages`                                 | integer | `1`                   | 总页数                                             |
| `data.categories.orders`                                     | array   | `-`                   | 实际排序规则                                       |
| `data.categories.orders.field`                               | string  | `totalRevenues`       | 排序字段                                           |
| `data.categories.orders.direction`                           | string  | `DESC`                | 排序方向                                           |
| `data.categories.records.id`                                 | string  | `-`                   | 分组 ID                                            |
| `data.categories.records.totalRevenues`                      | number  | `124187644`           | 销售额                                             |
| `data.categories.records.totalSales`                         | integer | `75246`               | 销量                                               |
| `data.categories.records.revenueRate`                        | number  | `11`                  | 销售额增长率                                       |
| `data.categories.records.salesRate`                          | number  | `7`                   | 销量增长率                                         |
| `data.categories.records.products`                           | integer | `18`                  | 商品数                                             |
| `data.categories.records.avgPrice`                           | number  | `1794`                | 平均价格，单位卢布                                 |
| `data.categories.records.categoryInfo`                       | object  | `-`                   | 完整类目路径信息                                   |
| `data.categories.records.categoryInfo.category`              | object  | `-`                   | 当前类目信息                                       |
| `data.categories.records.categoryInfo.category.id`           | string  | `-`                   | 类目 ID                                            |
| `data.categories.records.categoryInfo.category.enTitle`      | string  | `Printer Paper`       | 类目英文名称                                       |
| `data.categories.records.categoryInfo.category.title`        | string  | `Бумага для принтера` | 类目俄文名称                                       |
| `data.categories.records.categoryInfo.category.cnTitle`      | string  | `打印纸`              | 类目中文名称                                       |
| `data.categories.records.categoryInfo.category.pid`          | string  | `-`                   | 父类目 ID                                          |
| `data.categories.records.categoryInfo.category.level`        | integer | `3`                   | 类目层级                                           |
| `data.categories.records.categoryInfo.category.disabled`     | boolean | `false`               | 类目是否禁用                                       |
| `data.categories.records.categoryInfo.category.crossBorderSellable` | boolean | `true`                | 是否支持跨境销售                                   |
| `data.categories.records.categoryInfo.category.children`     | array   | `-`                   | 子类目列表                                         |
| `data.categories.records.categoryInfo.fullCategoryId`        | array   | `-`                   | 完整类目 ID 路径                                   |
| `data.categories.records.categoryInfo.titlePath`             | string  | `-`                   | 完整俄文类目路径                                   |
| `data.categories.records.categoryInfo.cnTitlePath`           | string  | `-`                   | 完整中文类目路径                                   |
| `data.categories.records.categoryInfo.enTitlePath`           | string  | `-`                   | 完整英文类目路径                                   |
| `data.top`                                                   | object  | `-`                   | 类目销售额/销量 Top 数据，仅在 pageNumber=1 时返回 |
| `data.top.revenues`                                          | array   | `-`                   | 销售额 Top 列表                                    |
| `data.top.revenues.id`                                       | string  | `-`                   | 类目 ID                                            |
| `data.top.revenues.name`                                     | string  | `-`                   | 类目名称                                           |
| `data.top.revenues.quantity`                                 | number  | `124187644`           | 销售额                                             |
| `data.top.sales`                                             | array   | `-`                   | 销量 Top 列表                                      |
| `data.top.sales.id`                                          | string  | `-`                   | 类目 ID                                            |
| `data.top.sales.name`                                        | string  | `-`                   | 类目名称                                           |
| `data.top.sales.quantity`                                    | integer | `75246`               | 销量                                               |

### 错误响应

| 状态码 | 说明             | 示例                                                 |
| :----- | :--------------- | :--------------------------------------------------- |
| `500`  | 失败             | `{ "code": 500, "msg": "Server error" }`             |
| `401`  | 未授权           | `{ "code": 401, "msg": "Unauthorized" }`             |
| `429`  | 请求过多         | `{ "code": 429, "msg": "Too Many Requests" }`        |
| `403`  | 无权限           | `{ "code": 403, "msg": "Forbidden" }`                |
| `200`  | API Key 积分耗尽 | `{ "code": 8000, "msg": "Api Key limit exhausted" }` |



## Ozon 查竞品

POST/open-api/product/detail/search/ozon

按 SKU 和日期范围查询 Ozon 商品详情、销量、销售额、库存和趋势数据。

试一试

### Header 参数

| 参数            | 类型   | 必填 | 示例               | 说明    |
| :-------------- | :----- | :--- | :----------------- | :------ |
| `Authorization` | string | 是   | `Bearer {Api Key}` | API Key |

### Body 参数

| 参数        | 类型   | 必填 | 示例                                                         | 说明                   |
| :---------- | :----- | :--- | :----------------------------------------------------------- | :--------------------- |
| `sku`       | string | 是   | `175924376`                                                  | 商品sku                |
| `dateRange` | string | 否   | `past_30_days，past_7_days，past_60_days，past_90_days，past_180_days，past_365_days` | 日期范围, 默认为近30天 |

### 请求体

Request Body复制

```
{
  "sku": "175924376",
  "dateRange": "past_30_days"
}
```

### 请求示例

cURL复制

```
curl "http://api.seerfar.cn/open-api/product/detail/search/ozon" \
  -X POST \
  -H "Authorization: Bearer <platform_api_key>" \
  -H "Content-Type: application/json" \
  -d '{"sku":"175924376","dateRange":"past_30_days"}'
```

### 响应示例

JSON复制

```
{
  "code": 200,
  "msg": "SUCCESS",
  "data": {
    "product": {
      "sku": 175924376,
      "title": "Яндекс Плюс на 12 месяцев",
      "productUrl": "https://www.ozon.ru/product/175924376",
      "brandId": 13013270,
      "brandName": "Яндекс",
      "brandUrl": "https://www.ozon.ru/brand/13013270/",
      "imageUrls": [
        "https://ir.ozone.ru/s3/multimedia-1-a/wc500/9252960310.jpg",
        "https://ir.ozone.ru/s3/multimedia-1-l/wc500/9199921053.jpg",
        "https://ir.ozone.ru/s3/multimedia-1-h/wc500/9199921013.jpg",
        "https://ir.ozone.ru/s3/multimedia-1-5/wc500/9199921037.jpg",
        "https://ir.ozone.ru/s3/multimedia-1-q/wc500/9199921022.jpg"
      ],
      "sellerId": -4,
      "sellerName": "Ozon Россия",
      "fulfillment": [
        "OZON"
      ],
      "weight": null,
      "questionsAndAnswers": 2850,
      "upTime": 1591647267000,
      "upDays": 2107,
      "upMonths": 70,
      "price": 3490,
      "grossMargin": null,
      "reviewCount": 44514,
      "reviewRating": 4.9,
      "categoryInfo": {
        "category": {
          "id": "99999999_200001489_970727001",
          "enTitle": "Music Subscription",
          "title": "Подписка на музыку",
          "cnTitle": "订阅音乐",
          "pid": "99999999_200001489",
          "level": 3,
          "disabled": true,
          "crossBorderSellable": false,
          "children": null
        },
        "fullCategoryId": [
          "99999999",
          "99999999_200001489",
          "99999999_200001489_970727001"
        ],
        "titlePath": "Кино, музыка, видеоигры, софт > Цифровые товары > Подписка на музыку",
        "cnTitlePath": "电影、音乐、视频游戏、软件 > 数码商品 > 订阅音乐",
        "enTitlePath": "Movies, Music, Video Games, Software > Digital Products > Music Subscription"
      },
      "volume": null,
      "dimension": "",
      "variants": 4,
      "sessionCount": 490275,
      "sessionCountSearch": 186055,
      "drr": 4.61,
      "convToCartSearch": 10.25,
      "discount": 15.5,
      "promoRevenueShare": 62.4,
      "convViewToOrder": 4.8,
      "convToCartPdp": 12.43,
      "returnCancellationRate": null,
      "orderConversionRate": 67.2,
      "sellerType": 0
    },
    "totalSales": 40963,
    "totalRevenue": 142960870,
    "dailySales": 1365,
    "stock": 9999,
    "startDate": "2026-02-14",
    "endDate": "2026-03-15",
    "categoryRanks": [
      {
        "date": "2026-02",
        "rank": 1,
        "count": 21
      },
      {
        "date": "2026-03-16",
        "rank": 1,
        "count": 23
      }
    ],
    "salesTrendVOList": [
      {
        "date": "2026-02-14",
        "sales": 0,
        "revenue": 0,
        "price": 3490,
        "reviewCount": 44513,
        "reviewRating": 4.9,
        "stock": 9999
      },
      {
        "date": "2026-02-15",
        "sales": 0,
        "revenue": 0,
        "price": 3490,
        "reviewCount": 44513,
        "reviewRating": 4.9,
        "stock": 9999
      }
    ]
  }
}
```

### 响应字段

| 字段                                                     | 类型    | 示例                                                         | 说明                                                         |
| :------------------------------------------------------- | :------ | :----------------------------------------------------------- | :----------------------------------------------------------- |
| `code`                                                   | number  | `200`                                                        | 状态码                                                       |
| `msg`                                                    | string  | `SUCCESS`                                                    | 返回文字描述                                                 |
| `data`                                                   | object  | `-`                                                          | 返回数据                                                     |
| `data.product`                                           | object  | `-`                                                          | 商品数据                                                     |
| `data.product.sku`                                       | number  | `175924376`                                                  | 商品sku                                                      |
| `data.product.title`                                     | string  | `Яндекс Плюс на 12 месяцев`                                  | 商品标题                                                     |
| `data.product.productUrl`                                | string  | `https://www.ozon.ru/product/175924376`                      | 商品url                                                      |
| `data.product.brandId`                                   | number  | `13013270`                                                   | 品牌id                                                       |
| `data.product.brandName`                                 | string  | `Яндекс`                                                     | 品牌名称                                                     |
| `data.product.brandUrl`                                  | string  | `https://www.ozon.ru/brand/13013270/`                        | 品牌链接                                                     |
| `data.product.imageUrls`                                 | array   | `-`                                                          | 商品图片url                                                  |
| `data.product.sellerId`                                  | number  | `-4`                                                         | 卖家id                                                       |
| `data.product.sellerName`                                | string  | `Ozon Россия`                                                | 卖家名称                                                     |
| `data.product.fulfillment`                               | array   | `-`                                                          | 配送方式                                                     |
| `data.product.weight`                                    | number  | `123`                                                        | 商品重量，单位g                                              |
| `data.product.questionsAndAnswers`                       | number  | `2850`                                                       | qa                                                           |
| `data.product.upTime`                                    | number  | `1591647267000`                                              | 上架时间（毫秒时间戳）                                       |
| `data.product.upDays`                                    | number  | `2107`                                                       | 上架天数                                                     |
| `data.product.upMonths`                                  | number  | `70`                                                         | 上架月数                                                     |
| `data.product.price`                                     | number  | `3490`                                                       | 价格                                                         |
| `data.product.grossMargin`                               | number  | `56.5`                                                       | 毛利率                                                       |
| `data.product.reviewCount`                               | number  | `44514`                                                      | 评论数                                                       |
| `data.product.reviewRating`                              | number  | `4.9`                                                        | 评分                                                         |
| `data.product.categoryInfo`                              | object  | `-`                                                          | 类目信息                                                     |
| `data.product.categoryInfo.category`                     | object  | `-`                                                          | 类目信息                                                     |
| `data.product.categoryInfo.category.id`                  | string  | `99999999_200001489_970727001`                               | 类目id（seerfar自定义）                                      |
| `data.product.categoryInfo.category.enTitle`             | string  | `Music Subscription`                                         | 类目英文名称                                                 |
| `data.product.categoryInfo.category.title`               | string  | `Подписка на музыку`                                         | 类目俄文名称                                                 |
| `data.product.categoryInfo.category.cnTitle`             | string  | `订阅音乐`                                                   | 类目中文名称                                                 |
| `data.product.categoryInfo.category.pid`                 | string  | `99999999_200001489`                                         | 父类目id                                                     |
| `data.product.categoryInfo.category.level`               | number  | `3`                                                          | 类目层级                                                     |
| `data.product.categoryInfo.category.disabled`            | boolean | `true`                                                       | 类目是否可用                                                 |
| `data.product.categoryInfo.category.crossBorderSellable` | boolean | `false`                                                      | 是否跨境可售                                                 |
| `data.product.categoryInfo.category.children`            | array   | `-`                                                          | 子类目信息                                                   |
| `data.product.categoryInfo.fullCategoryId`               | array   | `-`                                                          | 类目id路径                                                   |
| `data.product.categoryInfo.titlePath`                    | string  | `Кино, музыка, видеоигры, софт > Цифровые товары > Подписка на музыку` | 俄文类目路径                                                 |
| `data.product.categoryInfo.cnTitlePath`                  | string  | `电影、音乐、视频游戏、软件 > 数码商品 > 订阅音乐`           | 中文类目路径                                                 |
| `data.product.categoryInfo.enTitlePath`                  | string  | `Movies, Music, Video Games, Software > Digital Products > Music Subscription` | 英文类目路径                                                 |
| `data.product.volume`                                    | number  | `25.684`                                                     | 体积，单位L                                                  |
| `data.product.dimension`                                 | string  | `432×356×167`                                                | 尺寸，单位毫米                                               |
| `data.product.variants`                                  | number  | `4`                                                          | 变体数                                                       |
| `data.product.sessionCount`                              | number  | `490275`                                                     | 产品卡浏览量                                                 |
| `data.product.sessionCountSearch`                        | number  | `186055`                                                     | 曝光量                                                       |
| `data.product.drr`                                       | number  | `4.61`                                                       | 广告费用份额                                                 |
| `data.product.convToCartSearch`                          | number  | `10.25`                                                      | 搜索加购率                                                   |
| `data.product.discount`                                  | number  | `15.5`                                                       | 平均折扣                                                     |
| `data.product.promoRevenueShare`                         | number  | `62.4`                                                       | 促销销售占比                                                 |
| `data.product.convViewToOrder`                           | number  | `4.8`                                                        | 展示转化率                                                   |
| `data.product.convToCartPdp`                             | number  | `12.43`                                                      | 加购率                                                       |
| `data.product.returnCancellationRate`                    | number  | `45.2`                                                       | 退货取消率                                                   |
| `data.product.orderConversionRate`                       | number  | `67.2`                                                       | 订单转化率                                                   |
| `data.product.sellerType`                                | number  | `0`                                                          | 卖家类型，0：本土，1：跨境                                   |
| `data.totalSales`                                        | number  | `40963`                                                      | 销量                                                         |
| `data.totalRevenue`                                      | number  | `142960870`                                                  | 销售额                                                       |
| `data.dailySales`                                        | number  | `1365`                                                       | 平均每天销量                                                 |
| `data.stock`                                             | number  | `9999`                                                       | 库存                                                         |
| `data.startDate`                                         | string  | `2026-02-14`                                                 | 起始日期                                                     |
| `data.endDate`                                           | string  | `2026-03-15`                                                 | 结束                                                         |
| `data.categoryRanks`                                     | array   | `-`                                                          | 商品类目排名                                                 |
| `data.categoryRanks.date`                                | string  | `2025-10`                                                    | 日期                                                         |
| `data.categoryRanks.rank`                                | number  | `1`                                                          | 类目排名；当 rank=5001 时，表示该商品的类目排名在 5000 名以外，5000 名以外不返回具体排名 |
| `data.categoryRanks.count`                               | number  | `23`                                                         | 类目商品数                                                   |
| `data.salesTrendVOList`                                  | array   | `-`                                                          | 每天销售数据                                                 |
| `data.salesTrendVOList.date`                             | string  | `2026-02-14`                                                 | 日期时间                                                     |
| `data.salesTrendVOList.sales`                            | number  | `0`                                                          | 天销量                                                       |
| `data.salesTrendVOList.revenue`                          | number  | `0`                                                          | 天销售额                                                     |
| `data.salesTrendVOList.price`                            | number  | `3490`                                                       | 价格                                                         |
| `data.salesTrendVOList.reviewCount`                      | number  | `44513`                                                      | 评论数                                                       |
| `data.salesTrendVOList.reviewRating`                     | number  | `4.9`                                                        | 评分                                                         |
| `data.salesTrendVOList.stock`                            | number  | `9999`                                                       | 库存                                                         |

### 错误响应

| 状态码 | 说明             | 示例                                                 |
| :----- | :--------------- | :--------------------------------------------------- |
| `500`  | 失败             | `{ "code": 500, "msg": "Server error" }`             |
| `401`  | 未授权           | `{ "code": 401, "msg": "Unauthorized" }`             |
| `429`  | 请求过多         | `{ "code": 429, "msg": "Too Many Requests" }`        |
| `403`  | 无权限           | `{ "code": 403, "msg": "Forbidden" }`                |
| `200`  | API Key 积分耗尽 | `{ "code": 8000, "msg": "Api Key limit exhausted" }` |





## Ozon 查相似商品

POST/open-api/product/detail/similar/ozon

按目标商品 SKU 查询 Ozon 相似商品及其销量、销售额、价格、库存和评价等指标。

试一试

### Header 参数

| 参数            | 类型   | 必填 | 示例               | 说明    |
| :-------------- | :----- | :--- | :----------------- | :------ |
| `Authorization` | string | 是   | `Bearer {Api Key}` | API Key |

### Body 参数

| 参数  | 类型    | 必填 | 示例        | 说明         |
| :---- | :------ | :--- | :---------- | :----------- |
| `sku` | integer | 是   | `175924376` | 目标商品 SKU |

### 请求体

Request Body复制

```
{
  "sku": 175924376
}
```

### 请求示例

cURL复制

```
curl "http://api.seerfar.cn/open-api/product/detail/similar/ozon" \
  -X POST \
  -H "Authorization: Bearer <platform_api_key>" \
  -H "Content-Type: application/json" \
  -d '{"sku":175924376}'
```

### 响应示例

JSON复制

```
{
  "code": 200,
  "msg": "SUCCESS",
  "data": [
    {
      "sku": 175924376,
      "sales": 40963,
      "revenue": 142960870,
      "stock": 9999,
      "title": "Яндекс Плюс на 12 месяцев",
      "brandId": 13013270,
      "brandName": "Яндекс",
      "imageUrl": "https://ir.ozone.ru/s3/multimedia-1-a/wc300/9252960310.jpg",
      "sellerId": -4,
      "sellerName": "Ozon Россия",
      "fulfillment": [
        "OZON"
      ],
      "questionsAndAnswers": 2850,
      "upTime": 1591647267000,
      "upDays": 2107,
      "upMonths": 70,
      "price": 3490,
      "grossMargin": null,
      "reviewCount": 44514,
      "reviewRating": 4.9,
      "categoryInfo": {
        "category": {
          "id": "99999999_200001489_970727001",
          "enTitle": "Music Subscription",
          "title": "Подписка на музыку",
          "cnTitle": "订阅音乐",
          "pid": "99999999_200001489",
          "level": 3,
          "disabled": true,
          "crossBorderSellable": false,
          "children": null
        },
        "fullCategoryId": [
          "99999999",
          "99999999_200001489",
          "99999999_200001489_970727001"
        ],
        "titlePath": "Кино, музыка, видеоигры, софт > Цифровые товары > Подписка на музыку",
        "cnTitlePath": "电影、音乐、视频游戏、软件 > 数码商品 > 订阅音乐",
        "enTitlePath": "Movies, Music, Video Games, Software > Digital Products > Music Subscription"
      },
      "volume": null,
      "variants": 4,
      "sellerType": 0
    }
  ]
}
```

### 响应字段

| 字段                                             | 类型    | 示例        | 说明                                         |
| :----------------------------------------------- | :------ | :---------- | :------------------------------------------- |
| `code`                                           | integer | `200`       | 业务状态码                                   |
| `msg`                                            | string  | `SUCCESS`   | 响应消息                                     |
| `data`                                           | array   | `-`         | 相似商品列表，最多返回 21 条（包含目标商品） |
| `data.sku`                                       | integer | `175924376` | 商品 SKU                                     |
| `data.sales`                                     | integer | `-`         | 近 30 天销量                                 |
| `data.revenue`                                   | number  | `-`         | 近 30 天销售额                               |
| `data.stock`                                     | integer | `-`         | 库存                                         |
| `data.title`                                     | string  | `-`         | 商品标题                                     |
| `data.brandId`                                   | integer | `-`         | 品牌 ID                                      |
| `data.brandName`                                 | string  | `-`         | 品牌名称                                     |
| `data.imageUrl`                                  | string  | `-`         | 商品图片 URL                                 |
| `data.sellerId`                                  | integer | `-`         | 卖家 ID                                      |
| `data.sellerName`                                | string  | `-`         | 卖家名称                                     |
| `data.fulfillment`                               | array   | `-`         | 配送方式                                     |
| `data.questionsAndAnswers`                       | integer | `-`         | 问答数                                       |
| `data.upTime`                                    | integer | `-`         | 上架时间（毫秒时间戳）                       |
| `data.upDays`                                    | integer | `-`         | 上架天数                                     |
| `data.upMonths`                                  | integer | `-`         | 上架月数                                     |
| `data.price`                                     | number  | `-`         | 最新价格，单位卢布                           |
| `data.grossMargin`                               | number  | `-`         | 毛利率                                       |
| `data.reviewCount`                               | integer | `-`         | 评价数                                       |
| `data.reviewRating`                              | number  | `-`         | 评价星级                                     |
| `data.categoryInfo`                              | object  | `-`         | 类目信息                                     |
| `data.categoryInfo.category`                     | object  | `-`         | 当前类目信息                                 |
| `data.categoryInfo.category.id`                  | string  | `-`         | 类目 ID                                      |
| `data.categoryInfo.category.enTitle`             | string  | `-`         | 类目英文名称                                 |
| `data.categoryInfo.category.title`               | string  | `-`         | 类目俄文名称                                 |
| `data.categoryInfo.category.cnTitle`             | string  | `-`         | 类目中文名称                                 |
| `data.categoryInfo.category.pid`                 | string  | `-`         | 父类目 ID                                    |
| `data.categoryInfo.category.level`               | integer | `2`         | 类目层级                                     |
| `data.categoryInfo.category.disabled`            | boolean | `false`     | 类目是否禁用                                 |
| `data.categoryInfo.category.crossBorderSellable` | boolean | `false`     | 是否支持跨境销售                             |
| `data.categoryInfo.category.children`            | array   | `-`         | 子类目列表                                   |
| `data.categoryInfo.fullCategoryId`               | array   | `-`         | 完整类目 ID 路径                             |
| `data.categoryInfo.titlePath`                    | string  | `-`         | 完整俄文类目路径                             |
| `data.categoryInfo.cnTitlePath`                  | string  | `-`         | 完整中文类目路径                             |
| `data.categoryInfo.enTitlePath`                  | string  | `-`         | 完整英文类目路径                             |
| `data.volume`                                    | number  | `-`         | 体积，单位 L                                 |
| `data.variants`                                  | integer | `-`         | 变体数                                       |
| `data.sellerType`                                | integer | `0`         | 卖家类型：0 本土，1 跨境                     |

### 错误响应

| 状态码 | 说明             | 示例                                                 |
| :----- | :--------------- | :--------------------------------------------------- |
| `500`  | 失败             | `{ "code": 500, "msg": "Server error" }`             |
| `401`  | 未授权           | `{ "code": 401, "msg": "Unauthorized" }`             |
| `429`  | 请求过多         | `{ "code": 429, "msg": "Too Many Requests" }`        |
| `403`  | 无权限           | `{ "code": 403, "msg": "Forbidden" }`                |
| `200`  | API Key 积分耗尽 | `{ "code": 8000, "msg": "Api Key limit exhausted" }` |





## Ozon 查变体特征

POST/open-api/product/detail/variations/characteristics/ozon

查询 Ozon 指定商品可用于变体筛选的特征字段。

试一试

### Header 参数

| 参数            | 类型   | 必填 | 示例               | 说明    |
| :-------------- | :----- | :--- | :----------------- | :------ |
| `Authorization` | string | 是   | `Bearer {Api Key}` | API Key |

### Body 参数

| 参数             | 类型    | 必填 | 示例        | 说明                                                         |
| :--------------- | :------ | :--- | :---------- | :----------------------------------------------------------- |
| `sku`            | integer | 是   | `175924376` | 目标商品 SKU                                                 |
| `clientLanguage` | string  | 否   | `zh-CN`     | 返回数据语言：zh-CN 中文、ru-RU 俄文、en-US 英文；不传时默认为 zh-CN |

### 请求体

Request Body复制

```
{
  "sku": 175924376,
  "clientLanguage": "zh-CN"
}
```

### 请求示例

cURL复制

```
curl "http://api.seerfar.cn/open-api/product/detail/variations/characteristics/ozon" \
  -X POST \
  -H "Authorization: Bearer <platform_api_key>" \
  -H "Content-Type: application/json" \
  -d '{"sku":175924376,"clientLanguage":"zh-CN"}'
```

### 响应示例

JSON复制

```
{
  "code": 200,
  "msg": "SUCCESS",
  "data": [
    {
      "sourceName": "Цвет",
      "name": "颜色"
    }
  ]
}
```

### 响应字段

| 字段              | 类型    | 示例      | 说明                                    |
| :---------------- | :------ | :-------- | :-------------------------------------- |
| `code`            | integer | `200`     | 业务状态码                              |
| `msg`             | string  | `SUCCESS` | 响应消息                                |
| `data`            | array   | `-`       | 可用于变体筛选的特征列表                |
| `data.sourceName` | string  | `Цвет`    | 原始特征名称；调用 Top 变体接口时传此值 |
| `data.name`       | string  | `颜色`    | 按当前语言展示的特征名称                |



## Ozon 查 Top 变体

POST/open-api/product/detail/variations/top/ozon

查询 Ozon 指定商品在某一特征维度下按销售额和销量排名的前 10 个变体特征值。

试一试

### Header 参数

| 参数            | 类型   | 必填 | 示例               | 说明    |
| :-------------- | :----- | :--- | :----------------- | :------ |
| `Authorization` | string | 是   | `Bearer {Api Key}` | API Key |

### Body 参数

| 参数             | 类型    | 必填 | 示例        | 说明                                                         |
| :--------------- | :------ | :--- | :---------- | :----------------------------------------------------------- |
| `sku`            | integer | 是   | `175924376` | 目标商品 SKU                                                 |
| `characteristic` | string  | 是   | `Цвет`      | 原始特征名称，应传变体特征接口返回的 sourceName              |
| `clientLanguage` | string  | 否   | `zh-CN`     | 返回数据语言：zh-CN 中文、ru-RU 俄文、en-US 英文；不传时默认为 zh-CN |

### 请求体

Request Body复制

```
{
  "sku": 175924376,
  "characteristic": "Цвет",
  "clientLanguage": "zh-CN"
}
```

### 请求示例

cURL复制

```
curl "http://api.seerfar.cn/open-api/product/detail/variations/top/ozon" \
  -X POST \
  -H "Authorization: Bearer <platform_api_key>" \
  -H "Content-Type: application/json" \
  -d '{"sku":175924376,"characteristic":"Цвет","clientLanguage":"zh-CN"}'
```

### 响应示例

JSON复制

```
{
  "code": 200,
  "msg": "SUCCESS",
  "data": {
    "revenues": [
      {
        "name": "Черный",
        "quantity": 785000
      },
      {
        "name": "Белый",
        "quantity": 463000
      }
    ],
    "sales": [
      {
        "name": "Черный",
        "quantity": 245
      },
      {
        "name": "Белый",
        "quantity": 138
      }
    ]
  }
}
```

### 响应字段

| 字段                     | 类型    | 示例      | 说明                         |
| :----------------------- | :------ | :-------- | :--------------------------- |
| `code`                   | integer | `200`     | 业务状态码                   |
| `msg`                    | string  | `SUCCESS` | 响应消息                     |
| `data.revenues`          | array   | `-`       | 按销售额排序的前 10 个特征值 |
| `data.revenues.name`     | string  | `Черный`  | 特征值                       |
| `data.revenues.quantity` | number  | `-`       | 销售额                       |
| `data.sales`             | array   | `-`       | 按销量排序的前 10 个特征值   |
| `data.sales.name`        | string  | `Черный`  | 特征值                       |
| `data.sales.quantity`    | integer | `-`       | 销量                         |



## Ozon 查商品变体

POST/open-api/product/detail/variations/search/ozon

分页查询 Ozon 指定商品的全部变体详情，包括特征、价格、销量、销售额和评价等信息。

试一试

### Header 参数

| 参数            | 类型   | 必填 | 示例               | 说明    |
| :-------------- | :----- | :--- | :----------------- | :------ |
| `Authorization` | string | 是   | `Bearer {Api Key}` | API Key |

### Body 参数

| 参数                    | 类型    | 必填 | 示例        | 说明                                                         |
| :---------------------- | :------ | :--- | :---------- | :----------------------------------------------------------- |
| `sku`                   | integer | 是   | `175924376` | 目标商品 SKU                                                 |
| `page`                  | object  | 是   | `-`         | 分页参数                                                     |
| `page.pageNumber`       | integer | 是   | `1`         | 页码，从 1 开始                                              |
| `page.pageSize`         | integer | 是   | `20`        | 每页条数                                                     |
| `page.isExpand`         | boolean | 否   | `false`     | 是否按变体特征值扩展排序；为 true 时 orders.field 应传变体特征的 sourceName |
| `page.orders`           | array   | 否   | `-`         | 排序规则数组                                                 |
| `page.orders.field`     | string  | 否   | `revenue`   | 排序字段；普通排序支持 price、upTime、sales、revenue、reviewCount、reviewRating，扩展排序传特征 sourceName |
| `page.orders.direction` | string  | 否   | `DESC`      | 排序方向：DESC 倒序，ASC 正序                                |
| `clientLanguage`        | string  | 否   | `zh-CN`     | 返回数据语言：zh-CN 中文、ru-RU 俄文、en-US 英文；不传时默认为 zh-CN |

### 请求体

Request Body复制

```
{
  "sku": 175924376,
  "clientLanguage": "zh-CN",
  "page": {
    "pageNumber": 1,
    "pageSize": 20,
    "isExpand": false,
    "orders": [
      {
        "field": "revenue",
        "direction": "DESC"
      }
    ]
  }
}
```

### 请求示例

cURL复制

```
curl "http://api.seerfar.cn/open-api/product/detail/variations/search/ozon" \
  -X POST \
  -H "Authorization: Bearer <platform_api_key>" \
  -H "Content-Type: application/json" \
  -d '{"sku":175924376,"clientLanguage":"zh-CN","page":{"pageNumber":1,"pageSize":20,"isExpand":false,"orders":[{"field":"revenue","direction":"DESC"}]}}'
```

### 响应示例

JSON复制

```
{
  "code": 200,
  "msg": "SUCCESS",
  "data": {
    "records": [
      {
        "characteristics": [
          {
            "sourceName": "Цвет",
            "name": "颜色",
            "value": "Черный"
          }
        ],
        "sku": 175924376,
        "price": 3490,
        "upTime": 1591647267000,
        "title": "Яндекс Плюс на 12 месяцев",
        "productUrl": "https://www.ozon.ru/product/175924376",
        "brandId": 13013270,
        "brandName": "Яндекс",
        "imageUrl": "https://ir.ozone.ru/s3/multimedia-1-a/wc300/9252960310.jpg",
        "sellerId": -4,
        "sellerName": "Ozon Россия",
        "sales": 40963,
        "revenue": 142960870,
        "reviewCount": 44514,
        "reviewRating": 4.9,
        "categoryInfo": {
          "category": {
            "id": "99999999_200001489_970727001",
            "enTitle": "Music Subscription",
            "title": "Подписка на музыку",
            "cnTitle": "订阅音乐",
            "pid": "99999999_200001489",
            "level": 3,
            "disabled": true,
            "crossBorderSellable": false,
            "children": null
          },
          "fullCategoryId": [
            "99999999",
            "99999999_200001489",
            "99999999_200001489_970727001"
          ],
          "titlePath": "Кино, музыка, видеоигры, софт > Цифровые товары > Подписка на музыку",
          "cnTitlePath": "电影、音乐、视频游戏、软件 > 数码商品 > 订阅音乐",
          "enTitlePath": "Movies, Music, Video Games, Software > Digital Products > Music Subscription"
        },
        "brandUrl": "https://www.ozon.ru/brand/13013270",
        "sessionCountSearch": 186055,
        "drr": 4.61,
        "convToCartPdp": 12.43,
        "returnCancellationRate": null,
        "orderConversionRate": 67.2,
        "sessionCount": 490275
      }
    ],
    "total": 1,
    "size": 20,
    "current": 1,
    "currentSize": 0,
    "totalPages": 1,
    "orders": null,
    "timeInterval": null
  }
}
```

### 响应字段

| 字段                                                     | 类型    | 示例        | 说明                     |
| :------------------------------------------------------- | :------ | :---------- | :----------------------- |
| `code`                                                   | integer | `200`       | 业务状态码               |
| `msg`                                                    | string  | `SUCCESS`   | 响应消息                 |
| `data.records`                                           | array   | `-`         | 当前页变体记录           |
| `data.total`                                             | integer | `-`         | 记录总数                 |
| `data.size`                                              | integer | `20`        | 每页条数                 |
| `data.current`                                           | integer | `1`         | 当前页码                 |
| `data.currentSize`                                       | integer | `0`         | 当前页记录数（已弃用）   |
| `data.totalPages`                                        | integer | `-`         | 总页数                   |
| `data.orders`                                            | array   | `-`         | 排序规则（已弃用）       |
| `data.timeInterval`                                      | object  | `-`         | 时间范围（已弃用）       |
| `data.records.characteristics`                           | array   | `-`         | 变体特征列表             |
| `data.records.characteristics.sourceName`                | string  | `Цвет`      | 原始特征名称             |
| `data.records.characteristics.name`                      | string  | `颜色`      | 按当前语言展示的特征名称 |
| `data.records.characteristics.value`                     | string  | `Черный`    | 当前变体的特征值         |
| `data.records.sku`                                       | integer | `175924376` | 变体商品 SKU             |
| `data.records.price`                                     | number  | `-`         | 价格，单位卢布           |
| `data.records.upTime`                                    | integer | `-`         | 上架时间（毫秒时间戳）   |
| `data.records.title`                                     | string  | `-`         | 商品标题                 |
| `data.records.productUrl`                                | string  | `-`         | 商品详情 URL             |
| `data.records.brandId`                                   | integer | `-`         | 品牌 ID                  |
| `data.records.brandName`                                 | string  | `-`         | 品牌名称                 |
| `data.records.imageUrl`                                  | string  | `-`         | 商品图片 URL             |
| `data.records.sellerId`                                  | integer | `-`         | 卖家 ID                  |
| `data.records.sellerName`                                | string  | `-`         | 卖家名称                 |
| `data.records.sales`                                     | integer | `-`         | 销量                     |
| `data.records.revenue`                                   | number  | `-`         | 销售额                   |
| `data.records.reviewCount`                               | integer | `-`         | 评价数                   |
| `data.records.reviewRating`                              | number  | `-`         | 评价星级                 |
| `data.records.categoryInfo`                              | object  | `-`         | 类目信息                 |
| `data.records.categoryInfo.category`                     | object  | `-`         | 当前类目信息             |
| `data.records.categoryInfo.category.id`                  | string  | `-`         | 类目 ID                  |
| `data.records.categoryInfo.category.enTitle`             | string  | `-`         | 类目英文名称             |
| `data.records.categoryInfo.category.title`               | string  | `-`         | 类目俄文名称             |
| `data.records.categoryInfo.category.cnTitle`             | string  | `-`         | 类目中文名称             |
| `data.records.categoryInfo.category.pid`                 | string  | `-`         | 父类目 ID                |
| `data.records.categoryInfo.category.level`               | integer | `2`         | 类目层级                 |
| `data.records.categoryInfo.category.disabled`            | boolean | `false`     | 类目是否禁用             |
| `data.records.categoryInfo.category.crossBorderSellable` | boolean | `false`     | 是否支持跨境销售         |
| `data.records.categoryInfo.category.children`            | array   | `-`         | 子类目列表               |
| `data.records.categoryInfo.fullCategoryId`               | array   | `-`         | 完整类目 ID 路径         |
| `data.records.categoryInfo.titlePath`                    | string  | `-`         | 完整俄文类目路径         |
| `data.records.categoryInfo.cnTitlePath`                  | string  | `-`         | 完整中文类目路径         |
| `data.records.categoryInfo.enTitlePath`                  | string  | `-`         | 完整英文类目路径         |
| `data.records.brandUrl`                                  | string  | `-`         | 品牌 URL                 |
| `data.records.sessionCountSearch`                        | integer | `-`         | 搜索曝光量               |
| `data.records.drr`                                       | number  | `-`         | 广告费用份额             |
| `data.records.convToCartPdp`                             | number  | `-`         | 加购率                   |
| `data.records.returnCancellationRate`                    | number  | `-`         | 退货取消率               |
| `data.records.orderConversionRate`                       | number  | `-`         | 订单转化率               |
| `data.records.sessionCount`                              | integer | `-`         | 浏览数                   |





## Ozon 月度销量趋势

POST/open-api/product/monthlySalesTrend/ozon

按商品 SKU 查询 Ozon 月度销量和销售额，返回按月份组织的数组。sku 必填且大于 0；销量或销售额为 null 表示暂无数据。

试一试

### Header 参数

| 参数            | 类型   | 必填 | 示例               | 说明    |
| :-------------- | :----- | :--- | :----------------- | :------ |
| `Authorization` | string | 是   | `Bearer {Api Key}` | API Key |

### Body 参数

| 参数  | 类型    | 必填 | 示例        | 说明                                |
| :---- | :------ | :--- | :---------- | :---------------------------------- |
| `sku` | integer | 是   | `175924376` | 商品 SKU（64 位整数），必填且大于 0 |

### 请求体

Request Body复制

```
{
  "sku": 175924376
}
```

### 请求示例

cURL复制

```
curl "http://api.seerfar.cn/open-api/product/monthlySalesTrend/ozon" \
  -X POST \
  -H "Authorization: Bearer <platform_api_key>" \
  -H "Content-Type: application/json" \
  -d '{"sku":175924376}'
```

### 响应示例

JSON复制

```
{
  "code": 200,
  "msg": "SUCCESS",
  "data": [
    {
      "date": "2026-09",
      "sale": 12,
      "revenue": 1234.56
    },
    {
      "date": "2026-08",
      "sale": null,
      "revenue": null
    }
  ]
}
```

### 响应字段

| 字段           | 类型            | 示例      | 说明                                               |
| :------------- | :-------------- | :-------- | :------------------------------------------------- |
| `code`         | integer         | `200`     | 业务状态码；下游业务错误码原样返回                 |
| `msg`          | string          | `SUCCESS` | 响应消息                                           |
| `data`         | array \| null   | `-`       | 月度销量趋势记录数组                               |
| `data.date`    | string          | `2026-09` | 月份，格式 yyyy-MM                                 |
| `data.sale`    | integer \| null | `12`      | 月销量（64 位整数）；null 表示暂无数据，字段仍保留 |
| `data.revenue` | number \| null  | `1234.56` | 月销售额；null 表示暂无数据，字段仍保留            |

### 错误响应

| 状态码 | 说明                             | 示例                                                 |
| :----- | :------------------------------- | :--------------------------------------------------- |
| `400`  | 参数错误：sku 必填且大于 0       | `{ "code": 400, "msg": "Bad Request" }`              |
| `500`  | 失败                             | `{ "code": 500, "msg": "Server error" }`             |
| `401`  | 未授权                           | `{ "code": 401, "msg": "Unauthorized" }`             |
| `429`  | 请求过多                         | `{ "code": 429, "msg": "Too Many Requests" }`        |
| `403`  | 无权限                           | `{ "code": 403, "msg": "Forbidden" }`                |
| `403`  | API Key 积分耗尽                 | `{ "code": 8000, "msg": "Api Key limit exhausted" }` |
| `200`  | 下游商品不存在（业务状态码透传） | `{ "code": 5001, "msg": "Product not exist" }`       |

单 API Key 限制为 3 次/3 秒，每个平台接口的全局限制为 10 次/秒，两个平台分别限流。

响应透传下游业务状态，请同时检查 HTTP 状态和 code。当前版本按 HTTP 状态处理扣费：HTTP 200 且 code 非 200 的业务失败仍会扣除 1 积分；HTTP 非 200 或调用异常时退回预扣积分。



## Ozon 查类目

POST/open-api/category/detail/search/ozon

按类目 ID、日期范围和分页参数查询 Ozon 类目商品、销量、销售额和排名数据。商品列表按照销售额倒序。

试一试

### Header 参数

| 参数            | 类型   | 必填 | 示例               | 说明    |
| :-------------- | :----- | :--- | :----------------- | :------ |
| `Authorization` | string | 是   | `Bearer {Api Key}` | API Key |

### Body 参数

| 参数                         | 类型    | 必填 | 示例                          | 说明                                                         |
| :--------------------------- | :------ | :--- | :---------------------------- | :----------------------------------------------------------- |
| `categoryId`                 | string  | 是   | `15621032_15621049_115951147` | 类目id。从类目文档中获取，文档链接：[Ozon类目](https://e1p7i0bkkue.feishu.cn/wiki/R2Nmwih5li76bdkv71ecJkBFnJg) |
| `date`                       | string  | 否   | `-`                           | 查询日期。仅能查询近1年的数据。查近30天数据时，不传该参数。查历史月份数据时，传参格式：yyyy-MM。例如：2026-02 |
| `reviewCount`                | object  | 否   | `-`                           | 评论数                                                       |
| `reviewCount.min`            | integer | 否   | `-`                           | 最小评论数                                                   |
| `reviewCount.max`            | integer | 否   | `-`                           | 最大评论数                                                   |
| `drr`                        | object  | 否   | `-`                           | 广告费用份额                                                 |
| `drr.min`                    | number  | 否   | `-`                           | 最小广告费用份额                                             |
| `drr.max`                    | number  | 否   | `-`                           | 最大广告费用份额                                             |
| `reviewRating`               | object  | 否   | `-`                           | 评分                                                         |
| `reviewRating.min`           | number  | 否   | `-`                           | 最小评分                                                     |
| `reviewRating.max`           | number  | 否   | `-`                           | 最大评分                                                     |
| `questionsAndAnswers`        | object  | 否   | `-`                           | qa                                                           |
| `questionsAndAnswers.min`    | integer | 否   | `-`                           | 最小qa                                                       |
| `questionsAndAnswers.max`    | integer | 否   | `-`                           | 最大qa                                                       |
| `price`                      | object  | 否   | `-`                           | 价格，单位卢布                                               |
| `price.min`                  | number  | 否   | `-`                           | 最小价格                                                     |
| `price.max`                  | number  | 否   | `-`                           | 最大价格                                                     |
| `monthlyRevenue`             | object  | 否   | `-`                           | 销售额                                                       |
| `monthlyRevenue.min`         | number  | 否   | `-`                           | 最小销售额                                                   |
| `monthlyRevenue.max`         | number  | 否   | `-`                           | 最大销售额                                                   |
| `monthlySales`               | object  | 否   | `-`                           | 销量                                                         |
| `monthlySales.min`           | integer | 否   | `-`                           | 最小销量                                                     |
| `monthlySales.max`           | integer | 否   | `-`                           | 最大销量                                                     |
| `monthlySalesRate`           | object  | 否   | `-`                           | 销量增长率                                                   |
| `monthlySalesRate.min`       | number  | 否   | `-`                           | 最小销量增长率                                               |
| `monthlySalesRate.max`       | number  | 否   | `-`                           | 最大销量增长率                                               |
| `weight`                     | object  | 否   | `-`                           | 重量，单位g                                                  |
| `weight.min`                 | number  | 否   | `-`                           | 最小重量                                                     |
| `weight.max`                 | number  | 否   | `-`                           | 最大重量                                                     |
| `volume`                     | object  | 否   | `-`                           | 体积，单位L                                                  |
| `volume.min`                 | number  | 否   | `-`                           | 最小体积                                                     |
| `volume.max`                 | number  | 否   | `-`                           | 最大体积                                                     |
| `grossMargin`                | object  | 否   | `-`                           | 毛利率                                                       |
| `grossMargin.min`            | number  | 否   | `-`                           | 最小毛利率                                                   |
| `grossMargin.max`            | number  | 否   | `-`                           | 最大毛利率                                                   |
| `variants`                   | object  | 否   | `-`                           | 变体数                                                       |
| `variants.min`               | integer | 否   | `-`                           | 最小变体数                                                   |
| `variants.max`               | integer | 否   | `-`                           | 最大变体数                                                   |
| `convToCartPdp`              | object  | 否   | `-`                           | 购物车转化率                                                 |
| `convToCartPdp.min`          | number  | 否   | `-`                           | 最小购物车转化率                                             |
| `convToCartPdp.max`          | number  | 否   | `-`                           | 最大购物车转化率                                             |
| `returnCancellationRate`     | object  | 否   | `-`                           | 退货取消率                                                   |
| `returnCancellationRate.min` | number  | 否   | `-`                           | 最小退货取消率                                               |
| `returnCancellationRate.max` | number  | 否   | `-`                           | 最大退货取消率                                               |
| `creationDate`               | integer | 否   | `-`                           | 上架时间，null：不筛选，1：近30天，3：近90天，6：近180天，12：近一年，24：近2年 |
| `fulfillment`                | string  | 否   | `FBO`                         | 配送方式，可传值：OZON，FBO，FBS，RFBS，FBP                  |
| `skus`                       | array   | 否   | `-`                           | sku数组，最多可传10个sku                                     |
| `sellerName`                 | array   | 否   | `-`                           | 卖家名称                                                     |
| `brand`                      | object  | 否   | `-`                           | 品牌                                                         |
| `brand.type`                 | number  | 否   | `0`                           | 0:包含品牌 1:排除品牌 2:无品牌                               |
| `brand.brandName`            | array   | 否   | `-`                           | 品牌名称                                                     |
| `labels`                     | array   | 否   | `-`                           | 标签数组，0：新品，1：正品，2：畅销品                        |
| `keywords`                   | array   | 否   | ``                            | 关键词                                                       |
| `tag`                        | string  | 否   | `-`                           | 标签词                                                       |
| `page`                       | object  | 是   | `-`                           | 分页参数                                                     |
| `page.pageNumber`            | number  | 是   | `1`                           | 分页页码                                                     |
| `page.pageSize`              | number  | 是   | `20`                          | 分页每页条数，最大100                                        |
| `page.orders`                | array   | 是   | `-`                           | 排序规则                                                     |
| `page.orders.field`          | string  | 是   | `revenue`                     | 排序字段，支持：revenue,price,sales,grossMargin,views,sessionCountSearch,sessionCount,convToCartPdp,orderConversionRate,drr,returnCancellationRate,missedRevenue,variants,reviewCount,reviewRating,upTime,weight,volume,questionsAndAnswers |
| `page.orders.direction`      | string  | 是   | `DESC`                        | DESC：倒序，ASC：正序                                        |

### 请求体

Request Body复制

```
{
  "categoryId": "15621032_15621049_115951147",
  "date": null,
  "reviewCount": {
    "min": null,
    "max": null
  },
  "drr": {
    "min": null,
    "max": null
  },
  "reviewRating": {
    "min": null,
    "max": null
  },
  "questionsAndAnswers": {
    "min": null,
    "max": null
  },
  "price": {
    "min": null,
    "max": null
  },
  "monthlyRevenue": {
    "min": null,
    "max": null
  },
  "monthlySales": {
    "min": null,
    "max": null
  },
  "monthlySalesRate": {
    "min": null,
    "max": null
  },
  "weight": {
    "min": null,
    "max": null
  },
  "volume": {
    "min": null,
    "max": null
  },
  "grossMargin": {
    "min": null,
    "max": null
  },
  "variants": {
    "min": null,
    "max": null
  },
  "convToCartPdp": {
    "min": null,
    "max": null
  },
  "returnCancellationRate": {
    "min": null,
    "max": null
  },
  "creationDate": null,
  "fulfillment": "FBO",
  "skus": [],
  "sellerName": [],
  "brand": {
    "type": 0,
    "brandName": []
  },
  "labels": [],
  "keywords": [],
  "filterRemoveProduct": true,
  "tag": "",
  "page": {
    "pageNumber": 1,
    "pageSize": 20,
    "orders": [
      {
        "field": "revenue",
        "direction": "DESC"
      }
    ]
  }
}
```

### 请求示例

cURL复制

```
curl "http://api.seerfar.cn/open-api/category/detail/search/ozon" \
  -X POST \
  -H "Authorization: Bearer <platform_api_key>" \
  -H "Content-Type: application/json" \
  -d '{"categoryId":"15621032_15621049_115951147","date":null,"reviewCount":{"min":null,"max":null},"drr":{"min":null,"max":null},"reviewRating":{"min":null,"max":null},"questionsAndAnswers":{"min":null,"max":null},"price":{"min":null,"max":null},"monthlyRevenue":{"min":null,"max":null},"monthlySales":{"min":null,"max":null},"monthlySalesRate":{"min":null,"max":null},"weight":{"min":null,"max":null},"volume":{"min":null,"max":null},"grossMargin":{"min":null,"max":null},"variants":{"min":null,"max":null},"convToCartPdp":{"min":null,"max":null},"returnCancellationRate":{"min":null,"max":null},"creationDate":null,"fulfillment":"FBO","skus":[],"sellerName":[],"brand":{"type":0,"brandName":[]},"labels":[],"keywords":[],"filterRemoveProduct":true,"tag":"","page":{"pageNumber":1,"pageSize":20,"orders":[{"field":"revenue","direction":"DESC"}]}}'
```

### 响应示例

JSON复制

```
{
  "code": 200,
  "msg": "SUCCESS",
  "data": {
    "id": "15621032_15621049_115951147",
    "rating": 4.9,
    "totalRevenue": 15350495,
    "avgPrice": 6989,
    "totalSales": 2485,
    "sellerType": {
      "FBO": 217,
      "FBS": 263,
      "OZON": 1,
      "RFBS": 570
    },
    "products": 955,
    "startDate": "2026-01-30",
    "endDate": "2026-03-01",
    "categoryInfo": {
      "category": {
        "id": "15621032_15621049_115951147",
        "enTitle": "Weightlifting Shoes",
        "title": "Штангетки",
        "cnTitle": "举重鞋",
        "pid": "15621032_15621049",
        "level": 3,
        "disabled": false,
        "crossBorderSellable": true,
        "children": null
      },
      "fullCategoryId": [
        "15621032",
        "15621032_15621049",
        "15621032_15621049_115951147"
      ],
      "titlePath": "Обувь > Спортивная и рабочая обувь > Штангетки",
      "cnTitlePath": "鞋类 > 运动鞋和工作鞋 > 举重鞋",
      "enTitlePath": "Footwear > Sports and Work Footwear > Weightlifting Shoes"
    },
    "categoryLibraryName": null,
    "seasonalityAmplitude": "STRONG_SEASONALITY",
    "seasonalityCoef": "TRANSITION_PERIOD",
    "productList": [
      {
        "sku": 2100100166,
        "title": "Штангетки SABOSPORTS Powerlift 20 для тяжелой атлетики и пауэрлифтинга",
        "productUrl": "https://www.ozon.ru/product/2100100166",
        "brandId": 87326141,
        "brandName": "SABOSPORTS",
        "brandUrl": "https://www.ozon.ru/brand/87326141",
        "imageUrl": "https://ir.ozone.ru/s3/multimedia-1-8/wc300/7599803300.jpg",
        "sellerId": 444286,
        "sellerName": "SABOSPORTS Russia",
        "sellers": 0,
        "fulfillment": [
          "FBO"
        ],
        "weight": 1044,
        "questionsAndAnswers": 19,
        "upTime": 1746392400000,
        "upDays": 326,
        "upMonths": 10,
        "price": 8827,
        "profit": null,
        "grossMargin": 25.4,
        "reviewCount": 65,
        "reviewRating": 5,
        "reviewIncr": null,
        "ratingsRate": null,
        "sales": 34,
        "originSales": null,
        "salesRate": -11,
        "revenue": 297356,
        "revenueRate": -4,
        "categoryInfo": {
          "category": {
            "id": "15621032_15621049_115951147",
            "enTitle": "Weightlifting Shoes",
            "title": "Штангетки",
            "cnTitle": "举重鞋",
            "pid": "15621032_15621049",
            "level": 3,
            "disabled": false,
            "crossBorderSellable": true,
            "children": null
          },
          "fullCategoryId": [
            "15621032",
            "15621032_15621049",
            "15621032_15621049_115951147"
          ],
          "titlePath": "Обувь > Спортивная и рабочая обувь > Штангетки",
          "cnTitlePath": "鞋类 > 运动鞋和工作鞋 > 举重鞋",
          "enTitlePath": "Footwear > Sports and Work Footwear > Weightlifting Shoes"
        },
        "volume": 9.319,
        "dimension": "364×200×128",
        "labels": [],
        "variants": 6,
        "variationIds": [
          2100100141,
          2100100201,
          2100100203,
          2100100166,
          2100100184,
          2100100178
        ],
        "variationsRelationId": 12018605,
        "sellerType": 0,
        "sessionCount": 2025,
        "sessionCountSearch": 7379,
        "drr": 0,
        "convToCartSearch": 10.25,
        "discount": 15.5,
        "promoRevenueShare": 62.4,
        "convViewToOrder": 4.8,
        "convToCartPdp": 2.81,
        "returnCancellationRate": 45.2,
        "orderConversionRate": 54.4,
        "naturalRank": null,
        "adRank": null,
        "categoryRank": null,
        "views": 22950,
        "missedRevenue": 31379
      }
    ],
    "hasNextPage": true
  }
}
```

### 响应字段

| 字段                                                         | 类型    | 示例                                                         | 说明                                                         |
| :----------------------------------------------------------- | :------ | :----------------------------------------------------------- | :----------------------------------------------------------- |
| `code`                                                       | number  | `200`                                                        | 状态码                                                       |
| `msg`                                                        | string  | `SUCCESS`                                                    | 返回文字描述                                                 |
| `data`                                                       | object  | `-`                                                          | 返回数据                                                     |
| `data.id`                                                    | string  | `15621032_15621049_115951147`                                | 类目id                                                       |
| `data.rating`                                                | number  | `4.9`                                                        | 类目商品平均评分                                             |
| `data.totalRevenue`                                          | number  | `15350495`                                                   | 类目总销售额                                                 |
| `data.avgPrice`                                              | number  | `6989`                                                       | 商品平均价格                                                 |
| `data.totalSales`                                            | number  | `2485`                                                       | 类目总销量                                                   |
| `data.sellerType`                                            | object  | `-`                                                          | 各配送方式商品个数                                           |
| `data.sellerType.FBO`                                        | number  | `217`                                                        | FBO商品个数                                                  |
| `data.sellerType.FBS`                                        | number  | `263`                                                        | FBS商品个数                                                  |
| `data.sellerType.OZON`                                       | number  | `1`                                                          | OZON商品个数                                                 |
| `data.sellerType.RFBS`                                       | number  | `570`                                                        | RFBS商品个数                                                 |
| `data.startDate`                                             | string  | `2026-01-30`                                                 | 起始日期                                                     |
| `data.endDate`                                               | string  | `2026-03-01`                                                 | 结束日期                                                     |
| `data.categoryInfo`                                          | object  | `-`                                                          | 类目信息                                                     |
| `data.categoryInfo.category`                                 | object  | `-`                                                          | 类目信息                                                     |
| `data.categoryInfo.category.id`                              | string  | `15621032_15621049_115951147`                                | 类目id                                                       |
| `data.categoryInfo.category.enTitle`                         | string  | `Weightlifting Shoes`                                        | 类目英文名称                                                 |
| `data.categoryInfo.category.title`                           | string  | `Штангетки`                                                  | 类目俄文名称                                                 |
| `data.categoryInfo.category.cnTitle`                         | string  | `举重鞋`                                                     | 类目中文名称                                                 |
| `data.categoryInfo.category.pid`                             | string  | `15621032_15621049`                                          | 父类id                                                       |
| `data.categoryInfo.category.level`                           | number  | `3`                                                          | 类目层级                                                     |
| `data.categoryInfo.category.disabled`                        | boolean | `false`                                                      | 类目是否可用                                                 |
| `data.categoryInfo.category.crossBorderSellable`             | boolean | `true`                                                       | 是否跨境可售                                                 |
| `data.categoryInfo.category.children`                        | array   | `-`                                                          | 子类目信息                                                   |
| `data.categoryInfo.fullCategoryId`                           | array   | `-`                                                          | 类目id路径                                                   |
| `data.categoryInfo.titlePath`                                | string  | `Канцелярские товары > Бумага > Бумага для принтера`         | 类目路径                                                     |
| `data.categoryInfo.cnTitlePath`                              | string  | `Канцелярские товары > Бумага > Бумага для принтера`         | 类目路径                                                     |
| `data.categoryInfo.enTitlePath`                              | string  | `Канцелярские товары > Бумага > Бумага для принтера`         | 类目路径                                                     |
| `data.categoryLibraryName`                                   | string  | `-`                                                          | 类目库名称（已弃用）                                         |
| `data.seasonalityAmplitude`                                  | string  | `STRONG_SEASONALITY`                                         | NO_SEASONALITY：无季节性；WEAK_SEASONALITY：弱季节性；STRONG_SEASONALITY：强季节性 |
| `data.seasonalityCoef`                                       | string  | `TRANSITION_PERIOD`                                          | PEAK_SEASON：旺季；TRANSITION_PERIOD：过渡期；OFF_SEASON：淡季； |
| `data.productList`                                           | array   | `-`                                                          | 商品列表                                                     |
| `data.productList.sku`                                       | number  | `2100100166`                                                 | 商品sku                                                      |
| `data.productList.title`                                     | string  | `Штангетки SABOSPORTS Powerlift 20 для тяжелой атлетики и пауэрлифтинга` | 商品标题                                                     |
| `data.productList.productUrl`                                | string  | `https://www.ozon.ru/product/2100100166`                     | 商品链接                                                     |
| `data.productList.brandId`                                   | number  | `87326141`                                                   | 品牌id                                                       |
| `data.productList.brandName`                                 | string  | `SABOSPORTS`                                                 | 品牌名称                                                     |
| `data.productList.brandUrl`                                  | string  | `https://www.ozon.ru/brand/87326141`                         | 品牌链接                                                     |
| `data.productList.imageUrl`                                  | string  | `https://ir.ozone.ru/s3/multimedia-1-8/wc300/7599803300.jpg` | 商品图片链接                                                 |
| `data.productList.sellerId`                                  | number  | `444286`                                                     | 卖家id                                                       |
| `data.productList.sellerName`                                | string  | `SABOSPORTS Russia`                                          | 卖家名称                                                     |
| `data.productList.sellers`                                   | number  | `0`                                                          | 卖家类型。0：本土；1：跨境；                                 |
| `data.productList.fulfillment`                               | array   | `-`                                                          | 配送方式                                                     |
| `data.productList.weight`                                    | number  | `1044`                                                       | 重量，单位：g                                                |
| `data.productList.questionsAndAnswers`                       | number  | `19`                                                         | qa数                                                         |
| `data.productList.upTime`                                    | number  | `1746392400000`                                              | 上架时间戳（毫秒）                                           |
| `data.productList.upDays`                                    | number  | `326`                                                        | 上架天数                                                     |
| `data.productList.upMonths`                                  | number  | `10`                                                         | 上架月数                                                     |
| `data.productList.price`                                     | number  | `8827`                                                       | 价格                                                         |
| `data.productList.grossMargin`                               | number  | `25.4`                                                       | 毛利率                                                       |
| `data.productList.reviewCount`                               | number  | `65`                                                         | 评论数                                                       |
| `data.productList.reviewRating`                              | number  | `5`                                                          | 评分                                                         |
| `data.productList.reviewIncr`                                | number  | `-`                                                          | 评论增长数（已弃用）                                         |
| `data.productList.ratingsRate`                               | number  | `-`                                                          | 评分增长（已弃用）                                           |
| `data.productList.sales`                                     | number  | `34`                                                         | 销量                                                         |
| `data.productList.salesRate`                                 | number  | `-11`                                                        | 销量增长率                                                   |
| `data.productList.revenue`                                   | number  | `297356`                                                     | 销售额                                                       |
| `data.productList.revenueRate`                               | number  | `-4`                                                         | 销售额增长率                                                 |
| `data.productList.categoryInfo`                              | object  | `-`                                                          | 类目                                                         |
| `data.productList.categoryInfo.category`                     | object  | `-`                                                          | 类目信息                                                     |
| `data.productList.categoryInfo.category.id`                  | string  | `15621032_15621049_115951147`                                | 类目id                                                       |
| `data.productList.categoryInfo.category.enTitle`             | string  | `Weightlifting Shoes`                                        | 类目名称                                                     |
| `data.productList.categoryInfo.category.title`               | string  | `Штангетки`                                                  | 类目名称                                                     |
| `data.productList.categoryInfo.category.cnTitle`             | string  | `举重鞋`                                                     | 类目名称                                                     |
| `data.productList.categoryInfo.category.pid`                 | string  | `15621032_15621049`                                          | 父类id                                                       |
| `data.productList.categoryInfo.category.level`               | number  | `3`                                                          | 类目层级                                                     |
| `data.productList.categoryInfo.category.disabled`            | boolean | `false`                                                      | 类目是否可用                                                 |
| `data.productList.categoryInfo.category.crossBorderSellable` | boolean | `true`                                                       | 是否跨境可售                                                 |
| `data.productList.categoryInfo.category.children`            | array   | `-`                                                          | 子类目信息                                                   |
| `data.productList.categoryInfo.fullCategoryId`               | array   | `-`                                                          | 类目id路径                                                   |
| `data.productList.categoryInfo.titlePath`                    | string  | `Обувь > Спортивная и рабочая обувь > Штангетки`             | 类目路径                                                     |
| `data.productList.categoryInfo.cnTitlePath`                  | string  | `鞋类 > 运动鞋和工作鞋 > 举重鞋`                             | 类目路径                                                     |
| `data.productList.categoryInfo.enTitlePath`                  | string  | `Footwear > Sports and Work Footwear > Weightlifting Shoes`  | 类目路径                                                     |
| `data.productList.volume`                                    | number  | `9.319`                                                      | 体积                                                         |
| `data.productList.dimension`                                 | string  | `364×200×128`                                                | 尺寸                                                         |
| `data.productList.labels`                                    | array   | `-`                                                          | 标签                                                         |
| `data.productList.variants`                                  | number  | `6`                                                          | 变体数                                                       |
| `data.productList.variationIds`                              | array   | `-`                                                          | 变体sku                                                      |
| `data.productList.variationsRelationId`                      | number  | `12018605`                                                   | 变体关联id                                                   |
| `data.productList.sellerType`                                | number  | `0`                                                          | 卖家类型                                                     |
| `data.productList.sessionCount`                              | number  | `2025`                                                       | 产品卡浏览量                                                 |
| `data.productList.sessionCountSearch`                        | number  | `7379`                                                       | 曝光量                                                       |
| `data.productList.drr`                                       | number  | `0`                                                          | 广告费用份额                                                 |
| `data.productList.convToCartSearch`                          | number  | `10.25`                                                      | 搜索加购率                                                   |
| `data.productList.discount`                                  | number  | `15.5`                                                       | 平均折扣                                                     |
| `data.productList.promoRevenueShare`                         | number  | `62.4`                                                       | 促销销售占比                                                 |
| `data.productList.convViewToOrder`                           | number  | `4.8`                                                        | 展示转化率                                                   |
| `data.productList.convToCartPdp`                             | number  | `2.81`                                                       | 购物车转化率                                                 |
| `data.productList.returnCancellationRate`                    | number  | `45.2`                                                       | 退货取消率                                                   |
| `data.productList.orderConversionRate`                       | number  | `54.4`                                                       | 订单转化率                                                   |
| `data.productList.naturalRank`                               | number  | `2`                                                          | 自然排名（已弃用）                                           |
| `data.productList.adRank`                                    | number  | `3`                                                          | 广告排名（已弃用）                                           |
| `data.productList.categoryRank`                              | number  | `4`                                                          | 类目排名（已弃用）                                           |
| `data.productList.views`                                     | number  | `22950`                                                      | 展示总量                                                     |
| `data.productList.missedRevenue`                             | number  | `31379`                                                      | 错失销售额                                                   |
| `data.hasNextPage`                                           | boolean | `true`                                                       | 是否有下一页                                                 |





## Ozon 查热销榜单

POST/open-api/productReport/search/ozon

按筛选条件查询 Ozon 热销榜单商品数据。

试一试

### Header 参数

| 参数            | 类型   | 必填 | 示例               | 说明    |
| :-------------- | :----- | :--- | :----------------- | :------ |
| `Authorization` | string | 是   | `Bearer {Api Key}` | API Key |

### Body 参数

| 参数                         | 类型    | 必填 | 示例      | 说明                                                         |
| :--------------------------- | :------ | :--- | :-------- | :----------------------------------------------------------- |
| `reviewCount`                | object  | 否   | `-`       | 评论数                                                       |
| `reviewCount.min`            | integer | 否   | `-`       | 最小评论数                                                   |
| `reviewCount.max`            | integer | 否   | `-`       | 最大评论数                                                   |
| `drr`                        | object  | 否   | `-`       | 广告费用份额                                                 |
| `drr.min`                    | number  | 否   | `-`       | 最小广告费用份额                                             |
| `drr.max`                    | number  | 否   | `-`       | 最大广告费用份额                                             |
| `reviewRating`               | object  | 否   | `-`       | 评分                                                         |
| `reviewRating.min`           | number  | 否   | `-`       | 最小评分                                                     |
| `reviewRating.max`           | number  | 否   | `-`       | 最大评分                                                     |
| `questionsAndAnswers`        | object  | 否   | `-`       | qa                                                           |
| `questionsAndAnswers.min`    | integer | 否   | `-`       | 最小qa                                                       |
| `questionsAndAnswers.max`    | integer | 否   | `-`       | 最大qa                                                       |
| `price`                      | object  | 否   | `-`       | 价格，单位卢布                                               |
| `price.min`                  | number  | 否   | `-`       | 最小价格                                                     |
| `price.max`                  | number  | 否   | `-`       | 最大价格                                                     |
| `monthlyRevenue`             | object  | 否   | `-`       | 销售额                                                       |
| `monthlyRevenue.min`         | number  | 否   | `-`       | 最小销售额                                                   |
| `monthlyRevenue.max`         | number  | 否   | `-`       | 最大销售额                                                   |
| `monthlySales`               | object  | 否   | `-`       | 销量                                                         |
| `monthlySales.min`           | integer | 否   | `-`       | 最小销量                                                     |
| `monthlySales.max`           | integer | 否   | `-`       | 最大销量                                                     |
| `monthlySalesRate`           | object  | 否   | `-`       | 销量增长率                                                   |
| `monthlySalesRate.min`       | number  | 否   | `-`       | 最小销量增长率                                               |
| `monthlySalesRate.max`       | number  | 否   | `-`       | 最大销量增长率                                               |
| `weight`                     | object  | 否   | `-`       | 重量，单位g                                                  |
| `weight.min`                 | number  | 否   | `-`       | 最小重量                                                     |
| `weight.max`                 | number  | 否   | `-`       | 最大重量                                                     |
| `volume`                     | object  | 否   | `-`       | 体积，单位L                                                  |
| `volume.min`                 | number  | 否   | `-`       | 最小体积                                                     |
| `volume.max`                 | number  | 否   | `-`       | 最大体积                                                     |
| `grossMargin`                | object  | 否   | `-`       | 毛利率                                                       |
| `grossMargin.min`            | number  | 否   | `-`       | 最小毛利率                                                   |
| `grossMargin.max`            | number  | 否   | `-`       | 最大毛利率                                                   |
| `variants`                   | object  | 否   | `-`       | 变体数                                                       |
| `variants.min`               | integer | 否   | `-`       | 最小变体数                                                   |
| `variants.max`               | integer | 否   | `-`       | 最大变体数                                                   |
| `convToCartPdp`              | object  | 否   | `-`       | 购物车转化率                                                 |
| `convToCartPdp.min`          | number  | 否   | `-`       | 最小购物车转化率                                             |
| `convToCartPdp.max`          | number  | 否   | `-`       | 最大购物车转化率                                             |
| `returnCancellationRate`     | object  | 否   | `-`       | 退货取消率                                                   |
| `returnCancellationRate.min` | number  | 否   | `-`       | 最小退货取消率                                               |
| `returnCancellationRate.max` | number  | 否   | `-`       | 最大退货取消率                                               |
| `creationDate`               | integer | 否   | `-`       | 上架时间，null：不筛选，1：近30天，3：近90天，6：近180天，12：近一年，24：近2年 |
| `categoryIds`                | array   | 否   | `-`       | 类目id数组                                                   |
| `fulfillment`                | array   | 否   | `-`       | 配送方式数组，可传值：OZON，FBO，FBS，RFBS，FBP              |
| `skus`                       | array   | 否   | `-`       | sku数组，最多可传10个sku                                     |
| `sellerName`                 | array   | 否   | `-`       | 卖家名称                                                     |
| `brand`                      | object  | 否   | `-`       | 品牌                                                         |
| `brand.type`                 | number  | 否   | `0`       | 0:包含品牌 1:排除品牌 2:无品牌                               |
| `brand.brandName`            | array   | 否   | `-`       | 品牌名称                                                     |
| `labels`                     | array   | 否   | `-`       | 标签数组，0：新品，1：正品，2：畅销品                        |
| `keywords`                   | array   | 否   | ``        | 关键词                                                       |
| `variationsMerge`            | number  | 否   | `0`       | 合并变体，0：不合并，1：合并                                 |
| `searchDate`                 | string  | 否   | `-`       | 日期范围，不传默认查近30天数据，示例：传2026-04-01查2026年3月数据，仅能查近1年的数据 |
| `tag`                        | string  | 否   | `-`       | 标签词                                                       |
| `page`                       | object  | 是   | `-`       | 分页参数                                                     |
| `page.pageNumber`            | number  | 是   | `1`       | 分页页码                                                     |
| `page.pageSize`              | number  | 是   | `20`      | 分页每页条数，最大100                                        |
| `page.orders`                | array   | 是   | `-`       | 排序规则                                                     |
| `page.orders.field`          | string  | 是   | `revenue` | 排序字段，支持：revenue,price,sales,grossMargin,views,sessionCountSearch,sessionCount,convToCartPdp,orderConversionRate,drr,returnCancellationRate,missedRevenue,variants,reviewCount,reviewRating,upTime,weight,volume,questionsAndAnswers |
| `page.orders.direction`      | string  | 是   | `DESC`    | DESC：倒序，ASC：正序                                        |

### 请求体

Request Body复制

```
{
  "reviewCount": {
    "min": null,
    "max": null
  },
  "drr": {
    "min": null,
    "max": null
  },
  "reviewRating": {
    "min": null,
    "max": null
  },
  "questionsAndAnswers": {
    "min": null,
    "max": null
  },
  "price": {
    "min": null,
    "max": null
  },
  "monthlyRevenue": {
    "min": null,
    "max": null
  },
  "monthlySales": {
    "min": null,
    "max": null
  },
  "monthlySalesRate": {
    "min": null,
    "max": null
  },
  "weight": {
    "min": null,
    "max": null
  },
  "volume": {
    "min": null,
    "max": null
  },
  "grossMargin": {
    "min": null,
    "max": null
  },
  "variants": {
    "min": null,
    "max": null
  },
  "convToCartPdp": {
    "min": null,
    "max": null
  },
  "returnCancellationRate": {
    "min": null,
    "max": null
  },
  "creationDate": null,
  "categoryIds": null,
  "fulfillment": [],
  "skus": [],
  "sellerName": [],
  "brand": {
    "type": 0,
    "brandName": []
  },
  "labels": [],
  "keywords": [],
  "variationsMerge": 0,
  "searchDate": "",
  "filterRemoveProduct": true,
  "tag": "",
  "page": {
    "pageNumber": 1,
    "pageSize": 20,
    "orders": [
      {
        "field": "revenue",
        "direction": "DESC"
      }
    ]
  }
}
```

### 请求示例

cURL复制

```
curl "http://api.seerfar.cn/open-api/productReport/search/ozon" \
  -X POST \
  -H "Authorization: Bearer <platform_api_key>" \
  -H "Content-Type: application/json" \
  -d '{"reviewCount":{"min":null,"max":null},"reviewRating":{"min":null,"max":null},"questionsAndAnswers":{"min":null,"max":null},"price":{"min":null,"max":null},"monthlyRevenue":{"min":null,"max":null},"monthlySales":{"min":null,"max":null},"monthlySalesRate":{"min":null,"max":null},"sellers":{"min":null,"max":null},"weight":{"min":null,"max":null},"volume":{"min":null,"max":null},"ratingsRate":{"min":null,"max":null},"grossMargin":{"min":null,"max":null},"variants":{"min":null,"max":null},"convToCartPdp":{"min":null,"max":null},"returnCancellationRate":{"min":null,"max":null},"creationDate":null,"categoryIds":null,"fulfillment":[],"skus":[],"sellerName":[],"brand":{"type":0,"brandName":[]},"labels":[],"keywords":[],"variationsMerge":0,"searchDate":"","filterRemoveProduct":true,"tag":"","page":{"pageNumber":1,"pageSize":20,"orders":[{"field":"revenue","direction":"DESC"}]}}'
```

### 响应示例

JSON复制

```
{
  "code": 200,
  "msg": "SUCCESS",
  "data": {
    "records": [
      {
        "sku": 149222760,
        "title": "SvetoCopy 5 шт A4 500 л Бумага для принтера",
        "productUrl": "https://www.ozon.ru/product/149222760",
        "brandId": 33321059,
        "brandName": "SvetoCopy",
        "brandUrl": "https://www.ozon.ru/brand/33321059",
        "imageUrl": "https://ir.ozone.ru/s3/multimedia-1-9/wc300/7599846609.jpg",
        "sellerId": -2,
        "sellerName": "Ozon Express",
        "sellers": 0,
        "fulfillment": [
          "OZON"
        ],
        "weight": 12520,
        "questionsAndAnswers": 714,
        "upTime": 1334869200000,
        "upDays": 5115,
        "upMonths": 170,
        "price": 1794,
        "grossMargin": 17.3,
        "reviewCount": 649792,
        "reviewRating": 4.8,
        "reviewIncr": null,
        "sales": 75246,
        "salesRate": 7,
        "revenue": 124187644,
        "revenueRate": 11,
        "categoryInfo": {
          "category": {
            "id": "17027492_17029017_91400",
            "enTitle": "Printer Paper",
            "title": "Бумага для принтера",
            "cnTitle": "打印纸",
            "pid": "17027492_17029017",
            "level": 3,
            "disabled": false,
            "crossBorderSellable": true,
            "children": null
          },
          "fullCategoryId": [
            "17027492",
            "17027492_17029017",
            "17027492_17029017_91400"
          ],
          "titlePath": "Канцелярские товары > Бумага > Бумага для принтера",
          "cnTitlePath": "文具 > 纸 > 打印纸",
          "enTitlePath": "Stationery > Paper > Printer Paper"
        },
        "volume": 18.788,
        "dimension": "305×280×220",
        "labels": [
          1,
          2
        ],
        "variants": 3,
        "variationIds": [
          7969279,
          149222760,
          929833643
        ],
        "variationsRelationId": 26792,
        "sellerType": 0,
        "sessionCount": 211521,
        "sessionCountSearch": 343064,
        "drr": 0,
        "convToCartSearch": 10.25,
        "discount": 15.5,
        "promoRevenueShare": 62.4,
        "convViewToOrder": 4.8,
        "convToCartPdp": 14.96,
        "returnCancellationRate": null,
        "orderConversionRate": 209.8,
        "views": 7311433,
        "missedRevenue": 0
      }
    ],
    "total": 27744276,
    "size": 1,
    "current": 1,
    "currentSize": 0,
    "totalPages": 27744276,
    "orders": null,
    "timeInterval": {
      "min": "2026-03-22",
      "max": "2026-04-20"
    }
  }
}
```

### 响应字段

| 字段                                                     | 类型    | 示例                                                         | 说明                                  |
| :------------------------------------------------------- | :------ | :----------------------------------------------------------- | :------------------------------------ |
| `code`                                                   | number  | `200`                                                        | 状态码                                |
| `msg`                                                    | string  | `SUCCESS`                                                    | 返回文字描述                          |
| `data`                                                   | object  | `-`                                                          | 返回数据                              |
| `data.records`                                           | array   | `-`                                                          | 数据集合                              |
| `data.records.sku`                                       | number  | `149222760`                                                  | sku                                   |
| `data.records.title`                                     | string  | `SvetoCopy 5 шт A4 500 л Бумага для принтера`                | 商品标题                              |
| `data.records.productUrl`                                | string  | `https://www.ozon.ru/product/149222760`                      | 商品链接                              |
| `data.records.brandId`                                   | number  | `33321059`                                                   | 品牌id                                |
| `data.records.brandName`                                 | string  | `SvetoCopy`                                                  | 品牌名称                              |
| `data.records.brandUrl`                                  | string  | `https://www.ozon.ru/brand/33321059`                         | 品牌链接                              |
| `data.records.imageUrl`                                  | string  | `https://ir.ozone.ru/s3/multimedia-1-9/wc300/7599846609.jpg` | 商品图片链接                          |
| `data.records.sellerId`                                  | number  | `-2`                                                         | 卖家                                  |
| `data.records.sellerName`                                | string  | `Ozon Express`                                               | 卖家名称                              |
| `data.records.sellers`                                   | number  | `0`                                                          | 卖家数（已弃用）                      |
| `data.records.fulfillment`                               | array   | `-`                                                          | 配送方式                              |
| `data.records.weight`                                    | number  | `12520`                                                      | 重量，单位g                           |
| `data.records.questionsAndAnswers`                       | number  | `714`                                                        | qa                                    |
| `data.records.upTime`                                    | number  | `1334869200000`                                              | 上架时间戳，毫秒                      |
| `data.records.upDays`                                    | number  | `5115`                                                       | 上架天数                              |
| `data.records.upMonths`                                  | number  | `170`                                                        | 上架月数                              |
| `data.records.price`                                     | number  | `1794`                                                       | 价格，单位卢布                        |
| `data.records.grossMargin`                               | number  | `17.3`                                                       | 毛利率                                |
| `data.records.reviewCount`                               | number  | `649792`                                                     | 评论数                                |
| `data.records.reviewRating`                              | number  | `4.8`                                                        | 评分                                  |
| `data.records.reviewIncr`                                | number  | `-`                                                          | 评论增长数（已弃用）                  |
| `data.records.sales`                                     | number  | `75246`                                                      | 销量                                  |
| `data.records.salesRate`                                 | number  | `7`                                                          | 销量增长率                            |
| `data.records.revenue`                                   | number  | `124187644`                                                  | 销售额                                |
| `data.records.revenueRate`                               | number  | `11`                                                         | 销售额增长率                          |
| `data.records.categoryInfo`                              | object  | `-`                                                          | 类目                                  |
| `data.records.categoryInfo.category`                     | object  | `-`                                                          | 类目信息                              |
| `data.records.categoryInfo.category.id`                  | string  | `17027492_17029017_91400`                                    | 类目id                                |
| `data.records.categoryInfo.category.enTitle`             | string  | `Printer Paper`                                              | 类目名称                              |
| `data.records.categoryInfo.category.title`               | string  | `Бумага для принтера`                                        | 类目名称                              |
| `data.records.categoryInfo.category.cnTitle`             | string  | `打印纸`                                                     | 类目名称                              |
| `data.records.categoryInfo.category.pid`                 | string  | `17027492_17029017`                                          | 父类id                                |
| `data.records.categoryInfo.category.level`               | number  | `3`                                                          | 类目层级                              |
| `data.records.categoryInfo.category.disabled`            | boolean | `false`                                                      | 类目是否可用                          |
| `data.records.categoryInfo.category.crossBorderSellable` | boolean | `true`                                                       | 跨境是否可售                          |
| `data.records.categoryInfo.category.children`            | array   | `-`                                                          | 子类目信息                            |
| `data.records.categoryInfo.fullCategoryId`               | array   | `-`                                                          | 类目id路径                            |
| `data.records.categoryInfo.titlePath`                    | string  | `Канцелярские товары > Бумага > Бумага для принтера`         | 类目路径                              |
| `data.records.categoryInfo.cnTitlePath`                  | string  | `文具 > 纸 > 打印纸`                                         | 类目路径                              |
| `data.records.categoryInfo.enTitlePath`                  | string  | `Stationery > Paper > Printer Paper`                         | 类目路径                              |
| `data.records.volume`                                    | number  | `18.788`                                                     | 体积，单位L                           |
| `data.records.dimension`                                 | string  | `305×280×220`                                                | 尺寸，单位毫米                        |
| `data.records.labels`                                    | array   | `-`                                                          | 标签数组，0：新品，1：正品，2：畅销品 |
| `data.records.variants`                                  | number  | `3`                                                          | 变体数                                |
| `data.records.variationIds`                              | array   | `-`                                                          | 变体sku                               |
| `data.records.variationsRelationId`                      | number  | `26792`                                                      | 变体关联id                            |
| `data.records.sellerType`                                | number  | `0`                                                          | 卖家类型，0：本土，1：跨境            |
| `data.records.sessionCount`                              | number  | `211521`                                                     | 产品卡浏览量                          |
| `data.records.sessionCountSearch`                        | number  | `343064`                                                     | 曝光量                                |
| `data.records.drr`                                       | number  | `0`                                                          | 广告费用                              |
| `data.records.convToCartSearch`                          | number  | `10.25`                                                      | 搜索加购率                            |
| `data.records.discount`                                  | number  | `15.5`                                                       | 平均折扣                              |
| `data.records.promoRevenueShare`                         | number  | `62.4`                                                       | 促销销售占比                          |
| `data.records.convViewToOrder`                           | number  | `4.8`                                                        | 展示转化率                            |
| `data.records.convToCartPdp`                             | number  | `14.96`                                                      | 加购率                                |
| `data.records.returnCancellationRate`                    | number  | `45.2`                                                       | 退货取消率                            |
| `data.records.orderConversionRate`                       | number  | `209.8`                                                      | 订单转化率                            |
| `data.records.views`                                     | number  | `7311433`                                                    | 展示总量                              |
| `data.records.missedRevenue`                             | number  | `0`                                                          | 错失销售额                            |
| `data.total`                                             | number  | `27744276`                                                   | 符合筛选条件的商品数                  |
| `data.size`                                              | number  | `1`                                                          | （已弃用）                            |
| `data.current`                                           | number  | `1`                                                          | （已弃用）                            |
| `data.currentSize`                                       | number  | `0`                                                          | （已弃用）                            |
| `data.totalPages`                                        | number  | `27744276`                                                   | （已弃用）                            |
| `data.orders`                                            | array   | `-`                                                          | （已弃用）                            |
| `data.timeInterval`                                      | object  | `-`                                                          | （已弃用）                            |
| `data.timeInterval.min`                                  | string  | `2026-03-22`                                                 | （已弃用）                            |
| `data.timeInterval.max`                                  | string  | `2026-04-20`                                                 | （已弃用）                            |

### 错误响应

| 状态码 | 说明             | 示例                                                 |
| :----- | :--------------- | :--------------------------------------------------- |
| `500`  | 失败             | `{ "code": 500, "msg": "Server error" }`             |
| `401`  | 未授权           | `{ "code": 401, "msg": "Unauthorized" }`             |
| `429`  | 请求过多         | `{ "code": 429, "msg": "Too Many Requests" }`        |
| `403`  | 无权限           | `{ "code": 403, "msg": "Forbidden" }`                |
| `200`  | API Key 积分耗尽 | `{ "code": 8000, "msg": "Api Key limit exhausted" }` |





## Ozon 查市场热词

POST/open-api/market/search/ozon

按筛选条件查询 Ozon 市场热词和关键词指标。

试一试

### Header 参数

| 参数            | 类型   | 必填 | 示例               | 说明    |
| :-------------- | :----- | :--- | :----------------- | :------ |
| `Authorization` | string | 是   | `Bearer {Api Key}` | API Key |

### Body 参数

| 参数                    | 类型    | 必填 | 示例           | 说明                                                         |
| :---------------------- | :------ | :--- | :------------- | :----------------------------------------------------------- |
| `price`                 | object  | 否   | `-`            | 平均价格，单位卢布                                           |
| `price.min`             | number  | 否   | `-`            | 最小平均价格                                                 |
| `price.max`             | number  | 否   | `-`            | 最大平均价格                                                 |
| `monthlySales`          | object  | 否   | `-`            | 销量                                                         |
| `monthlySales.min`      | integer | 否   | `-`            | 最小销量                                                     |
| `monthlySales.max`      | integer | 否   | `-`            | 最大销量                                                     |
| `monthlyRevenue`        | object  | 否   | `-`            | 销售额                                                       |
| `monthlyRevenue.min`    | number  | 否   | `-`            | 最小销售额                                                   |
| `monthlyRevenue.max`    | number  | 否   | `-`            | 最大销售额                                                   |
| `weight`                | object  | 否   | `-`            | 重量，单位g                                                  |
| `weight.min`            | number  | 否   | `-`            | 最小重量                                                     |
| `weight.max`            | number  | 否   | `-`            | 最大重量                                                     |
| `volume`                | object  | 否   | `-`            | 体积，单位L                                                  |
| `volume.min`            | number  | 否   | `-`            | 最小体积                                                     |
| `volume.max`            | number  | 否   | `-`            | 最大体积                                                     |
| `reviews`               | object  | 否   | `-`            | 评论数                                                       |
| `reviews.min`           | integer | 否   | `-`            | 最小评论数                                                   |
| `reviews.max`           | integer | 否   | `-`            | 最大评论数                                                   |
| `ratings`               | object  | 否   | `-`            | 评分                                                         |
| `ratings.min`           | number  | 否   | `-`            | 最小评分                                                     |
| `ratings.max`           | number  | 否   | `-`            | 最大评分                                                     |
| `searchVolume`          | object  | 否   | `-`            | 月搜热度                                                     |
| `searchVolume.min`      | integer | 否   | `-`            | 最小月搜热度                                                 |
| `searchVolume.max`      | integer | 否   | `-`            | 最大月搜热度                                                 |
| `searchChange30`        | object  | 否   | `-`            | 月搜增长                                                     |
| `searchChange30.min`    | number  | 否   | `-`            | 最小月搜增长                                                 |
| `searchChange30.max`    | number  | 否   | `-`            | 最大月搜增长                                                 |
| `sellers`               | object  | 否   | `-`            | 有销量卖家                                                   |
| `sellers.min`           | integer | 否   | `-`            | 最小有销量卖家                                               |
| `sellers.max`           | integer | 否   | `-`            | 最大有销量卖家                                               |
| `products`              | object  | 否   | `-`            | 有销量商品                                                   |
| `products.min`          | integer | 否   | `-`            | 最小有销量商品                                               |
| `products.max`          | integer | 否   | `-`            | 最大有销量商品                                               |
| `productViews`          | object  | 否   | `-`            | 商品可见度                                                   |
| `productViews.min`      | number  | 否   | `-`            | 最小商品可见度                                               |
| `productViews.max`      | number  | 否   | `-`            | 最大商品可见度                                               |
| `conversionSharing`     | object  | 否   | `-`            | 转化集中度                                                   |
| `conversionSharing.min` | number  | 否   | `-`            | 最小转化集中度                                               |
| `conversionSharing.max` | number  | 否   | `-`            | 最大转化集中度                                               |
| `marketSpace`           | object  | 否   | `-`            | 市场空间                                                     |
| `marketSpace.min`       | number  | 否   | `-`            | 最小市场空间                                                 |
| `marketSpace.max`       | number  | 否   | `-`            | 最大市场空间                                                 |
| `categories`            | array   | 否   | `-`            | 类目id数组                                                   |
| `keywords`              | array   | 否   | `-`            | 关键词数组                                                   |
| `matchType`             | number  | 否   | `0`            | 关键词匹配模式，0：精准，1：模糊                             |
| `searchDate`            | string  | 否   | `-`            | 日期范围，不传默认查近30天数据，示例：传2026-04-01查2026年3月数据，仅能查近1年的数据 |
| `page`                  | object  | 是   | `-`            | 分页参数                                                     |
| `page.pageNumber`       | integer | 是   | `1`            | 分页页码                                                     |
| `page.pageSize`         | integer | 是   | `1`            | 分页每页条数，最大100                                        |
| `page.orders`           | array   | 是   | `-`            | 排序规则                                                     |
| `page.orders.field`     | string  | 是   | `searchVolume` | 排序字段，支持：searchVolume,avgPrice,sales,revenue,count30GrowthRate,productCount,sellers,competingProducts,reviews,ratings,marketSpace,itemsViews,conversionSharing,returnCancellationRate,weight,volume |
| `page.orders.direction` | string  | 是   | `DESC`         | DESC：倒序，ASC：正序                                        |

### 请求体

Request Body复制

```
{
  "price": {
    "min": null,
    "max": null
  },
  "monthlySales": {
    "min": null,
    "max": null
  },
  "monthlyRevenue": {
    "min": null,
    "max": null
  },
  "weight": {
    "min": null,
    "max": null
  },
  "volume": {
    "min": null,
    "max": null
  },
  "reviews": {
    "min": null,
    "max": null
  },
  "ratings": {
    "min": null,
    "max": null
  },
  "searchVolume": {
    "min": null,
    "max": null
  },
  "searchChange30": {
    "min": null,
    "max": null
  },
  "sellers": {
    "min": null,
    "max": null
  },
  "products": {
    "min": null,
    "max": null
  },
  "productViews": {
    "min": null,
    "max": null
  },
  "conversionSharing": {
    "min": null,
    "max": null
  },
  "marketSpace": {
    "min": null,
    "max": null
  },
  "categories": null,
  "keywords": [],
  "matchType": 0,
  "searchDate": "",
  "page": {
    "pageNumber": 1,
    "pageSize": "1",
    "orders": [
      {
        "field": "searchVolume",
        "direction": "DESC"
      }
    ]
  }
}
```

### 请求示例

cURL复制

```
curl "http://api.seerfar.cn/open-api/market/search/ozon" \
  -X POST \
  -H "Authorization: Bearer <platform_api_key>" \
  -H "Content-Type: application/json" \
  -d '{"price":{"min":null,"max":null},"monthlySales":{"min":null,"max":null},"monthlyRevenue":{"min":null,"max":null},"weight":{"min":null,"max":null},"volume":{"min":null,"max":null},"reviews":{"min":null,"max":null},"ratings":{"min":null,"max":null},"searchVolume":{"min":null,"max":null},"searchChange30":{"min":null,"max":null},"sellers":{"min":null,"max":null},"products":{"min":null,"max":null},"productViews":{"min":null,"max":null},"conversionSharing":{"min":null,"max":null},"marketSpace":{"min":null,"max":null},"categories":null,"keywords":[],"matchType":0,"searchDate":"","page":{"pageNumber":1,"pageSize":"1","orders":[{"field":"searchVolume","direction":"DESC"}]}}'
```

### 响应示例

JSON复制

```
{
  "code": 200,
  "msg": "SUCCESS",
  "data": {
    "records": [
      {
        "id": "69e7c423d1fd12d9b571ac1b",
        "query": "кроссовки женские",
        "queryCn": "女士运动鞋",
        "platform": 0,
        "categoryInfos": [
          {
            "id": "15621032_15621048_91248",
            "titleRu": "Кроссовки",
            "titlePath": "Обувь > Повседневная обувь > Кроссовки",
            "titleCn": "运动鞋",
            "cnTitlePath": "鞋类 > 休闲鞋 > 运动鞋",
            "titleEn": "Athletic Shoes",
            "enTitlePath": "Footwear > Casual Footwear > Athletic Shoes",
            "crossBorderSellable": true
          }
        ],
        "categories": [
          "15621032_15621048_91248"
        ],
        "searchVolume": 1389359,
        "count30GrowthRate": 24.9,
        "avgPrice": 3112,
        "competingProducts": 4240,
        "itemsViews": 111.3,
        "sellers": 316,
        "ca": 16.5,
        "uniqQueriesWCa": 228853,
        "viewSharing": 35.1,
        "conversionSharing": 30.5,
        "withinThesaurus": null,
        "marketSpace": 328,
        "products": [
          {
            "title": "Кроссовки T.TACCARDI на высокой подошве дышащие",
            "sku": 1830568440,
            "ozonId": 1830568440,
            "advert": 0,
            "imageUrl": "https://ir.ozone.ru/s3/multimedia-1-4/wc300/9836771152.jpg"
          }
        ],
        "returnCancellationRate": 54.4,
        "productCount": 1015144,
        "count90GrowthRate": null,
        "weight": 849,
        "sales": 1062,
        "revenue": 2027351,
        "margin": null,
        "volume": 6.9,
        "reviews": 7777,
        "ratings": 4.6,
        "queryTime": "2026-04-21",
        "createTime": "2026-04-22 02:38:23"
      }
    ],
    "total": 576364,
    "size": 1,
    "current": 1,
    "currentSize": 1,
    "totalPages": 576364,
    "orders": []
  }
}
```

### 响应字段

| 字段                                             | 类型    | 示例                                                         | 说明                                          |
| :----------------------------------------------- | :------ | :----------------------------------------------------------- | :-------------------------------------------- |
| `code`                                           | number  | `200`                                                        | 状态码                                        |
| `msg`                                            | string  | `SUCCESS`                                                    | 返回文字描述                                  |
| `data`                                           | object  | `-`                                                          | 返回数据                                      |
| `data.records`                                   | array   | `-`                                                          | 数据集合                                      |
| `data.records.id`                                | string  | `69e7c423d1fd12d9b571ac1b`                                   | 记录id                                        |
| `data.records.query`                             | string  | `кроссовки женские`                                          | 关键词                                        |
| `data.records.queryCn`                           | string  | `女士运动鞋`                                                 | 关键词中文翻译                                |
| `data.records.categoryInfos`                     | array   | `-`                                                          | 类目信息                                      |
| `data.records.categoryInfos.id`                  | string  | `15621032_15621048_91248`                                    | 类目id                                        |
| `data.records.categoryInfos.titleRu`             | string  | `Кроссовки`                                                  | 类目名称                                      |
| `data.records.categoryInfos.titlePath`           | string  | `Обувь > Повседневная обувь > Кроссовки`                     | 类目路径                                      |
| `data.records.categoryInfos.titleCn`             | string  | `运动鞋`                                                     | 类目名称                                      |
| `data.records.categoryInfos.cnTitlePath`         | string  | `鞋类 > 休闲鞋 > 运动鞋`                                     | 类目路径                                      |
| `data.records.categoryInfos.titleEn`             | string  | `Athletic Shoes`                                             | 类目名称                                      |
| `data.records.categoryInfos.enTitlePath`         | string  | `Footwear > Casual Footwear > Athletic Shoes`                | 类目路径                                      |
| `data.records.categoryInfos.crossBorderSellable` | boolean | `true`                                                       | 类目跨境是否可售                              |
| `data.records.categories`                        | array   | `-`                                                          | 类目id数组                                    |
| `data.records.searchVolume`                      | number  | `1389359`                                                    | 月搜热度                                      |
| `data.records.count30GrowthRate`                 | number  | `24.9`                                                       | 月搜增长                                      |
| `data.records.avgPrice`                          | number  | `3112`                                                       | 平均价格                                      |
| `data.records.competingProducts`                 | number  | `4240`                                                       | 有销量商品                                    |
| `data.records.sellers`                           | number  | `316`                                                        | 卖家数                                        |
| `data.records.conversionSharing`                 | number  | `30.5`                                                       | 转化集中度                                    |
| `data.records.marketSpace`                       | number  | `328`                                                        | 市场空间                                      |
| `data.records.products`                          | array   | `-`                                                          | top10商品数据                                 |
| `data.records.products.title`                    | string  | `Кроссовки T.TACCARDI на высокой подошве дышащие`            | 商品标题                                      |
| `data.records.products.sku`                      | number  | `1830568440`                                                 | 商品sku                                       |
| `data.records.products.ozonId`                   | number  | `-`                                                          | 商品sku（已弃用）                             |
| `data.records.products.advert`                   | number  | `0`                                                          | 0: 非广告，1：广告                            |
| `data.records.products.imageUrl`                 | string  | `https://ir.ozone.ru/s3/multimedia-1-4/wc300/9836771152.jpg` | 商品图片链接                                  |
| `data.records.returnCancellationRate`            | number  | `54.4`                                                       | 退货取消率                                    |
| `data.records.productCount`                      | number  | `1015144`                                                    | 商品数                                        |
| `data.records.weight`                            | number  | `849`                                                        | 重量，单位g                                   |
| `data.records.sales`                             | number  | `1062`                                                       | 该关键词下销售额前100的商品最近30天的平均销量 |
| `data.records.revenue`                           | number  | `2027351`                                                    | 销售额                                        |
| `data.records.margin`                            | number  | `-`                                                          | 已弃用                                        |
| `data.records.volume`                            | number  | `6.9`                                                        | 体积，单位L                                   |
| `data.records.reviews`                           | number  | `7777`                                                       | 评论数                                        |
| `data.records.ratings`                           | number  | `4.6`                                                        | 评分                                          |
| `data.records.queryTime`                         | string  | `2026-04-21`                                                 | 查询时间                                      |
| `data.records.createTime`                        | string  | `2026-04-22 02:38:23`                                        | 创建时间                                      |
| `data.total`                                     | number  | `576364`                                                     | 符合筛选条件的商品数                          |
| `data.size`                                      | number  | `1`                                                          | （已弃用）                                    |
| `data.current`                                   | number  | `1`                                                          | （已弃用）                                    |
| `data.currentSize`                               | number  | `1`                                                          | （已弃用）                                    |
| `data.totalPages`                                | number  | `576364`                                                     | （已弃用）                                    |
| `data.orders`                                    | array   | `-`                                                          | （已弃用）                                    |



## Ozon 关键词挖掘

POST/open-api/keyword/mining/ozon

按筛选条件挖掘 Ozon 关键词和相关商品指标。

试一试

### Header 参数

| 参数            | 类型   | 必填 | 示例               | 说明    |
| :-------------- | :----- | :--- | :----------------- | :------ |
| `Authorization` | string | 是   | `Bearer {Api Key}` | API Key |

### Body 参数

| 参数                    | 类型    | 必填 | 示例                    | 说明                                                         |
| :---------------------- | :------ | :--- | :---------------------- | :----------------------------------------------------------- |
| `uniqQueriesWCa`        | object  | 否   | `-`                     | 加购数                                                       |
| `uniqQueriesWCa.min`    | integer | 否   | `-`                     | 最小加购数                                                   |
| `uniqQueriesWCa.max`    | integer | 否   | `-`                     | 最大加购数                                                   |
| `relevancy`             | object  | 否   | `-`                     | 相关度                                                       |
| `relevancy.min`         | number  | 否   | `-`                     | 最小相关度                                                   |
| `relevancy.max`         | number  | 否   | `-`                     | 最大相关度                                                   |
| `searchVolume`          | object  | 否   | `-`                     | 月搜热度                                                     |
| `searchVolume.min`      | integer | 否   | `-`                     | 最小月搜热度                                                 |
| `searchVolume.max`      | integer | 否   | `-`                     | 最大月搜热度                                                 |
| `ca`                    | object  | 否   | `-`                     | 加购转化率                                                   |
| `ca.min`                | number  | 否   | `-`                     | 最小加购转化率                                               |
| `ca.max`                | number  | 否   | `-`                     | 最大加购转化率                                               |
| `products`              | object  | 否   | `-`                     | 有销量商品                                                   |
| `products.min`          | integer | 否   | `-`                     | 最小有销量商品                                               |
| `products.max`          | integer | 否   | `-`                     | 最大有销量商品                                               |
| `wordCount`             | object  | 否   | `-`                     | 字数                                                         |
| `wordCount.min`         | integer | 否   | `-`                     | 最小字数                                                     |
| `wordCount.max`         | integer | 否   | `-`                     | 最大字数                                                     |
| `titleDensity`          | object  | 否   | `-`                     | 标题密度                                                     |
| `titleDensity.min`      | integer | 否   | `-`                     | 最小标题密度                                                 |
| `titleDensity.max`      | integer | 否   | `-`                     | 最大标题密度                                                 |
| `price`                 | object  | 否   | `-`                     | 平均价格，单位卢布                                           |
| `price.min`             | number  | 否   | `-`                     | 最小平均价格                                                 |
| `price.max`             | number  | 否   | `-`                     | 最大平均价格                                                 |
| `sellers`               | object  | 否   | `-`                     | 有销量卖家                                                   |
| `sellers.min`           | integer | 否   | `-`                     | 最小有销量卖家                                               |
| `sellers.max`           | integer | 否   | `-`                     | 最大有销量卖家                                               |
| `adRivalCount`          | object  | 否   | `-`                     | 广告竞品数                                                   |
| `adRivalCount.min`      | integer | 否   | `-`                     | 最小广告竞品数                                               |
| `adRivalCount.max`      | integer | 否   | `-`                     | 最大广告竞品数                                               |
| `productViews`          | object  | 否   | `-`                     | 商品可见度                                                   |
| `productViews.min`      | number  | 否   | `-`                     | 最小商品可见度                                               |
| `productViews.max`      | number  | 否   | `-`                     | 最大商品可见度                                               |
| `conversionSharing`     | object  | 否   | `-`                     | 转化集中度                                                   |
| `conversionSharing.min` | number  | 否   | `-`                     | 最小转化集中度                                               |
| `conversionSharing.max` | number  | 否   | `-`                     | 最大转化集中度                                               |
| `searchChange30`        | object  | 否   | `-`                     | 月搜增长                                                     |
| `searchChange30.min`    | number  | 否   | `-`                     | 最小月搜增长                                                 |
| `searchChange30.max`    | number  | 否   | `-`                     | 最大月搜增长                                                 |
| `marketSpace`           | object  | 否   | `-`                     | 市场空间                                                     |
| `marketSpace.min`       | integer | 否   | `-`                     | 最小市场空间                                                 |
| `marketSpace.max`       | integer | 否   | `-`                     | 最大市场空间                                                 |
| `includeKeywords`       | array   | 否   | `-`                     | 包含关键词数组                                               |
| `excludeKeywords`       | array   | 否   | `-`                     | 排除关键词数组                                               |
| `matchType`             | integer | 否   | `0`                     | 关键词匹配模式，0：精准，1：模糊                             |
| `keyword`               | string  | 是   | `наушники беспроводные` | 关键词                                                       |
| `page`                  | object  | 是   | `-`                     | 分页参数                                                     |
| `page.pageNumber`       | integer | 是   | `1`                     | 分页页码                                                     |
| `page.pageSize`         | integer | 是   | `1`                     | 分页每页条数，最大100                                        |
| `page.orders`           | array   | 是   | `-`                     | 排序规则                                                     |
| `page.orders.field`     | string  | 是   | `relevancy`             | 排序字段，支持：uniqQueriesWCa,ca,searchVolume,count30GrowthRate,relevancy,titleDensity,wordCount,avgPrice,competingProducts,productCount,sellers,adRivalCount,itemsViews,marketSpace,conversionSharing,returnCancellationRate |
| `page.orders.direction` | string  | 是   | `DESC`                  | DESC：倒序，ASC：正序                                        |

### 请求体

Request Body复制

```
{
  "uniqQueriesWCa": {
    "min": null,
    "max": null
  },
  "relevancy": {
    "min": null,
    "max": null
  },
  "searchVolume": {
    "min": null,
    "max": null
  },
  "ca": {
    "min": null,
    "max": null
  },
  "products": {
    "min": null,
    "max": null
  },
  "wordCount": {
    "min": null,
    "max": null
  },
  "titleDensity": {
    "min": null,
    "max": null
  },
  "price": {
    "min": null,
    "max": null
  },
  "sellers": {
    "min": null,
    "max": null
  },
  "adRivalCount": {
    "min": null,
    "max": null
  },
  "productViews": {
    "min": null,
    "max": null
  },
  "conversionSharing": {
    "min": null,
    "max": null
  },
  "searchChange30": {
    "min": null,
    "max": null
  },
  "marketSpace": {
    "min": null,
    "max": null
  },
  "includeKeywords": [],
  "excludeKeywords": [],
  "matchType": 0,
  "keyword": "наушники беспроводные",
  "page": {
    "pageNumber": 1,
    "pageSize": "1",
    "orders": [
      {
        "field": "relevancy",
        "direction": "DESC"
      }
    ]
  }
}
```

### 请求示例

cURL复制

```
curl "http://api.seerfar.cn/open-api/keyword/mining/ozon" \
  -X POST \
  -H "Authorization: Bearer <platform_api_key>" \
  -H "Content-Type: application/json" \
  -d '{"uniqQueriesWCa":{"min":null,"max":null},"relevancy":{"min":null,"max":null},"searchVolume":{"min":null,"max":null},"ca":{"min":null,"max":null},"products":{"min":null,"max":null},"wordCount":{"min":null,"max":null},"titleDensity":{"min":null,"max":null},"price":{"min":null,"max":null},"sellers":{"min":null,"max":null},"adRivalCount":{"min":null,"max":null},"productViews":{"min":null,"max":null},"conversionSharing":{"min":null,"max":null},"searchChange30":{"min":null,"max":null},"marketSpace":{"min":null,"max":null},"includeKeywords":[],"excludeKeywords":[],"matchType":0,"keyword":"наушники беспроводные","page":{"pageNumber":1,"pageSize":"1","orders":[{"field":"relevancy","direction":"DESC"}]}}'
```

### 响应示例

JSON复制

```
{
  "code": 200,
  "msg": "SUCCESS",
  "data": {
    "records": [
      {
        "id": "69e7beecd1fd12d9b55251cd",
        "query": "наушники беспроводные",
        "queryCn": "无线耳机",
        "platform": 0,
        "categoryInfos": null,
        "categories": [
          "15621042_17028929_504866264"
        ],
        "searchVolume": 1151374,
        "count30GrowthRate": 54.1,
        "avgPrice": 7869,
        "competingProducts": 1932,
        "itemsViews": 42.3,
        "sellers": 704,
        "ca": 22.1,
        "uniqQueriesWCa": 250730,
        "viewSharing": 11.3,
        "conversionSharing": 23.1,
        "withinThesaurus": null,
        "marketSpace": 596,
        "products": [
          {
            "title": "Беспроводные наушники с активным шумоподавлением ANC и микрофоном, Bluetooth, сенсорные, для телефона, TWS",
            "sku": 3452757705,
            "ozonId": 3452757705,
            "advert": 0,
            "imageUrl": "https://ir.ozone.ru/s3/multimedia-1-y/wc300/8939510962.jpg"
          }
        ],
        "returnCancellationRate": 16.3,
        "productCount": 335994,
        "titleDensity": 1,
        "wordCount": 2,
        "relevancy": 100,
        "absoluteRelevancy": 152,
        "adRivalCount": null
      }
    ],
    "total": 1000,
    "size": 1,
    "current": 1,
    "currentSize": 1,
    "totalPages": 1000,
    "orders": []
  }
}
```

### 响应字段

| 字段                                  | 类型   | 示例                                                         | 说明                 |
| :------------------------------------ | :----- | :----------------------------------------------------------- | :------------------- |
| `code`                                | number | `200`                                                        | 状态码               |
| `msg`                                 | string | `SUCCESS`                                                    | 返回文字描述         |
| `data`                                | object | `-`                                                          | 返回数据             |
| `data.records`                        | array  | `-`                                                          | 数据集合             |
| `data.records.id`                     | string | `69e7beecd1fd12d9b55251cd`                                   | 记录id               |
| `data.records.query`                  | string | `наушники беспроводные`                                      | 关键词               |
| `data.records.queryCn`                | string | `无线耳机`                                                   | 关键词中文翻译       |
| `data.records.categoryInfos`          | array  | `-`                                                          | 类目信息             |
| `data.records.categories`             | array  | `-`                                                          | 类目id数组           |
| `data.records.searchVolume`           | number | `1151374`                                                    | 月搜热度             |
| `data.records.count30GrowthRate`      | number | `54.1`                                                       | 月搜增长             |
| `data.records.avgPrice`               | number | `7869`                                                       | 平均价格             |
| `data.records.competingProducts`      | number | `1932`                                                       | 有销量商品           |
| `data.records.itemsViews`             | number | `42.3`                                                       | 商品可见度           |
| `data.records.sellers`                | number | `704`                                                        | 卖家数               |
| `data.records.ca`                     | number | `22.1`                                                       | 加购转化率           |
| `data.records.uniqQueriesWCa`         | number | `250730`                                                     | 加购数               |
| `data.records.conversionSharing`      | number | `23.1`                                                       | 转化集中度           |
| `data.records.marketSpace`            | number | `596`                                                        | 市场空间             |
| `data.records.products`               | array  | `-`                                                          | top10商品数据        |
| `data.records.products.title`         | string | `Беспроводные наушники с активным шумоподавлением ANC и микрофоном, Bluetooth, сенсорные, для телефона, TWS` | 商品标题             |
| `data.records.products.sku`           | number | `3452757705`                                                 | 商品sku              |
| `data.records.products.ozonId`        | number | `-`                                                          | 商品sku（已弃用）    |
| `data.records.products.advert`        | number | `0`                                                          | 0: 非广告，1：广告   |
| `data.records.products.imageUrl`      | string | `https://ir.ozone.ru/s3/multimedia-1-y/wc300/8939510962.jpg` | 商品图片链接         |
| `data.records.returnCancellationRate` | number | `16.3`                                                       | 退货取消率           |
| `data.records.productCount`           | number | `335994`                                                     | 商品数               |
| `data.records.titleDensity`           | number | `1`                                                          | 标题密度             |
| `data.records.wordCount`              | number | `2`                                                          | 字数                 |
| `data.records.relevancy`              | number | `100`                                                        | 相关度               |
| `data.total`                          | number | `1000`                                                       | 符合筛选条件的商品数 |
| `data.size`                           | number | `1`                                                          | （已弃用）           |
| `data.current`                        | number | `1`                                                          | （已弃用）           |
| `data.currentSize`                    | number | `1`                                                          | （已弃用）           |
| `data.totalPages`                     | number | `1000`                                                       | （已弃用）           |
| `data.orders`                         | array  | `-`                                                          | （已弃用）           |





## Ozon 关键词反查

POST/open-api/keyword/backSearch/ozon

按 SKU 和筛选条件反查 Ozon 关键词及搜索表现。

试一试

### Header 参数

| 参数            | 类型   | 必填 | 示例               | 说明    |
| :-------------- | :----- | :--- | :----------------- | :------ |
| `Authorization` | string | 是   | `Bearer {Api Key}` | API Key |

### Body 参数

| 参数                    | 类型    | 必填 | 示例       | 说明                                                         |
| :---------------------- | :------ | :--- | :--------- | :----------------------------------------------------------- |
| `uniqQueriesWCa`        | object  | 否   | `-`        | 加购数                                                       |
| `uniqQueriesWCa.min`    | integer | 否   | `-`        | 最小加购数                                                   |
| `uniqQueriesWCa.max`    | integer | 否   | `-`        | 最大加购数                                                   |
| `ca`                    | object  | 否   | `-`        | 加购转化率                                                   |
| `ca.min`                | number  | 否   | `-`        | 最小加购转化率                                               |
| `ca.max`                | number  | 否   | `-`        | 最大加购转化率                                               |
| `searchVolume`          | object  | 否   | `-`        | 月搜热度                                                     |
| `searchVolume.min`      | integer | 否   | `-`        | 最小月搜热度                                                 |
| `searchVolume.max`      | integer | 否   | `-`        | 最大月搜热度                                                 |
| `searchChange30`        | object  | 否   | `-`        | 月搜增长                                                     |
| `searchChange30.min`    | number  | 否   | `-`        | 最小月搜增长                                                 |
| `searchChange30.max`    | number  | 否   | `-`        | 最大月搜增长                                                 |
| `naturalRank`           | object  | 否   | `-`        | 自然排名                                                     |
| `naturalRank.min`       | integer | 否   | `-`        | 最小自然排名                                                 |
| `naturalRank.max`       | integer | 否   | `-`        | 最大自然排名                                                 |
| `adRank`                | object  | 否   | `-`        | 广告排名                                                     |
| `adRank.min`            | integer | 否   | `-`        | 最小广告排名                                                 |
| `adRank.max`            | integer | 否   | `-`        | 最大广告排名                                                 |
| `titleDensity`          | object  | 否   | `-`        | 标题密度                                                     |
| `titleDensity.min`      | number  | 否   | `-`        | 最小标题密度                                                 |
| `titleDensity.max`      | number  | 否   | `-`        | 最大标题密度                                                 |
| `wordCount`             | object  | 否   | `-`        | 字数                                                         |
| `wordCount.min`         | integer | 否   | `-`        | 最小字数                                                     |
| `wordCount.max`         | integer | 否   | `-`        | 最大字数                                                     |
| `products`              | object  | 否   | `-`        | 有销量商品                                                   |
| `products.min`          | integer | 否   | `-`        | 最小有销量商品                                               |
| `products.max`          | integer | 否   | `-`        | 最大有销量商品                                               |
| `adRivalCount`          | object  | 否   | `-`        | 广告竞品数                                                   |
| `adRivalCount.min`      | integer | 否   | `-`        | 最小广告竞品数                                               |
| `adRivalCount.max`      | integer | 否   | `-`        | 最大广告竞品数                                               |
| `productViews`          | object  | 否   | `-`        | 商品可见度                                                   |
| `productViews.min`      | number  | 否   | `-`        | 最小商品可见度                                               |
| `productViews.max`      | number  | 否   | `-`        | 最大商品可见度                                               |
| `conversionSharing`     | object  | 否   | `-`        | 转化集中度                                                   |
| `conversionSharing.min` | number  | 否   | `-`        | 最小转化集中度                                               |
| `conversionSharing.max` | number  | 否   | `-`        | 最大转化集中度                                               |
| `sellers`               | object  | 否   | `-`        | 有销量卖家                                                   |
| `sellers.min`           | integer | 否   | `-`        | 最小有销量卖家                                               |
| `sellers.max`           | integer | 否   | `-`        | 最大有销量卖家                                               |
| `exposure`              | object  | 否   | `-`        | 曝光贡献率                                                   |
| `exposure.min`          | number  | 否   | `-`        | 最小曝光贡献率                                               |
| `exposure.max`          | number  | 否   | `-`        | 最大曝光贡献率                                               |
| `conversion`            | object  | 否   | `-`        | 转化贡献率                                                   |
| `conversion.min`        | number  | 否   | `-`        | 最小转化贡献率                                               |
| `conversion.max`        | number  | 否   | `-`        | 最大转化贡献率                                               |
| `marketSpace`           | object  | 否   | `-`        | 市场空间                                                     |
| `marketSpace.min`       | integer | 否   | `-`        | 最小市场空间                                                 |
| `marketSpace.max`       | integer | 否   | `-`        | 最大市场空间                                                 |
| `includeKeywords`       | array   | 否   | `-`        | 包含关键词数组                                               |
| `excludeKeywords`       | array   | 否   | `-`        | 排除关键词数组                                               |
| `type`                  | array   | 否   | `-`        | 类型，传字符串数组，不传则不筛选，0:自然搜索词 1:广告搜索词  |
| `matchType`             | number  | 否   | `0`        | 关键词匹配模式，0：精准，1：模糊                             |
| `skuIds`                | array   | 是   | `-`        | 反查sku，最多20个sku                                         |
| `hasVariant`            | number  | 是   | `0`        | 0：不剔除变体，1：剔除变体                                   |
| `page`                  | object  | 是   | `-`        | 分页参数                                                     |
| `page.pageNumber`       | integer | 是   | `1`        | 分页页码                                                     |
| `page.pageSize`         | integer | 是   | `20`       | 分页每页条数，最大100                                        |
| `page.orders`           | array   | 是   | `-`        | 排序规则                                                     |
| `page.orders.field`     | string  | 是   | `exposure` | 排序字段支持：exposure,conversion,uniqQueriesWCa,ca,searchVolume,count30GrowthRate,naturalRank,adRank,titleDensity,wordCount,competingProducts,productCount,sellers,adRivalCount,itemsViews,marketSpace,conversionSharing,returnCancellationRate |
| `page.orders.direction` | string  | 是   | `DESC`     | DESC：倒序，ASC：正序                                        |

### 请求体

Request Body复制

```
{
  "uniqQueriesWCa": {
    "min": null,
    "max": null
  },
  "ca": {
    "min": null,
    "max": null
  },
  "searchVolume": {
    "min": null,
    "max": null
  },
  "searchChange30": {
    "min": null,
    "max": null
  },
  "naturalRank": {
    "min": null,
    "max": null
  },
  "adRank": {
    "min": null,
    "max": null
  },
  "titleDensity": {
    "min": null,
    "max": null
  },
  "wordCount": {
    "min": null,
    "max": null
  },
  "products": {
    "min": null,
    "max": null
  },
  "adRivalCount": {
    "min": null,
    "max": null
  },
  "productViews": {
    "min": null,
    "max": null
  },
  "conversionSharing": {
    "min": null,
    "max": null
  },
  "sellers": {
    "min": null,
    "max": null
  },
  "exposure": {
    "min": null,
    "max": null
  },
  "conversion": {
    "min": null,
    "max": null
  },
  "marketSpace": {
    "min": null,
    "max": null
  },
  "includeKeywords": [],
  "excludeKeywords": [],
  "type": [],
  "matchType": 0,
  "skuIds": [
    1061073694
  ],
  "historyDate": "",
  "hasVariant": 0,
  "page": {
    "pageNumber": 1,
    "pageSize": "20",
    "orders": [
      {
        "field": "exposure",
        "direction": "DESC"
      }
    ]
  }
}
```

### 请求示例

cURL复制

```
curl "http://api.seerfar.cn/open-api/keyword/backSearch/ozon" \
  -X POST \
  -H "Authorization: Bearer <platform_api_key>" \
  -H "Content-Type: application/json" \
  -d '{"uniqQueriesWCa":{"min":null,"max":null},"ca":{"min":null,"max":null},"searchVolume":{"min":null,"max":null},"searchChange30":{"min":null,"max":null},"naturalRank":{"min":null,"max":null},"adRank":{"min":null,"max":null},"titleDensity":{"min":null,"max":null},"wordCount":{"min":null,"max":null},"products":{"min":null,"max":null},"adRivalCount":{"min":null,"max":null},"productViews":{"min":null,"max":null},"conversionSharing":{"min":null,"max":null},"sellers":{"min":null,"max":null},"exposure":{"min":null,"max":null},"conversion":{"min":null,"max":null},"marketSpace":{"min":null,"max":null},"includeKeywords":[],"excludeKeywords":[],"type":[],"matchType":0,"skuIds":[1061073694],"historyDate":"","hasVariant":0,"page":{"pageNumber":1,"pageSize":"20","orders":[{"field":"exposure","direction":"DESC"}]}}'
```

### 响应示例

JSON复制

```
{
  "code": 200,
  "msg": "SUCCESS",
  "data": {
    "records": [
      {
        "id": "69e7c419d1fd12d9b5717883",
        "query": "кроссовки мужские",
        "queryCn": "男士运动鞋",
        "platform": 0,
        "categoryInfos": null,
        "categories": [
          "15621032_15621048_91248"
        ],
        "searchVolume": 1309433,
        "count30GrowthRate": 20.4,
        "avgPrice": 4690,
        "competingProducts": 4143,
        "itemsViews": 118.3,
        "sellers": 307,
        "ca": 12,
        "uniqQueriesWCa": 156603,
        "viewSharing": 16.8,
        "conversionSharing": 19,
        "withinThesaurus": null,
        "marketSpace": 316,
        "products": [
          {
            "title": "Кроссовки K2 collection Кроссовки мужские",
            "sku": 3480252496,
            "ozonId": 3480252496,
            "advert": 0,
            "imageUrl": "https://ir.ozone.ru/s3/multimedia-1-q/wc300/9175046066.jpg"
          }
        ],
        "returnCancellationRate": 47.7,
        "productCount": 1134829,
        "titleDensity": 0.3,
        "wordCount": 2,
        "absoluteRelevancy": null,
        "dimension": {
          "naturalRank": null,
          "adRank": null,
          "relateAdCount": null,
          "position": null,
          "relativeRank": null,
          "avgRivalRank": null,
          "relateCount": null,
          "avgAdRank": null,
          "adRivalCount": null,
          "advancedRankCount": null,
          "type": 0,
          "exposure": null,
          "conversion": null,
          "x": null,
          "productPositions": null,
          "cpm": null
        }
      }
    ],
    "total": 379,
    "size": 1,
    "current": 1,
    "currentSize": 1,
    "totalPages": 379,
    "orders": []
  }
}
```

### 响应字段

| 字段                                  | 类型   | 示例                                                         | 说明                            |
| :------------------------------------ | :----- | :----------------------------------------------------------- | :------------------------------ |
| `code`                                | number | `200`                                                        | 状态码                          |
| `msg`                                 | string | `SUCCESS`                                                    | 返回文字描述                    |
| `data`                                | object | `-`                                                          | 返回数据                        |
| `data.records`                        | array  | `-`                                                          | 数据集合                        |
| `data.records.id`                     | string | `69e7c419d1fd12d9b5717883`                                   | 记录id                          |
| `data.records.query`                  | string | `кроссовки мужские`                                          | 关键词                          |
| `data.records.queryCn`                | string | `男士运动鞋`                                                 | 关键词中文翻译                  |
| `data.records.platform`               | number | `0`                                                          | 平台，0：ozon, 1：wb            |
| `data.records.categoryInfos`          | array  | `-`                                                          | 类目信息                        |
| `data.records.categories`             | array  | `-`                                                          | 类目id数组                      |
| `data.records.searchVolume`           | number | `1309433`                                                    | 月搜热度                        |
| `data.records.count30GrowthRate`      | number | `20.4`                                                       | 月搜增长                        |
| `data.records.avgPrice`               | number | `4690`                                                       | 平均价格                        |
| `data.records.competingProducts`      | number | `4143`                                                       | 有销量商品                      |
| `data.records.itemsViews`             | number | `118.3`                                                      | 商品可见度                      |
| `data.records.sellers`                | number | `307`                                                        | 卖家数                          |
| `data.records.ca`                     | number | `12`                                                         | 加购转化率                      |
| `data.records.uniqQueriesWCa`         | number | `156603`                                                     | 加购数                          |
| `data.records.conversionSharing`      | number | `19`                                                         | 转化集中度                      |
| `data.records.marketSpace`            | number | `316`                                                        | 市场空间                        |
| `data.records.products`               | array  | `-`                                                          | top10商品数据                   |
| `data.records.products.title`         | string | `Кроссовки K2 collection Кроссовки мужские`                  | 商品标题                        |
| `data.records.products.sku`           | number | `3480252496`                                                 | 商品sku                         |
| `data.records.products.ozonId`        | number | `-`                                                          | 商品sku（已弃用）               |
| `data.records.products.advert`        | number | `0`                                                          | 0: 非广告，1：广告              |
| `data.records.products.imageUrl`      | string | `https://ir.ozone.ru/s3/multimedia-1-q/wc300/9175046066.jpg` | 商品图片链接                    |
| `data.records.returnCancellationRate` | number | `47.7`                                                       | 退货取消率                      |
| `data.records.productCount`           | number | `1134829`                                                    | 商品数                          |
| `data.records.titleDensity`           | number | `0.3`                                                        | 标题密度                        |
| `data.records.wordCount`              | number | `2`                                                          | 字数                            |
| `data.records.dimension`              | object | `-`                                                          | 维度数据                        |
| `data.records.dimension.naturalRank`  | number | `3`                                                          | 自然排名                        |
| `data.records.dimension.adRank`       | number | `3`                                                          | 广告排名                        |
| `data.records.dimension.type`         | number | `0`                                                          | 类型，0:自然搜索词 1:广告搜索词 |
| `data.records.dimension.exposure`     | number | `-`                                                          | 曝光贡献度                      |
| `data.records.dimension.conversion`   | number | `20`                                                         | 转化贡献度                      |
| `data.total`                          | number | `379`                                                        | 符合筛选条件的商品数            |
| `data.size`                           | number | `1`                                                          | （已弃用）                      |
| `data.current`                        | number | `1`                                                          | （已弃用）                      |
| `data.currentSize`                    | number | `1`                                                          | （已弃用）                      |
| `data.totalPages`                     | number | `379`                                                        | （已弃用）                      |
| `data.orders`                         | array  | `-`                                                          | （已弃用）                      |



## Ozon 创建评论分析任务

POST/open-api/review/analyse/ozon/task/add

批量提交评论分析任务。按去重后的 SKU 数预扣积分，实际单价见返回的 unitCost；任务异步执行。successTasks/failedTasks 是创建结果，PRE_DEDUCTED 不表示分析完成；重试命中已有结算时任务列表可能为空。 同一账号、同一平台并发创建任务时，如未取得锁，当前请求返回 6102，不创建任务、不扣积分；锁不按 API Key 或 SKU 区分。

试一试

### Header 参数

| 参数            | 类型   | 必填 | 示例               | 说明    |
| :-------------- | :----- | :--- | :----------------- | :------ |
| `Authorization` | string | 是   | `Bearer {Api Key}` | API Key |

### Body 参数

| 参数   | 类型          | 必填 | 示例            | 说明                                                         |
| :----- | :------------ | :--- | :-------------- | :----------------------------------------------------------- |
| `skus` | array<string> | 是   | `["149222760"]` | 商品 SKU 字符串数组；去重后须有 1～10 个，每个 SKU 为 1～15 位数字。 |

### 请求体

Request Body复制

```
{
  "skus": [
    "149222760"
  ]
}
```

### 请求示例

cURL复制

```
curl "http://api.seerfar.cn/open-api/review/analyse/ozon/task/add" \
  -X POST \
  -H "Authorization: Bearer <platform_api_key>" \
  -H "Content-Type: application/json" \
  -d '{"skus":["149222760"]}'
```

### 响应示例

JSON复制

```
{
  "code": 200,
  "msg": "SUCCESS",
  "data": {
    "settlementId": "settlement-example",
    "status": "PRE_DEDUCTED",
    "skuCount": 1,
    "unitCost": 200,
    "totalCost": 200,
    "freeCost": 200,
    "paidCost": 0,
    "reason": null,
    "successTasks": [
      {
        "sku": "149222760",
        "taskId": "task-example"
      }
    ],
    "failedTasks": []
  }
}
```

### 响应字段

| 字段                         | 类型          | 示例                 | 说明                                                         |
| :--------------------------- | :------------ | :------------------- | :----------------------------------------------------------- |
| `code`                       | integer       | `200`                | 业务状态码                                                   |
| `msg`                        | string        | `SUCCESS`            | 返回文字描述                                                 |
| `data`                       | object        | `-`                  | 批次额度结算及任务创建结果。                                 |
| `data.settlementId`          | string        | `settlement-example` | 批次结算 ID。                                                |
| `data.status`                | string        | `PRE_DEDUCTED`       | 额度结算状态：PREPARING、PRE_DEDUCTED、REJECTED、REFUND_PENDING 或 REFUNDED；PRE_DEDUCTED 不表示分析已完成。 |
| `data.skuCount`              | integer       | `1`                  | 去重后的 SKU 数量。                                          |
| `data.unitCost`              | integer       | `200`                | 本次每个 SKU 的实际积分单价。                                |
| `data.totalCost`             | integer       | `200`                | 本次预扣总积分。                                             |
| `data.freeCost`              | integer       | `200`                | 从免费额度预扣的积分。                                       |
| `data.paidCost`              | integer       | `0`                  | 从付费额度预扣的积分。                                       |
| `data.reason`                | string        | `-`                  | 结算状态原因；可能为 null。                                  |
| `data.successTasks`          | array<object> | `-`                  | 任务创建成功列表；重试命中已有结算时可能为 null。            |
| `data.successTasks[].sku`    | string        | `149222760`          | 创建成功的 SKU。                                             |
| `data.successTasks[].taskId` | string        | `task-example`       | 下游任务 ID。                                                |
| `data.failedTasks`           | array<object> | `-`                  | 任务创建失败列表；重试命中已有结算时可能为 null。            |
| `data.failedTasks[].sku`     | string        | `149222760`          | 创建失败的 SKU。                                             |
| `data.failedTasks[].reason`  | string        | `-`                  | 创建失败原因。                                               |

### 错误响应

| 状态码 | 说明                                                         | 示例                                                         |
| :----- | :----------------------------------------------------------- | :----------------------------------------------------------- |
| `200`  | SKU 列表为空                                                 | `{ "code": 400, "msg": "skus cannot be empty" }`             |
| `200`  | 去重后超过 10 个 SKU                                         | `{ "code": 400, "msg": "skus cannot be greater than 10" }`   |
| `200`  | SKU 格式非法                                                 | `{ "code": 400, "msg": "sku format error" }`                 |
| `400`  | 请求体类型错误                                               | `{ "code": 400, "msg": "Bad Request" }`                      |
| `200`  | SKU 已有任务                                                 | `{ "code": 5012, "msg": "Duplicate sku" }`                   |
| `200`  | 同账号、同平台并发创建任务导致锁竞争；SKU 可以相同或不同，本次不创建任务、不扣积分 | `{ "code": 6102, "msg": "Conflict caused by multiple people operating simultaneously." }` |
| `403`  | API Key 积分不足                                             | `{ "code": 8000, "msg": "Api Key limit exhausted" }`         |
| `200`  | 当前身份不支持                                               | `{ "code": 403, "msg": "forbidden" }`                        |
| `401`  | 未授权                                                       | `{ "code": 401, "msg": "Unauthorized" }`                     |
| `429`  | 请求过多                                                     | `{ "code": 429, "msg": "Too Many Requests" }`                |
| `500`  | 服务端错误                                                   | `{ "code": 500, "msg": "Server error" }`                     |

## Ozon 查评论分析报表

POST/open-api/review/analyse/ozon/report

查询当前用户已完成的评论分析任务报表。需先创建对应平台和 SKU 的任务；任务仍在执行或失败时返回相应业务状态码。

试一试

### Header 参数

| 参数            | 类型   | 必填 | 示例               | 说明    |
| :-------------- | :----- | :--- | :----------------- | :------ |
| `Authorization` | string | 是   | `Bearer {Api Key}` | API Key |

### Body 参数

| 参数       | 类型    | 必填 | 示例        | 说明                                                |
| :--------- | :------ | :--- | :---------- | :-------------------------------------------------- |
| `sku`      | integer | 是   | `149222760` | 已提交任务的商品 SKU。                              |
| `language` | string  | 是   | `CN`        | 分析语言枚举：CN、EN 或 RU；不是 zh-CN 等语言代码。 |

### 请求体

Request Body复制

```
{
  "sku": 149222760,
  "language": "CN"
}
```

### 请求示例

cURL复制

```
curl "http://api.seerfar.cn/open-api/review/analyse/ozon/report" \
  -X POST \
  -H "Authorization: Bearer <platform_api_key>" \
  -H "Content-Type: application/json" \
  -d '{"sku":149222760,"language":"CN"}'
```

### 响应示例

JSON复制

```
{
  "code": 200,
  "msg": "SUCCESS",
  "data": {
    "sku": 149222760,
    "userId": 123,
    "createTime": "2026-09-28 10:00:00",
    "advantages": [
      {
        "dimensionRu": "Качество",
        "dimensionCn": "质量",
        "count": 12,
        "proportion": 0.3
      }
    ],
    "disadvantages": [],
    "usageScenarios": [],
    "userCharacteristics": [],
    "unmetNeeds": [],
    "timePoints": [],
    "usageLocations": [],
    "userBehavior": [],
    "purchaseMotivations": [],
    "optSugges": {},
    "qaAnalysis": {}
  }
}
```

### 响应字段

| 字段                            | 类型                  | 示例                  | 说明                                               |
| :------------------------------ | :-------------------- | :-------------------- | :------------------------------------------------- |
| `code`                          | integer               | `200`                 | 业务状态码                                         |
| `msg`                           | string                | `SUCCESS`             | 返回文字描述                                       |
| `data`                          | object                | `-`                   | 评论分析报表。                                     |
| `data.sku`                      | integer               | `149222760`           | 商品 SKU。                                         |
| `data.userId`                   | integer               | `123`                 | 任务所属用户 ID。                                  |
| `data.createTime`               | string                | `2026-09-28 10:00:00` | 报表创建时间。                                     |
| `data.advantages`               | array<object>         | `-`                   | 优点分析项。                                       |
| `data.disadvantages`            | array<object>         | `-`                   | 缺点分析项。                                       |
| `data.usageScenarios`           | array<object>         | `-`                   | 使用场景分析项。                                   |
| `data.userCharacteristics`      | array<object>         | `-`                   | 用户特征分析项。                                   |
| `data.unmetNeeds`               | array<object>         | `-`                   | 未被满足的需求分析项。                             |
| `data.timePoints`               | array<object>         | `-`                   | 使用时刻分析项。                                   |
| `data.usageLocations`           | array<object>         | `-`                   | 使用地点分析项。                                   |
| `data.userBehavior`             | array<object>         | `-`                   | 用户行为分析项。                                   |
| `data.purchaseMotivations`      | array<object>         | `-`                   | 购买动机分析项。                                   |
| `data.advantages[].dimensionRu` | string                | `-`                   | 九类分析项结构相同；分析维度的俄文名称。           |
| `data.advantages[].dimensionCn` | string                | `-`                   | 九类分析项结构相同；分析维度的中文名称。           |
| `data.advantages[].count`       | integer               | `12`                  | 九类分析项结构相同；该维度的评论数量。             |
| `data.advantages[].proportion`  | number                | `0.3`                 | 九类分析项结构相同；该维度占比；以实际返回值为准。 |
| `data.optSugges`                | object<string,string> | `-`                   | 运营优化建议；键和值均为字符串。                   |
| `data.qaAnalysis`               | object<string,string> | `-`                   | 问答分析；键和值均为字符串。                       |

### 错误响应

| 状态码 | 说明                     | 示例                                                         |
| :----- | :----------------------- | :----------------------------------------------------------- |
| `400`  | 请求参数无效             | `{ "code": 400, "msg": "Bad Request" }`                      |
| `200`  | 无权查询或未找到所属任务 | `{ "code": 403, "msg": "forbidden" }`                        |
| `200`  | 任务正在获取评论         | `{ "code": 5057, "msg": "Review analysis task is getting reviews" }` |
| `200`  | 任务正在分析             | `{ "code": 5058, "msg": "Review analysis task is analyzing" }` |
| `200`  | 任务执行失败             | `{ "code": 5059, "msg": "Review analysis task failed" }`     |
| `200`  | 商品不存在               | `{ "code": 5001, "msg": "Review analysis task failed: product not exist" }` |
| `200`  | 商品无评论               | `{ "code": 5002, "msg": "Review analysis task failed: no review" }` |
| `401`  | 未授权                   | `{ "code": 401, "msg": "Unauthorized" }`                     |
| `429`  | 请求过多                 | `{ "code": 429, "msg": "Too Many Requests" }`                |
| `500`  | 服务端错误               | `{ "code": 500, "msg": "Server error" }`                     |

## Ozon 查评论词频

POST/open-api/review/analyse/ozon/wordFrequency

查询当前用户已完成的评论分析任务词频。需先创建对应平台和 SKU 的任务；任务仍在执行或失败时返回相应业务状态码。

试一试

### Header 参数

| 参数            | 类型   | 必填 | 示例               | 说明    |
| :-------------- | :----- | :--- | :----------------- | :------ |
| `Authorization` | string | 是   | `Bearer {Api Key}` | API Key |

### Body 参数

| 参数       | 类型    | 必填 | 示例        | 说明                                                |
| :--------- | :------ | :--- | :---------- | :-------------------------------------------------- |
| `sku`      | integer | 是   | `149222760` | 已提交任务的商品 SKU。                              |
| `language` | string  | 是   | `CN`        | 分析语言枚举：CN、EN 或 RU；不是 zh-CN 等语言代码。 |

### 请求体

Request Body复制

```
{
  "sku": 149222760,
  "language": "CN"
}
```

### 请求示例

cURL复制

```
curl "http://api.seerfar.cn/open-api/review/analyse/ozon/wordFrequency" \
  -X POST \
  -H "Authorization: Bearer <platform_api_key>" \
  -H "Content-Type: application/json" \
  -d '{"sku":149222760,"language":"CN"}'
```

### 响应示例

JSON复制

```
{
  "code": 200,
  "msg": "SUCCESS",
  "data": {
    "sku": 149222760,
    "userId": 123,
    "origin": [
      "качество"
    ],
    "sinicized": [
      "质量"
    ]
  }
}
```

### 响应字段

| 字段             | 类型          | 示例        | 说明               |
| :--------------- | :------------ | :---------- | :----------------- |
| `code`           | integer       | `200`       | 业务状态码         |
| `msg`            | string        | `SUCCESS`   | 返回文字描述       |
| `data`           | object        | `-`         | 评论分析词频结果。 |
| `data.sku`       | integer       | `149222760` | 商品 SKU。         |
| `data.userId`    | integer       | `123`       | 任务所属用户 ID。  |
| `data.origin`    | array<string> | `-`         | 原文词频结果。     |
| `data.sinicized` | array<string> | `-`         | 中文化词频结果。   |

### 错误响应

| 状态码 | 说明                     | 示例                                                         |
| :----- | :----------------------- | :----------------------------------------------------------- |
| `400`  | 请求参数无效             | `{ "code": 400, "msg": "Bad Request" }`                      |
| `200`  | 无权查询或未找到所属任务 | `{ "code": 403, "msg": "forbidden" }`                        |
| `200`  | 任务正在获取评论         | `{ "code": 5057, "msg": "Review analysis task is getting reviews" }` |
| `200`  | 任务正在分析             | `{ "code": 5058, "msg": "Review analysis task is analyzing" }` |
| `200`  | 任务执行失败             | `{ "code": 5059, "msg": "Review analysis task failed" }`     |
| `200`  | 商品不存在               | `{ "code": 5001, "msg": "Review analysis task failed: product not exist" }` |
| `200`  | 商品无评论               | `{ "code": 5002, "msg": "Review analysis task failed: no review" }` |
| `401`  | 未授权                   | `{ "code": 401, "msg": "Unauthorized" }`                     |
| `429`  | 请求过多                 | `{ "code": 429, "msg": "Too Many Requests" }`                |
| `500`  | 服务端错误               | `{ "code": 500, "msg": "Server error" }`                     |

## Ozon 查评论统计

POST/open-api/review/analyse/ozon/reviewStatistic

按 SKU 查询当前用户的评论统计。需已有对应平台和 SKU 的任务；任务状态与错误码由下游服务返回。统计字段见下表，相关数据缺失时字段可能为 null。任务失败时下游统一返回 5059，不细分商品不存在或无评论。

试一试

### Header 参数

| 参数            | 类型   | 必填 | 示例               | 说明    |
| :-------------- | :----- | :--- | :----------------- | :------ |
| `Authorization` | string | 是   | `Bearer {Api Key}` | API Key |

### Body 参数

| 参数  | 类型   | 必填 | 示例        | 说明                            |
| :---- | :----- | :--- | :---------- | :------------------------------ |
| `sku` | string | 是   | `149222760` | 商品 SKU 字符串，1～15 位数字。 |

### 请求体

Request Body复制

```
{
  "sku": "149222760"
}
```

### 请求示例

cURL复制

```
curl "http://api.seerfar.cn/open-api/review/analyse/ozon/reviewStatistic" \
  -X POST \
  -H "Authorization: Bearer <platform_api_key>" \
  -H "Content-Type: application/json" \
  -d '{"sku":"149222760"}'
```

### 响应示例

JSON复制

```
{
  "code": 200,
  "msg": "SUCCESS",
  "data": {
    "imageUrl": "https://example.com/product.jpg",
    "title": "Пример товара",
    "sku": "149222760",
    "reviewStatistic": {
      "sku": "149222760",
      "reviewCount": 22,
      "reviewRating": 4.5,
      "avgRating": null,
      "fiveStarCount": 18,
      "fiveStarPercent": 81.82,
      "fourStarCount": 2,
      "fourStarPercent": 9.09,
      "threeStarCount": 0,
      "threeStarPercent": 0,
      "twoStarCount": 0,
      "twoStarPercent": 0,
      "oneStarCount": 2,
      "oneStarPercent": 9.09,
      "updateTime": 1790566812
    }
  }
}
```

### 响应字段

| 字段                                    | 类型           | 示例         | 说明                                      |
| :-------------------------------------- | :------------- | :----------- | :---------------------------------------- |
| `code`                                  | integer        | `200`        | 业务状态码                                |
| `msg`                                   | string         | `SUCCESS`    | 返回文字描述                              |
| `data`                                  | object         | `-`          | 评论统计结果。                            |
| `data.imageUrl`                         | string \| null | `-`          | 商品首图 URL；无商品图片时可能为 null。   |
| `data.title`                            | string \| null | `-`          | 商品标题；可能为 null。                   |
| `data.sku`                              | string \| null | `149222760`  | 商品 SKU；商品信息未找到时可能为 null。   |
| `data.reviewStatistic`                  | object \| null | `-`          | 评论统计详情；尚无统计数据时可能为 null。 |
| `data.reviewStatistic.sku`              | string         | `149222760`  | 统计对应的商品 SKU。                      |
| `data.reviewStatistic.reviewCount`      | integer        | `22`         | 评论总数。                                |
| `data.reviewStatistic.reviewRating`     | number         | `4.5`        | 商品评论评分。                            |
| `data.reviewStatistic.avgRating`        | number \| null | `-`          | 平均评分；可能为 null。                   |
| `data.reviewStatistic.fiveStarCount`    | integer        | `18`         | 五星评论数。                              |
| `data.reviewStatistic.fiveStarPercent`  | number         | `81.82`      | 五星评论占比，单位 %。                    |
| `data.reviewStatistic.fourStarCount`    | integer        | `2`          | 四星评论数。                              |
| `data.reviewStatistic.fourStarPercent`  | number         | `9.09`       | 四星评论占比，单位 %。                    |
| `data.reviewStatistic.threeStarCount`   | integer        | `0`          | 三星评论数。                              |
| `data.reviewStatistic.threeStarPercent` | number         | `0.0`        | 三星评论占比，单位 %。                    |
| `data.reviewStatistic.twoStarCount`     | integer        | `0`          | 二星评论数。                              |
| `data.reviewStatistic.twoStarPercent`   | number         | `0.0`        | 二星评论占比，单位 %。                    |
| `data.reviewStatistic.oneStarCount`     | integer        | `2`          | 一星评论数。                              |
| `data.reviewStatistic.oneStarPercent`   | number         | `9.09`       | 一星评论占比，单位 %。                    |
| `data.reviewStatistic.updateTime`       | integer        | `1790566812` | 统计更新时间戳。                          |

### 错误响应

| 状态码 | 说明                     | 示例                                                         |
| :----- | :----------------------- | :----------------------------------------------------------- |
| `400`  | SKU 参数无效             | `{ "code": 400, "msg": "Bad Request" }`                      |
| `200`  | 无权访问或未找到所属任务 | `{ "code": 403, "msg": "forbidden" }`                        |
| `200`  | 任务正在获取评论         | `{ "code": 5057, "msg": "Review analysis task is getting reviews" }` |
| `200`  | 任务正在分析             | `{ "code": 5058, "msg": "Review analysis task is analyzing" }` |
| `200`  | 任务失败（不细分原因）   | `{ "code": 5059, "msg": "Review analysis task failed" }`     |
| `401`  | 未授权                   | `{ "code": 401, "msg": "Unauthorized" }`                     |
| `429`  | 请求过多                 | `{ "code": 429, "msg": "Too Many Requests" }`                |
| `500`  | 服务端错误               | `{ "code": 500, "msg": "Server error" }`                     |

## Ozon 查原始评论

POST/open-api/review/analyse/ozon/originalReview

按 SKU 查询当前用户的原始评论。需已有对应平台和 SKU 的任务；任务状态与错误码由下游服务返回。返回的评论可能包含变体 SKU。 任务失败时下游统一返回 5059，不细分商品不存在或无评论。

试一试

### Header 参数

| 参数            | 类型   | 必填 | 示例               | 说明    |
| :-------------- | :----- | :--- | :----------------- | :------ |
| `Authorization` | string | 是   | `Bearer {Api Key}` | API Key |

### Body 参数

| 参数  | 类型   | 必填 | 示例        | 说明                            |
| :---- | :----- | :--- | :---------- | :------------------------------ |
| `sku` | string | 是   | `149222760` | 商品 SKU 字符串，1～15 位数字。 |

### 请求体

Request Body复制

```
{
  "sku": "149222760"
}
```

### 请求示例

cURL复制

```
curl "http://api.seerfar.cn/open-api/review/analyse/ozon/originalReview" \
  -X POST \
  -H "Authorization: Bearer <platform_api_key>" \
  -H "Content-Type: application/json" \
  -d '{"sku":"149222760"}'
```

### 响应示例

JSON复制

```
{
  "code": 200,
  "msg": "SUCCESS",
  "data": {
    "skus": [
      "149222760"
    ],
    "reviews": [
      {
        "date": "2026-09-27",
        "ruDate": "2026-09-27",
        "author": "Покупатель",
        "star": 5,
        "text": "Хороший товар",
        "photos": [],
        "videos": [],
        "skus": "149222760"
      }
    ]
  }
}
```

### 响应字段

| 字段                    | 类型                  | 示例         | 说明                                        |
| :---------------------- | :-------------------- | :----------- | :------------------------------------------ |
| `code`                  | integer               | `200`        | 业务状态码                                  |
| `msg`                   | string                | `SUCCESS`    | 返回文字描述                                |
| `data`                  | object                | `-`          | 原始评论结果。                              |
| `data.skus`             | array<string>         | `-`          | 实际返回评论涉及的 SKU 列表，可能包含变体。 |
| `data.reviews`          | array<object>         | `-`          | 原始评论列表；无评论时可为空数组。          |
| `data.reviews[].date`   | string                | `2026-09-27` | 评论日期，格式 YYYY-MM-DD。                 |
| `data.reviews[].ruDate` | string                | `2026-09-27` | 俄区评论日期，格式 YYYY-MM-DD。             |
| `data.reviews[].author` | string \| null        | `-`          | 评论作者；可能为空。                        |
| `data.reviews[].star`   | integer               | `5`          | 评论星级。                                  |
| `data.reviews[].text`   | string \| null        | `-`          | 评论正文；可能为空。                        |
| `data.reviews[].photos` | array<string> \| null | `-`          | 评论图片 URL 列表；可能为空。               |
| `data.reviews[].videos` | array<string> \| null | `-`          | 评论视频 URL 列表；可能为空。               |
| `data.reviews[].skus`   | string                | `149222760`  | 该条评论对应的 SKU。                        |

### 错误响应

| 状态码 | 说明                     | 示例                                                         |
| :----- | :----------------------- | :----------------------------------------------------------- |
| `400`  | SKU 参数无效             | `{ "code": 400, "msg": "Bad Request" }`                      |
| `200`  | 无权访问或未找到所属任务 | `{ "code": 403, "msg": "forbidden" }`                        |
| `200`  | 任务正在获取评论         | `{ "code": 5057, "msg": "Review analysis task is getting reviews" }` |
| `200`  | 任务正在分析             | `{ "code": 5058, "msg": "Review analysis task is analyzing" }` |
| `200`  | 任务失败（不细分原因）   | `{ "code": 5059, "msg": "Review analysis task failed" }`     |
| `401`  | 未授权                   | `{ "code": 401, "msg": "Unauthorized" }`                     |
| `429`  | 请求过多                 | `{ "code": 429, "msg": "Too Many Requests" }`                |
| `500`  | 服务端错误               | `{ "code": 500, "msg": "Server error" }`                     |