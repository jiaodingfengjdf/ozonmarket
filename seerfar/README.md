# Seerfar · Ozon 选品台（v1.0）

**完全基于 Seerfar Open API 的独立系统**，替代此前所有 Ozon 前台抓取方案。

- 旧项目（`web/` `tools/` `docs/` `out/` 等）**原地封存，一个文件都没删、没改、没引用**；本目录零依赖旧代码。唯一例外：在根 `.gitignore` 追加了 4 行，用于排除新系统的凭证与运行产物。
- 不再需要：cookie 快照、CDP 调试 Chrome、abt 挑战、出口 IP 池、robots 节奏、MM 第三方凭证、Ozon Seller API 类目树。
- 数据源只剩一个：`http://api.seerfar.cn` + 一个 Bearer Key。

---

## 1. 实测事实（2026-11-12，不是文档推测）

| 项 | 结论 |
|---|---|
| 凭证 | 有效，`creditLimit=10000` |
| **计费** | **按调用次数扣，约 8~10 分/次，与 `pageSize` 无关**；`pageSize=1` 也扣 10 分。10000 分约够 1000~1250 次调用 |
| **限流** | 连续请求会触发 **HTTP 429**，连 `/open-api/quota` 一起被限 |
| 网络 | 偶发连接超时、`IncompleteRead`（响应体读到一半断开） |
| 系统代理 | 本机 `127.0.0.1:17891` 对出站请求不通，客户端默认禁用系统代理直连 |
| 查类目 | 一级 / 二级 ID **只返回大盘汇总**，`productList` 为空；**三级（叶子）类目才返回商品清单** |
| categoryIds | `查热销榜单` 的 `categoryIds` 传一级 ID 返回 0 行，同样只认三级 ID |
| 类目名称 | **`Ozon类目.xlsx` 本身就带三语名称**（6 列：类目ID / 英文名 / 俄文名 / 中文名 / 父类目ID / 层级，10021 行全填充），导入即 100% 命名。接口响应的 `categoryInfo` 只作为补充 |
| 评论分析任务 | **200 积分/SKU 的写操作**，默认拒绝，必须显式确认 |

这些约束直接决定了架构：**全局限速 + 磁盘缓存 + 积分预算 + 自动重试 + 本地落库**，否则 10000 分会在几分钟内烧完。

---

## 2. 目录结构

```
seerfar/
├── config.json              实际配置（含 API Key，已加入 .gitignore）
├── config.example.json      配置模板（Key 留空）
├── requirements.txt         仅 openpyxl，其余全是标准库
├── 启动选品台.bat            一键启动
├── sf_client.py             API 客户端：鉴权/限速/重试/缓存/预算/日志（20 个 endpoint）
├── sf_db.py                 SQLite 层：api_cache / api_log / category / product / keyword / shop
├── sf_catalog.py            类目字典：xlsx 导入 + 响应沉淀名称 + 树/搜索/解析
├── sf_select.py             选品业务：榜单/大盘/热词/挖词/反查/竞品/店铺/变体/评论 + 机会分
├── sf_export.py             XLSX / CSV 导出
├── cli.py                   命令行与自检
├── server.py                本地 Web 服务（标准库 http.server）
├── static/                  index.html / app.js / style.css
├── data/
│   ├── ozon_categories.xlsx  Seerfar 官方类目 ID 清单副本（10021 个）
│   └── seerfar.db            运行时 SQLite（自动生成）
└── export/                  导出的 XLSX
```

---

## 3. 安装与启动

前提：Python 3.10+（实测 3.13）、Windows。

```powershell
cd C:\Users\shenzhendeyi\Desktop\ozon数据\seerfar
pip install -r requirements.txt      # 只装 openpyxl
copy config.example.json config.json # 已有 config.json 则跳过；把 api.key 换成你的 Key
```

**方式 A：一键**
```powershell
.\启动选品台.bat
```
打开 <http://127.0.0.1:8900/>

**局域网访问（默认开启）**

服务默认监听 `0.0.0.0`，同一局域网内其它设备也能访问。启动时控制台会打印实际地址：

```
Seerfar Ozon 选品台已启动
  本机访问    http://127.0.0.1:8900/
  局域网访问  http://192.168.1.55:8900/
              其它网卡地址：http://198.18.0.1:8900/
  防火墙提示  局域网打不开时，请放行 TCP 8900 端口
```

- 多网卡机器（装了代理 / VPN / TUN）会列出多个地址，**首选是 `192.168.x.x` / `10.x.x.x` 这类真实局域网段**，
  `198.18.x.x` 是代理工具的虚拟网卡，同事通常连不上。
- 打不开：Windows 防火墙放行 TCP 8900（`netsh advfirewall firewall add rule name="Seerfar" dir=in action=allow protocol=TCP localport=8900`）。
- **注意安全**：局域网开放意味着同网段任何人都能调接口消耗你的积分、看你的选品条件与结果。
  只给自己用就改 `config.json` 的 `server.host` 为 `127.0.0.1` 后重启。

**方式 B：命令行**
```powershell
python server.py --port 8900
```

