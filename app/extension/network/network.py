"""
# @Time    : 2025/11/1 1:48
# @Author  : Pedro
# @File    : network.py
# @Software: PyCharm
"""
# @Time    : 2025/11/1 00:01
# @Author  : Pedro
# @File    : network_intel.py
# @Software: PyCharm

import re
from functools import lru_cache
from typing import Optional, TypedDict

import geoip2.database
from fastapi import Request

# --- 路径按你的项目来 ---
GEO_COUNTRY_DB = "./Country.mmdb"
GEO_ASN_DB     = "./GeoLite2-ASN.mmdb"

# 常见 IDC/云厂商关键字（可扩展维护）
IDC_PATTERNS = [
    r"amazon|aws|google|gcp|microsoft|azure|digitalocean|linode|vultr|ovh|leaseweb|hetzner|tencent|aliyun|alibaba|huawei|upcloud|ionos|scaleway|cloudflare|fastly|cloudfront",
]
IDC_REGEX = re.compile("|".join(IDC_PATTERNS), re.I)


class NetIntel(TypedDict, total=False):
    ip: str
    country: Optional[str]
    asn: Optional[int]
    org: Optional[str]
    is_idc: bool
    vpn_score: int   # 0~100
    reason: list[str]


@lru_cache(maxsize=1)
def _open_country_reader():
    return geoip2.database.Reader(GEO_COUNTRY_DB)

@lru_cache(maxsize=1)
def _open_asn_reader():
    return geoip2.database.Reader(GEO_ASN_DB)

def get_client_ip(request: Request) -> str:
    # 优先取 Cloudflare 透传的真实 IP
    real = request.headers.get("CF-Connecting-IP")
    if real:
        return real
    fwd = request.headers.get("X-Forwarded-For")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host

def geo_lookup(ip: str) -> NetIntel:
    intel: NetIntel = {"ip": ip, "is_idc": False, "vpn_score": 0, "reason": []}
    try:
        cr = _open_country_reader().country(ip)
        intel["country"] = getattr(cr.country, "iso_code", None)
    except Exception:
        intel["reason"].append("no_country")

    try:
        ar = _open_asn_reader().asn(ip)
        intel["asn"] = ar.autonomous_system_number
        intel["org"] = ar.autonomous_system_organization or ""
        if intel["org"] and IDC_REGEX.search(intel["org"]):
            intel["is_idc"] = True
            intel["vpn_score"] += 60
            intel["reason"].append("asn_idc_pattern")
    except Exception:
        intel["reason"].append("no_asn")

    # Cloudflare 透传国家（优先级略低于本地库，一致性可做对账）
    cf_country = None
    # 若你在 FastAPI 中作为依赖注入，可把 header 传进来；这里留接口位
    # intel["cf_country"] = cf_country

    # 简单附加规则：国家/语言/时区不一致可叠加分（建议前端传 UA / tz）
    # intel["vpn_score"] += 0..40

    return intel

def calc_vpn_score(intel: NetIntel, accept_language: Optional[str] = None, tz: Optional[str] = None) -> NetIntel:
    # 语言与国家不一致时加分（简单示例，可按业务调参/打表）
    if accept_language and intel.get("country"):
        lang = accept_language.split(",")[0].lower()
        c = intel["country"].lower()
        suspicious = [
            ("us", "zh"),
            ("jp", "zh"),
            ("cn", "en"),
        ]
        for cc, ll in suspicious:
            if c == cc and lang.startswith(ll):
                intel["vpn_score"] += 15
                intel["reason"].append("lang_mismatch")
                break
    # 你也可以叠加 UA/设备/行为学特征加权
    intel["vpn_score"] = min(100, intel["vpn_score"])
    return intel
