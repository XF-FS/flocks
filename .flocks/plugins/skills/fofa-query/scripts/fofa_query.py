#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FOFA API 查询：仅 --search 传入 FOFA 语法；预览用 search/next；导出用 search/all 按页拉取。
"""
# 说明：与 Hunter/Quake 技能一致，命中数超过阈值导出前可交互确认（--yes 跳过）。

import argparse
import base64
import csv
import ipaddress
import json
import os
import re
import sys
import time
from datetime import datetime
from typing import Any, Optional

try:
    import requests
except ImportError:
    print("Please install requests: pip install requests")
    sys.exit(1)

BASE = "https://fofa.info/api/v1"
EXPORT_CONFIRM_THRESHOLD = 2000
# 默认仅请求 CSV 14 列映射所需字段；自定义 --fields 只列需要的键
# 映射：server→指纹；cert.subject.org→主体公司（无则空，不用 org）；
# location.country_name+location.region→省份；lastupdatetime→更新时间
DEFAULT_FIELDS = ",".join(
    [
        "link",
        "ip",
        "port",
        "host",
        "title",
        "protocol",
        "base_protocol",
        "server",
        "status_code",
        "icp",
        "lastupdatetime",
        "cert.subject.org",
        "location",
        "country_name",
        "region",
    ]
)
PREVIEW_SIZE = 5
BASE_OUTPUT_DIR = os.path.expanduser("~/.openclaw/assets_measure/fofa")

# 与 tools/360-quake/quake_query.py save_result 表头一致（列顺序固定）
QUAKE_CSV_HEADERS = [
    "url",
    "ip",
    "domain",
    "port",
    "host",
    "title",
    "协议",
    "指纹",
    "网站返回状态",
    "备案",
    "主体公司",
    "更新时间",
    "省份",
    "来源",
]


def _maybe_json_obj(v: Any) -> Any:
    """部分接口把嵌套对象序列化成 JSON 字符串"""
    if isinstance(v, str) and v.strip().startswith("{"):
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            return v
    return v


def _strip_http_scheme(host: Any) -> str:
    """FOFA 偶发把 host 写成带 http(s):// 的 URL，导出时去掉协议前缀"""
    s = str(host or "").strip()
    low = s.lower()
    if low.startswith("https://"):
        return s[8:].strip()
    if low.startswith("http://"):
        return s[7:].strip()
    return s


def _is_ip_host(s: str) -> bool:
    """判断去协议后的 host 是否为 IP（IPv4/IPv6，含 :port、[v6]:port）"""
    t = (s or "").strip()
    if not t:
        return False
    m = re.match(r"^\[(.+)\](:\d+)?$", t)
    if m:
        t = m.group(1)
    elif re.match(r"^\d{1,3}(?:\.\d{1,3}){3}:\d+$", t):
        t = t.rsplit(":", 1)[0]
    elif t.count(":") >= 2 and t.rsplit(":", 1)[-1].isdigit():
        try:
            ipaddress.ip_address(t.rsplit(":", 1)[0])
            return True
        except ValueError:
            pass
    if "%" in t:
        t = t.split("%")[0]
    if "/" in t:
        t = t.split("/")[0]
    try:
        ipaddress.ip_address(t)
        return True
    except ValueError:
        return False


def _domain_from_host(host: Any) -> str:
    """domain 列：与 host 同去协议；若为 IP 则留空"""
    s = _strip_http_scheme(host)
    if not s:
        return ""
    if _is_ip_host(s):
        return ""
    return s


def _get_by_dotted_path(d: Any, path: str) -> Any:
    """支持 cert.subject.org、location.country_name 等点号路径；兼容字面键 cert.subject.org"""
    if not isinstance(d, dict):
        return None
    if path in d:
        return _maybe_json_obj(d[path])
    cur: Any = d
    for part in path.split("."):
        cur = _maybe_json_obj(cur)
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _row_to_cells(row: Any, field_list: list[str]) -> list[str]:
    """FOFA 在 r_type=json 时 results 可能为对象数组；dict 行支持 cert.subject.org 等点号嵌套路径。"""
    if isinstance(row, dict):
        out = []
        for k in field_list:
            v = _get_by_dotted_path(row, k)
            out.append("" if v is None else str(v))
        return out
    if isinstance(row, (list, tuple)):
        xs = list(row)
        n = len(field_list)
        if len(xs) < n:
            xs = xs + [""] * (n - len(xs))
        return ["" if x is None else str(x) for x in xs[:n]]
    return [""] * len(field_list)


def _pick_company(d: dict) -> str:
    """主体公司：仅 cert.subject.org（嵌套或字面键）；无则空"""
    v = _get_by_dotted_path(d, "cert.subject.org")
    if v is not None and str(v).strip():
        return str(v).strip()
    return ""


