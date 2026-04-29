#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
零零信安 0.zone 数据 API 查询（query_type：site / domain / email / apk）

POST https://0.zone/api/data/
请求体 JSON：query、query_type、page、pagesize、zone_key_id

完整语法与字段见官方： https://0.zone/grammarList
API 申请：site   https://0.zone/applyParticulars?type=site
         domain https://0.zone/applyParticulars?type=domain
         email  https://0.zone/applyParticulars?type=email
         apk    https://0.zone/applyParticulars?type=apk
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from typing import Any, Optional
from urllib.parse import urlparse

try:
    import requests
except ImportError:
    print("请安装 requests 库: pip install requests")
    sys.exit(1)

# 与 Quake/Hunter 导出确认阈值一致
EXPORT_CONFIRM_THRESHOLD = 2000

# 官方约束：单页最大 40；请求速率建议 <=2 次/秒（README 社区脚本说明）
ZONE_MAX_PAGE_SIZE = 40
ZONE_API_MIN_INTERVAL = 0.55

QUAKE_CSV_COLUMNS = [
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


def _confirm_export_if_needed(actual_total: int, fetch_size: int, skip_confirm: bool) -> bool:
    if skip_confirm or actual_total <= EXPORT_CONFIRM_THRESHOLD:
        return True
    try:
        ans = input(
            f"命中数 {actual_total}（将导出至多 {fetch_size} 条），超过 {EXPORT_CONFIRM_THRESHOLD}，是否继续？(y/N) "
        ).strip().lower()
    except EOFError:
        return False
    return ans in ("y", "yes")


def _domain_host_from_url(url: str) -> tuple[str, str]:
    if not url or not isinstance(url, str):
        return "", ""
    try:
        p = urlparse(url.strip())
        host = p.hostname or ""
        return host, host
    except Exception:
        return "", ""


def _email_msg_tags(item: dict) -> str:
    """邮箱接口 msg.tags，可能为平铺键或 msg.tags / msg['tags']。"""
    v = item.get("msg.tags")
    if v is not None and str(v).strip():
        return str(v).strip()
    m = item.get("msg")
    if isinstance(m, dict):
        t = m.get("tags")
        if t is not None:
            return str(t).strip()
    return ""


def _row_to_quake_line(item: dict, query_type: str = "site") -> list:
    """将 0.zone 单条记录映射为与 Quake 导出一致的列顺序。"""
    if query_type == "email":
        # 泄露邮箱：email、email_domain、company、email_type、leakage_num、source、msg.tags、timestamp
        email_addr = str(item.get("email") or "").strip()
        email_dom = str(item.get("email_domain") or "").strip()
        company = str(item.get("company") or "").strip()
        etype = str(item.get("email_type") or "").strip()
        leak = item.get("leakage_num")
        leak_s = "" if leak is None else str(leak).strip()
        src = str(item.get("source") or "").strip()
        tags = _email_msg_tags(item)
        fp = " | ".join(x for x in (tags, src) if x)
        host = ""
        if "@" in email_addr:
            host = email_addr.split("@", 1)[1].strip()
        elif email_dom:
            host = email_dom
        url = f"mailto:{email_addr}" if email_addr else ""
        ts = item.get("timestamp")
        update_time = "" if ts is None else str(ts).strip()
        return [
            url,
            "",
            email_dom,
            "",
            host,
            email_addr or email_dom,
            etype,
            fp,
            leak_s,
            "",
            company,
            update_time,
            "",
            "零零信安 0.zone",
        ]

    if query_type == "domain":
        # domain 接口字段：icp、domain、url、msg.ip、company（备案主体）、timestamp
        url = str(item.get("url") or "").strip()
        dom = str(item.get("domain") or "").strip()
        host = dom
        if not host and url:
            h, _ = _domain_host_from_url(url)
            host = h
        msg = item.get("msg")
        ip = ""
        if isinstance(msg, dict):
            ip = str(msg.get("ip") or "").strip()
        icp = str(item.get("icp") or "").strip()
        company = str(item.get("company") or "").strip()
        ts = item.get("timestamp")
        update_time = "" if ts is None else str(ts).strip()
        return [
            url,
            ip,
            dom,
            "",
            host,
            "",
            "",
            "",
            "",
            icp,
            company,
            update_time,
            "",
            "零零信安 0.zone",
        ]

    url = str(item.get("url") or "").strip()
    dom, host = _domain_host_from_url(url)
    ip = str(item.get("ip") or "").strip()
    port = str(item.get("port") or "").strip()
    title = str(item.get("title") or "").strip()
    proto = str(item.get("service") or "").strip()
    fp = str(item.get("component") or item.get("cms") or item.get("banner_os") or "").strip()
    status = str(item.get("status_code") or "").strip()
    company = str(item.get("group") or "").strip()
    province = str(item.get("city") or "").strip()
    icp = ""
    ex = item.get("extra_info")
    if isinstance(ex, str) and "备案" in ex:
        icp = ex.strip()
    ts = item.get("timestamp")
    update_time = "" if ts is None else str(ts).strip()
    return [
        url,
        ip,
        dom,
        port,
        host,
        title,
        proto,
        fp,
        status,
        icp,
        company,
        update_time,
        province,
        "零零信安 0.zone",
    ]


class ZoneAPI:
    BASE_URL = "https://0.zone/api/data/"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or self._load_api_key()
        if not self.api_key:
            raise ValueError(
                "未找到 API Key，请通过 --api-key、环境变量 ZONE_API_KEY 或 tools/0-zone/config.json（api_key）配置"
            )
        self.headers = {"Content-Type": "application/json"}

    def _load_api_key(self) -> Optional[str]:
        k = os.environ.get("ZONE_API_KEY") or os.environ.get("ZERO_ZONE_API_KEY")
        if k:
            return k.strip()
        paths = [
            os.path.join(os.path.dirname(__file__), "config.json"),
            os.path.join(os.getcwd(), "config.json"),
        ]
        for p in paths:
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                    return (cfg.get("api_key") or cfg.get("zone_key_id") or "").strip() or None
                except (json.JSONDecodeError, OSError):
                    continue
        return None

    def search(
        self,
        query: str,
        query_type: str = "site",
        page: int = 1,
        pagesize: int = 40,
    ) -> dict[str, Any]:
        ps = max(1, min(int(pagesize), ZONE_MAX_PAGE_SIZE))
        p = max(1, int(page))
        payload = {
            "query": query,
            "query_type": query_type,
            "page": p,
            "pagesize": ps,
            "zone_key_id": self.api_key,
        }
        try:
            r = requests.post(
                self.BASE_URL,
                headers=self.headers,
                data=json.dumps(payload),
                timeout=120,
            )
            r.raise_for_status()
            return r.json()
        except requests.exceptions.RequestException as e:
            return {"code": -1, "message": str(e), "data": []}

    @staticmethod
    def parse_total(resp: dict[str, Any]) -> int:
        """从响应中解析总条数；若无字段则返回 -1 表示未知。"""
        if not isinstance(resp, dict):
            return -1
        for k in ("total", "count", "total_count", "recordsTotal"):
            v = resp.get(k)
            if isinstance(v, int) and v >= 0:
                return v
            if isinstance(v, str) and v.isdigit():
                return int(v)
        data = resp.get("data")
        if isinstance(data, dict):
            for k in ("total", "count"):
                v = data.get(k)
                if isinstance(v, int) and v >= 0:
                    return v
        return -1

    @staticmethod
    def parse_rows(resp: dict[str, Any]) -> list[dict[str, Any]]:
        if not isinstance(resp, dict):
            return []
        if resp.get("code") != 0:
            return []
        data = resp.get("data")
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict) and "list" in data:
            lst = data.get("list")
            return [x for x in lst if isinstance(x, dict)] if isinstance(lst, list) else []
        return []


