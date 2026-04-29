#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
360 Quake API 查询工具（仅支持 --search 传入完整 Quake 语法）

使用方法:
    python quake_query.py --search 'domain: "example.com" OR cert: "example.com"'
"""

import argparse
import json
import os
import sys
import time
import re
from datetime import datetime
from typing import Optional

try:
    import requests
except ImportError:
    print("请安装 requests 库: pip install requests")
    sys.exit(1)

# 与 Hunter query.py 一致：命中数超过该值时导出前需确认（可用 --yes 跳过）
EXPORT_CONFIRM_THRESHOLD = 2000
BASE_OUTPUT_DIR = os.path.expanduser("~/.openclaw/assets_measure/quake")


def _sanitize_filename(value: str, max_len: int = 40) -> str:
    s = (value or "").strip().lower()
    s = re.sub(r"^https?://", "", s)
    s = s.split("/")[0].split(":")[0]
    s = re.sub(r'[^a-zA-Z0-9._-]+', '_', s).strip('._-')
    return (s or "query")[:max_len]


def _extract_query_keyword(query: str) -> str:
    patterns = [
        r'ip\s*:\s*"([^"]+)"',
        r'domain\s*:\s*"([^"]+)"',
        r'host\s*:\s*"([^"]+)"',
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
    ext = os.path.splitext(os.path.basename(user_output))[1] or ".csv"
    filename = f"quake_{keyword}_{ts}{ext}"
    return os.path.join(BASE_OUTPUT_DIR, filename)


def _confirm_export_if_needed(actual_total: int, fetch_size: int, skip_confirm: bool) -> bool:
    """Returns False if user cancels."""
    if skip_confirm or actual_total <= EXPORT_CONFIRM_THRESHOLD:
        return True
    try:
        ans = input(
            f"Total hits {actual_total} (will export up to {fetch_size} rows), "
            f"exceeds {EXPORT_CONFIRM_THRESHOLD}. Proceed with export? (y/N) "
        ).strip().lower()
    except EOFError:
        return False
    return ans in ("y", "yes")


class QuakeAPI:
    """360 Quake API 封装"""

    BASE_URL = "https://quake.360.net/api/v3"

    def __init__(self, api_key: Optional[str] = None):
        """
        初始化Quake API客户端

        Args:
            api_key: Quake API Key，如果不提供则从环境变量QUAKE_API_KEY或配置文件读取
        """
        self.api_key = api_key or self._load_api_key()
        if not self.api_key:
            raise ValueError("未找到API Key，请通过参数传入、设置环境变量QUAKE_API_KEY或创建配置文件")

        self.headers = {
            "X-QuakeToken": self.api_key,
            "Content-Type": "application/json"
        }

    def _load_api_key(self) -> Optional[str]:
        """从环境变量或配置文件加载API Key"""
        # 优先从环境变量读取
        api_key = os.environ.get("QUAKE_API_KEY")
        if api_key:
            return api_key

        # 从配置文件读取
        config_paths = [
            os.path.expanduser("~/.quake/config.json"),
            os.path.join(os.path.dirname(__file__), "config.json"),
            os.path.expanduser("~/.config/quake/config.json"),
        ]

        for config_path in config_paths:
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r") as f:
                        config = json.load(f)
                        return config.get("api_key")
                except (json.JSONDecodeError, IOError):
                    continue

        return None

    def search(
        self,
        query: str,
        size: int = 100,
        start: int = 0,
        service: Optional[list] = None,
        ignore_cache: bool = False
    ) -> dict:
        """
        执行Quake查询

        Args:
            query: 查询语句
            size: 返回结果数量，默认100，最大10000
            start: 起始位置，用于分页
            service: 服务类型过滤，如 ["http", "https"]
            ignore_cache: 是否忽略缓存

        Returns:
            查询结果字典
        """
        url = f"{self.BASE_URL}/search/quake_service"

        payload = {
            "query": query,
            "size": size,
            "start": start,
            "ignore_cache": ignore_cache
        }

        if service:
            payload["service"] = service

        try:
            response = requests.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"error": str(e), "code": -1}

    def search_dorks(self, dork: str, size: int = 100) -> dict:
        """
        使用dork语法查询

        Args:
            dork: Quake dork查询语句
            size: 返回结果数量

        Returns:
            查询结果
        """
        return self.search(query=dork, size=size)

    def get_user_info(self) -> dict:
        """获取用户信息（验证API Key是否有效）"""
        url = f"{self.BASE_URL}/user/info"
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"error": str(e), "code": -1}


def _scheme_from_service_name(name: str) -> str:
    """根据 service.name 归一化协议（http/ssl、http-ssl→https，http→http，其它原样）。"""
    if not name:
        return "http"
    n = name.lower().strip()
    if n in ("https", "ssl", "tls", "http-ssl", "http/ssl"):
        return "https"
    if n == "http":
        return "http"
    return n


def _normalize_quake_url(url: str) -> str:
    """将 Quake 返回的非常规 scheme 规范为 https://。"""
    if not isinstance(url, str) or not url:
        return url or ""
    u = url.strip()
    low = u.lower()
    if low.startswith("http-ssl://"):
        return "https://" + u[10:]
    if low.startswith("http/ssl://"):
        return "https://" + u[12:]
    return u


