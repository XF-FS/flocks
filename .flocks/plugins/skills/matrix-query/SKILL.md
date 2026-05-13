---
name: matrix-query
description: Matrix 资产测绘查询。通过 Matrix API 按 q 语法检索资产，支持 limit/page/select/CSV 参数，采用 apikey 鉴权。
---

# Matrix 资产测绘查询

通过 Matrix API 进行网络资产检索，查询语句直接透传为 `q`，应使用 Matrix 原生语法。

默认优先使用内网地址：`http://10.66.192.246:31276/api/search/asset`

外网地址：`https://asset01.threatbook-inc.cn/api/search/asset`

## 基本命令

```bash
# 预览（默认 5 条）
python3 scripts/matrix_query.py --search 'ip="1.1.1.1" && port="80"'

# 导出 CSV
python3 scripts/matrix_query.py --search 'cert.subject="P18055077" && cert.subject.country="US"' -o result.csv --yes

# 指定返回字段
python3 scripts/matrix_query.py --search 'domain="example.com"' --select 'url,host,ip,port,title,update_time' -o result.csv --yes

# 指定走外网地址
python3 scripts/matrix_query.py --search 'ip="1.1.1.1"' --base-url 'https://asset01.threatbook-inc.cn/api/search/asset'

# 测试 API key
python3 scripts/matrix_query.py --search 'ip="1.1.1.1"' --page_size 1
```

## 参数说明

- `--search` Matrix 查询语法
- `-o` 导出 CSV 文件
- `--select` 指定返回字段
- `--page_size` 每页条数
- `--page` 起始页
- `-s/--size` 导出上限
- `--csv-mode` 附加 `CSV=CSV`
- `--base-url` 自定义接口地址
- `--yes` 跳过确认

## 查询语法

支持 Matrix 原生语法，查询语句不要在本地改写。

常用规则：

- `&&` 与
- `||` 或
- `!=` 排除
- `>=`、`<=`、`>`、`<` 数值/范围比较
- `==` 精准匹配
- `*` 前缀模糊匹配
- `()` 组合优先级
- `exists=domain,title` 过滤字段存在的资产

注意事项：

- 运算符前后建议加空格，例如 `title="abc" || body="def"`
- 字符串值通常使用双引号，例如 `ip="1.1.1.1"`
- `==` 用于精准匹配，`=` 常用于普通匹配
- `*` 可用于短语前缀匹配，例如 `html_hash="79e89d*"`

常用字段速查：

| 字段 | 示例 | 说明 |
|:--|:--|:--|
| `ip` | `ip="1.1.1.1"` | 单一 IPv4 或网段/多 IP 检索入口 |
| `port` | `port="80"` | 端口查询，也可配合 `!=`、`>=` |
| `protocol` | `protocol="http"` | 协议查询 |
| `domain` | `domain="example.com"` | 域名查询 |
| `root_domain` | `root_domain="example.com"` | 根域名查询 |
| `title` | `title="网络空间测绘"` | 页面标题查询 |
| `body` | `body="微步在线"` | HTML 正文关键词 |
| `header` | `header="elastic"` | HTTP 响应头关键词 |
| `url` | `url="threatbook"` | URL 中包含指定内容 |
| `app` | `app="Nginx"` | 组件名称查询 |
| `app_version` | `app_version="1.2"` | 组件版本查询 |
| `server` | `server="Microsoft-IIS/10"` | Web Server 查询 |
| `status_code` | `status_code="200"` | HTTP 状态码 |
| `city` | `city="北京"` | 城市查询 |
| `isp` | `isp="阿里云"` | 运营商查询 |
| `icp_company` | `icp_company="微步在线科技有限公司"` | 备案主体公司 |
| `cert.subject.org` | `cert.subject.org="Oracle Corporation"` | 证书持有者组织 |
| `favicon` | `favicon="28db76bf560e2e65f3405d611fbafaea"` | favicon MD5 |
| `html_hash` | `html_hash="79e89d6a6fdd79bb8e52d8a7e430aaf2"` | HTML 源码 hash |
| `after` | `after="2022-06-01"` | 指定日期之后 |

更多字段和全部语法参考见：`references/query-syntax.md`

遇到一些不常见的字段查询，直接先查 `references/query-syntax.md`，不要自行猜字段名。

## 鉴权配置

优先级如下：

1. `--api-key`
2. 环境变量 `MATRIX_API_KEY`
3. 配置文件 `scripts/config.json`

示例：

```bash
export MATRIX_API_KEY="your-key"
```

或：

```json
{"api_key": "your-key"}
```

## 接口说明

- 采用 GET 请求
- apikey 通过查询参数 `apikey` 传递
- 检索语法通过查询参数 `q` 传递
- 支持 `limit/page/select/CSV`
- 默认按 Matrix 平台原生语法传入，不在本地改写查询语句

## 使用建议

- 优先用 Matrix 原生语法直接写 `q`
- 优先使用 `&&` / `||` / `()` 组合复杂条件，不要写成其他平台 DSL
- 优先先小批量预览，再扩大 `--page_size` 或导出
- 大批量导出时避免过大分页
- 如果需要稳定融入 Coruna 流程，建议导出字段尽量覆盖 `url/ip/domain/port/host/title/协议/指纹/网站返回状态/备案/主体公司/更新时间/省份/来源`
