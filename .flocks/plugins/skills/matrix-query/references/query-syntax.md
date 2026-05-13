# Matrix Query Syntax Reference

以下为 Matrix 常见与扩展语法参考。主 `SKILL.md` 中只保留 10 个最常用字段；其余字段统一查这里。

## 运算规则

| 语法 | 示例 | 说明 |
|:--|:--|:--|
| `&&` | `title="threatbook" && body="微步在线"` | 与条件 |
| `||` | `title="threatbook" || domain="threatbook.cn"` | 或条件 |
| `!=` | `port!="80"` | 排除条件 |
| `==` | `title=="首页"` | 精准匹配 |
| `>=` `<=` `>` `<` | `port>="60000"` | 数值比较 |
| `()` | `(title="a" && body="b") || domain="c"` | 条件分组 |
| `*` | `html_hash="79e89d*"` | 短语前缀匹配 |
| `exists` | `exists=domain,title` | 搜索存在指定字段的资产 |

## 组合示例

| 字段 | 示例 | 说明 |
|:--|:--|:--|
| 组合查询 | `title="情报社区" || (title="threatbook" && title="微步在线") || (body="微步在线" && domain="threatbook")` | 多条件组合查询 |

## 网络与地理

| 字段 | 示例 | 说明 |
|:--|:--|:--|
| `ip` | `ip="1.1.1.1/25"` | 搜索 IPv4 网段 |
| `ip` | `ip="1.1.1.1,1.1.1.2"` | 搜索多个 IPv4 |
| `ipv6` | `ipv6="2a00:7a60:0:10a1::1"` | 搜索 IPv6 资产 |
| `apply` | `apply="microsoft-iis/8.5"` | 搜索端口上的应用信息 |
| `apply_version` | `apply_version="1.2"` | 搜索端口上的应用版本 |
| `country` | `country="中国"` | 搜索国家 |
| `area_code` | `area_code="CN"` | 搜索国家代码 |
| `province` | `province="北京市"` | 搜索省份 |
| `city` | `city="北京市"` | 搜索城市，支持前缀匹配 |
| `district` | `district="海淀区"` | 搜索区县 |
| `isp` | `isp="中国移动"` | 搜索运营商 |
| `asn` | `asn="19551"` | 搜索指定 ASN |
| `asn_name` | `asn_name=TRA` | 搜索指定 ASN 名称 |
| `asn_org` | `asn_org=TRA` | 搜索指定 ASN 组织 |
| `owner` | `owner="阿里云"` | 搜索 IP 地址所属组织 |
| `service` | `service="WEB服务"` | 搜索应用服务 |
| `app_version` | `app_version="1.2"` | 搜索组件版本 |
| `app_category` | `app_category="OA"` | 搜索组件所属大类 |
| `os` | `os="linux"` | 搜索操作系统 |
| `ip_type` | `ip_type="false"` | 搜索 IPv6 资产，`false` 为 IPv6 |
| `hostname` | `hostname="localhost"` | 搜索主机名 |
| `device` | `device="路由器"` | 搜索设备名称 |
| `device_factory` | `device_factory="思科"` | 搜索设备厂商 |
| `device_category` | `device_category="交换机"` | 搜索设备分类 |
| `apps` | `apps="赌博"` | 搜索情报分类站点 |
| `lables` | `lables="涉政"` | 搜索网页源码中的涉政/暴恐等资产 |
| `before` | `before="2022-01-01"` | 搜索指定日期之前的资产 |
| `after` | `after="2022-06-01"` | 搜索指定日期之后的资产 |
| `protocol_type` | `protocol_type="udp"` | 搜索传输层协议类型 |

## DNS 与域名

| 字段 | 示例 | 说明 |
|:--|:--|:--|
| `dns` | `dns="23.227.38.71"` | 搜索域名 DNS 解析到指定 IP 的资产 |
| `dns_type` | `dns_type="A"` | 搜索 DNS 解析类型 |
| `rdns` | `rdns=dns.google` | 搜索反向解析资产 |

## Web 与页面内容