def _pick_province(d: dict) -> str:
    """省份：location.country_name + location.region（点号路径）；再试 camelCase；最后顶层 country_name、region"""
    cn = _get_by_dotted_path(d, "location.country_name") or _get_by_dotted_path(d, "location.countryName")
    reg = _get_by_dotted_path(d, "location.region") or _get_by_dotted_path(d, "location.Region")
    parts = []
    for x in (cn, reg):
        if x is not None and str(x).strip():
            parts.append(str(x).strip())
    if parts:
        return " / ".join(parts)
    for k in ("country_name", "region"):
        v = d.get(k)
        if v is not None and str(v).strip():
            parts.append(str(v).strip())
    return " / ".join(parts) if parts else ""


def _fofa_dict_to_quake_cells(d: dict) -> list[str]:
    """将 FOFA 单条结果映射为 Quake 同款 14 列（最后一列来源）。"""
    port = d.get("port")
    port_s = "" if port is None else str(port)

    proto = str(d.get("protocol") or "").strip()
    base_p = str(d.get("base_protocol") or "").strip()
    if proto and base_p and base_p.lower() != proto.lower():
        proto_col = f"{proto} ({base_p})"
    else:
        proto_col = proto or base_p

    fingerprint = str(d.get("server") or "").strip()

    province = _pick_province(d)
    company = _pick_company(d)

    host_norm = _strip_http_scheme(d.get("host"))
    domain_col = _domain_from_host(d.get("host"))

    return [
        str(d.get("link") or ""),
        str(d.get("ip") or ""),
        domain_col,
        port_s,
        host_norm,
        str(d.get("title") or ""),
        proto_col,
        str(fingerprint),
        str(d.get("status_code") or ""),
        str(d.get("icp") or ""),
        company,
        str(d.get("lastupdatetime") or ""),
        str(province),
        "FOFA",
    ]


def _fofa_to_quake_row(row: Any, field_list: list[str]) -> list[str]:
    if isinstance(row, dict):
        return _fofa_dict_to_quake_cells(row)
    if isinstance(row, (list, tuple)):
        cells = _row_to_cells(row, field_list)
        d = {field_list[i]: cells[i] if i < len(cells) else "" for i in range(len(field_list))}
        return _fofa_dict_to_quake_cells(d)
    return [""] * len(QUAKE_CSV_HEADERS)


def _sanitize_filename(value: str, max_len: int = 40) -> str:
    s = (value or "").strip().lower()
    s = re.sub(r"^https?://", "", s)
    s = s.split("/")[0].split(":")[0]
    s = re.sub(r'[^a-zA-Z0-9._-]+', '_', s).strip('._-')
    return (s or "query")[:max_len]


def _extract_query_keyword(query: str) -> str:
    patterns = [
        r'ip\s*=\s*"([^"]+)"',
        r'domain\s*=\s*"([^"]+)"',
        r'host\s*=\s*"([^"]+)"',
    ]
    for pat in patterns:
        m = re.search(pat, query, re.IGNORECASE)
        if m:
            return _sanitize_filename(m.group(1))
    m = re.search(r'((?:\d{1,3}\.){3}\d{1,3})', query)
    if m:
        return _sanitize_filename(m.group(1))
    m = re.search(r'([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', query)
    if m:
        return _sanitize_filename(m.group(1))
    return "query"


