#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import csv
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
    print("Please install requests: pip install requests", file=sys.stderr)
    sys.exit(1)


DEFAULT_BASE_URL = "http://10.66.192.246:31276/api/search/asset"
FALLBACK_BASE_URL = "https://asset01.threatbook-inc.cn/api/search/asset"
EXPORT_CONFIRM_THRESHOLD = 2000
BASE_OUTPUT_DIR = os.path.expanduser("~/.openclaw/assets_measure/matrix")
CSV_HEADERS = [
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
    "地区",
    "来源",
]


def _sanitize_filename(value: str, max_len: int = 40) -> str:
    s = (value or "").strip().lower()
    s = re.sub(r"^https?://", "", s)
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", s).strip("._-")
    return (s or "query")[:max_len]


def _extract_query_keyword(query: str) -> str:
    patterns = [
        r'ip\s*=+\s*"([^"]+)"',
        r'domain\s*=+\s*"([^"]+)"',
        r'root_domain\s*=+\s*"([^"]+)"',
        r'hostname\s*=+\s*"([^"]+)"',
        r'cert\.subject\.org\s*=+\s*"([^"]+)"',
        r'body\s*=+\s*"([^"]+)"',
        r'title\s*=+\s*"([^"]+)"',
    ]
    for pat in patterns:
        m = re.search(pat, query, re.IGNORECASE)
        if m:
            return _sanitize_filename(m.group(1))
    return "query"


def build_output_path(query: str, user_output: Optional[str]) -> str:
    if user_output:
        output_path = os.path.abspath(os.path.expanduser(user_output))
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        return output_path
    os.makedirs(BASE_OUTPUT_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    keyword = _extract_query_keyword(query)
    return os.path.join(BASE_OUTPUT_DIR, f"matrix_{keyword}_{ts}.csv")


def _load_api_key() -> Optional[str]:
    api_key = os.environ.get("MATRIX_API_KEY")
    if api_key:
        return api_key
    for path in (
        os.path.join(os.path.dirname(__file__), "config.json"),
        os.path.expanduser("~/.matrix/config.json"),
        os.path.expanduser("~/.config/matrix/config.json"),
    ):
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f).get("api_key")
        except (OSError, json.JSONDecodeError):
            continue
    return None


def _confirm_export_if_needed(total: int, fetch_cap: int, skip_confirm: bool) -> bool:
    if skip_confirm or total <= EXPORT_CONFIRM_THRESHOLD:
        return True
    try:
        ans = input(
            f"Total hits {total} (will export up to {fetch_cap} rows), exceeds {EXPORT_CONFIRM_THRESHOLD}. Proceed? (y/N) "
        ).strip().lower()
    except EOFError:
        return False
    return ans in ("y", "yes")


def _flatten(value: Any, prefix: str = "", out: Optional[dict] = None) -> dict:
    if out is None:
        out = {}
    if isinstance(value, dict):
        for k, v in value.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            _flatten(v, key, out)
        return out
    if isinstance(value, list):
        if value and all(not isinstance(x, (dict, list)) for x in value):
            out[prefix] = ", ".join(str(x) for x in value)
        else:
            out[prefix] = json.dumps(value, ensure_ascii=False)
        return out
    out[prefix] = value
    return out


def _pick(flat: dict, *keys: str) -> str:
    for key in keys:
        value = flat.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _join_location(*parts: str) -> str:
    values = [str(part).strip() for part in parts if str(part).strip()]
    return "-".join(values)


def _normalize_url(url: str, protocol: str, host: str, port: str) -> str:
    u = (url or "").strip()
    if u.startswith(("http://", "https://")):
        return u
    p = (protocol or "").strip().lower()
    h = (host or "").strip()
    po = str(port or "").strip()
    if not h:
        return ""
    if p not in ("http", "https"):
        p = "https" if po == "443" else "http"
    if po and po not in ("80", "443") and ":" not in h:
        return f"{p}://{h}:{po}"
    return f"{p}://{h}"