def format_preview(
    rows: list[dict],
    total_hint: int,
    query_type: str = "site",
    max_rows: int = 5,
) -> str:
    if not rows:
        return "未查询到结果"
    n = len(rows)
    th = f"共约 {total_hint} 条" if total_hint >= 0 else "总数由接口字段决定（本批未返回 total）"
    lines = [f"查询结果: {th}，本批展示 {min(n, max_rows)} 条", "-" * 120]
    if query_type == "domain":
        lines.append(f"{'URL':<36} {'domain':<28} {'IP':<16} {'备案':<14} {'主体':<12}")
        lines.append("-" * 120)
        for item in rows[:max_rows]:
            q = _row_to_quake_line(item, "domain")
            url = q[0][:34] + ".." if len(q[0]) > 36 else q[0]
            dom = q[2][:26] + ".." if len(q[2]) > 28 else q[2]
            ip = q[1][:14] + ".." if len(q[1]) > 16 else q[1]
            icp = q[9][:12] + ".." if len(q[9]) > 14 else q[9]
            comp = q[10][:10] + ".." if len(q[10]) > 12 else q[10]
            lines.append(f"{url:<36} {dom:<28} {ip:<16} {icp:<14} {comp:<12}")
        return "\n".join(lines)

    if query_type == "email":
        lines.append(
            f"{'email':<36} {'email_domain':<22} {'company':<18} {'type':<12} {'leak':<6} {'source':<12}"
        )
        lines.append("-" * 120)
        for item in rows[:max_rows]:
            em = str(item.get("email") or "")[:34] + ".." if len(str(item.get("email") or "")) > 36 else str(
                item.get("email") or ""
            )
            ed = str(item.get("email_domain") or "")[:20] + ".." if len(str(item.get("email_domain") or "")) > 22 else str(
                item.get("email_domain") or ""
            )
            co = str(item.get("company") or "")[:16] + ".." if len(str(item.get("company") or "")) > 18 else str(
                item.get("company") or ""
            )
            et = str(item.get("email_type") or "")[:10] + ".." if len(str(item.get("email_type") or "")) > 12 else str(
                item.get("email_type") or ""
            )
            lk = str(item.get("leakage_num") or "")[:6]
            sr = str(item.get("source") or "")[:10] + ".." if len(str(item.get("source") or "")) > 12 else str(
                item.get("source") or ""
            )
            lines.append(f"{em:<36} {ed:<22} {co:<18} {et:<12} {lk:<6} {sr:<12}")
        return "\n".join(lines)

    lines.append(f"{'URL':<38} {'标题':<22} {'主机':<22} {'状态':<6} {'省份':<10} {'协议':<8}")
    lines.append("-" * 120)
    for item in rows[:max_rows]:
        q = _row_to_quake_line(item, query_type)
        url = q[0][:36] + ".." if len(q[0]) > 38 else q[0]
        title = q[5][:20] + ".." if len(q[5]) > 22 else q[5]
        host = q[4][:20] + ".." if len(q[4]) > 22 else q[4]
        st = (q[8] or "")[:6]
        prov = q[12][:8] + ".." if len(q[12]) > 10 else q[12]
        protocol = (q[6] or "")[:8]
        lines.append(f"{url:<38} {title:<22} {host:<22} {st:<6} {prov:<10} {protocol:<8}")
    return "\n".join(lines)


