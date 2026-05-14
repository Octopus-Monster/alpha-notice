#!/usr/bin/env python3
"""手动测试：发一条 Bark，确认 BARK_URL Secret 与手机端正常。"""
from __future__ import annotations

import os
import sys
import urllib.parse
import urllib.request

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def main() -> int:
    bark = os.environ.get("BARK_URL", "").strip()
    if not bark:
        print("缺少环境变量 BARK_URL（请在仓库 Actions Secrets 中配置）", file=sys.stderr)
        return 2
    bark = bark.rstrip("/")
    title = "Alpha Notice 连接测试"
    body = "来自 GitHub Actions：若 iPhone Bark 收到本条，说明 Secret 与网络配置正常。"
    path_title = urllib.parse.quote(title, safe="")
    path_body = urllib.parse.quote(body, safe="")
    full = f"{bark}/{path_title}/{path_body}"
    req = urllib.request.Request(full, method="GET", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=35) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except OSError as e:
        print(f"请求失败: {e}", file=sys.stderr)
        return 1
    print("HTTP 请求已发出。响应片段:", raw[:300])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