**方式 C：纯 CLI（不开网页）**
```powershell
python cli.py init                    # 首次：导入 10021 个类目 ID（本地，不扣积分）
python cli.py selftest                # 连通性自检（约 60 积分）
python cli.py stats                   # 配额 / 消耗 / 缓存 / 本地数据量
```

密钥也可用环境变量覆盖，避免写进文件：
```powershell
$env:SEERFAR_API_KEY="eyJ..."
```

---

## 4. CLI 速查

| 命令 | 作用 | 积分 |
|---|---|---|
| `python cli.py init` | 导入类目 ID 表 | 0 |
| `python cli.py stats` | 本地运行状态 | 0 |
| `python cli.py quota` | 查 Key 余额 | 0（但仍受限流约束） |
| `python cli.py selftest` | 6 个只读接口自检 | ≈60 |
| `python cli.py categories --search 服装` | 中文/俄文/ID 搜类目 | 0 |
| `python cli.py categories --enrich --level 1 --yes` | 补一级类目中文名 | ≈220（一次性） |
| `python cli.py top --size 50 --export` | 热销榜单 + 导出 XLSX | 10/页 |
| `python cli.py category 15621032_15621049_115951147 --size 20 --export` | 查类目：大盘 + 商品清单 + 排名 | 10/页 |
| `python cli.py category 15621031 --leaves` | 列出该类目下三级子类目（本地） | 0 |
| `python cli.py hotwords --size 50 --export` | 市场热词 | 10/页 |
| `python cli.py mining "наушники" --size 30` | 关键词挖掘 | 10/页 |
| `python cli.py backsearch 175924376` | 关键词反查 | 10/页 |
| `python cli.py product 175924376` | 竞品详情 + 日趋势 + 月度 | 20 |
| `python cli.py shop 7` | 店铺商品 | 10 |
| `python cli.py export --type products --limit 1000` | 从本地库导出 | 0 |
| `python cli.py rescore` | 重算本地库机会分（从 raw 还原） | 0 |
| `python cli.py cache-clear --yes` | 清缓存 | 0（但之后会重新扣费） |

**筛选参数**：`--price-min/--price-max`、`--monthly-sales-min`、`--review-count-max`、
`--review-rating-min`、`--search-volume-min`、`--sellers-max`、`--competing-products-max`、
`--market-space-min`、`--sort`、`--direction`、`--keyword`、`--category-ids`、`--creation-date`、
`--search-date` 等。`--pages N > 1` 与 `--enrich`、`cache-clear` 都需要 `--yes` 确认。

---

## 5. Web 界面：10 个独立页面

**每个功能是一个独立 HTML 页面**（独立 URL、独立标题、独立筛选表单、独立结果表），
顶部导航栏在 10 个页面间跳转，当前页高亮——不是单页里换表单：

| 导航项 | URL | 说明 | 筛选字段 |
|---|---|---|---|
| **在线选品** | `/` | 全站商品筛选：预设卡片 + 平铺条件 + 汇总洞察 + 明细表 | 67 |
| **市场热词** | `/hotwords` | 全站搜索热词：搜索量 / 30天增长 / 竞品数 / 市场空间 | 35 |
| **关键词挖掘** | `/mining` | 种子词扩展长尾词：相关度 / 标题密度 / CA / 广告对手 | 36 |
| **关键词反查** | `/backsearch` | 竞品 SKU 反查引流词：曝光 / 自然排名 / 广告排名 | 41 |
| **竞品详情** | `/product` | 单品销量 / 价格 / 库存 / 类目排名 / 日月趋势 | 3 |
| **类目大盘** | `/category` | 类目容量 / 均价 / 季节性 / 商品清单 | 50 |
| **店铺分析** | `/shop` | 店铺近 30 天商品、销售额、配送结构 | 48 |
| **本地商品库** | `/local-products` | 已落库商品快照（0 积分） | 3 |
| **本地关键词库** | `/local-keywords` | 已落库关键词（0 积分） | 3 |
| **调用日志** | `/logs` | 调用耗时 / 缓存命中 / 积分消耗 | 1 |

- 页面文件在 `static/` 下一一对应：`index.html` `hotwords.html` `mining.html` `backsearch.html`
  `product.html` `category.html` `shop.html` `local-products.html` `local-keywords.html` `logs.html`。
- **筛选条件按官方接口参数全量补齐**：每个页面的区间 / 枚举 / 文本条件都对应该接口的真实字段；
  已选条件标签化（每条可单个 × 删除）。
- **左侧类目树**只在用得上的页面显示（在线选品 / 市场热词 / 类目大盘），其它页面自动全宽；
  已选类目跨页面保留（sessionStorage），切换页面不丢勾选。