def _build_url_fallback(service: dict, item: dict, http: dict) -> str:
    """无 http_load_url 时，用 service.name 作协议与 host/ip/domain/port 拼接 URL。"""
    scheme = _scheme_from_service_name(service.get("name") or "")
    host = (http or {}).get("host") or item.get("domain") or item.get("ip") or ""
    if not host:
        return ""
    port_raw = item.get("port")
    port = str(port_raw) if port_raw is not None and port_raw != "" else ""

    if scheme in ("http", "https"):
        if scheme == "https" and port in ("443", ""):
            return f"https://{host}"
        if scheme == "http" and port in ("80", ""):
            return f"http://{host}"
        if port and port not in ("80", "443"):
            return f"{scheme}://{host}:{port}"
        return f"{scheme}://{host}"

    if port:
        return f"{scheme}://{host}:{port}"
    return f"{scheme}://{host}"


def format_result(
    result: dict,
    output_format: str = "table",
    max_display_rows: Optional[int] = None,
) -> str:
    """
    格式化输出结果

    Args:
        result: API返回结果
        output_format: 输出格式 (table/json/simple)
        max_display_rows: 仅表格/简单格式限制终端展示行数；摘要仍按本批 len(data) 统计

    Returns:
        格式化后的字符串
    """
    if result.get("code") == -1 or result.get("error"):
        return f"查询失败: {result.get('error', '未知错误')}"

    if result.get("code") != 0:
        return f"查询失败: {result.get('message', '未知错误')}"

    data = result.get("data", [])
    total = result.get("meta", {}).get("pagination", {}).get("total", 0)

    if not data:
        return "未查询到结果"

    if output_format == "json":
        return json.dumps(result, indent=2, ensure_ascii=False)

    batch_n = len(data)
    summary = f"查询结果: 共 {total} 条记录，本批返回 {batch_n} 条"
    if max_display_rows is not None and batch_n > max_display_rows:
        summary += f"（终端预览前 {max_display_rows} 条）"
    lines = []
    lines.append(summary)
    lines.append("-" * 120)

    show = data if max_display_rows is None else data[:max_display_rows]

    if output_format == "simple":
        # 简单格式：只输出URL
        for item in show:
            info = extract_item_info(item)
            lines.append(info["url"])
    else:
        # 表格格式
        lines.append(
            f"{'URL':<38} {'标题':<22} {'主机':<22} {'状态':<6} {'省份':<10} {'协议':<8}"
        )
        lines.append("-" * 120)

        for item in show:
            info = extract_item_info(item)
            url = info["url"][:36] + ".." if len(info["url"]) > 38 else info["url"]
            title = info["title"][:20] + ".." if len(info["title"]) > 22 else info["title"]
            host = info["host"][:20] + ".." if len(info["host"]) > 22 else info["host"]
            st = info["status_code"][:6]
            prov = info["province_cn"][:8] + ".." if len(info["province_cn"]) > 10 else info["province_cn"]
            protocol = info["protocol"][:8]
            lines.append(f"{url:<38} {title:<22} {host:<22} {st:<6} {prov:<10} {protocol:<8}")

    return "\n".join(lines)