def build_output_path(query: str, user_output: Optional[str]) -> str:
    os.makedirs(BASE_OUTPUT_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    keyword = _extract_query_keyword(query)
    if user_output:
        ext = os.path.splitext(os.path.basename(user_output))[1] or ".csv"
    else:
        ext = ".csv"
    filename = f"fofa_{keyword}_{ts}{ext}"
    return os.path.join(BASE_OUTPUT_DIR, filename)


def encode_qbase64(query: str) -> str:
    """FOFA 要求对查询语法做标准 Base64 编码为 qbase64"""
    return base64.b64encode(query.encode("utf-8")).decode("ascii")


def _load_api_key() -> Optional[str]:
    api_key = os.environ.get("FOFA_API_KEY")
    if api_key:
        return api_key
    for path in (
        os.path.join(os.getcwd(), "config.json"),
        os.path.join(os.path.dirname(__file__), "config.json"),
    ):
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    return cfg.get("api_key") or cfg.get("FOFA_API_KEY")
            except (json.JSONDecodeError, OSError):
                continue
    return None


def clamp_page_size(query: str, size: int) -> int:
    """官方：含 body 时单页最大 500；含 cert/banner 时单页最大 2000；否则最大 10000"""
    q = query.lower()
    s = max(1, min(size, 10000))
    if "body" in q:
        return min(s, 500)
    if "banner" in q or "cert" in q:
        return min(s, 2000)
    return s


def _confirm_export_if_needed(total: int, fetch_cap: int, skip_confirm: bool) -> bool:
    if skip_confirm or total <= EXPORT_CONFIRM_THRESHOLD:
        return True
    try:
        ans = input(
            f"命中数 {total}（将导出至多 {fetch_cap} 条），超过 {EXPORT_CONFIRM_THRESHOLD}，是否继续？(y/N) "
        ).strip().lower()
    except EOFError:
        return False
    return ans in ("y", "yes")


def _format_fofa_preview_table(rows: list[Any], field_list: list[str], total: int, max_display_rows: int = 5) -> str:
    """与 Quake/Hunter 一致的终端表格预览（基于 14 列映射）"""
    batch_n = len(rows)
    summary = f"查询结果: 共 {total} 条记录，本批返回 {batch_n} 条"
    if batch_n > max_display_rows:
        summary += f"（终端预览前 {max_display_rows} 条）"
    lines = [summary, "-" * 120]
    lines.append(f"{'URL':<38} {'标题':<22} {'主机':<22} {'状态':<6} {'省份':<10} {'协议':<8}")
    lines.append("-" * 120)
    show = rows[:max_display_rows]
    for row in show:
        q = _fofa_to_quake_row(row, field_list)
        url = q[0][:36] + ".." if len(q[0]) > 38 else q[0]
        title = q[5][:20] + ".." if len(q[5]) > 22 else q[5]
        host = q[4][:20] + ".." if len(q[4]) > 22 else q[4]
        st = (q[7] or "")[:6]
        prov = q[12][:8] + ".." if len(q[12]) > 10 else q[12]
        protocol = (q[6] or "")[:8]
        lines.append(f"{url:<38} {title:<22} {host:<22} {st:<6} {prov:<10} {protocol:<8}")
    return "\n".join(lines)


class FofaClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or _load_api_key()
        if not self.api_key:
            raise ValueError("Missing API key: use --api-key, FOFA_API_KEY, or config.json api_key")

    def _get(self, path: str, params: dict) -> Optional[dict]:
        p = {"key": self.api_key, "r_type": "json", **params}
        try:
            r = requests.get(f"{BASE}{path}", params=p, timeout=120)
            r.raise_for_status()
            data = r.json()
            if data.get("error"):
                err = data.get("errmsg") or data.get("message") or str(data)
                print(f"FOFA API error: {err}", file=sys.stderr)
                return None
            return data
        except Exception as e:
            print(f"Request failed: {e}", file=sys.stderr)
            return None

    def info_my(self) -> Optional[dict]:
        return self._get("/info/my", {})

    def search_next(self, qbase64: str, fields: str, size: int, full: bool, next_token: Optional[str]) -> Optional[dict]:
        params: dict[str, Any] = {
            "qbase64": qbase64,
            "fields": fields,
            "size": size,
            "full": str(full).lower(),
        }
        if next_token:
            params["next"] = next_token
        return self._get("/search/next", params)

    def search_all(self, qbase64: str, fields: str, size: int, full: bool, page: int) -> Optional[dict]:
        """传统分页，用于 search/next 无游标时从第 2 页起补足（与首包第 1 页衔接）"""
        params: dict[str, Any] = {
            "qbase64": qbase64,
            "fields": fields,
            "size": size,
            "full": str(full).lower(),
            "page": max(1, int(page)),
        }
        return self._get("/search/all", params)


def _write_csv_chunk(
    path: str,
    field_list: list[str],
    rows: list[Any],
    write_header: bool,
    query: Optional[str] = None,
) -> None:
    """一律追加写入、不覆盖；write_header 为真时先写查询语句行，再写表头。"""
    if not rows:
        return
    enc = "utf-8-sig" if write_header else "utf-8"
    with open(path, "a", newline="", encoding=enc) as f:
        w = csv.writer(f)
        if write_header:
            w.writerow([f"# query: {query or ''}"])
            w.writerow(QUAKE_CSV_HEADERS)
        for row in rows:
            w.writerow(_fofa_to_quake_row(row, field_list))


def run_preview(client: FofaClient, query: str, fields: str, full: bool) -> int:
    field_list = [x.strip() for x in fields.split(",") if x.strip()]
    qb = encode_qbase64(query)
    ps = clamp_page_size(query, PREVIEW_SIZE)
    data = client.search_next(qb, fields, ps, full, None)
    if not data:
        return 1
    total = int(data.get("size") or 0)
    print(f"Query: {data.get('query', query)}")
    print(f"Total: {total}")
    print("-" * 50)
    res = data.get("results") or []
    for i, row in enumerate(res[:PREVIEW_SIZE]):
        cells = _fofa_to_quake_row(row, field_list)
        print(f"[{i+1}] " + " | ".join(cells))
    if total > EXPORT_CONFIRM_THRESHOLD:
        print(f"\nLarge result set. Export with: --output file.csv --yes")
    return 0


def run_export(
    client: FofaClient,
    query: str,
    fields: str,
    output: str,
    page_size: int,
    max_rows: int,
    full: bool,
    skip_confirm: bool,
) -> int:
    """使用 search/all 按页导出（与游标版相比可一次拉满单页；终端日志与 Quake/Hunter 对齐）"""
    qb = encode_qbase64(query)
    ps = clamp_page_size(query, page_size)
    field_list = [x.strip() for x in fields.split(",") if x.strip()]

    print(f"查询语句: {query}")
    print("-" * 50)
    print("正在查询总数...")
    time.sleep(0.35)

    first = client.search_all(qb, fields, ps, full, 1)
    if not first:
        print("查询失败")
        return 1
    total = int(first.get("size") or 0)
    if total == 0:
        print("未查询到结果")
        return 0
    fetch_cap = total if max_rows <= 0 else min(total, max_rows)
    batch_count = max(1, (fetch_cap + ps - 1) // ps)

    print(f"总记录数: {total}")
    print(f"计划获取: {fetch_cap} 条")
    print(f"每批条数 (--page_size): {ps} 条/批")
    print("-" * 50)

    if not _confirm_export_if_needed(total, fetch_cap, skip_confirm):
        print("已取消导出。")
        return 0

    pre_existing = os.path.exists(output) and os.path.getsize(output) > 0

    written = 0
    chunk_idx = 0
    page = 1

    while written < fetch_cap and page <= 10000:
        if page > 1:
            time.sleep(0.35)
        res = first if page == 1 else client.search_all(qb, fields, ps, full, page)
        if not res:
            print(f"第 {page} 页请求失败", file=sys.stderr)
            break
        arr = list(res.get("results") or [])
        if not arr:
            break
        need = fetch_cap - written
        chunk = arr[:need]
        start_idx = written + 1
        end_idx = written + len(chunk)
        print(f"正在查询: 第 {chunk_idx + 1}/{batch_count} 批 ({start_idx}-{min(end_idx, fetch_cap)}) [search/all page={page}]")

        if chunk_idx == 0:
            print(_format_fofa_preview_table(chunk, field_list, total))

        write_header = (not pre_existing) and chunk_idx == 0
        _write_csv_chunk(output, field_list, chunk, write_header, query)
        written += len(chunk)
        print(f"已获取: {written}/{fetch_cap} 条")

        if written >= fetch_cap:
            break
        page += 1
        chunk_idx += 1

    print(f"\n{'='*50}")
    print(f"查询完成，共获取 {written} 条结果")
    print(f"结果已保存到: {output}")
    return 0


def main():
    p = argparse.ArgumentParser(description="FOFA API（预览 search/next；导出 search/all）")
    p.add_argument("--search", help="FOFA query syntax (plain text; encoded as qbase64)")
    p.add_argument("--api-key", dest="api_key", help="FOFA API key")
    p.add_argument(
        "--fields",
        default=DEFAULT_FIELDS,
        help="FOFA fields，逗号分隔；默认仅为 CSV 14 列映射所需键，勿重复传全表字段",
    )
    p.add_argument("--page_size", type=int, default=500, help="Per-request size (clamped by FOFA rules), default 500")
    p.add_argument("--size", "-s", type=int, default=0, help="Max rows to export, 0 = unlimited")
    p.add_argument("--full", action="store_true", help="Search full data (not only last year)")
    p.add_argument("-o", "--output", help="Export CSV path")
    p.add_argument("--yes", "-y", action="store_true", help="Skip confirm when hits > 2000")
    p.add_argument("--info", action="store_true", help="Account info (no --search)")

    args = p.parse_args()

    try:
        client = FofaClient(api_key=args.api_key)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.info:
        data = client.info_my()
        if data:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        sys.exit(0 if data else 1)

    if not args.search or not str(args.search).strip():
        print("Error: provide --search 'FOFA syntax'", file=sys.stderr)
        sys.exit(1)

    query = str(args.search).strip()

    if args.output:
        output_path = build_output_path(query, args.output)
        sys.exit(
            run_export(
                client,
                query,
                args.fields,
                output_path,
                args.page_size,
                args.size,
                args.full,
                args.yes,
            )
        )

    sys.exit(run_preview(client, query, args.fields, args.full))


if __name__ == "__main__":
    main()