- **汇总洞察卡片**（在线选品 / 类目大盘 / 店铺分析）：命中数、均价、均月销、均月GMV、均评分、均毛利率。
- **商品明细表 36 列**，产品数据前置、按选品动线分组：图/SKU/标题 → **产品数据（重量/体积/尺寸）** → 类目/品牌/店铺/卖家类型/配送 → 价格与销售（价格/平均折扣/月销量/环比/月销售额/销售额增长/毛利率）→ 口碑与售后（评论数/评分/问答数/退货取消率）→ 流量与转化漏斗（展示总量/曝光量/产品卡浏览/搜索加购率/购物车转化率/展示转化/订单转化）→ 广告与促销（广告费用份额/促销销售占比）→ 上架时间/上架天数/变体数 → 机会分。**率/占比/折扣类数值统一带 %**；产品图 76px（约两倍缩略图）。点 SKU 开详情抽屉、表头本地排序、涨跌着色（涨红跌绿）、一键导出 XLSX（48 列同顺序）。
- **列表 / 卡片双视图**：结果区右上角「☰ 列表 / ▦ 卡片」一键切换（在线选品 / 类目大盘 / 店铺分析 / 本地商品库四个商品页通用）。
  卡片模式 = 大图（1:1）+ 折扣角标 + 两行标题 + 评分行（★评分 · 评论数 · 上架时间）+ 价格行（价格 / 折扣% / 月销）+ SKU/类目脚注，
  自适应网格排布，点卡片任意位置开详情抽屉；**选择会记住**（localStorage，换页/刷新保持）。
- 快捷键：`Enter` 查询、`Esc` 关闭抽屉。

### 5.1 条件与 Seerfar 官方字段的对应关系（重要）

「查热销榜单」`/open-api/productReport/search/ozon` 是主查询引擎。**能接的都接了，接不上的明确禁用，不做假实现**。

| 界面条件 | 官方字段 | 状态 |
|---|---|---|
| 标题 / 平台热词 | `keywords` | ✅ |
| 商品ID、商品链接 | `skus`（≤10，链接自动提取 SKU） | ✅ |
| 店铺ID / 店铺名称 | `sellerName` | ✅ |
| 品牌名称 + 包含/排除/无品牌 | `brand: {type, brandName}` | ✅ |
| 价格 (₽) | `price {min,max}` | ✅ |
| 30 天销量 | `monthlySales` | ✅ |
| 30 天销量环比 % | `monthlySalesRate` | ✅ |
| 30 天销售额 | `monthlyRevenue` | ✅ |
| 总评论数 / 评分 | `reviewCount` / `reviewRating` | ✅ |
| 重量 (kg) | `weight`（官方单位 g，界面自动 ×1000） | ✅ |
| 转化率 % | `convToCartPdp`（购物车转化率） | ◐ 口径近似，界面已标注 |
| 上架日期 + 最近15/30/60/90/180/365天 | `creationDate` 枚举 + 结果侧按 `upTime` 精确过滤 | ◐ 官方无任意日期区间 |
| 商品状态 | `filterRemoveProduct`（过滤下架） | ◐ 仅此一项，其余状态无字段 |
| 仓储 / 配送 | `fulfillment`：OZON / FBO / FBS / RFBS / FBP | ✅ |
| 商品标签 | `labels`：0新品 / 1正品 / 2畅销品 | ✅ |
| 跨境可售 / 店铺类型 | `crossBorderSellable` / `sellerType` | ◐ 响应字段，结果侧本地过滤 |
| 变体合并 / 每页 / 排序 / 历史月 | `variationsMerge` / `page` / `searchDate` | ✅ |
| 更多官方条件（可展开） | `grossMargin` `drr` `questionsAndAnswers` `variants` `volume` `returnCancellationRate` `sellers` `ratingsRate` | ✅ 8 组区间 |
| 类目多选 | `categoryIds`（三级 ID，最多 20 个） | ✅ |
| BSR 排名 / 库存数 / 评论率 / 30天商品量 / 是否跟卖 | — | **官方无对应字段，界面已移除这些条件**（不保留置灰控件干扰使用）。库存按 SKU 走「竞品详情」查看 |

### 5.2 直达链接

```
http://127.0.0.1:8900/                    # 在线选品
http://127.0.0.1:8900/hotwords            # 市场热词
http://127.0.0.1:8900/mining              # 关键词挖掘
http://127.0.0.1:8900/backsearch          # 关键词反查
http://127.0.0.1:8900/product             # 竞品详情
http://127.0.0.1:8900/category            # 类目大盘
http://127.0.0.1:8900/shop                # 店铺分析
http://127.0.0.1:8900/local-products      # 本地商品库
http://127.0.0.1:8900/local-keywords      # 本地关键词库
http://127.0.0.1:8900/logs                # 调用日志

# 带参数（任意页面通用）
http://127.0.0.1:8900/?cat=15621032_15621049_115951147   # 带入一个类目（选品/热词/类目页）
http://127.0.0.1:8900/?parent=17027494                   # 类目树直接定位到该分支
http://127.0.0.1:8900/?auto=1                            # 打开即执行一次查询（分享/自动化验收）
```

### 5.3 类目大盘 / 查类目

导航栏点「类目大盘」（`/category`）可单独用 `/open-api/category/detail/search/ozon`：按类目 ID + 日期 +
全量筛选查类目商品、销量、销售额、季节性；一级/二级只有大盘，三级才有商品清单。
CLI：`python cli.py category <ID> --leaves` 列三级子类目（0 积分），
`python cli.py category <三级ID> --size 50 --price-min 1000 --fulfillment FBO --export`。
`categoryRank / naturalRank / adRank` 官方标注「已弃用」且实测返回 `null`，导出列保留并标注；
类目排名走势看「竞品详情」的 `categoryRanks`。

---