def extract_item_info(item: dict) -> dict:
    """
    从Quake返回的单条数据中提取信息（优先 service.http 嵌套字段）

    Args:
        item: Quake API返回的单条数据

    Returns:
        提取后的信息字典
    """
    service = item.get("service", {})
    if not isinstance(service, dict):
        service = {}

    http = service.get("http")
    if not isinstance(http, dict):
        http = {}

    icp_obj = http.get("icp")
    if not isinstance(icp_obj, dict):
        icp_obj = {}

    main_lic = icp_obj.get("main_licence")
    if not isinstance(main_lic, dict):
        main_lic = {}

    location = item.get("location")
    if not isinstance(location, dict):
        location = {}

    load_url = http.get("http_load_url")
    if isinstance(load_url, str) and load_url.strip():
        url = _normalize_quake_url(load_url.strip())
    else:
        url = _normalize_quake_url(_build_url_fallback(service, item, http))

    raw_title = http.get("title")
    if raw_title is None or raw_title == "":
        title = ""
    else:
        title = str(raw_title).strip()

    port_raw = item.get("port")
    port = str(port_raw) if port_raw is not None and port_raw != "" else ""

    sc = http.get("status_code")
    status_code = str(sc) if sc is not None and sc != "" else ""

    raw_proto = service.get("name") or service.get("transport") or ""
    protocol = _scheme_from_service_name(raw_proto) if raw_proto else ""

    return {
        "url": url,
        "ip": item.get("ip", "") or "",
        "domain": item.get("domain", "") or "",
        "port": port,
        "host": http.get("host") or "",
        "title": title,
        "protocol": protocol,
        "fingerprint": str(http.get("server") or "") if http.get("server") is not None else "",
        "status_code": status_code,
        "icp": icp_obj.get("licence") or "",
        "main_unit": main_lic.get("unit") or "",
        "update_time": item.get("time", "") or item.get("update_time", "") or item.get("updated_at", "") or "",
        "province_cn": location.get("province_cn") or "",
        "source": "360 Quake",
    }


def save_result(result: dict, output_file: str, query: Optional[str] = None):
    """
    保存结果到文件（一律追加、不覆盖；仅文件不存在或为空时先写查询语句，再写表头）
    """
    data = result.get("data", [])

    import csv

    is_empty = not os.path.exists(output_file) or os.path.getsize(output_file) == 0
    need_header = is_empty
    enc = "utf-8-sig" if need_header else "utf-8"
    with open(output_file, "a", newline="", encoding=enc) as f:
        writer = csv.writer(f)
        # 表头（仅首次写入或新建文件时写入）
        if need_header:
            writer.writerow([f"# query: {query or ''}"])
            writer.writerow([
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
            ])

        for item in data:
            info = extract_item_info(item)
            writer.writerow([
                info["url"],
                info["ip"],
                info["domain"],
                info["port"],
                info["host"],
                info["title"],
                info["protocol"],
                info["fingerprint"],
                info["status_code"],
                info["icp"],
                info["main_unit"],
                info["update_time"],
                info["province_cn"],
                info["source"],
            ])