def extract_item_info(item: dict) -> dict:
    flat = _flatten(item)
    ip = _pick(flat, "ip")
    domain = _pick(flat, "domain.domain")
    host = _pick(flat, "host", "hostname", "web.host", "http.host", "asset.host", "domain.domain", "domain") or ip
    port = _pick(flat, "port")
    protocol = _pick(flat, "protocol", "service", "service.name", "scheme", "web.protocol", "asset.protocol")
    url = _pick(flat, "url")
    title = _pick(flat, "web.title")
    fingerprint = _pick(flat, "fingerprint", "app", "apps", "server", "web.server", "http.server", "banner")
    status_code = _pick(flat, "web.http_status_code")
    icp = _pick(flat, "domain.record_site_license")
    company = _pick(flat, "domain.record_company")
    update_time = _pick(flat, "created_at")
    location = _join_location(
        _pick(flat, "address.country"),
        _pick(flat, "address.province"),
        _pick(flat, "address.city"),
    )

    return {
        "url": _normalize_url(url, protocol, host or domain or ip, port),
        "ip": ip,
        "domain": domain,
        "port": port,
        "host": host or domain or ip,
        "title": title,
        "协议": protocol,
        "指纹": fingerprint,
        "网站返回状态": status_code,
        "备案": icp,
        "主体公司": company,
        "更新时间": update_time,
        "地区": location,
        "来源": "Matrix",
    }


def format_result(rows: list[dict], total: Optional[int], max_display_rows: int = 5) -> str:
    shown = rows[:max_display_rows]
    total_text = total if total is not None else len(rows)
    summary = f"查询结果: 共 {total_text} 条记录，本批返回 {len(rows)} 条"
    if len(rows) > max_display_rows:
        summary += f"（终端预览前 {max_display_rows} 条）"
    lines = [summary, "-" * 120]
    lines.append(f"{'URL':<38} {'标题':<22} {'主机':<22} {'状态':<6} {'地区':<18} {'协议':<8}")
    lines.append("-" * 120)
    for item in shown:
        info = extract_item_info(item)
        url = info["url"][:36] + ".." if len(info["url"]) > 38 else info["url"]
        title = info["title"][:20] + ".." if len(info["title"]) > 22 else info["title"]
        host = info["host"][:20] + ".." if len(info["host"]) > 22 else info["host"]
        status = info["网站返回状态"][:6]
        location = info["地区"][:16] + ".." if len(info["地区"]) > 18 else info["地区"]
        protocol = info["协议"][:8]
        lines.append(f"{url:<38} {title:<22} {host:<22} {status:<6} {location:<18} {protocol:<8}")
    return "\n".join(lines)


class MatrixClient:
    def __init__(self, api_key: Optional[str] = None, base_url: str = DEFAULT_BASE_URL):
        self.api_key = api_key or _load_api_key()
        if not self.api_key:
            raise ValueError("Missing API key: use --api-key, MATRIX_API_KEY, or scripts/config.json api_key")
        self.base_url = base_url

    def search(self, query: str, limit: int, page: int, select: str = "", csv_mode: bool = False) -> dict:
        params = {
            "apikey": self.api_key,
            "q": query,
            "limit": max(1, int(limit)),
            "page": max(1, int(page)),
        }
        if select:
            params["select"] = select
        if csv_mode:
            params["CSV"] = "CSV"
        try:
            r = requests.get(self.base_url, params=params, timeout=60)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            return {"code": -1, "message": str(e), "data": {}}
        except ValueError as e:
            return {"code": -1, "message": f"invalid json: {e}", "data": {}}


def _extract_rows(payload: dict) -> tuple[list[dict], Optional[int]]:
    if not isinstance(payload, dict):
        return [], None
    top_total = payload.get("total") or payload.get("count") or payload.get("total_count") or payload.get("hits")
    data = payload.get("data")
    if isinstance(data, dict):
        rows = data.get("data")
        total = data.get("total") or data.get("count") or data.get("total_count") or data.get("hits") or top_total
        if isinstance(rows, list):
            return rows, int(total) if str(total).isdigit() else None
    if isinstance(data, list):
        total = top_total if str(top_total).isdigit() else len(data)
        return data, int(total)
    return [], None