## 6. 类目体系（重要）

用户提供的 `Ozon类目.xlsx` 共 **10021 个类目：29 一级 / 618 二级 / 9374 三级**，
**6 列：类目ID / 类目名称（英文）/ 类目名称（俄文）/ 类目名称（中文）/ 父类目ID / 层级**，
10021 行名称全部填充，已复制进 `data/ozon_categories.xlsx`，系统自包含。

- 导入后 **100% 有中文名 + 三语全路径**（路径由本地按 ID 层级拼接，不调接口、0 积分）。
- ID 即层级路径：`15621032_15621049_115951147`，父 ID = 去掉最后一段；**不需要任何跨体系映射**。
- **Seller API 的 `description_category_id` 与这套 ID 完全不通用**，不要把 Seller 类目 ID 传给 `categoryId`（实测返回 `data: null`）。此前设计的 Seller 桥接方案已废弃。
- **一级/二级只有大盘，三级才有商品清单**；左侧勾选父节点会自动收集其下三级 ID 参与筛选。
- 接口响应里的 `categoryInfo` 只作补充（表外新增类目），**命名以 xlsx 为权威**。

> 修正记录：早期版本误以为该表只有「类目ID」一列（读取时只取了 `row[0]`，漏掉后 5 列），
> 曾花约 430 积分调接口补类目名。现已改为按表头定位 6 列读取，命名不再消耗任何积分。

---

## 7. 积分与稳定性保护（核心设计）

| 机制 | 实现 |
|---|---|
| 全局限速 | 任意两次真实请求最小间隔 `min_interval=1.3s`（±35% 抖动），线程锁串行 |
| 自动重试 | 429 / 5xx / 超时 / `IncompleteRead` / `RemoteDisconnected` 指数退避 `[3,8,20]s`，最多 3 次 |
| 磁盘缓存 | `endpoint + body` 的 SHA256 作 key 存入 SQLite；日级数据 24h、榜单 6h、竞品 12h、月度趋势 72h。**命中缓存不发起请求、不扣积分** |
| 预算保护 | `daily_credit_limit=1500`、`single_run_credit_limit=800`；超预算直接抛 `BudgetExceeded` 拒绝调用 |
| 熔断 | 收到业务码 `8000`（积分耗尽）立即置 `_fused`，本进程不再发起任何付费调用 |
| 写操作确认 | `review_task` 必须 `confirm=True`；Web 端先返回 `need_confirm + estimated_credit`，二次确认才执行 |
| 调用日志 | 每次调用记录接口、耗时、是否命中缓存、估算积分，界面「本地库」页可查 |
| 落库 | 所有商品/关键词/店铺结果写入 SQLite，可离线查询与导出，避免重复扣费 |

调预算：改 `config.json` 的 `budget` 段。想省积分就调大 `cache.default_ttl`、多用「本地库」页。

---

## 8. 服务端 API（供二次开发）

统一响应 `{"ok":true,"data":...,"meta":{...}}` 或 `{"ok":false,"error":"...","type":"..."}`。

```
GET  /api/status                    配额 / 消耗 / 缓存 / 本地统计
GET  /api/categories?level=1&parent=&q=   类目树 / 搜索
POST /api/categories/enrich         补中文名（先无 confirm 拿预估，再带 confirm 执行）
GET  /api/filters                   列定义与排序字段白名单
POST /api/top                      {filters:{...}, force:false}
POST /api/category                 {category_id:"...", filters:{...}}
POST /api/hotwords                 {filters:{...}}
POST /api/mining                   {keyword:"...", filters:{...}}
POST /api/backsearch               {skus:[...], filters:{...}}
GET  /api/product?sku=&date_range=  竞品详情
GET  /api/shop?id=                 店铺
GET  /api/variations?sku=         商品变体
GET  /api/reviews?sku=&type=stat|original|words|report
POST /api/reviews/task             评论分析任务（需 confirm）
GET  /api/local/products|keywords  本地库（不扣积分）
GET  /api/logs                     调用日志
POST /api/export                   {kind, rows} → XLSX
GET  /api/download?file=           下载导出文件
POST /api/cache/clear              清缓存（需 confirm）
```

所有查询接口都接受 `filters.pages`（1~10）：`pages>1` 且未带 `confirm:true` 时，返回
`{"need_confirm":true,"pages":N,"estimated_credit":X}`，带 `confirm:true` 才真正翻页抓取。

---

## 9. 已知约束 / 排障

| 现象 | 原因与处理 |
|---|---|
| `429 Too Many Requests` | 客户端会自动退避重试。若持续出现，调大 `api.min_interval` |
| `BudgetExceeded` | 本地预算挡住了付费调用，属预期行为。提高 `budget.daily_credit_limit` 或等次日 / 用缓存数据 |
| `8000 积分耗尽` | 已熔断，需充值或换 Key，重启服务 |
| 一级类目查不出商品 | 官方只返回大盘。左侧勾选父节点会自动收集其下三级 ID 参与榜单筛选；要看类目汇总切右上角「类目大盘」工具 |
| `data: null` | 传了无效/未收录的 `categoryId`，或该类目无数据 |
| 类目显示一串数字 | 该节点中文名还没沉淀；点「补全一级类目中文名」或查一次该类目即可补上 |
| 全部请求 SSL 握手超时 | 本机系统代理不通；`api.disable_proxy` 保持 `true` |
| `IncompleteRead` | 网络抖动，已自动重试；频繁出现检查网络 |
| 导出文件名是英文 | 刻意使用 ASCII 文件名，避免 HTTP 下载头编码问题 |

