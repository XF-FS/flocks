---
name: quake-query
description: 360 Quake 网络空间资产测绘与暴露面排查工具。用于域名、IP、证书、端口、ICP备案、应用指纹等资产查询。适用于资产梳理、子域发现、攻击面分析、外网暴露排查、红队信息收集等场景。触发词包括：quake、360资产、360测绘、空间测绘、外网暴露排查、应用指纹查询。
---

# 360 Quake 资产测绘查询

使用 360 Quake API 进行网络空间资产查询。

## 使用流程

1. 识别用户查询目标（域名 / IP / 证书 / 端口 / 应用指纹等）
2. 构造 Quake 查询语法
3. 调用脚本执行查询
4. 如需大规模导出，确认是否调整 --size 或分页参数

## 基本命令

```bash
# 预览（默认5条）
python3 scripts/quake_query.py --search 'domain: "example.com"'

# 导出 CSV
python3 scripts/quake_query.py --search 'domain: "example.com"' -o result.csv

# 指定大小
python3 scripts/quake_query.py --search 'ip: "1.2.3.4"' --size 5000 -o result.csv

# 查看账号信息
python3 scripts/quake_query.py --info
```

## 参数说明

- --search     Quake 查询语法
- -o           导出 CSV 文件
- -s/--size    导出上限
- --page_size  每批条数（默认2000）
- --yes        跳过确认
- --service    服务过滤

## 查询语法

详细语法见：

references/query-syntax.md

## API Key 配置

通过以下方式提供 Quake API Key：

1. 环境变量：
   export QUAKE_API_KEY="your-key"

2. 配置文件：
   scripts/config.json
   {"api_key": "your-key"}