| 字段 | 示例 | 说明 |
|:--|:--|:--|
| `banner` | `banner="sip:nm SIP/2.0"` | 搜索 banner 信息 |
| `banner_md5_hash` | `banner_md5_hash="7535cdf4828da56347b8441ce591b09b"` | 搜索 banner hash |
| `url` | `url="threatbook"` | 搜索 URL 中包含指定内容的资产 |
| `redirect_header` | `redirect_header="elastic"` | 搜索重定向响应头 |
| `header_md5_hash` | `header_md5_hash="13f73a50a794f1f2eb6b95d18e3da6e4"` | 搜索响应头 hash |
| `header_order_md5_hash` | `header_order_md5_hash=99db1c28fb8513ed3cdae44cc24359fd` | 搜索响应头顺序 hash |
| `dom` | `dom=div` | 搜索 DOM 树结构 |
| `server` | `server="Microsoft-IIS/10"` | 搜索服务器类型 |
| `server_md5_hash` | `server_md5_hash=5fb5d0a83deef6b77ec75927de3f1886` | 搜索 server hash |
| `plugins` | `plugins="CobaltStrikeBeacon"` | 搜索 CS 服务器地址 |
| `plugins.values` | `plugins.values="service-5dttvfnl-1253933974.sh.apigw.tencentcs.com"` | 搜索 CS 字段详情 |
| `robots` | `robots="Disallow"` | 搜索 robots 内容 |
| `html_domains` | `html_domains="threatbook.cn"` | 搜索 HTML 中包含的域名 |
| `js_name` | `js_name="bootstrap-datetimepicker.min.js"` | 搜索页面包含的 JS 文件名 |
| `content_type` | `content_type=text/html` | 搜索指定 content-type |
| `content_length` | `content_length=125` | 搜索指定内容长度 |

## 图标、Logo 与页面哈希

| 字段 | 示例 | 说明 |
|:--|:--|:--|
| `favicon` | `favicon="28db76bf560e2e65f3405d611fbafaea"` | 搜索 favicon，精准匹配 |
| `favicon_dhash` | `favicon_dhash="13889365890323984432"` | 搜索 favicon 相似性 |
| `cpe` | `cpe="cpe:/a:igor_sysoev:nginx"` | 搜索应用 CPE |
| `icon_mmh3_hash` | `icon_mmh3_hash="-1765087058"` | 搜索 favicon 的 mmh3 hash |
| `icon_link` | `icon_link=https://www.ordenadoresatm.com/favicon.ico` | 搜索 favicon URL |
| `logo_url` | `logo_url=http://160.16.51.12/common/images/logo.jpg` | 搜索 logo URL |
| `logo_hash` | `logo_hash=4e30b0c0519f494548759cfe13c34e54` | 搜索 logo MD5 hash |
| `logo_dhash` | `logo_dhash=4159524580383865128` | 搜索 logo dhash |
| `html_hash` | `html_hash="79e89d6a6fdd79bb8e52d8a7e430aaf2"` | 搜索 HTML 页面源码相同站点 |
| `body_hash` | `body_hash="bf5e3d7118544648d513f6c688be9eea"` | 搜索 HTML Body 相同站点 |
| `dom_hash` | `dom_hash="fdac776e7b22f07df3e9b0776b6670cb"` | 搜索 DOM 结构相同站点 |
| `html_header_md5_hash` | `html_header_md5_hash="d0d32f31f8b6edd58d81b8796517d957"` | 搜索源码 head hash |
| `html_ssdeep_hash` | `html_ssdeep_hash="39363a6a4231364869385842393443704c4a584937615336703034466430384442383653673a6a6e3648693858423934734c4a75573038444238365367"` | 搜索源码 ssdeep hash |
| `sitemap_md5_hash` | `sitemap_md5_hash="bf929e401ccc65605ef3ecc5bf367bed"` | 搜索 sitemap hash |
| `robots_md5_hash` | `robots_md5_hash="4a6c16a62047601b7eef23a21bb00bce"` | 搜索 robots hash |
| `js_md5_hash` | `js_md5_hash="4fd48cb285dcbe6949bc162f93b573f7"` | 搜索 JS 文件 MD5 |

## 备案与网站主体