**未实现**：评论分析任务的自动轮询（创建后需另调报表接口）；批量定时任务。
**不做**：任何形式的 Ozon 页面抓取、cookie 复用、挑战绕过 —— 这些正是本系统要替换掉的东西。

---

## 9.1 阶段 1 修正（已上线，2026-11-13）

这一批修的是「界面能选、后端没发 / 发了但只作用于本页」这类**假生效**问题：

| 修正 | 之前 | 现在 |
|---|---|---|
| **市场热词页左侧类目树** | 勾选后不进请求，永远是全站热词 | `collectForm` 把已选类目注入 `categories`（≤20），后端 `hot_words` 同时兼容 `categories / category_ids / category_id` |
| **店铺分析页 7 个条件** | 界面有 `fulfillment / labels / brands / brand_type / keywords / tag / creation_date`，后端只发区间与 SKU | 全部按官方 Body 表透传；响应 `applied` 里可核对实际发送内容 |
| **评论接口语言** | 传 `zh-CN`（官方枚举是 `CN/EN/RU`），`sku` 传字符串 | `language` 归一为 `CN/EN/RU`，词频/报表的 `sku` 转 int，非数字直接报错 |
| **本地过滤冒充全站过滤** | 跨境 / 店铺类型 / 上架日期只过滤当前页，`filtered_out` 前端不显示 | 返回 `local_filter{fields,filtered_out,scope}`，结果区红字提示「仅作用于本页 N 行，不是全站」 |
| **表头排序** | 只对已加载的 20~50 行排序，用户以为全站降序 | 能映射到官方排序字段的列 → 改写表单 `sort/direction` 并**重新请求**（服务端排序）；映射不到的列明确提示「仅对当前 N 行排序」 |
| **导出** | 只导出当前页 | 导出前若命中数 > 当前行数，提示「抓取 M 页（约 X 积分）后再导出」，确认后自动翻页抓取再导出 |
| **多页抓取** | CLI 有 `--pages`，网页没有 | 每个查询页底部新增「抓取 [1~10] 页」；`pages>1` 时后端先返回 `need_confirm + estimated_credit`，前端弹确认后才执行（按页计费，命中缓存 0 积分） |
| **关键词反查** | 没传文档里的 `type`（自然/广告），SKU 数量无校验 | 新增「词类型」自然/广告多选；`skuIds` 超过 20 或为空直接 400 报错 |
| **评论 `sku` 校验 / 类目 ID 归一** | 任何输入都直接透传 | `_sku_int()` 严格数字校验；`_ids_list()` 兼容数组/逗号串/单值并去重 |

多页抓取的计费口径：`pages × 单次成本（约 9~10 分）`，**同一参数再次抓取命中缓存不扣费**，所以重复导出不会重复烧积分。
分页控件同时兼容 `totalPages`（榜单/关键词）与 `hasNextPage`（查类目/查店铺），后者不会再无限往下翻。

自测（不消耗积分，用假客户端断言 Body）：
```powershell
python tools/test_stage1.py      # 39 项断言：条件透传 / 多页去重 / 语言枚举 / 上限校验 / 本地过滤标注
```

---

## 9.2 阶段 2 修正（已上线，2026-11-13）

这一批把「后端已经写好、界面完全没有入口」的 10 个接口接到界面上，并补了 3 条缺失路由。

| 能力 | 涉及接口 | 界面位置 | 花费 |
|---|---|---|---|
| **店铺品牌结构** | 查店铺品牌（`shop_brand`） | 店铺分析页「品牌结构」卡片：品牌数、店铺总销额/总销量、Top10 销售额占比，逐品牌 销售额/占本页%/Top10 份额%/商品数/有销量商品/均价/均销/均评分/均评论/卖家数/退货率 | 约 9 分/次 |
| **店铺类目结构** | 查店铺类目（`shop_category`） | 店铺分析页「类目结构」卡片：类目路径、销售额、占本页%、销量、商品数、均价、销额/销量增长 | 约 9 分/次 |
| **变体列表** | 查商品变体（`var_search`） | 竞品详情页「变体分析」→ 变体列表：SKU、**变体特征（有效期:1 год 这类）**、价格、月销/销额、评论、评分、上架日 | 约 9 分/次 |
| **变体特征 + Top10** | 变体特征（`var_chars`）+ Top 变体（`var_top`） | 先点「特征维度」拿到维度（颜色/有效期…），再点维度看该维度销售额榜与销量榜 Top10 | 各约 9 分/次 |
| **评论星级分布** | 评论统计（`review_stat`） | 竞品页「评论分析」→ 星级分布：评论总数、商品评分、平均评分 + 5★~1★ 横条占比 | 约 9 分/次 |
| **评论词频** | 评论词频（`review_words`） | 中文词频 / 原文词频 双栏词条（语言可选 CN/EN/RU） | 约 9 分/次 |
| **原始评论** | 原始评论（`review_original`） | 星级 + 日期 + 作者 + 正文 + 评论图（最多 60 条） | 约 9 分/次 |
| **AI 报表** | 评论分析报表（`review_report`） | 九维分析（优点/缺点/场景/用户特征/未满足需求/使用时刻/地点/行为/购买动机）+ 运营建议 + 问答分析 | 约 9 分/次 |
| **创建分析任务** | 评论分析任务（`review_task`） | 竞品页「创建分析任务」按钮，明文 200 积分/SKU，弹窗二次确认 | 200 分/SKU |
| **相似商品** | 查相似商品（`similar`） | 新增独立路由 `GET /api/similar?sku=`，返回归一化商品行并**带库存**（供后续做对比矩阵） | 约 9 分/次 |