def build_domain_company_search(company: str) -> str:
    """domain 类型：按「所属公司」构造 company==...（支持完整企业名中的引号转义）。"""
    c = (company or "").strip()
    if not c:
        raise ValueError("company 为空")
    esc = c.replace("\\", "\\\\").replace('"', '\\"')
    return f'company=="{esc}"'


def unique_root_domains_from_rows(rows: list[dict]) -> list[str]:
    """从 domain 接口返回行中提取去重后的备案主域名：优先 root_domain，否则退回 domain。"""
    seen: set[str] = set()
    out: list[str] = []
    for r in rows:
        rd = str(r.get("root_domain") or "").strip()
        if not rd:
            rd = str(r.get("domain") or "").strip()
        if not rd:
            continue
        k = rd.lower()
        if k not in seen:
            seen.add(k)
            out.append(rd)
    return sorted(out, key=str.lower)


def collect_all_rows_paged(
    api: ZoneAPI,
    query: str,
    query_type: str,
    pagesize: int,
    max_rows: int,
) -> list[dict]:
    """分页拉取原始 dict 列表，至多 max_rows 条（0 表示 10000 上限）。"""
    ps = max(1, min(pagesize, ZONE_MAX_PAGE_SIZE))
    cap = max_rows if max_rows > 0 else 10_000
    out: list[dict] = []
    page = 1
    time.sleep(ZONE_API_MIN_INTERVAL)
    while len(out) < cap:
        resp = api.search(query, query_type=query_type, page=page, pagesize=ps)
        if resp.get("code") != 0:
            break
        chunk = ZoneAPI.parse_rows(resp)
        if not chunk:
            break
        for row in chunk:
            if len(out) >= cap:
                return out
            out.append(row)
        if len(chunk) < ps:
            break
        page += 1
        time.sleep(ZONE_API_MIN_INTERVAL)
    return out


