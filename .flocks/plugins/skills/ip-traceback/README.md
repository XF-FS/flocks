# tb_ip_profile

微步 ThreatBook v3 云 API 命令行客户端：统一拉取 IP/域名/文件/Hunting 等接口，输出结构化 JSON 或简短摘要。

## 环境

- Python 3.8+
- 推荐：`pip install certifi`（缓解 macOS 上 Python `SSL: CERTIFICATE_VERIFY_FAILED`）

## 密钥

任选其一（脚本内勿长期硬编码 key，勿提交仓库）：

1. 环境变量：`export THREATBOOK_API_KEY='你的key'`
2. 配置文件：`~/.openclaw/openclaw.json` → `skills.entries["threatbook-alert"].apiKey`

## 用法要点

- **每次只能选一个查询入口**（如只选 `--ip_query` 或只选 `--file_report`）。
- 通用参数：`--lang zh|en`、`--timeout 秒`、`--json`（仅打印 JSON）。

## `--fields`（四类查询）

适用于 **`--ip_query`**、**`--ip_adv_query`**、**`--domain_query`**、**`--domain_adv_query`**。脚本始终拉取全量响应；若传入 `--fields`，仅在输出的 `threatbook` 中保留列出的**顶层**键（与接口返回求交集）。逗号分隔、**不要空格**。不传则输出响应中已有的全部顶层键（顺序按脚本约定）。

### `--fields` 允许的键名

**`--ip_query`**

`basic`, `judgments`, `tags_classes`, `intelligences`, `samples`, `asn`, `ports`, `cas`, `rdns_list`, `update_time`, `sum_cur_domains`, `scene`, `permalink`

**`--ip_adv_query`**

`ip`, `basic`, `asn`, `cur_domains`, `history_domains`, `permalink`

**`--domain_query`**

允许：`cur_ips`, `cur_whois`, `cas`, `intelligences`, `judgments`, `tags_classes`, `samples`, `categories`, `sum_sub_domains`, `sum_cur_ips`, `rank`, `icp`, `permalink`。

**`--domain_adv_query`**

允许：`domain`, `history_ips`, `history_whoises`, `permalink`。

拼写错误会在启动时报 JSON 错误并列出 `allowed`。

### 示例

```bash
# 白名单：不要 asn 块（本地裁剪，非 API 参数）
python3 tb_ip_profile.py --ip_query 1.1.1.1 --fields basic,judgments,intelligences,permalink --json

# 白名单：只要基础信息与判定
python3 tb_ip_profile.py --ip_query 1.1.1.1 --fields basic,judgments,permalink --json

# 域名查询：不要解析 IP 与 whois 块
python3 tb_ip_profile.py --domain_query example.com --fields cas,judgments,permalink --json
```

其它接口的「子块选择」仍按微步原参数：例如 **`--file_report`** 使用 **`--query-fields`**（summary、network 等）。

## 其它接口速查

| 参数 | 说明 |
|------|------|
| `--ip_reputation` / `--ips` | IP 信誉场景，批量 IP |
| `--ioc` | IOC 场景，IP/域名混合批量 |
| `--domain_context` | 域名上下文，单域名 |
| `--domain_query` | 域名查询，单域名 |
| `--domain_sub_domains` | 子域名，单域名 |
| `--file_upload` | 上传样本；可选 `--sandbox-type`、`--run-time` |
| `--file_report` | 文件报告；可选 `--sandbox-type`、`--query-fields` |
| `--file_report_multiengines` | 多引擎报告 |
| `--hunting_query` | Hunting 搜索；翻页 `--hunting-cursor` |

## 接口测试语句

```bash
# 1. IP 信誉查询
python3 tb_ip_profile.py --ip_reputation 1.1.1.1 --json

# 2. 兼容旧参数 --ips
python3 tb_ip_profile.py --ips 1.1.1.1,8.8.8.8 --json

# 3. IOC 查询（IP/域名混合）
python3 tb_ip_profile.py --ioc 8.8.8.8,example.com --json

# 4. 域名上下文
python3 tb_ip_profile.py --domain_context example.com --json

# 5. IP 查询
python3 tb_ip_profile.py --ip_query 1.1.1.1 --json

# 6. IP 高级查询
python3 tb_ip_profile.py --ip_adv_query 1.1.1.1 --json

# 7. 域名查询
python3 tb_ip_profile.py --domain_query example.com --json

# 8. 域名高级查询
python3 tb_ip_profile.py --domain_adv_query example.com --json

# 9. 子域名查询
python3 tb_ip_profile.py --domain_sub_domains example.com --json

# 10. 文件上传沙箱
python3 tb_ip_profile.py --file_upload ./sample.exe --sandbox-type win7_sp1_enx64_office2010 --run-time 120 --json

# 11. 文件沙箱报告
python3 tb_ip_profile.py --file_report 44d88612fea8a8f36de82e1278abb02f --query-fields summary,network --json

# 12. 文件多引擎报告
python3 tb_ip_profile.py --file_report_multiengines 44d88612fea8a8f36de82e1278abb02f --json

# 13. Hunting 查询
python3 tb_ip_profile.py --hunting_query 'file_name="sample.exe"' --json

# 14. Hunting 翻页
python3 tb_ip_profile.py --hunting_query 'file_name="sample.exe"' --hunting-cursor '下一页cursor' --json
```

## 权限与报错

若返回 `No Access to API Method`，表示当前 key/套餐未开通该 API，与脚本参数是否正确无关。

## 许可与合规

API 使用须遵守微步用户协议与配额；本仓库仅为调用示例代码。
