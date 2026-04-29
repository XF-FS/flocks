---
name: zero-zone-query
description: 零零信安 0.zone 数据 API（site / domain / email / apk 移动端应用）：通过 --search 传入完整 0.zone 语法，预览或导出与 Quake 同构 CSV。
compatibility: Python 3.10+
metadata: { "openclaw": { "emoji": "🔎", "requires": { "bins": [ "python3" ] }, "primaryEnv": "ZONE_API_KEY" } }
---

# 零零信安 0.zone 资产查询

通过 `scripts/zone_query.py` 调用官方数据接口。**语法为 0.zone 自有**，与 Quake/Hunter/FOFA 不同；字段与运算符以官网为准。

- **语法说明**：[0.zone 查询语法 / 字段列表](https://0.zone/grammarList)
- **API 申请**
  - **信息系统**（`query_type=site`）：[申请页 type=site](https://0.zone/applyParticulars?type=site)
  - **域名**（`query_type=domain`，子域名 / 根域 / 备案等）：[申请页 type=domain](https://0.zone/applyParticulars?type=domain)
  - **泄露邮箱**（`query_type=email`）：[申请页 type=email](https://0.zone/applyParticulars?type=email)
  - **移动端应用**（`query_type=apk`，小程序 / 公众号 / 安卓 / iOS 等）：[申请页 type=apk](https://0.zone/applyParticulars?type=apk)

接口形态（以平台当前文档为准）：`POST https://0.zone/api/data/`，JSON 体含 `query`、`query_type`（`site` / `domain` / `email` / `apk` 等，与所申请的 API 类型一致）、`page`、`pagesize`（单页最大 **40**）、`zone_key_id`（即 API Key）。**不同 `query_type` 对应不同字段表**，下列分表查阅。

社区脚本常见约束（请以账户与官网为准）：单页最多 40 条、单条件可查上限约 1 万条、单日调用次数有限、请求频率建议 **≤2 次/秒**；本脚本在分页间自动 `sleep`，避免过快。

## 备案主域名（domain API + 企业名）

须已申请 **`query_type=domain`** 的 `zone_key_id`。

1. **`--company`**：传入**完整或规范企业名**，脚本自动生成 `company=="…"` 查询（与 `--search` 二选一，勿同时使用）。
2. **`--list-root-domains`**：在**当前查询**（来自 `--company` 或 `--search`）下分页拉取记录，从每条 `data` 中取 **`root_domain`**，为空则退回 **`domain`**，去重、排序后输出到终端；加 **`-o roots.txt`** 时每行一个主域。

```bash
python3 scripts/zone_query.py --query-type domain --company '某某有限公司' --list-root-domains
python3 scripts/zone_query.py --query-type domain --company '某某有限公司' --list-root-domains -o icp_roots.txt --size 2000
```

主域列表依赖接口返回字段；若平台未返回 `root_domain`，退回到 `domain` 列，可能与子域混用，需结合 `--display json` 核对。

## 环境与 Key

- Python 3.10+、`requests`
- Key：`--api-key` → `ZONE_API_KEY`（或 `ZERO_ZONE_API_KEY`）→ `scripts/config.json` 中 `api_key` / `zone_key_id`

```bash
export ZONE_API_KEY="你的 zone_key_id"
```

```json
{ "api_key": "你的 zone_key_id" }
```

仓库根执行示例：

```bash
# 信息系统（默认 --query-type site）
python3 scripts/zone_query.py --search '(title=="example")||(ip=="1.2.3.4")'

# 域名能力（需在平台申请 domain API，与 site 的 Key 可能不同，以账户为准）
python3 scripts/zone_query.py --query-type domain --search 'root_domain==example.com'

# 泄露邮箱（需申请 email API）
python3 scripts/zone_query.py --query-type email --search 'email_domain==126.com'

# 移动端应用（需申请 apk API）
python3 scripts/zone_query.py --query-type apk --search 'name==万能'
```

## 查询语法参考

- Shell 用**单引号**包住整条 `--search`，内部双引号按 0.zone 语法书写。
- 完整字段与运算符以 [grammarList](https://0.zone/grammarList) 为准；下表摘自平台说明，便于构造 `--search`。

### 逻辑连接符

连接符**中间不能有空格**（与官网「点击可搜索」示例一致）。更多写法见 [grammarList](https://0.zone/grammarList)。


| 符号    | 说明             |
| ----- | -------------- |
| `&&`  | 且：满足 A 并且满足 B。 |
| `     |                |
| `( )` | 条件分组，用括号标明优先级。 |


示例（可直接改写成 `--search '...'` 内容）：

```text
company==保险&&email===163.com
company==电力建设有限公司||company==能源有限公司
(company==学院||company==学校)&&(name==李)
```

### 【信息系统】常用字段（`query_type=site`）


| 参数            | 说明                                                                                       |
| ------------- | ---------------------------------------------------------------------------------------- |
| `company`     | 按「所属公司」包含某关键词检索，如：`company==网络科技`，用于定位某公司相关资产。                                           |
| `ip`          | 按 IP / IP 段检索；段格式示例：`10.0.0.1/24`、`10.0.0.1-10.0.0.34`，如：`ip=39.98.171.0-39.98.171.254`。 |
| `url`         | 按 URL / 域名包含关系检索，如：`url==00sec.com`。                                                     |
| `title`       | 按网页标题检索，如：`title==情报`。                                                                   |
| `html_banner` | 按 HTML 原文包含内容检索，如：`html_banner==零零信安`。                                                   |
| `icp`         | 按备案号包含内容检索，如：`icp==2022`。                                                                |
| `icon`        | 按网站 ICON 的 MD5（精确）检索，如：`icon=baf2ef6b13cd5157e578074ecf7bc872`。                          |


**site 接口返回：** 每条 `data` 中 `**timestamp`** 写入导出 CSV 的「**更新时间**」列（其余列仍按脚本内通用字段映射：`url`、`ip`、`title`、`service` 等）。

### 【域名】常用字段（`query_type=domain`）

用于**域名维度**检索（子域名、根域、后缀、级别等），需在平台申请 [域名 API](https://0.zone/applyParticulars?type=domain)。


| 参数             | 说明                                                       |
| -------------- | -------------------------------------------------------- |
| `company`      | 按「所属公司」包含关键词检索，如：`company==网络科技`，用于定位某公司相关域名数据。          |
| `root_domain`  | 按「根域」包含关系检索，如：`root_domain==00sec.com`。                  |
| `ip`           | 按「IP 地址」等于某值检索，如：`ip=39.98.171.121`。                     |
| `domain`       | 按「子域名」等于某值检索，如：`domain=vip.00sec.com`。                   |
| `icp`          | 按「备案号」逐字匹配，如：`icp===备2022`（运算符以官网为准）。                    |
| `toplv_domain` | 按「域名后缀」包含关系检索，如：`toplv_domain==org`（如 com、cn、net、org 等）。 |
| `level`        | 按「域名级别」等于某值检索，如：`level=子域名`。                             |


**domain 接口返回与 CSV 映射（当前仅下列字段；其余列留空）：**


| 接口字段        | CSV 列            |
| ----------- | ---------------- |
| `icp`       | 备案               |
| `domain`    | domain、host（主机列） |
| `url`       | url              |
| `msg.ip`    | ip               |
| `company`   | 主体公司（备案主体）       |
| `timestamp` | 更新时间             |


### 【邮箱】常用字段（`query_type=email`）

用于**泄露邮箱**检索，需在平台申请 [邮箱 API](https://0.zone/applyParticulars?type=email)。


| 参数             | 说明                                              |
| -------------- | ----------------------------------------------- |
| `company`      | 按「所属公司」包含关键词检索，如：`company==网络科技`，用于定位某公司相关邮箱数据。 |
| `email`        | 按「邮箱地址」包含关系检索，如：`email==@126.com`。              |
| `email_domain` | 按「邮箱域名」包含关系检索，如：`email_domain==126.com`。        |
| `email_type`   | 按「邮箱类型」等于某值检索，如：`email_type=企业邮箱`。              |
| `leakage_num`  | 按「泄露次数」等于某值检索，如：`leakage_num=4`。                |
| `source`       | 按「来源」等于某值检索，如：`source=0.zone`。                  |
| `msg.tags`     | 按「标签」包含关系检索，如：`msg.tags==科技有限公司`。               |

**email 接口返回与导出：** 脚本将 `email`、`email_domain`、`company`、`email_type`、`leakage_num`、`source`、`msg.tags`（平铺字段或 `msg.tags` / `msg['tags']`）映射到 CSV；`timestamp` →「更新时间」；终端预览单独展示 email / 域名 / 公司 / 类型 / 泄露次数 / 来源（避免沿用 site 的 URL 表头导致空白）。

### 【移动端应用】常用字段（`query_type=apk`）

用于**移动端应用**检索（应用名、描述、类型、关联域名等），需在平台申请 [移动端 API](https://0.zone/applyParticulars?type=apk)。


| 参数            | 说明                                                                            |
| ------------- | ----------------------------------------------------------------------------- |
| `company`     | 按「所属公司」包含关键词检索，如：`company==网络科技`，用于定位某公司相关应用数据。                               |
| `name`        | 按「应用名称」包含关系检索，如：`name==万能`。                                                   |
| `description` | 按「应用描述」包含关系检索，如：`description==去水印`。                                           |
| `type`        | 按「应用类型」等于某值检索，如：`type=微信小程序`、`type=微信公众号`、`type=安卓APK`、`type=iOS` 等（以平台枚举为准）。 |
| `domain_list` | 按「相关域名」包含关系检索，如：`domain_list==zhushou03.abu.com`。                             |


### 组合示例

```text
(company=某某有限公司)&&(title==某某有限公司)
(title=="关键字")||(ip=="1.2.3.4")
```

域名示例：

```text
root_domain==example.com&&level=子域名
domain=vip.00sec.com||ip=39.98.171.121
```

邮箱示例：

```text
company==网络科技&&email_domain==126.com
email==@126.com||email_type=企业邮箱
```

移动端示例：

```text
name==万能&&type=微信小程序
company==网络科技||domain_list==example.com
```

## 命令

```bash
# 终端预览（默认表格；可加 --display json 看原始响应）
python3 scripts/zone_query.py --search '(title=="test")'

# 导出 CSV（列与 Quake 脚本一致，来源列为「零零信安 0.zone」）
python3 scripts/zone_query.py --search '(ip=="192.168.1.1")' -o result.csv

# 限制最多 500 条；每页 40（默认）；命中 >2000 需确认（-y 跳过）
python3 scripts/zone_query.py --search '...' --size 500 -y -o out.csv

# 域名：查某根域下子域名等（字段见上表）
python3 scripts/zone_query.py --query-type domain --search 'root_domain==example.com' -o domains.csv

# 泄露邮箱
python3 scripts/zone_query.py --query-type email --search 'email_domain==126.com' -o emails.csv

# 移动端应用
python3 scripts/zone_query.py --query-type apk --search 'name==万能' -o apps.csv

# 按企业名拉备案主域名列表（见上文「备案主域名」）
python3 scripts/zone_query.py --query-type domain --company '某某有限公司' --list-root-domains -o icp_roots.txt
```

## 参数


| 参数                | 说明                                                                                  |
| ----------------- | ----------------------------------------------------------------------------------- |
| `--search`        | 完整 0.zone 查询语句；与 `--company` 二选一（domain）                                              |
| `--company`       | 仅 `domain`：企业全称，自动生成 `company=="…"`                                                     |
| `--list-root-domains` | 仅 `domain`：汇总去重 `root_domain`（无则 `domain`），`-o` 时为每行一个主域的文本文件                        |
| `--query-type`    | `site`（默认）/ `domain` / `email` / `apk`，须与 [申请页](https://0.zone/apply) 开通的能力及 Key 一致 |
| `--page-size`     | 每页条数，最大40                                                                           |
| `--size` / `-s`   | 导出上限，`0` 表示在接口允许范围内尽量拉取                                                             |
| `-o` / `--output` | 输出 CSV；与 `--list-root-domains` 联用时为主域列表纯文本                                              |
| `-y` / `--yes`    | 命中数超过 2000 时跳过确认                                                                    |
| `--api-key`       | 覆盖配置文件与环境变量                                                                         |
| `--display`       | 无 `-o` 时：`table` 或 `json`                                                           |


## CSV 列（与 Quake 同构）

url、ip、domain、port、host、title、协议、指纹、网站返回状态、备案、主体公司、更新时间、省份、来源。`**query_type=site**` 时「更新时间」取 `data.timestamp`。`**query_type=domain**` 时按上表「返回与 CSV 映射」填充，其余列空。`email`、`apk` 等仍按通用字段尽力映射；需要原始结构时可加 `--display json` 预览。

## 参考

- `scripts/zone_query.py`
- `scripts/config.json`

