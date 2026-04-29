# ThreatBook 查询

## IP / 域名 / URL 情报

使用 ThreatBook MCP 工具：

| 查询类型 | MCP 工具 | 调用方式 |
|---|---|---|
| IP 情报 | `threatbook-mcp_ip_query` | `threatbook-mcp_ip_query(ip="<ip>")` |
| IP 溯源 | `threatbook-mcp_ip_attribution` | `threatbook-mcp_ip_attribution(ip="<ip>")` |
| 域名情报 | `threatbook-mcp_domain_query` | `threatbook-mcp_domain_query(domain="<domain>")` |
| 域名溯源 | `threatbook-mcp_domain_attribution` | `threatbook-mcp_domain_attribution(domain="<domain>")` |

必须关注：

- `is_malicious`
- `severity`
- `confidence` / `confidence_level`
- 当前有效标签
- 标签时间是否覆盖告警时间
- `judgments`、`tags_classes`、`hist_behavior`
- 地理位置、ASN、`permalink`

判定原则：

- `is_malicious=false`：倾向低风险 / 非恶意。
- `is_malicious=true` 且 `severity=high/critical`：倾向恶意。
- `medium/low/info`：必须结合行为和场景判断。
- 标签在告警时间无效、已失效或与场景不匹配：不得直接判恶意。

## 情报类告警

`T` 类告警必须：

1. 提取 IOC：IP、域名或 URL。
2. 查询 ThreatBook。
3. 核验情报标签与告警时间的对应关系。

情报明确恶意且时间有效时，倾向“攻击尝试 / 可疑攻击行为”或更高；情报不存在、标签失效或时间不匹配时，倾向“误报”；证据弱或关联不足时，判“待进一步确认”。

## 样本 hash 分析

使用 ThreatBook MCP 工具：

```text
threatbook-mcp_hash_query(hash="<sha256|sha1|md5>")
```

必须关注：

- `threat_level`
- `threat_score`
- `malware_type`
- `malware_family`
- `multi_engines`
- `is_whitelist`
- `sandbox`
- `signature`
- `network`
- `permalink`

判定原则：

- `clean` + 低检出：倾向安全 / 误报。
- `suspicious`：可疑，需结合上下文或人工确认。
- `malicious` + 高检出：倾向恶意样本。

## 文件类告警

`F` 类告警先提取文件字段：

```bash
python3 scripts/alert_summary.py <json_file> --fields data,input_time,hash,file_upload_data.hash,file_upload_data.FileSize,file_upload_data.Magic,file_upload_data.file_action,established,net.bytes_toserver,net.bytes_toclient,net.pkts_toserver,net.pkts_toclient,threat.multi_engine_result,threat.result,threat.is_custom,time
```

必须确认：

- 是否白名单。
- 是否真实建立连接。
- 是否存在真实文件传输 / 落地迹象。
- 沙箱、多引擎、行为签名是否一致支持恶意判断。

判定原则：

- 有连接 + 有文件 + 沙箱恶意 + 结果性证据明确：可判“攻击成立”。
- 有文件 + 沙箱恶意，但缺少结果性证据：判“攻击尝试 / 可疑攻击行为”。
- 有文件但沙箱 clean / 白名单 / 无连接：判“误报”。
- 证据不足或关键字段缺失：判“待进一步确认”。