新增路由：`GET /api/shop/brands?id=&page=&size=`、`GET /api/shop/categories?id=&page=&size=`、`GET /api/similar?sku=`。

两处口径修正（实测发现，文档没写清）：
- **店铺品牌销售额字段是 `totalRevenues`（复数）**，不是 `totalRevenue`；代码已做双兼容，实测 id=7：`T.TACCARDI 22.7 亿₽ / 占本页 63.3% / 官方 Top10 份额 97.82%`。
- 评论 `words/report` 的 `language` 必须是 `CN/EN/RU`；`sku` 为 integer。已在阶段 1 修正，本阶段界面按枚举提供下拉。

自测（不消耗积分）：
```powershell
python tools/test_stage2.py      # 46 项断言：品牌/类目归一化、variation_text、评论四件套、路由与前端接线
```


---

## 9.3 阶段 3 修正（已上线，2026-11-13）

这一批把「本地库只是看板 / 机会分不可配 / 没有自己的成本账」补成可决策的工具。

### 9.3.1 本地库升级（0 积分）

- **扩表**：`product` 从 15 列扩到 **50 列**（重量/体积/尺寸/毛利率/DRR/加购率/转化率/退货率/变体数/问答数/曝光/浏览/上架天数/机会分/真毛利/净利/保本价/建议售价…），`keyword` 补 `title_density / relevancy / word_count / opportunity`。
- **自动迁移**：旧库启动时按 `PRAGMA table_info` 比对并 `ALTER TABLE ADD COLUMN`，无需手动重建。
- **筛选 + 分页**：`GET /api/local/products` 支持 `q`（标题/品牌/店铺/类目/SKU）、`price/sales/gross_margin/net_margin/opportunity/review_count/weight/…` 的 `_min/_max` 区间、`favorite_only=1`、`sort/direction/limit/offset`，返回 `{rows,total}`；关键词库同理。**所有过滤在 SQL 层完成，0 积分。**
- 界面：本地商品库/关键词库页各加了完整筛选表单 + 分页器（之前只有 `limit+sort`，等于看不全也筛不了）。

### 9.3.2 机会分可配 + 落库

- 权重与量纲移到 `config.json` 的 `opportunity` 段（默认商品：销量35/增长25/低竞争25/毛利转化15），**权重自动归一到 100**，改配置即改口径。
- 分数写入 `product.opportunity` / `keyword.opportunity`，支持本地库按机会分排序与区间筛选。
- 新增 `python cli.py rescore`：从历史 `raw` JSON 还原并重算本地库机会分（实测 170 条，0 积分）。

### 9.3.3 利润模型（自建成本账，0 积分）

`sf_profit.py` + `POST /api/profit`，把官方 `grossMargin` 换成可解释的账：

```
售价 − 采购(CNY×汇率) − 头程(计费重×单价×汇率) − 佣金(售价×%) − 支付(%) − 广告(DRR%) − 退货损耗(×0.5)
= 净利 → 真毛利率 = 净利/售价
保本价 = (采购+头程) / (1 − 佣金% − 支付% − 广告% − 退货%×0.5)
建议售价 = (采购+头程) / (1 − 上述合计 − 目标毛利%)
```

- 计费重 = `max(实重, 体积重)`，体积重 = `体积(cm³)/5000`（体积缺失时用 `dimension` 毫米串换算）；支持直接指定每件物流费覆盖。
- 广告费默认取商品自带 `drr`，也可手动覆盖；结果写回库（`net_profit / net_margin / breakeven / suggested`），可排序、可筛「真毛利率 ≥ X」。
- 界面：在线选品页新增「利润计算器」（9 个参数，localStorage 记忆，含「只看盈利」开关），算完表头立刻多出 净利/真毛利/保本价/建议售价 四列。
- 实测样例：售价 28 217₽、采购 40 CNY、头程 32 CNY/kg、佣金 15% → 计费重 16.97kg、头程 9 052₽、净利 13 868₽、真毛利 49.15%、保本 11 509₽、建议 16 470₽。

### 9.3.4 收藏 + 选品报告

- 表格首列 ★ 一键收藏（`POST /api/favorites/toggle`），本地库可「只看收藏」，`GET /api/favorites` 返回带商品字段的清单。
- 「导出选品报告」= 多 sheet XLSX：**选品结论**（时间/页面/筛选条件/利润参数/命中数/平均毛利/亏损行）→ **商品清单**（54 列，含净利与真毛利）→ **关键词**（关键词页）→ **收藏清单**。

