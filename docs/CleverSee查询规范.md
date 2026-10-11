# 阿里云 CleverSee 查询规范（草案）

- 起草日期：2026-10-11
- 状态：暂停使用（D-09：数据来源改为太平洋电脑网产品库，CleverSee 暂不接入）。保留本草案，供以后需要到官方渠道核对时使用。
- 依据：D-01（中国大陆、人民币）、D-02（补查 1 次）、D-07（CleverSee）、D-08（官方渠道与查找顺序）；接口文档为阿里云帮助中心《联网搜索（搜文）API》。
- 实现位置：查询流程在 `backend/app/core/verification/source_search.py`；接口适配在任务 20 实现（`backend/app/adapters/search/`）。

## 1. 一次推荐里怎样调用

每个候选按 D-08 的顺序最多查三个阶段，某个阶段找到官方页面就停止：

| 阶段 | 限定站点（`includeSites`） | 什么时候查 |
| --- | --- | --- |
| 1. 品牌官网和官方商城 | 渠道规则表中该品牌的官网域名 | 总是先查 |
| 2. 京东官方旗舰店 | 该品牌的京东店铺域名，加上商品详情页站点 `item.jd.com`、`item.m.jd.com`；有店铺编号的再加 `mall.jd.com` | 官网没有找到官方页面时 |
| 3. 天猫官方旗舰店 | 该品牌的天猫店铺域名，加上 `detail.tmall.com`、`detail.m.tmall.com` | 京东也没有找到时 |

- 每个阶段只调用 1 次，三个阶段用同一个搜索词。
- 品牌没有某个渠道（比如苹果没有京东旗舰店），就跳过这个阶段，不占调用次数。
- 品牌不在渠道规则表里时不搜索，直接记为“品牌不在官方渠道清单中”。
- 整次推荐的搜索次数不超过 `runtime.json` 中的 `max_search_calls`（目前为 12）。
- `includeSites` 只能写域名，写不了路径。像 `consumer.huawei.com/cn/` 这种要求路径的规则，搜索回来后由程序再按渠道规则表过滤一遍。

## 2. 请求参数

所有阶段都用同一个模板，只有 `query` 和 `includeSites` 不同：

```json
{
  "query": "华为 MateBook 14 2024 16GB 1TB",
  "engineType": "CNLiteBasic",
  "timeRange": "NoLimit",
  "contents": {
    "mainText": false,
    "markdownText": false,
    "richMainBody": false,
    "summary": false,
    "rerankScore": true
  },
  "advancedParams": {
    "numResults": "10",
    "includeSites": "consumer.huawei.com,consumer.huawei.cn,vmall.com"
  }
}
```

| 参数 | 取值 | 原因 |
| --- | --- | --- |
| `engineType` | `CNLiteBasic`（极速版） | 文档写明只有这个版本支持 `includeSites`；按次计费，每千次 12 元 |
| `numResults` | 10 | 按次计费，与条数无关；10 条留出过滤列表页、非官方店铺的余量 |
| `timeRange` | `NoLimit` | 产品参数页可能发布较早，限定时间会漏掉 |
| `category` | 不设置 | 文档说明通用场景指定分类会影响召回 |
| `contents.mainText`、`markdownText`、`richMainBody` | 关闭 | 这些是搜索服务商存的网页副本，不是本次实际读取的页面，不能作为证据 |
| `contents.summary` | 关闭 | 增强摘要另外收费，而且是二次加工的内容 |
| `contents.rerankScore` | 开启（默认值） | 极速版必定返回且不影响排序，不另外收费；程序不依赖这个分数 |
| `locationInfo` | 不设置 | 只对天气等场景有效 |

CleverSee 没有“地区”和“语言”参数。D-01 规定的中国大陆范围由 `includeSites` 加上渠道规则表的路径过滤来保证。

三个阶段的 `includeSites` 示例（华为）：

| 阶段 | `includeSites` |
| --- | --- |
| 官网 | `consumer.huawei.com,consumer.huawei.cn,vmall.com` |
| 京东 | `huawei.jd.com,item.jd.com,item.m.jd.com` |
| 天猫 | `huaweistore.tmall.com,detail.m.tmall.com,detail.tmall.com` |

## 3. 搜索词怎样写

搜索词由模型为每个候选写一条（任务 29 的 `write_queries`）。写法要求：

