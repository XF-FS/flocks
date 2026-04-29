---
name: zero-zone-query
description: 零零信安 0.zone 数据 API 资产查询工具。支持信息系统（site）、域名（domain）、泄露邮箱（email）、移动端应用（apk）等类型查询。适用于备案主域名收集、子域名梳理、邮箱泄露排查、移动端资产盘点等场景。触发词包括：0.zone、零零信安、备案域名、备案主域名、子域名查询、泄露邮箱、zone查询。
---

# 零零信安 0.zone 资产查询

使用 0.zone API 进行多类型资产查询。

## 使用流程

1. 判断查询类型（site / domain / email / apk）
2. 构造符合 grammarList 的查询语法
3. 调用脚本执行查询
4. 如需备案主域名列表，使用 --list-root-domains

## 基本命令

```bash
# 信息系统（默认 site）
python3 scripts/zone_query.py --search 'url==example.com'

# 域名
python3 scripts/zone_query.py --query-type domain --search 'root_domain==example.com' -o domains.csv

# 泄露邮箱
python3 scripts/zone_query.py --query-type email --search 'email_domain==126.com' -o emails.csv

# 移动端应用
python3 scripts/zone_query.py --query-type apk --search 'name==万能' -o apps.csv

# 备案主域名
python3 scripts/zone_query.py --query-type domain --company '公司全称' --list-root-domains -o icp_roots.txt
```

## 参数说明

- --query-type          查询类型（默认 site）
- --search              查询语法
- --company             企业全称（用于备案主域名收集）
- --list-root-domains   去重输出 root_domain
- -o                    导出文件
- -y                    跳过确认

## 查询语法

详细语法与字段说明见：

references/query-guide.md

## API Key 配置

通过以下方式提供 ZONE API Key：

1. 环境变量：
   export ZONE_API_KEY="your-key"

2. 配置文件：
   scripts/config.json
   {"api_key":"your-key"}