def fetch_all_results(quake: QuakeAPI, query: str, total_size: int, output_file: str,
                      page_size: int = 2000, service: list = None, ignore_cache: bool = False,
                      display: str = "table", preview_only: bool = False,
                      skip_confirm: bool = False) -> tuple:
    """
    分页获取结果并追加写入CSV

    Args:
        quake: QuakeAPI实例
        query: 查询语句
        total_size: 要获取的总数量，0表示获取全部
        output_file: 输出文件路径
        page_size: 每批拉取条数（与 Hunter --page_size 语义一致），默认2000
        service: 服务类型过滤
        ignore_cache: 是否忽略缓存
        display: 显示格式
        preview_only: 是否仅预览（不保存文件）

    Returns:
        (实际获取的总数量, 总记录数)
    """
    # 先获取第一批，确认总数
    print(f"正在查询总数...")
    result = quake.search(
        query=query,
        size=1,  # 仅获取1条确认总数
        start=0,
        service=service,
        ignore_cache=ignore_cache
    )

    if result.get("code") == -1 or result.get("error"):
        print(f"查询失败: {result.get('error', '未知错误')}")
        return 0, 0

    if result.get("code") != 0:
        print(f"查询失败: {result.get('message', '未知错误')}")
        return 0, 0

    actual_total = result.get("meta", {}).get("pagination", {}).get("total", 0)

    if actual_total == 0:
        print("未查询到结果")
        return 0, 0

    # 短暂延迟避免API频率限制
    time.sleep(0.5)

    # 确定要获取的数量
    if total_size == 0 or total_size > actual_total:
        fetch_size = actual_total
    else:
        fetch_size = total_size

    print(f"总记录数: {actual_total}")
    print(f"计划获取: {fetch_size} 条")
    print(f"每批条数 (--page_size): {page_size} 条/批")
    print("-" * 50)

    # 计算批次数
    batch_count = (fetch_size + page_size - 1) // page_size

    # 如果仅预览，显示前5条
    if preview_only:
        # 短暂延迟避免API频率限制
        time.sleep(0.5)
        preview_result = quake.search(
            query=query,
            size=min(5, fetch_size),
            start=0,
            service=service,
            ignore_cache=ignore_cache
        )
        if preview_result.get("code") == 0:
            preview_data = preview_result.get("data", [])
            if preview_data:
                output = format_result({"code": 0, "data": preview_data, "meta": {"pagination": {"total": actual_total}}}, display)
                if output:
                    print(output)
            else:
                print("预览数据为空")
        else:
            print(f"预览查询失败: {preview_result.get('message', '未知错误')}")
        return 0, actual_total

    if output_file and not _confirm_export_if_needed(actual_total, fetch_size, skip_confirm):
        print("Export cancelled.")
        return 0, actual_total

    total_fetched = 0

    for batch_idx in range(batch_count):
        start = batch_idx * page_size
        current_batch_size = min(page_size, fetch_size - total_fetched)

        if current_batch_size <= 0:
            break

        print(f"正在查询: 第 {batch_idx + 1}/{batch_count} 批 ({start + 1}-{start + current_batch_size})")

        # 批次间延迟避免API频率限制
        if batch_idx > 0:
            time.sleep(0.5)

        result = quake.search(
            query=query,
            size=current_batch_size,
            start=start,
            service=service,
            ignore_cache=ignore_cache
        )

        if result.get("code") == -1 or result.get("error"):
            print(f"查询失败: {result.get('error', '未知错误')}")
            break

        if result.get("code") != 0:
            print(f"查询失败: {result.get('message', '未知错误')}")
            break

        data = result.get("data", [])
        if not data:
            break

        # 第一批显示结果（本批条数与终端表格行数分离，避免「返回 5 条」误导）
        if batch_idx == 0:
            print(
                format_result(
                    {"code": 0, "data": data, "meta": {"pagination": {"total": actual_total}}},
                    display,
                    max_display_rows=5,
                )
            )

        # 保存到文件
        if output_file:
            save_result(result, output_file, query)

        total_fetched += len(data)
        print(f"已获取: {total_fetched}/{fetch_size} 条")

        # 避免请求过快
        if batch_idx < batch_count - 1:
            time.sleep(0.3)

    return total_fetched, actual_total