1. 不超过 30 个字（接口文档建议的效果上限）。
2. 依次写品牌、型号、代际或年份，以及区分配置所必需的规格（如内存、存储、屏幕尺寸）。
3. 型号尽量用官网上的写法，比如 “MacBook Air 13 英寸 M4”，而不是“苹果轻薄本”。
4. 不写网站名或渠道名（如“官网”“京东”“旗舰店”）：渠道已经由 `includeSites` 限定，写进去反而干扰结果。
5. 不写价格、价位和评价性词语（如“最好”“推荐”“性价比”）。
6. 不写颜色，除非颜色会改变价格或配置。

模型漏写某个候选、或写的候选不存在时，程序用候选线索按“品牌 型号 代际 配置”的顺序拼一条。

### 示例（只演示写法，不代表这些型号一定在售）

| 品类 | 合格的搜索词 | 不合格的写法及原因 |
| --- | --- | --- |
| 笔记本电脑 | `华为 MateBook 14 2024 16GB 1TB` | `华为笔记本 官网 价格`：写了渠道和价格，没有型号 |
| 手机 | `小米 15 Pro 16GB 512GB` | `小米 15 Pro 京东自营旗舰店 多少钱`：写了渠道和价格 |
| 平板电脑 | `iPad Air 11 英寸 M3` | `适合学生的苹果平板`：没有型号，带评价 |
| 显示器 | `戴尔 U2724D 27 英寸` | `戴尔 27 寸 4K 显示器 推荐 性价比高 办公 设计`：没有型号，带评价，超过 30 字 |
| 耳机 | `索尼 WH-1000XM6` | `索尼降噪耳机 黑色 最新款`：没有型号，写了颜色 |

### 补查时的搜索词（D-02：每个候选最多补查 1 次）

第一次三个阶段都没有找到官方页面时，补查 1 次。补查词比第一次更宽：去掉配置，只保留品牌、型号、代际，例如 `华为 MateBook 14 2024`。补查从官网阶段重新开始，同样计入整次推荐的搜索次数。（补查的执行在任务 36 实现。）

## 4. 返回结果怎样用

| 返回字段 | 怎样用 |
| --- | --- |
| `pageItems[].link` | 按渠道规则表判断是否为官方渠道；官方的交给网页读取模块实际读取 |
| `pageItems[].title` | 和链接一起提供给后续步骤参考 |
| `pageItems[].snippet` | 只用来定位网页，其中出现的价格、参数都不算数 |
| `pageItems[].publishedTime` | 可以记录，但不能当作价格的生效日期 |
| `pageItems[].tags`、`rerankScore`、权威分 | 不依赖；是否官方只看渠道规则表 |
| `costCredits` | 记录本次调用量，供任务 46 统计费用 |
| `requestId` | 出错时记录，便于向阿里云排查 |
| `sceneItems` | 不使用（天气、时间等场景结果，与本产品无关） |

## 5. 超时与错误

- 单次调用超时设为 6 秒。服务端自身的超时是 5 秒，多留 1 秒用于网络传输。
- 搜索出错时记录错误，接着查下一个阶段，不重试同一个阶段。

| 接口返回 | 程序中的错误类型 | 处理 |
| --- | --- | --- |
| 404 `InvalidAccessKeyId.NotFound` | 密钥错误（`auth`） | 提示检查 `SEARCH_API_KEY` |
| 403 `Retrieval.NotActivate` | 密钥错误（`auth`） | 提示到 CleverSee 控制台开通服务 |
| 403 `Retrieval.NotAuthorised` | 密钥错误（`auth`） | 提示给子账号授权 |
| 403 `Retrieval.TestUserPeriodExpired` | 密钥错误（`auth`） | 提示测试期（下单后 15 天）已过，需要转正式 |
| 403 `Retrieval.Arrears` | 额度不足（`quota`） | 提示账户需要充值 |
| 429 `Retrieval.TestUserQueryExceeded` | 额度不足（`quota`） | 提示测试期每天 1000 次已用完 |
| 429 `Retrieval.Throttling.User` | 额度不足（`quota`） | 提示被限流 |
| 超时 | 超时（`timeout`） | 记录后查下一个阶段 |
| 其他网络错误 | 网络错误（`network`） | 记录后查下一个阶段 |

## 6. 待实测（任务 24）

1. 极速版能否搜到京东商品详情页（`item.jd.com`）和天猫商品详情页。
2. 官网阶段用一条搜索词，能否同时找到参数页和价格页；找不到时，是否需要分成“参数”“购买”两条搜索词（这会多占搜索次数）。
3. 模型按官网写法写出的型号名，与官网页面标题的匹配程度。
4. 京东商品页的价格如果是页面加载后才显示、我们直接读页面读不到，是否用 CleverSee 的正文副本兜底。这一点偏离“证据必须来自本次实际读取的页面”的原则，需要你决定后再实施。
