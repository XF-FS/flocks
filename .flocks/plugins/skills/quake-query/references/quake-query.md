---
name: quake-query
description: 360 Quake API：仅通过 --search 传入完整 Quake 语法，预览或分批导出 CSV。
compatibility: Python 3.10+
metadata: { "openclaw": { "emoji": "🔍", "requires": { "bins": [ "python3" ] }, "primaryEnv": "QUAKE_API_KEY" } }
---

# 360 Quake 资产查询

通过 `tools/360-quake/quake_query.py` 调用 Quake。**仅支持 `--search`** 传入整条 Quake 查询语句（与 Hunter 技能的 `--search` 用法一致；语法内容必须是 **Quake**，不可粘贴 Hunter 语法）。

无 `--output` 时先查总数再预览前 5 条；有 `--output` 时先查总数，命中 **>2000** 需确认（`--yes` 跳过），再按 **`--page_size`** 分批写 CSV（默认每批 2000）。`--info` 不需要 `--search`。

## 环境与 Key

- Python 3.10+、`requests`
- Key：`--api-key` → `QUAKE_API_KEY` → `~/.quake/config.json` / 脚本目录 `config.json`（`api_key`）

```bash
export QUAKE_API_KEY="XXXXX"
```

```json
{ "api_key": "XXXXX" }
```

仓库根执行：`python3 tools/360-quake/quake_query.py --info`

## 查询语法

- 以 **Quake 官方**为准；**Shell** 用单引号包住整条：`--search 'domain: "x" OR ip: "y"'`。

| 示例 `--search` 内容 | 说明 |
|:--|:--|
| `domain: "example.com" OR cert: "example.com" OR host: "example.com"` | 常见域名三维 OR |
| `ip: "1.2.3.4"` | IP |
| `icp: "京ICP备12345678号"` | 备案 |
| `cert: "example.com"` | 证书（Subject 等证书字段匹配） |
| `body: "keyword"` | 响应正文包含关键词 |
| `title: "login"` | 网页标题 |
| `app: "nginx" AND country: "CN"` | 组合 |

## 命令

```bash
# 预览
python3 tools/360-quake/quake_query.py --search 'domain: "example.com" OR cert: "example.com" OR host: "example.com"'

# 导出
python3 tools/360-quake/quake_query.py --search 'ip: "1.2.3.4"' -o result.csv
python3 tools/360-quake/quake_query.py --search 'domain: "example.com"' --size 5000 -o result.csv
python3 tools/360-quake/quake_query.py --search 'domain: "example.com"' --page_size 1000 -y -o result.csv
python3 tools/360-quake/quake_query.py --search 'domain: "example.com"' --service http https --no-cache -o result.csv
```

## 参数

| 参数 | 说明 |
|:--|:--|
| `--search` | 完整 Quake 查询语句（查询时必填） |
| `--api-key` | 覆盖配置文件与环境变量 |
| `-s` / `--size` | 导出上限，`0` 为全量 |
| `--page_size` | 每批拉取条数，默认 `2000`（与 Hunter `search` 导出语义对齐） |
| `-y` / `--yes` | 命中数超过 2000 时跳过确认直接导出 |
| `--service` | 服务过滤 |
| `--no-cache` | 忽略缓存 |
| `-o` / `--output` | 输出 CSV |
| `--display` | `table` / `json` / `simple` |
| `--info` | 账号信息（无需 `--search`） |

## CSV 列（节选）

url、ip、domain、port、host、title、协议、指纹、网站返回状态、备案、主体公司、更新时间、省份、来源（`360 Quake`）。

## 参考

- `tools/360-quake/quake_query.py`
- `tools/360-quake/config.json`
