---
name: fofa-query
description: FOFA 网络空间资产测绘与暴露面排查工具。用于域名、IP、证书、端口、ICP备案等资产查询。适用于资产梳理、子域发现、攻击面分析、外网暴露排查、红队信息收集等场景。触发词包括：fofa、资产测绘、空间测绘、外网暴露、子域资产查询、端口排查、证书反查。
---

# FOFA 资产测绘查询

使用 FOFA API 进行网络资产搜索。

## 使用流程

1. 识别用户查询目标（域名 / IP / 证书 / 端口等）
2. 构造 FOFA 查询语法
3. 调用脚本执行查询
4. 如需大量数据，需确认是否开启 --full

## 基本命令

```bash
# 预览（默认5条）
python3 scripts/fofa_query.py --search 'domain="example.com"'

# 导出 CSV
python3 scripts/fofa_query.py --search 'domain="example.com"' -o result.csv

# 全量数据（不限时间）
python3 scripts/fofa_query.py --search 'port="443"' --full -o all.csv --yes

# 查看账号信息
python3 scripts/fofa_query.py --info
```

## 参数说明

- --search    FOFA 查询语法
- -o          导出 CSV 文件
- --fields    指定字段
- --page_size 每批条数
- -s/--size   导出上限
- --full      不限时间（全量）
- --yes       跳过确认

## 查询语法

详细语法见：

references/query-syntax.md

## API Key 配置

通过以下方式提供 FOFA API Key：

1. 环境变量：
   export FOFA_API_KEY="your-key"

2. 配置文件：
   scripts/config.json
   {"api_key": "your-key"}