| 字段 | 示例 | 说明 |
|:--|:--|:--|
| `web.psr` | `web.psr="京公网安备11000002000008号"` | 搜索公安备案号 |
| `web.icp` | `web.icp="京icp备2022034774号-1"` | 搜索网站页面备案号 |
| `web.etag` | `web.etag="64a11841-23f"` | 搜索网站 etag |
| `web.meta` | `web.meta=nginx` | 搜索网站 meta |
| `icp` | `icp="京ICP证030173号"` | 搜索备案号 |
| `icp_web_name` | `icp_web_name="微步在线"` | 搜索备案网站名称 |
| `icp_type` | `icp_type="企业"` | 搜索备案主体类型 |
| `icp_company` | `icp_company="微步在线科技有限公司"` | 搜索备案主体公司 |

## 漏洞编号

| 字段 | 示例 | 说明 |
|:--|:--|:--|
| `cnnvd_id` | `cnnvd_id="CNNVD-200709-036"` | 搜索 CNNVD 编号，支持前缀匹配 |
| `cve_id` | `cve_id="CVE-2007-4723"` | 搜索 CVE 编号，支持前缀匹配 |

## 证书

| 字段 | 示例 | 说明 |
|:--|:--|:--|
| `cert.subject` | `cert.subject="Oracle Corporation"` | 搜索证书持有者 |
| `cert.subject.org` | `cert.subject.org="Oracle Corporation"` | 搜索证书持有组织 |
| `cert.subject.org_unit` | `cert.subject.org_unit=privateIP` | 搜索证书持有者 org_unit |
| `cert.subject.country` | `cert.subject.country="tt"` | 搜索证书持有者国家 |
| `cert.subject.locality` | `cert.subject.locality="tt"` | 搜索证书持有者地区 |
| `cert.subject.province` | `cert.subject.province="tt"` | 搜索证书持有者省份 |
| `cert.subject.street` | `cert.subject.street=beijing` | 搜索证书持有者地址 |
| `cert.subject.postal_code` | `cert.subject.postal_code=000000` | 搜索证书持有者邮编 |
| `cert.subject.serial_number` | `cert.subject.serial_number=91350000158142711F` | 搜索证书持有者 serial_number |
| `cert.subject.jurisdiction_country` | `cert.subject.jurisdiction_country=CN` | 搜索证书持有者 jurisdiction_country |
| `cert.subject.jurisdiction_province` | `cert.subject.jurisdiction_province=Fujian` | 搜索证书持有者 jurisdiction_province |
| `cert.subject.jurisdiction_locality` | `cert.subject.jurisdiction_locality=Fuzhou` | 搜索证书持有者 jurisdiction_locality |
| `cert.subject.business_category` | `cert.subject.business_category="private organization"` | 搜索证书持有者 business_category |
| `cert.subject.domain_component` | `cert.subject.domain_component=vsmp2` | 搜索证书持有者 domain_component |
| `cert.subject.org_id` | `cert.subject.org_id=VATES-S4611001A` | 搜索证书持有者 org_id |
| `cert.subject.email_address` | `cert.subject.email_address="ssl@vps.bleachanime.org"` | 搜索证书持有者邮箱 |
| `cert.subject.surname` | `cert.subject.surname=1e8ab825` | 搜索证书持有者 surname |
| `cert.subject.given_name` | `cert.subject.given_name=240297e7` | 搜索证书持有者 given_name |
| `cert.issuer` | `cert.issuer="DigiCert"` | 搜索证书颁发者 |
| `cert.issuer.org` | `cert.issuer.org="DigiCert"` | 搜索证书颁发组织 |
| `cert.issuer.org_unit` | `cert.issuer.org_unit=privateIP` | 搜索证书颁发者 org_unit |
| `cert.issuer.street` | `cert.issuer.street=beijing` | 搜索证书颁发者地址 |
| `cert.issuer.postal_code` | `cert.issuer.postal_code=000000` | 搜索证书颁发者邮编 |
| `cert.issuer.country` | `cert.issuer.country="tt"` | 搜索证书颁发者国家 |
| `cert.issuer.locality` | `cert.issuer.locality="tt"` | 搜索证书颁发者地区 |
| `cert.issuer.province` | `cert.issuer.province="tt"` | 搜索证书颁发者省份 |
| `cert.issuer.serial_number` | `cert.issuer.serial_number=91350000158142711F` | 搜索证书颁发者 serial_number |
| `cert.issuer.jurisdiction_country` | `cert.issuer.jurisdiction_country=CN` | 搜索证书颁发者 jurisdiction_country |
| `cert.issuer.jurisdiction_province` | `cert.issuer.jurisdiction_province=Fujian` | 搜索证书颁发者 jurisdiction_province |
| `cert.issuer.jurisdiction_locality` | `cert.issuer.jurisdiction_locality=Fuzhou` | 搜索证书颁发者 jurisdiction_locality |
| `cert.issuer.business_category` | `cert.issuer.business_category="private organization"` | 搜索证书颁发者 business_category |
| `cert.issuer.domain_component` | `cert.issuer.domain_component=vsmp2` | 搜索证书颁发者 domain_component |
| `cert.issuer.org_id` | `cert.issuer.org_id=VATES-S4611001A` | 搜索证书颁发者 org_id |
| `cert.issuer.email_address` | `cert.issuer.email_address="ssl@vps.bleachanime.org"` | 搜索证书颁发者邮箱 |
| `cert.issuer.surname` | `cert.issuer.surname=1e8ab825` | 搜索证书颁发者 surname |
| `cert.issuer.given_name` | `cert.issuer.given_name=240297e7` | 搜索证书颁发者 given_name |
| `cert.sha256` | `cert.sha256="34:9f:ed:35:fe:32:c1:40:56:af:d9:3d:74:f2:3a:36:9c:83:39:eb:f1:45:94:8e:f3:ca:f7:10:97:62:c8:f7"` | 搜索证书 SHA256 |
| `cert.md5` | `cert.md5="ab:b3:72:53:85:bf:16:ce:56:8e:7e:e1:ca:05:fb:93"` | 搜索证书 MD5 |
| `cert.sha1` | `cert.sha1="3a:b1:76:bf:65:f2:9d:ba:78:e4:22:90:73:53:74:b8:51:e6:b4:a4"` | 搜索证书 SHA1，也支持去冒号检索 |
| `cert.dns` | `cert.dns="threatbook.cn"` | 搜索证书包含的域名 |
| `cert.value` | `cert.value="1"` | 搜索颁发者和使用者相同的证书 |
| `cert.valid` | `cert.valid=true` | 搜索可信证书 |
| `cert.is_expired` | `cert.is_expired=true` | 搜索已过期证书 |
| `cert.validity.not_after` | `cert.validity.not_after="2020-02-23"` | 搜索证书截止时间之前 |
| `cert.validity.not_before` | `cert.validity.not_before="2023-02-22"` | 搜索证书开始时间之后 |
| `cert.extended_key_usage` | `cert.extended_key_usage=TLS Web server authentication` | 搜索证书 extended_key_usage |
| `cert.serial_number` | `cert.serial_number="04:c7:78:ae:45:28:d8:48:8f:53:a6:db:1e:2a:c9:e3:f6:13"` | 搜索证书序列号 |