def save_csv_append(path: str, rows: list[dict], query_type: str = "site") -> None:
    is_empty = not os.path.exists(path) or os.path.getsize(path) == 0
    enc = "utf-8-sig" if is_empty else "utf-8"
    with open(path, "a", newline="", encoding=enc) as f:
        w = csv.writer(f)
        if is_empty:
            w.writerow(QUAKE_CSV_COLUMNS)
        for item in rows:
            w.writerow(_row_to_quake_line(item, query_type))


def fetch_all(
    api: ZoneAPI,
    query: str,
    query_type: str,
    size_limit: int,
    pagesize: int,
    output: str,
    skip_confirm: bool,
) -> tuple[int, int]:
    """
    分页拉取并写入 CSV。size_limit：0 表示在单查询上限内尽量拉全（见文档）。
    返回 (写入条数, 用于确认的参考总命中)。
    """
    ps = max(1, min(pagesize, ZONE_MAX_PAGE_SIZE))
    time.sleep(ZONE_API_MIN_INTERVAL)
    first = api.search(query, query_type=query_type, page=1, pagesize=ps)
    if first.get("code") == -1:
        print(f"请求失败: {first.get('message', '未知错误')}")
        return 0, 0
    if first.get("code") != 0:
        print(f"查询失败: {first.get('message', '未知错误')}")
        return 0, 0

    total = api.parse_total(first)
    rows_first = api.parse_rows(first)
    if not rows_first:
        print("未查询到结果")
        return 0, max(total, 0)

    total_for_msg = total if total >= 0 else len(rows_first)
    if size_limit > 0:
        fetch_target = min(size_limit, total_for_msg) if total >= 0 else size_limit
    else:
        fetch_target = total_for_msg if total >= 0 else 10_000

    if not _confirm_export_if_needed(total_for_msg, fetch_target, skip_confirm):
        print("已取消导出。")
        return 0, total_for_msg

    got = 0
    page = 1
    print(f"参考命中数: {total_for_msg}，计划导出: {fetch_target} 条")
    print("-" * 50)

    chunk: list[dict] = rows_first
    while got < fetch_target:
        if not chunk:
            break
        need = fetch_target - got
        take = chunk if need >= len(chunk) else chunk[:need]
        save_csv_append(output, take, query_type)
        got += len(take)
        if page == 1:
            print(format_preview(chunk, total if total >= 0 else -1, query_type))
        print(f"已获取: {got}/{fetch_target} 条")
        if got >= fetch_target:
            break
        if len(chunk) < ps:
            break
        page += 1
        time.sleep(ZONE_API_MIN_INTERVAL)
        resp = api.search(query, query_type=query_type, page=page, pagesize=ps)
        if resp.get("code") != 0:
            print(f"分页失败: {resp.get('message', '')}")
            break
        chunk = api.parse_rows(resp)

    return got, total_for_msg


def preview_only(
    api: ZoneAPI,
    query: str,
    query_type: str,
    pagesize: int,
    display: str,
) -> None:
    ps = max(1, min(pagesize, ZONE_MAX_PAGE_SIZE))
    time.sleep(ZONE_API_MIN_INTERVAL)
    resp = api.search(query, query_type=query_type, page=1, pagesize=min(ps, 40))
    if resp.get("code") == -1:
        print(f"请求失败: {resp.get('message')}")
        return
    if resp.get("code") != 0:
        print(f"查询失败: {resp.get('message', '')}")
        return
    total = ZoneAPI.parse_total(resp)
    rows = ZoneAPI.parse_rows(resp)
    if display == "json":
        print(json.dumps(resp, indent=2, ensure_ascii=False))
        return
    if not rows:
        print("未查询到结果")
        return
    hint = total if total >= 0 else -1
    print(format_preview(rows, hint, query_type))
    if hint < 0:
        print(f"本批返回 {len(rows)} 条（接口未提供 total 字段时无法展示全局命中数）")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="零零信安 0.zone 数据 API（site / domain / email / apk）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
语法与字段: https://0.zone/grammarList
API 申请 site:   https://0.zone/applyParticulars?type=site
API 申请 domain: https://0.zone/applyParticulars?type=domain
API 申请 email:  https://0.zone/applyParticulars?type=email
API 申请 apk:    https://0.zone/applyParticulars?type=apk

