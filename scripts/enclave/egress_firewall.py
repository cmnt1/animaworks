#!/usr/bin/env python3
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""Restrict outbound traffic of the enclave OS user with nftables.

The enclave user may only reach:

* loopback: DNS (53) and the listed ports (its own server, the SSM tunnel port);
* the HOST:PORT pairs given with ``--allow-endpoints`` (e.g. in-house LLM
  servers), TCP only;
* AWS addresses of one region (the published ``AMAZON`` ranges), TCP 443
  only.  Service endpoints share these ranges with EC2, so this cannot tell
  an AWS API from a host someone runs on EC2 in that region; it closes the
  LAN, the host's other local services and the rest of the internet.

Only packets owned by that uid enter the restricting chain; packets without a
socket (FIN/ACK of closed sockets of other users) pass untouched.  Everything
else from that uid is rejected, including the host's other local
services (e.g. the main AnimaWorks API) and the LAN.  Run as root::

    python3 egress_firewall.py --user aw-enclave --region ap-northeast-1 \
        --loopback-ports 18610,33061 --apply

Without ``--apply`` the ruleset is printed.  ``--remove`` deletes the table.
Re-run periodically (e.g. weekly) to refresh the AWS ranges.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import pwd
import subprocess
import sys
import urllib.request

AWS_RANGES_URL = "https://ip-ranges.amazonaws.com/ip-ranges.json"
TABLE = "aw_enclave_egress"


def _aws_ranges(region: str) -> tuple[list[str], list[str]]:
    with urllib.request.urlopen(AWS_RANGES_URL, timeout=30) as resp:  # noqa: S310 - fixed https URL
        data = json.load(resp)

    def _collect(items: list[dict], key: str) -> list[str]:
        nets = [ipaddress.ip_network(i[key]) for i in items if i["region"] == region and i["service"] == "AMAZON"]
        return [str(n) for n in ipaddress.collapse_addresses(nets)] if nets else []

    v4 = _collect(data["prefixes"], "ip_prefix")
    v6 = _collect(data["ipv6_prefixes"], "ipv6_prefix")
    return v4, v6


def build_ruleset(
    uid: int,
    region: str,
    loopback_ports: list[int],
    endpoints: list[tuple[str, int]] | None = None,
) -> str:
    v4, v6 = _aws_ranges(region)
    if not v4:
        raise SystemExit(f"no AWS ranges found for region {region}")
    ports = ", ".join(str(p) for p in sorted({53, *loopback_ports}))
    lines = [
        f"table inet {TABLE} {{",
        "  set aws_v4 { type ipv4_addr; flags interval; elements = { " + ", ".join(v4) + " } }",
    ]
    if v6:
        lines.append("  set aws_v6 { type ipv6_addr; flags interval; elements = { " + ", ".join(v6) + " } }")
    lines += [
        "  chain output {",
        "    type filter hook output priority filter; policy accept;",
        # Packets without an owning socket (FIN/ACK from closed sockets,
        # kernel-generated ICMPv6) never match skuid, so only the enclave
        # user's own traffic enters the restricting chain.
        f"    meta skuid {uid} jump enclave",
        "  }",
        "  chain enclave {",
        "    ct state established,related accept",
        f"    oif lo meta l4proto {{ tcp, udp }} th dport {{ {ports} }} accept",
        f"    oif lo meta l4proto {{ tcp, udp }} th sport {{ {ports} }} accept",
        "    ip daddr @aws_v4 tcp dport 443 accept",
    ]
    for host, port in endpoints or []:
        family = "ip6" if ipaddress.ip_address(host).version == 6 else "ip"
        lines.append(f"    {family} daddr {host} tcp dport {port} accept")
    if v6:
        lines.append("    ip6 daddr @aws_v6 tcp dport 443 accept")
    lines += [
        '    limit rate 6/minute burst 5 packets log prefix "aw-enclave-egress-drop "',
        "    reject",
        "  }",
        "}",
    ]
    return "\n".join(lines) + "\n"


def _nft(args: list[str], stdin: str | None = None) -> None:
    subprocess.run(["nft", *args], input=stdin, text=True, check=True)


def _parse_endpoints(raw: str) -> list[tuple[str, int]]:
    endpoints: list[tuple[str, int]] = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        host, _, port = item.rpartition(":")
        host = host.strip("[]")
        ipaddress.ip_address(host)  # IP literals only; a name would be resolved once and go stale
        endpoints.append((host, int(port)))
    return endpoints


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--user", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--loopback-ports", default="", help="comma-separated loopback TCP ports to allow")
    parser.add_argument(
        "--allow-endpoints",
        default="",
        help="comma-separated HOST:PORT (IP literals) the enclave may also reach, e.g. in-house LLM servers",
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--remove", action="store_true")
    args = parser.parse_args()

    if args.remove:
        subprocess.run(["nft", "delete", "table", "inet", TABLE], check=False)
        return 0

    uid = pwd.getpwnam(args.user).pw_uid
    ports = [int(p) for p in args.loopback_ports.split(",") if p.strip()]
    ruleset = build_ruleset(uid, args.region, ports, _parse_endpoints(args.allow_endpoints))
    if not args.apply:
        sys.stdout.write(ruleset)
        return 0
    # Replace atomically: declare, flush, then load in one transaction.
    _nft(["-f", "-"], f"table inet {TABLE}\ndelete table inet {TABLE}\n{ruleset}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
