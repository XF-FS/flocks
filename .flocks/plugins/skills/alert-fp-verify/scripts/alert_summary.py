#!/usr/bin/env python3
"""
告警 JSON 预处理脚本
只提取关键字段，减少 token 消耗

用法:
  python3 alert_summary.py <json_file>                    # 默认摘要
  python3 alert_summary.py <json_file> --fields field1,field2  # 指定字段
  python3 alert_summary.py <json_file> --full              # 完整字段
  python3 alert_summary.py <json_file> --list-fields       # 列出所有可用字段
"""

import json
import sys
import argparse

# JSON 字段路径映射（支持嵌套路径，用 . 分隔）
FIELD_MAPPING = {
    # 基本信息
    "name": "threat.name",
    "type": "threat.type",
    "level": "threat.level",
    "severity": "threat.severity",
    "confidence": "threat.confidence",
    "highlight": "threat.high_light_content",
    "mitre": "threat.tactics",
    "mitre_id": "threat.tactics_id",
    "msg": "threat.msg",
    "payload": "threat.payload",
    "alert_id": "threat.id",
    "suuid": "threat.suuid",
    "name_lower": "threat.name_lower",
    "result": "threat.result",
    "incident_id": "incident_id",
    
    # 情报相关字段（T开头告警ID）
    "ioc_ip": "external_ip",      # IOC IP（带兜底提取）
    "ioc_domain": "url_host",     # IOC 域名（带兜底提取）
    "ioc_url": "net.http.url",    # IOC URL（带兜底提取）
    "external_ip": "external_ip", # 外部IP
    "attacker": "attacker",       # 攻击者IP
    
    # 原始数据（大字段，按需提取）
    "raw_data": "raw_data",
    
    # 五元组
    "src_ip": "net.src_ip",
    "src_port": "net.src_port",
    "dest_ip": "net.dest_ip",
    "dest_port": "net.dest_port",
    "proto": "net.proto",
    "real_src_ip": "net.real_src_ip",
    "http_xff": "net.http_xff",
    
    # HTTP 信息
    "url": "net.http.url",
    "host": "net.http.reqs_host",
    "method": "net.http.method",
    "status": "net.http.status",
    "referer": "net.http.reqs_referer",
    "user_agent": "net.http.reqs_user_agent",
    "content_type": "net.http.resp_content_type",
    
    # 请求/响应体
    "reqs_body": "net.http.reqs_body",
    "resp_body": "net.http.resp_body",
    "reqs_header": "net.http.reqs_header",
    "resp_header": "net.http.resp_header",
    
    # 流量信息
    "flow_id": "flow_id",
    "pcap_file": "threat.pcap_file",
    "bytes_in": "net.bytes_toserver",
    "bytes_out": "net.bytes_toclient",
    "pkts_in": "net.pkts_toserver",
    "pkts_out": "net.pkts_toclient",
    
    # 触发特征
    "pat_info": "pat_info",

    # ================== File 模块补充字段 ==================
    "file_hash": "hash",
    "file_hash_inner": "file_upload_data.hash",
    "file_size": "file_upload_data.FileSize",
    "file_magic": "file_upload_data.Magic",
    "file_action": "file_upload_data.file_action",
    "detect_source": "threat.detect_source",
    "multi_engine": "threat.multi_engine_result",
    # =========================================================
    
    # 其他
    "domain": "url_host",
    "machine": "machine",
    "attacker": "attacker",
    "victim": "victim",
    "direction": "direction",
    "incident_id": "incident_id",
    "time": "time",
}

# 需要按优先级兜底提取的字段
FIELD_CANDIDATES = {
    "ioc_ip": ["external_ip", "attacker", "net.real_src_ip", "net.src_ip"],
    "ioc_domain": ["url_host", "net.http.reqs_host"],
    "ioc_url": ["net.http.url"],
}

# 默认提取的字段（固定分析字段模板）
DEFAULT_FIELDS = [
    # 五元组
    "src_ip", "src_port", "dest_ip", "dest_port", "proto",

    # HTTP
    "method", "reqs_header", "host", "resp_header", "resp_body",
    "reqs_body", "user_agent", "status",

    # 威胁核心字段
    "payload", "suuid", "name_lower", "level", "result", "msg", "time",
]

# 完整字段列表（用于 --full）
FULL_FIELDS = list(FIELD_MAPPING.keys())

def get_nested_value(data, path):
    """从嵌套字典中获取值，支持 . 分隔的路径"""
    keys = path.split(".")
    value = data
    for key in keys:
        if isinstance(value, dict):
            value = value.get(key, "")
        else:
            return ""
    return value