示例:
  python3 zone_query.py --search '(title==\"example\")||(ip==\"1.2.3.4\")'
  python3 zone_query.py --query-type domain --search 'root_domain==example.com' -o domains.csv
  python3 zone_query.py --query-type email --search 'email_domain==126.com' -o emails.csv
  python3 zone_query.py --query-type apk --search 'name==万能' -o apps.csv
  python3 zone_query.py --search '(company=\"某某公司\")' -o result.csv
  python3 zone_query.py --search '...' --query-type site --page-size 40 -y -o out.csv

  # 按完整企业名查域名 API，并列出备案主域名（去重）
  python3 zone_query.py --query-type domain --company '某某有限公司' --list-root-domains
  python3 zone_query.py --query-type domain --company '某某有限公司' --list-root-domains -o roots.txt
        """,
    )
    parser.add_argument(
        "--search",
        default=None,
        help="0.zone 完整查询语句；与 --company 二选一（domain 时可用 --company）",
    )
    parser.add_argument(
        "--company",
        default=None,
        metavar="NAME",
        help="仅 --query-type domain：完整或规范企业名，自动生成 company==\"...\" 查询",
    )
    parser.add_argument(
        "--list-root-domains",
        action="store_true",
        help="仅 --query-type domain：分页拉取后从返回中提取去重的 root_domain（无则退回 domain），每行一个写出",
    )
    parser.add_argument(
        "--query-type",
        choices=("site", "domain", "email", "apk"),
        default="site",
        help="与平台开通的能力一致：site=信息系统，domain=域名，email=泄露邮箱，apk=移动端应用",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=40,
        help=f"每页条数，最大 {ZONE_MAX_PAGE_SIZE}",
    )
    parser.add_argument("--size", "-s", type=int, default=0, help="最多拉取条数，0 表示按接口返回尽可能拉取")
    parser.add_argument("--output", "-o", help="导出与 Quake 同构 CSV 路径")
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help=f"命中超过 {EXPORT_CONFIRM_THRESHOLD} 时跳过确认",
    )
    parser.add_argument("--api-key", help="覆盖环境变量与 config.json")
    parser.add_argument("--display", choices=["table", "json"], default="table", help="无 -o 时终端输出")

    args = parser.parse_args()
    try:
        api = ZoneAPI(api_key=args.api_key)
    except ValueError as e:
        print(f"错误: {e}")
        sys.exit(1)

    if args.company:
        if args.query_type != "domain":
            print("错误: --company 仅可与 --query-type domain 同时使用", file=sys.stderr)
            sys.exit(1)
        if args.search and str(args.search).strip():
            print("错误: 不要同时使用 --company 与 --search", file=sys.stderr)
            sys.exit(1)
        try:
            q = build_domain_company_search(args.company)
        except ValueError as e:
            print(f"错误: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.search is not None and str(args.search).strip():
        q = str(args.search).strip()
    else:
        print("错误: 请提供 --search，或对 domain 使用 --company", file=sys.stderr)
        sys.exit(1)

    print(f"查询语句: {q}")
    print("-" * 50)

    if args.list_root_domains:
        if args.query_type != "domain":
            print("错误: --list-root-domains 仅支持 --query-type domain", file=sys.stderr)
            sys.exit(1)
        max_r = int(args.size or 0)
        print("正在分页拉取并汇总 root_domain …")
        rows = collect_all_rows_paged(api, q, "domain", args.page_size, max_r)
        roots = unique_root_domains_from_rows(rows)
        print(f"去重备案主域名共 {len(roots)} 个（基于接口 root_domain/domain 字段）")
        for line in roots:
            print(line)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as nf:
                nf.write("\n".join(roots) + ("\n" if roots else ""))
            print(f"已写入: {args.output}")
        return

    if args.output:
        got, _ = fetch_all(
            api,
            q,
            args.query_type,
            size_limit=int(args.size or 0),
            pagesize=args.page_size,
            output=args.output,
            skip_confirm=args.yes,
        )
        print(f"\n{'='*50}")
        print(f"完成，共写入 {got} 条 -> {args.output}")
        return

    preview_only(api, q, args.query_type, args.page_size, args.display)


if __name__ == "__main__":
    main()
