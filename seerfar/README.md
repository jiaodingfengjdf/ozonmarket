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

## 10. 与旧项目的边界

旧 `README.md` 里那套（composer-api / cookie / CDP / 出口池 / MM / Seller 类目树）**全部停用**，
但文件保留在原地，历史抓包数据 `out/` `data/` 也还在，随时可回查。
本系统不 import 旧项目任何模块。类目 ID 表来自本次提供的 `Ozon类目.xlsx`（Seerfar 官方类目清单），
已复制进自己的 `data/ozon_categories.xlsx`，不依赖 Downloads 路径。