def extract_fields(json_path, fields, preview_len=500):
    """提取指定字段"""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    result = {}
    for field in fields:
        if field in FIELD_CANDIDATES:
            value = ""
            for candidate in FIELD_CANDIDATES[field]:
                value = get_nested_value(data, candidate)
                if value:
                    break
            result[field] = value
        elif field in FIELD_MAPPING:
            path = FIELD_MAPPING[field]
            value = get_nested_value(data, path)
            
            # 对请求/响应体做预览截断
            if field in ["reqs_body", "resp_body"] and isinstance(value, str):
                if len(value) > preview_len:
                    value = value[:preview_len] + "...(truncated)"
            
            # 对 header 做预览截断
            if field in ["reqs_header", "resp_header"] and isinstance(value, str):
                if len(value) > 500:
                    value = value[:500] + "...(truncated)"
            
            result[field] = value
        else:
            # 支持直接路径，如 "threat.name" 或 "net.http.url"
            value = get_nested_value(data, field)
            result[field] = value
    
    return result

def list_available_fields():
    """列出所有可用字段"""
    print("=" * 60)
    print("📋 可用字段列表")
    print("=" * 60)
    
    categories = {
        "基本信息": ["name", "type", "level", "severity", "confidence", "highlight", "mitre", "mitre_id", "msg", "payload", "alert_id", "incident_id"],
        "五元组": ["src_ip", "src_port", "dest_ip", "dest_port", "proto", "real_src_ip", "http_xff"],
        "HTTP信息": ["url", "host", "method", "status", "referer", "user_agent", "content_type"],
        "情报相关": ["ioc_ip", "ioc_domain", "ioc_url", "external_ip", "attacker"],
        "请求/响应": ["reqs_body", "resp_body", "reqs_header", "resp_header"],
        "流量信息": ["flow_id", "pcap_file", "bytes_in", "bytes_out", "pkts_in", "pkts_out"],
        "原始数据": ["raw_data"],
        "其他信息": ["domain", "machine", "victim", "direction", "time", "pat_info"],
    }
    
    for cat, fields in categories.items():
        print(f"\n【{cat}】")
        for f in fields:
            print(f"  {f:<15} -> {FIELD_MAPPING.get(f, f)}")
    
    print("\n" + "=" * 60)
    print("💡 提示: 也可以直接使用 JSON 路径，如 threat.name 或 net.http.url")
    print("=" * 60)

def main():
    parser = argparse.ArgumentParser(
        description="告警 JSON 预处理脚本 - 提取关键字段减少 token 消耗",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s alert.json                       # 默认摘要（精简字段）
  %(prog)s alert.json --fields name,url     # 指定字段
  %(prog)s alert.json --full                # 完整字段
  %(prog)s --list-fields                    # 列出所有可用字段
  %(prog)s alert.json --fields reqs_body --preview 1000  # 指定预览长度
"""
    )
    parser.add_argument("json_file", nargs="?", help="告警 JSON 文件路径")
    parser.add_argument("--fields", "-f", help="指定要提取的字段，逗号分隔")
    parser.add_argument("--full", action="store_true", help="提取所有字段")
    parser.add_argument("--list-fields", action="store_true", help="列出所有可用字段")
    parser.add_argument("--preview", "-p", type=int, default=500, help="请求/响应体预览长度（默认500）")
    parser.add_argument("--json", "-j", action="store_true", help="输出 JSON 格式")
    
    args = parser.parse_args()
    
    # 列出字段（不需要 json_file）
    if args.list_fields:
        list_available_fields()
        return
    
    # 检查 json_file
    if not args.json_file:
        parser.error("需要提供 JSON 文件路径，或使用 --list-fields 列出可用字段")
    
    # 确定要提取的字段
    if args.full:
        fields = FULL_FIELDS
    elif args.fields:
        fields = [f.strip() for f in args.fields.split(",")]
    else:
        fields = DEFAULT_FIELDS
    
    # 提取字段
    result = extract_fields(args.json_file, fields, args.preview)
    
    # 根据 suuid 自动判断检出类型
    suuid = result.get("suuid", "")
    if isinstance(suuid, str) and suuid:
        if suuid.startswith("T"):
            result["detection_type"] = "情报检出"
        elif suuid.startswith("F"):
            result["detection_type"] = "文件还原检出"
        else:
            result["detection_type"] = "未知类型"

    # 反向映射：简写字段名 -> 完整路径
    REVERSE_MAPPING = {v: k for k, v in FIELD_MAPPING.items()}
    
    # 输出
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("=" * 60)
        print("📋 告警摘要")
        print("=" * 60)
        for key, value in result.items():
            if value:
                if isinstance(value, list):
                    value = ", ".join(str(v) for v in value)
                # 显示完整路径
                full_path = FIELD_MAPPING.get(key, key)
                print(f"{full_path}: {value}")
        print("=" * 60)
        print(f"\n💡 默认已自动按 suuid 分流 (T=情报, F=文件还原)")

if __name__ == "__main__":
    main()
