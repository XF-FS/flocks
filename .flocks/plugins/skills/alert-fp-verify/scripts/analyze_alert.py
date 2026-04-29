#!/usr/bin/env python3
"""
TDP 告警流量特征提取脚本 (原子化版本)。
支持灵活的过滤条件，在 pcap 中定位并分析上下文。
"""

import sys
import json
import shutil
import subprocess
import argparse
from pathlib import Path
from typing import List, Dict

_TSHARK_PATH = shutil.which("tshark") or "/usr/bin/tshark"

def build_flow_filter(src_ip: str = None, dst_ip: str = None, src_port: int = None, dst_port: int = None) -> str:
    """
    根据传入的五元组条件构造 tshark display filter。
    """
    conditions = []

    if src_ip:
        conditions.append(f"ip.src == {src_ip}")
    if dst_ip:
        conditions.append(f"ip.dst == {dst_ip}")
    if src_port:
        conditions.append(f"(tcp.srcport == {src_port} or udp.srcport == {src_port})")
    if dst_port:
        conditions.append(f"(tcp.dstport == {dst_port} or udp.dstport == {dst_port})")

    return " and ".join(conditions)

def run_tshark_search(pcap_path: str, flow_filter: str, term: str, src_ip: str = None, src_port: int = None):
    """
    使用 tshark 在 pcap 中搜索字符串。
    """
    try:
        safe_term = term.replace("\\", "\\\\").replace('"', '\\"')
        # 优先匹配 DNS 查询字段
        if flow_filter:
            display_filter = f'({flow_filter}) and (dns.qry.name contains "{safe_term}" or frame contains "{safe_term}")'
        else:
            display_filter = f'dns.qry.name contains "{safe_term}" or frame contains "{safe_term}"'
        
        cmd = [
            _TSHARK_PATH, "-r", pcap_path,
            "-Y", display_filter,
            "-T", "fields",
            "-e", "frame.number",
            "-e", "ip.src",
            "-e", "tcp.srcport",
            "-e", "dns.qry.name",
            "-e", "http.request",
            "-e", "http.response",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0 or not result.stdout.strip():
            return "", 0
        
        line = result.stdout.strip().split("\n")[0]
        parts = line.split("\t")
        if len(parts) >= 5:
            frame_num = int(parts[0])
            pkt_src = parts[1].strip()
            pkt_sport = int(parts[2]) if parts[2].strip().isdigit() else 0
            is_http_request = parts[3].strip() == "1"
            is_http_response = parts[4].strip() == "1"

            if is_http_request:
                return "request", frame_num
            if is_http_response:
                return "response", frame_num
            
            # 无法直接从协议字段判断时，再退回到五元组启发式判断
            if src_ip and pkt_src == src_ip:
                return "request", frame_num
            if src_port and pkt_sport == src_port:
                return "request", frame_num
            return "unknown", frame_num
        return "", 0
    except Exception as e:
        print(f"[!] Search error: {e}")
        return "", 0

def get_http_context(pcap_path: str, target_frame: int, flow_filter: str, count: int = 5) -> List[Dict]:
    """
    获取目标包前后的 HTTP 请求上下文
    """
    try:
        # 提取 HTTP 请求包
        if flow_filter:
            filter_str = f"http.request and ({flow_filter})"
        else:
            filter_str = "http.request"
            
        cmd = [
            _TSHARK_PATH, "-r", pcap_path,
            "-Y", filter_str,
            "-T", "fields",
            "-e", "frame.number",
            "-e", "http.request.method",
            "-e", "http.host",
            "-e", "http.request.uri",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return []
        
        all_reqs = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip(): continue
            parts = line.split("\t")
            if len(parts) >= 4:
                all_reqs.append({
                    "frame": int(parts[0]),
                    "method": parts[1],
                    "host": parts[2],
                    "uri": parts[3]
                })
        
        if not all_reqs: return []

        target_idx = -1
        for i, req in enumerate(all_reqs):
            if req["frame"] >= target_frame:
                target_idx = i
                break
        if target_idx == -1: target_idx = len(all_reqs) - 1

        start = max(0, target_idx - count)
        end = min(len(all_reqs), target_idx + count + 1)
        
        context = []
        for i in range(start, end):
            req = all_reqs[i]
            req["rel"] = i - target_idx
            if req["rel"] == 0: req["target"] = True
            context.append(req)
        return context
    except Exception:
        return []

def main():
    parser = argparse.ArgumentParser(description="原子化流量分析脚本")
    parser.add_argument("--pcap", required=True, help="pcap 文件路径")
    parser.add_argument("--src", help="源 IP")
    parser.add_argument("--dst", help="目的 IP")
    parser.add_argument("--sport", type=int, help="源端口")
    parser.add_argument("--dport", type=int, help="目的端口")
    parser.add_argument("--term", required=True, help="检索的特征字符串")
    parser.add_argument("--count", type=int, default=5, help="上下文请求数量 (默认 5)")
    parser.add_argument("--json", action="store_true", help="仅输出 JSON 结果")
    
    args = parser.parse_args()

    if not Path(args.pcap).exists():
        print(f"[ERROR] pcap not found: {args.pcap}", file=sys.stderr)
        sys.exit(1)

    flow_filter = build_flow_filter(args.src, args.dst, args.sport, args.dport)

    where, frame_num = run_tshark_search(args.pcap, flow_filter, args.term, args.src, args.sport)
    
    context = []
    if frame_num > 0:
        context = get_http_context(args.pcap, frame_num, flow_filter, count=args.count)

    result = {
        "target_found": bool(where),
        "location": where,
        "frame_number": frame_num,
        "search_term": args.term,
        "flow_filter": flow_filter,
        "http_context": context
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"[*] Search Term: {args.term}")
        print(f"[*] Filter: {flow_filter or 'None'}")
        print(f"[*] Found in: {where or 'Not Found'} (Frame: {frame_num})")
        if context:
            print(f"[*] HTTP Context (Total {len(context)}):")
            for c in context:
                mark = "[*]" if c.get("target") else "   "
                print(f"{mark} [{c['rel']:+d}] Frame {c['frame']}: {c['method']} {c['host']}{c['uri']}")

if __name__ == "__main__":
    main()
