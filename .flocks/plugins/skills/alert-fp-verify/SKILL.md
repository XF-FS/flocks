---
name: alert-fp-verify
description: Analyzes security alerts from JSON, optionally validates traffic with pcap, and queries ThreatBook intelligence for IPs, domains, URLs, and file hashes. Use when the user asks to analyze alerts, verify false positives, validate pcap evidence, query IP/domain intelligence, or analyze sample hashes.
---

# 安全告警误报验证

## 入口分流

先根据用户输入选择唯一主路径：

| 输入 | 主路径 | 必读文档 |
|---|---|---|
| JSON 告警 | 告警研判 | `docs/alert-analysis.md` |
| JSON 告警 + pcap | 告警研判 + 流量验证 | `docs/alert-analysis.md`、`docs/traffic-pcap.md` |
| 仅 pcap | 补问 JSON 告警路径 | 无 |
| IP / 域名 / URL | 情报查询 | `docs/threatbook.md` |
| MD5 / SHA1 / SHA256 | 样本 hash 分析 | `docs/threatbook.md` |

只读取当前路径需要的文档。命令执行、脚本执行、高危函数、数据库高危过程类告警，额外读取 `docs/high-risk-call.md`。输出前读取 `docs/output-format.md`。

## 最小输入要求

- 告警研判必须有 JSON 告警文件。
- 流量验证必须同时有 JSON 告警和 pcap。
- 用户后续只补充 pcap 路径时，优先沿用上一轮 JSON；若上下文没有 JSON 路径，只问一次 JSON 路径。
- 仅查询 IP、域名、URL、hash 时，不进入告警研判流程。

## 硬约束

1. JSON 告警必须先执行摘要脚本，不得直接读取完整 JSON 下结论。
2. 结论必须基于行为证据链：触发原因 → 实际内容 → 行为是否成立 → 攻击目的性 / 业务合理性。
3. 不得仅依据告警名称、规则名称、单一特征串、情报标签直接定性。
4. 无 pcap 时，不得输出“攻击成立”“利用成功”或高置信强结论；必须注明“无 pcap，仅基于 JSON 研判，结论供参考”。
5. 只有存在结果性证据，才能判定“攻击成立”。
6. `threat.level == "action"` 是行为检出，默认不得判定为攻击成立或攻击尝试，必须建议用户确认是否为授权行为。
7. 搜索只作为辅助参考；仅在告警语义、攻击方式或访问路径不明确时使用 websearch。
8. 溯源报告必须直接输出给用户，禁止仅保存到本地文件。

## 工具与脚本

从当前 skill 根目录执行脚本，避免硬编码用户路径：

```bash
python3 scripts/alert_summary.py <json_file>
python3 scripts/analyze_alert.py --pcap <pcap> --src <ip> --dst <ip> --term "<feature>" --json
```

字段不足时先列字段，再定向补提：

```bash
python3 scripts/alert_summary.py --list-fields
python3 scripts/alert_summary.py <json_file> --fields <field1,field2,...>
```

## 默认工作流

1. 识别输入类型并读取对应文档。
2. 告警任务先运行摘要脚本，确认 `suuid`、`threat.level`、告警名称、命中特征、源目地址、时间。
3. 按 `suuid` 分流：`T` 类走情报，`F` 类走文件 / hash，其他走流量 / 规则类。
4. 输出结论前必须 websearch 搜索告警名称，结合搜索结果校验结论。
5. 若需要 pcap 但用户未提供，基于 JSON 证据输出结论，并询问是否有 pcap；证据不足时降级为待确认。
6. 输出前按 `docs/output-format.md` 使用默认短版模板。

## 按需文档

- `docs/alert-analysis.md`：JSON 告警研判、`threat.level` 分流、字段补提、结论分级。
- `docs/traffic-pcap.md`：pcap 验证、请求 / 响应侧判断、无 pcap 降级。
- `docs/threatbook.md`：IP、域名、URL、hash 的 ThreatBook 查询与判定。
- `docs/high-risk-call.md`：命令执行、高危函数、脚本执行类告警的追加判断。
- `docs/output-format.md`：默认短版、必要长版、输出约束。
