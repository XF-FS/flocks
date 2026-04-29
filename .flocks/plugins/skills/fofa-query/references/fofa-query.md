---
name: fofa-query
description: FOFA API：--search 传入 FOFA 语法（qbase64）；预览与导出均用 search/next。Key 支持环境变量或 config.json。
compatibility: Python 3.10+
metadata: { "openclaw": { "emoji": "🔍", "requires": { "bins": [ "python3" ] }, "primaryEnv": "FOFA_API_KEY" } }
---

# FOFA 资产查询

通过 `tools/fofa/scripts/fofa_query.py` 调用 FOFA **`/api/v1/search/next`**（**不再使用** `search/all`）。仅支持 **`--search`** 传入 **FOFA 查询语法原文**（脚本内做 **标准 Base64 → `qbase64`**）。

- **预览**（无 `-o`）：首次 `search/next`（小 `size`，默认最多展示 5 条样例），响应中仍含总命中数 **`size`**。
- **导出**（有 `-o`）：同一接口循环携带 **`next`**，直至无后续或达到 `--size` 上限；游标翻页避免页码错位。

## 环境与 Key

- Python 3.10+、`requests`
- Key：`--api-key` → `FOFA_API_KEY` → 当前目录或脚本目录 `config.json` 的 `api_key`

```bash
export FOFA_API_KEY="XXXXX"
```

```json
{ "api_key": "XXXXX" }
```

仓库根：`python3 tools/fofa/scripts/fofa_query.py --info`

## 查询语法

- 以 **[FOFA 官方查询语法](https://fofa.info/)** 为准；与 Hunter / Quake **不通用**。
- **Shell**：整条用单引号：`--search 'title="xxx"'`。
- 下列为**摘录**；字段权限、会员版本及运算符能力以官网当前说明为准。

### 逻辑连接符

| 符号 | 含义 |
|:--|:--|
| `=` | 匹配；`=""` 时可查询**不存在该字段**或**值为空**的情况。 |
| `==` | 完全匹配；`==""` 时可查询**存在且值为空**的情况。 |
| `&&` | 与 |
| OR（两个竖线） | 逻辑或（FOFA 文档中的 OR 运算符） |
| `!=` | 不匹配；`!=""` 时可查询**值不为空**的情况。 |
| `*=` | 模糊匹配，使用 `*` 或 `?` 通配。 |
| `()` | 括号内条件**优先级最高** |

### 常用字段与示例（摘录）

| 字段 | 示例 | 说明 |
|:--|:--|:--|
| `ip` | `ip="1.1.1.1"` | 单一 IPv4 |
| `ip` | `ip="220.181.111.1/24"` | IPv4 C 段 |
| `domain` | `domain="qq.com"` | 根域名 |
| `host` | `host=".fofa.info"` | 主机名 |
| `server` | `server="Microsoft-IIS/10"` | Web 服务器标识 |
| `title` | `title="beijing"` | 网站标题 |
| `header` | `header="elastic"` | 响应标头 |
| `header_hash` | `header_hash="1258854265"` | HTTP(S) 响应头 hash（个人版及以上） |
| `body` | `body="网络空间测绘"` | HTML 正文 |
| `body_hash` | `body_hash="-2090962452"` | 正文 hash |
| `js_name` | `js_name="js/jquery.js"` | 页面包含的 JS 路径 |
| `js_md5` | `js_md5="82ac3f14327a8b7ba49baa208d4eaa15"` | JS 内容 MD5 |
| `icon_hash` | `icon_hash="-247388890"` | 网站图标 favicon hash |
| `status_code` | `status_code="402"` | HTTP 状态码 |
| `icp` | `icp="京ICP证030173号"` | ICP 备案号 |
| `cert` | `cert="baidu"` | 证书内容相关 |
| `cert.subject` | `cert.subject="Oracle Corporation"` | 证书持有者 |
| `cert.issuer` | `cert.issuer="DigiCert"` | 证书颁发者 |
| `after` | `after="2023-01-01"` | 该时间**之后**有更新的资产（个人版及以上） |
| `before` | `before="2023-12-01"` | 该时间**之前**有更新的资产（个人版及以上） |
| 组合 | `after="2023-01-01" && before="2023-12-01"` | 更新时间区间 |

**说明**：原表中的 `✓` 表示不同运算符/会员下的可用性，**以 FOFA 官网与当前账号权限为准**；含 `body` 时 API 单页 `size` 上限较低，脚本内会收紧 `--page_size`。

## 命令

```bash
# 账号信息（无需 --search）
python3 tools/fofa/scripts/fofa_query.py --info

# 预览（总数 + 前 5 条，search/next）
python3 tools/fofa/scripts/fofa_query.py --search 'title="bing"'

# 导出 CSV（search/next；命中 >2000 需确认，--yes 跳过）
python3 tools/fofa/scripts/fofa_query.py --search 'domain="example.com"' -o result.csv
python3 tools/fofa/scripts/fofa_query.py --search 'ip="1.2.3.0/24"' --page_size 1000 --size 5000 -y -o out.csv

# 全库时段（默认近一年；全量加 --full）
python3 tools/fofa/scripts/fofa_query.py --search 'port="443"' --full -o all.csv --yes
```

## 参数

| 参数 | 说明 |
|:--|:--|
| `--search` | FOFA 语法原文（查询时必填；`--info` 除外） |
| `--api-key` | 覆盖环境变量与配置文件 |
| `--fields` | 逗号分隔字段，默认 `link,ip,port,host,domain,title,protocol,server,icp,country_name` |
| `--page_size` | 单次请求条数（脚本按官方规则与查询内容自动上限：如含 body 最大 500，含 cert/banner 最大 2000，否则最大 10000） |
| `-s` / `--size` | 导出最多行数，`0` 表示不限制（受总数约束） |
| `--full` | 不限于近一年数据 |
| `-o` / `--output` | 导出 CSV，末列固定 **`来源`= `FOFA`** |
| `--yes` / `-y` | 命中数超过 2000 时跳过确认 |
| `--info` | 调用 `/api/v1/info/my` |

## 参考

- `tools/fofa/scripts/fofa_query.py`
- `tools/fofa/scripts/config.json`