新增/变更 API：

```
GET  /api/local/products?q=&price_min=&price_max=&opportunity_min=&favorite_only=1&sort=&direction=&limit=&offset=
GET  /api/local/keywords?q=&search_volume_min=&growth30_min=&kind=&sort=&limit=&offset=
GET  /api/favorites
POST /api/favorites/toggle      {sku, tags?, note?}
POST /api/profit                {rows:[...], params:{cost_cny, rate_cny_rub, shipping_cny_per_kg,
                                 commission_pct, payment_pct, drr_pct, return_pct,
                                 target_margin_pct, volumetric_divisor}, persist:true}
POST /api/export                {kind:"report", rows, keywords?, favorites?, meta?, filename?}
```

自测（0 积分）：
```powershell
python tools/test_stage3.py     # 53 项：迁移/筛选分页/收藏/机会分可配/利润公式/报告 sheet/接线
```

---

## 9.4 阶段 4：商品内容（属性 / 描述 / 图片 / 变体）——补 Seerfar 的空白

**为什么之前没有**：Seerfar Open API 的 17 个接口全是「市场数据」，`查竞品` 返回的字段里没有
`attributes / description / richContent / hashtags`；它只有 `labels`（0 新品 / 1 正品 / 2 畅销品）
和用于筛选的 `tag` 词，以及 `变体特征`（只是给变体 Top 用的维度名）。所以属性表、描述、富文本、
真正的前台标签，**Seerfar 一条都拿不到**。

**怎么补的**：走 Ozon 前台自己的 Composer API。

```
GET https://www.ozon.ru/api/composer-api.bx/page/json/v2?url=/product/{sku}/
```

实测（2026-11-13）要点：

| 坑 | 结论 |
|---|---|
| 直接 HTTP | `307` → 带 cookie 再请求变 `403`（返回 `incidentId` 反爬拦截页） |
| 必须真实浏览器 | 用本机 Chrome/Edge `--headless=new` + **真实 UA**（默认 UA 带 `HeadlessChrome` 会被识别）；`--dump-dom` 打开上面的 URL，浏览器自动带通行 cookie，返回 `<pre>{...}</pre>` |
| 一份 JSON 全都有 | `seo.script[0].innerHTML` = JSON-LD（标题/描述/品牌/评分/评论数/价格/图片）；`webShortCharacteristics` = 属性表；`webAspects` = 变体维度（每个值带 SKU 与价格）；`webGallery` = 主图；`webPrice` = 现价/卡价/原价；`tapTags` = 标签 |
| 富文本 | **拿不到**：当前 PDP 不再返回 `richAnnotation` widget（新旧 layout 都不含）。要真富文本 HTML 只能走 Seller API（需要卖家 client_id/api_key） |

新增能力：

- `sf_content.py`：`fetch(sku)` → 浏览器抓 composer → 解析出
  `title / brand / rating / review_count / price / card_price / original_price / description /
   attributes[] / aspects[] / images[] / tags[] / rich`。
- 缓存表 `product_content`（默认 72h，`config.json → content.ttl_hours`），命中直接 0 请求。
- API：`GET /api/content?sku=149710140[&refresh=1]`（0 积分，与 Seerfar 额度无关）。
- 界面：竞品详情页新增「商品内容（Ozon 前台）」卡片——属性两列表、变体维度 chips（点 chip 直接开该变体 SKU）、
  描述、标签、图片墙；顶部显示来源 / 抓取时间 / 是否命中缓存。
- CLI：`python cli.py content --sku 149710140 [--refresh]`。

实测样例（`149710140`，首次 5~10 秒，第二次 0.07 秒）：
```
标题: Кофе растворимый Нескафе Голд, 500 г   品牌: НЕСКАФÉ   评分 4.9 / 1 181 144 条评论
价格 1 099₽（卡价 1 072₽，原价 1 759₽）      描述 1 733 字
属性 5 组：Тип=Кофе растворимый / Бренд=НЕСКАФÉ / Технология производства=Сублимированный …
变体 2 维：Вес товара, г → 47.50 / 75 / 85 …；Название вкуса → Голд / Голд Бариста …（每个值带 SKU+价格）
图片 10 张
```

配置（`config.json → content`）：
```json
"content": { "enabled": true, "chrome": "", "timeout_ms": 45000, "ttl_hours": 72, "min_interval": 1.5 }
```
`chrome` 留空自动探测 Chrome/Edge；`timeout_ms` 是浏览器渲染预算；`min_interval` 控制抓取间隔（对 Ozon 友好）。

限制与注意：
- 单次抓取要起一次浏览器，**5~15 秒**，请用缓存；批量抓请串行（`min_interval` 已做节流）。
- Ozon 反爬随时可能升级，若返回「非 JSON / 拦截页」，`sf_content` 会明确报错并提示 UA/浏览器问题。
- 只抓公开 PDP，不登录、不碰 Seller 后台；不含库存/物流的私有数据。

**实测边界（3 个 SKU，2026-11-13）**——不要抱不切实际的期待：