def _save_result(rows: list[dict], output_file: str, write_header: bool):
    if not rows:
        return
    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
    enc = "utf-8-sig" if write_header else "utf-8"
    with open(output_file, "a", encoding=enc, newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(CSV_HEADERS)
        for item in rows:
            info = extract_item_info(item)
            writer.writerow([info[h] for h in CSV_HEADERS])


def _is_success(payload: dict) -> bool:
    code = payload.get("code")
    return code in (0, "0", 200, "200")


def run_preview(client: MatrixClient, query: str, page_size: int, page: int, select: str, csv_mode: bool) -> int:
    result = client.search(query, page_size, page, select, csv_mode)
    if not _is_success(result):
        print(f"查询失败: {result.get('message', 'unknown error')}", file=sys.stderr)
        return 1
    rows, total = _extract_rows(result)
    if not rows:
        print("未查询到结果")
        return 0
    print(f"查询语句: {query}")
    print("-" * 50)
    print(format_result(rows, total))
    return 0


def run_export(client: MatrixClient, query: str, output: str, page_size: int, start_page: int, max_rows: int, select: str, csv_mode: bool, skip_confirm: bool) -> int:
    first = client.search(query, page_size, start_page, select, csv_mode)
    if not _is_success(first):
        print(f"查询失败: {first.get('message', 'unknown error')}", file=sys.stderr)
        return 1
    first_rows, total = _extract_rows(first)
    if not first_rows:
        print("未查询到结果")
        return 0
    fetch_cap = total if total is not None and max_rows <= 0 else max_rows
    if fetch_cap <= 0:
        fetch_cap = total if total is not None else len(first_rows)
    if total is None and max_rows <= 0:
        print("未返回总数信息，将持续翻页直到空结果")
    if total is not None:
        print(f"总记录数: {total}")
    print(f"计划获取: {fetch_cap} 条")
    print(f"每批条数 (--page_size): {page_size} 条/批")
    print("-" * 50)

    confirm_total = total if total is not None else fetch_cap
    if not _confirm_export_if_needed(confirm_total, fetch_cap, skip_confirm):
        print("Export cancelled.")
        return 0

    current_page = start_page
    written = 0
    batch_idx = 0
    pre_existing = os.path.exists(output) and os.path.getsize(output) > 0
    rows = first_rows
    while rows and written < fetch_cap:
        remaining = fetch_cap - written
        chunk = rows[:remaining]
        start_idx = written + 1
        end_idx = written + len(chunk)
        print(f"正在查询: 第 {batch_idx + 1} 批 ({start_idx}-{end_idx}) [page={current_page}]")
        if batch_idx == 0:
            print(format_result(rows, total))
        _save_result(chunk, output, write_header=(not pre_existing and batch_idx == 0))
        written += len(chunk)
        print(f"已获取: {written}/{fetch_cap} 条")
        if written >= fetch_cap:
            break
        current_page += 1
        batch_idx += 1
        time.sleep(0.35)
        result = client.search(query, page_size, current_page, select, csv_mode)
        if not _is_success(result):
            print(f"第 {current_page} 页查询失败: {result.get('message', 'unknown error')}", file=sys.stderr)
            break
        rows, _ = _extract_rows(result)

    print(f"\n{'=' * 50}")
    print(f"查询完成，共获取 {written} 条结果")
    print(f"结果已保存到: {output}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Matrix asset search client")
    parser.add_argument("--search", required=True, help="Matrix query syntax, mapped to q")
    parser.add_argument("--api-key", help="Matrix API key")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"API endpoint, default {DEFAULT_BASE_URL}")
    parser.add_argument("--select", default="", help="select fields, comma-separated")
    parser.add_argument("--page_size", type=int, default=500, help="limit per page")
    parser.add_argument("--page", type=int, default=1, help="start page")
    parser.add_argument("--size", "-s", type=int, default=0, help="max rows to export, 0 means as many as possible")
    parser.add_argument("--csv-mode", action="store_true", help="append CSV=CSV to request")
    parser.add_argument("-o", "--output", help="export CSV path")
    parser.add_argument("--yes", "-y", action="store_true", help="skip confirmation for large exports")
    args = parser.parse_args()

    try:
        client = MatrixClient(api_key=args.api_key, base_url=args.base_url)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("Config methods:", file=sys.stderr)
        print("  1. --api-key YOUR_API_KEY", file=sys.stderr)
        print("  2. export MATRIX_API_KEY=YOUR_API_KEY", file=sys.stderr)
        print("  3. scripts/config.json -> {\"api_key\": \"YOUR_API_KEY\"}", file=sys.stderr)
        sys.exit(1)

    if args.output:
        output_path = build_output_path(args.search, args.output)
        sys.exit(run_export(client, args.search, output_path, args.page_size, args.page, args.size, args.select, args.csv_mode, args.yes))

    sys.exit(run_preview(client, args.search, args.page_size, args.page, args.select, args.csv_mode))


if __name__ == "__main__":
    main()