## Whois 与指纹

| 字段 | 示例 | 说明 |
|:--|:--|:--|
| `whois.registrant_company` | `whois.registrant_company="REDACTED FOR PRIVACY"` | 搜索 Whois 注册者公司 |
| `whois.registrant_name` | `whois.registrant_name="REDACTED FOR PRIVACY"` | 搜索 Whois 注册者名字 |
| `whois.registrant_email` | `whois.registrant_email="@privacyguardian.org"` | 搜索 Whois 注册者邮箱 |
| `whois.registrar_name` | `whois.registrar_name="NameSilo, LLC"` | 搜索 Whois 注册商 |
| `jarm` | `jarm="2ad2ad16d2ad2ad0002ad2ad2ad2ad3efac3c09ad758e28a073f01a172085c"` | 搜索 JARM 指纹 |
| `ja3s` | `ja3s="f4febc55ea12b31ae17cfb7e614afda8"` | 搜索 JA3S 指纹 |
| `ja4x` | `ja4x=2bab15409345_af684594efb4_000000000000` | 搜索 JA4X 指纹 |
| `ja4s` | `ja4s=t120200_c02f_344b4dce5a52` | 搜索 JA4S 指纹 |
| `ssh_finger_md5` | `ssh_finger_md5=fc:43:fd:a5:0c:da:b6:98:c0:07:26:60:63:32:1f:a8` | 搜索 SSH 指纹 MD5 |
| `ssh_finger_sha256` | `ssh_finger_sha256=TtPO3N0ZvIf2zbrbRqnP3+cMH8BWMXLay4zXFI5ngXM` | 搜索 SSH 指纹 SHA256 |