| 内容 | 能否拿到 | 说明 |
|---|---|---|
| 描述正文 | ✅ | JSON-LD `description`，本例 1 733 字（纯文本，无 HTML 结构） |
| 属性表 | ◐ **只有「О товаре」那一组** | 3 个 SKU 都是 5 条（咖啡：Тип/Бренд/Технология/Состав/Без кофеина；手机：屏幕/电池/CPU/材质…）。完整「Все характеристики」不再由 composer 返回（试过 `/characteristics/`、`layout_container=pdpPageFull`、`/modal/characteristics` 都只有这 5 条） |
| 变体维度 | ✅ | 每个值带 SKU 与价格（对选品比"全属性"更实用） |
| 图片 | ✅ | 10~24 张 |
| 前台标签 `tapTags` | ✗ 字段在、内容空 | 3 个 SKU 全为 `items: []`，Ozon 前台已不暴露标签 |
| 富文本 `richAnnotation` | ✗ | 当前 PDP 不返回该 widget |
| 全属性 / 富文本 HTML / 官方标签 | — | 只能走 **Seller API**：`/v1/product/info/attributes`、`/v1/product/info/description`（需卖家 client_id + api_key，且要商品属于该店铺） |

Seerfar 那边能对上的只有：`labels`（0 新品 / 1 正品 / 2 畅销品）和 `tag`（筛选用标签词），**不是**商品详情里的属性/标签。

自测（0 请求、0 积分）：
```powershell
python tools/test_stage4_content.py    # 41 项：DOM→JSON 提取、字段解析、兜底、缓存 TTL、接线
```

---

## 9.5 照搬旧项目实现（v2，2026-11-13）

9.4 的浏览器方案只拿到「О товаре」5 条属性；按你的要求，直接照搬旧项目 `web/pdp.py` + `web/ozon_http.py` 的口径，现在能拿**完整属性 + 富文本**。

**搬过来的文件**（原样，仅改 cookie 路径）：

```
seerfar/pdp.py                     旧 web/pdp.py：PDP 全字段解析（属性/描述/富文本/卖家/货号）
seerfar/ozon_http.py               旧 web/ozon_http.py：cookie 快照 + urllib 直连，含挑战循环识别与 cookie 续期
seerfar/tools/ozon_cookie_export.mjs  旧 tools/：从调试 Chrome 导出 cookie
seerfar/tools/launch_chrome.ps1       旧 web/：按真实 Chrome 版本生成 UA 的调试实例
```

**关键发现（旧项目为什么能拿到）**：第二页必须用 `layout_container=pdpPage2column`，不是 `pdpPageFull`：

```
/product/{sku}/                                             → 主页（价格/图/评分/aspects）
/product/{sku}/?layout_container=pdpPage2column&layout_page_index=2
   ├─ webCharacteristics.totalCount=13, characteristics[0].short → 完整属性表
   └─ webDescription-*（可能有两个）
        ├─ {characteristics:[{title,content}]}      → 成分/储存条件等结构化块
        └─ {richAnnotationJson:{content:[...]}}     → 富文本（raTextBlock/raShowcase）
```

**两条路径，自动回落**：

| 路径 | 状态 | 说明 |
|---|---|---|
| `ozon_http` 纯 HTTP（cookie 直连） | ⚠️ 当前环境 403 | `robots.txt` 200，但 `/api/` 被 TLS 指纹拦（有头/无头导出的 cookie 都试过）。代码保留，网络允许时最快（2 请求） |
| 浏览器两页并发（`pdpPage2column`） | ✅ 实测可用 | 一次详情 7~9 秒；命中缓存 0.03 秒 |

**实测（149710140，真实抓取）**：
```
来源=ozon-composer-browser   属性 12 条（原来 5 条）  变体 2  图片 10  描述 1733 字  富文本 dict(2568B)
属性：Артикул / Тип / Бренд / Технология производства / Состав кофе / Без кофеина /
      Интенсивность вкуса / Единиц в одном товаре / Мин·Макс температура / Срок годности 540 дней / Страна-изготовитель
卖家：Ozon fresh · ООО «Интернет Решения» · ИНН 1027739244741 · 诚信标志 是
```

**按你的要求：不要重量 / 长宽高**——属性名命中 `вес|длин|ширин|высот|глубин|габарит|weight|length|width|height|depth|dimension` 的一律丢弃（`Размер` 保留，可能是服装尺码），`extra` 也不再输出这些字段；**只影响 composer 拿到的内容**；Seerfar 自己的 重量g / 体积L / 尺寸 列保持不动（利润模型的计费重还要用）。

接口与缓存不变：`GET /api/content?sku=&refresh=1`、表 `product_content`（默认 72h）。抽屉与「商品内容」卡片现在多出「卖家与库存」区块和富文本块渲染。

---

## 10. 与旧项目的边界

旧 `README.md` 里那套（composer-api / cookie / CDP / 出口池 / MM / Seller 类目树）**全部停用**，
但文件保留在原地，历史抓包数据 `out/` `data/` 也还在，随时可回查。
本系统不 import 旧项目任何模块。类目 ID 表来自本次提供的 `Ozon类目.xlsx`（Seerfar 官方类目清单），
已复制进自己的 `data/ozon_categories.xlsx`，不依赖 Downloads 路径。