def main():
    parser = argparse.ArgumentParser(
        description="360 Quake API 查询工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 预览（总数 + 前 5 条）
  python quake_query.py --search 'domain: "example.com" OR cert: "example.com" OR host: "example.com"'

  # 导出 CSV（自动分批）
  python quake_query.py --search 'ip: "1.2.3.4"' --output result.csv

  python quake_query.py --search 'domain: "example.com"' --size 5000 --output result.csv

  python quake_query.py --search 'app: "nginx" AND country: "CN"' --api-key YOUR_API_KEY -o out.csv

输出CSV字段说明:
  url           - service.http.http_load_url，缺省时按 service.name 协议拼接
  ip            - 网站 IP
  domain        - 网站域名
  port          - 端口
  host          - service.http.host
  title         - service.http.title
  协议           - service.name / transport
  指纹           - service.http.server
  网站返回状态   - service.http.status_code
  备案           - service.http.icp.licence
  主体公司       - service.http.icp.main_licence.unit
  更新时间       - time
  省份           - location.province_cn
  来源           - 数据来源(360 Quake)

查询流程:
  1. 不指定 --output：先查总数，再预览前 5 条
  2. 指定 --output：先查总数；命中数超过 2000 时需确认（可用 --yes 跳过）；再按 --page_size 分批写入 CSV
     - --size 0 表示导出全部（在确认后的计划条数内）
        """
    )

    # 查询条件参数
    query_group = parser.add_argument_group("查询条件")
    query_group.add_argument(
        "--search",
        required=False,
        help="完整 Quake 查询语句（与 Hunter --search 用法一致；使用 --info 时不必填）",
    )

    # 查询控制参数
    control_group = parser.add_argument_group("查询控制")
    control_group.add_argument("--size", "-s", type=int, default=0, help="获取结果数量，0表示全部获取")
    control_group.add_argument(
        "--page_size",
        type=int,
        default=2000,
        help="每批拉取条数（与 Hunter search 导出一致），默认2000",
    )
    control_group.add_argument("--service", nargs="+", help="服务类型过滤，如 http https")
    control_group.add_argument("--no-cache", action="store_true", help="忽略缓存，获取最新结果")
    control_group.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="命中数超过阈值时仍直接导出，不交互确认",
    )

    # 输出参数
    output_group = parser.add_argument_group("输出控制")
    output_group.add_argument("--output", "-o", help="输出文件路径(默认csv格式)")
    output_group.add_argument("--display", choices=["table", "json", "simple"], default="table", help="终端显示格式")

    # API参数
    api_group = parser.add_argument_group("API配置")
    api_group.add_argument("--api-key", help="Quake API Key（优先级最高）")
    api_group.add_argument("--info", action="store_true", help="显示用户信息（验证API Key）")

    args = parser.parse_args()

    # 初始化API客户端
    try:
        quake = QuakeAPI(api_key=args.api_key)
    except ValueError as e:
        print(f"错误: {e}")
        print("\n配置API Key的方法:")
        print("  1. 命令行参数: --api-key YOUR_API_KEY")
        print("  2. 环境变量: export QUAKE_API_KEY=YOUR_API_KEY")
        print("  3. 配置文件: ~/.quake/config.json")
        print('     {"api_key": "YOUR_API_KEY"}')
        sys.exit(1)

    # 显示用户信息
    if args.info:
        user_info = quake.get_user_info()
        if user_info.get("code") == 0:
            data = user_info.get("data", {})
            print(f"用户: {data.get('username', 'N/A')}")
            print(f"邮箱: {data.get('email', 'N/A')}")
            print(f"余额: {data.get('balance', 'N/A')}")
            print(f"VIP等级: {data.get('vip', 'N/A')}")
        else:
            print(f"获取用户信息失败: {user_info.get('message', '未知错误')}")
        sys.exit(0)

    if not args.search or not str(args.search).strip():
        print("错误: 请提供非空的 --search，例如 --search 'domain: \"example.com\"'", file=sys.stderr)
        sys.exit(1)

    query = str(args.search).strip()

    print(f"查询语句: {query}")
    print("-" * 50)

    # 分批获取结果模式（所有导出到文件的查询都使用批次模式）
    if args.output:
        output_path = build_output_path(query, args.output)
        total_fetched, actual_total = fetch_all_results(
            quake=quake,
            query=query,
            total_size=args.size,
            output_file=output_path,
            page_size=args.page_size,
            service=args.service,
            ignore_cache=args.no_cache,
            display=args.display,
            skip_confirm=args.yes,
        )
        print(f"\n{'='*50}")
        print(f"查询完成，共获取 {total_fetched} 条结果")
        print(f"结果已保存到: {output_path}")
        sys.exit(0)

    # 仅预览模式（不导出文件，显示前5条和总数）
    total_fetched, actual_total = fetch_all_results(
        quake=quake,
        query=query,
        total_size=5,  # 预览只显示5条
        output_file=None,
        page_size=args.page_size,
        service=args.service,
        ignore_cache=args.no_cache,
        display=args.display,
        preview_only=True,
        skip_confirm=True,
    )

    if actual_total > EXPORT_CONFIRM_THRESHOLD:
        print(f"\n⚠️  Result count is large ({actual_total:,} rows). Use --size to limit or --output to export.")
        print('Example: python quake_query.py --search \'domain: "example.com"\' --size 5000 -o result.csv')
    elif actual_total > 0:
        print(f"\nTip: use --output to export CSV")
        print('Example: python quake_query.py --search \'domain: "example.com"\' -o result.csv')


if __name__ == "__main__":
    main()
