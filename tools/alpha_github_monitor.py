#!/usr/bin/env python3
"""
供 GitHub Actions 定时运行：拉取 Alpha123「今日空投」指纹，**仅当今日至少有一条空投且指纹变化**时发 Bark。

环境变量：
  BARK_URL  必填。完整前缀，例如 https://api.day.app/你的Key
            （发通知时会再拼上 /title/body，见 Bark 文档）

仓库内状态文件（需提交进 Git，供下次运行对比）：
  data/alpha_monitor_state.json
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

URL = "https://alpha123.uk/api/data?fresh=0"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://alpha123.uk/zh/",
}

ROOT = Path(os.environ.get("GITHUB_WORKSPACE", ".")).resolve()
STATE_PATH = ROOT / "data" / "alpha_monitor_state.json"


def fetch_body() -> str:
    req = urllib.request.Request(URL, headers=HEADERS, method="GET")
    with urllib.request.urlopen(req, timeout=35) as resp:
        return resp.read().decode("utf-8", errors="replace")


def beijing_to_local(date_str: str, time_str: str, *, phase2: bool) -> datetime:
    t = time_str.strip()
    if ":" in t:
        parts = t.split(":")
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
    else:
        h, m = int(t), 0
    tz8 = timezone(timedelta(hours=8))
    base = datetime.strptime(f"{date_str} {h:02d}:{m:02d}", "%Y-%m-%d %H:%M").replace(tzinfo=tz8)
    if phase2:
        base += timedelta(hours=18)
    return base.astimezone()


def fingerprint_for_today(data: dict) -> tuple[str, str]:
    """返回 (指纹, Bark 正文)。"""
    airdrops = data.get("airdrops") or []
    now = datetime.now().astimezone()
    rows: list[tuple[str, str, str, object, str]] = []  # token, fp_line, name, pts, hm
    for a in airdrops:
        d = a.get("date")
        if not d:
            continue
        t = (a.get("time") or "").strip() or "14:00"
        phase2 = a.get("phase") == 2
        try:
            local = beijing_to_local(str(d), str(t), phase2=phase2)
        except (ValueError, OSError):
            continue
        if local.date() != now.date():
            continue
        token = str(a.get("token") or "")
        name = str(a.get("name") or token)
        pts = a.get("points")
        hm = local.strftime("%H:%M")
        fp_line = f"{token}|{name}|{pts}|{hm}"
        rows.append((token, fp_line, name, pts, hm))
    rows.sort(key=lambda x: x[0])
    fp = "\n".join(x[1] for x in rows)
    summary_lines = [f"• {name}  积分 {pts}  时间 {hm}" for _, _, name, pts, hm in rows]
    body = "今日空投有更新\n" + "\n".join(summary_lines) if summary_lines else "今日空投有更新（当前无行）"
    return fp, body


def send_bark(title: str, body: str) -> None:
    bark = os.environ.get("BARK_URL", "").strip()
    if not bark:
        print("缺少环境变量 BARK_URL", file=sys.stderr)
        sys.exit(2)
    bark = bark.rstrip("/")
    # Bark: https://api.day.app/key/title/body
    path_title = urllib.parse.quote(title, safe="")
    path_body = urllib.parse.quote(body, safe="")
    full = f"{bark}/{path_title}/{path_body}"
    req = urllib.request.Request(full, method="GET", headers={"User-Agent": HEADERS["User-Agent"]})
    with urllib.request.urlopen(req, timeout=35) as resp:
        resp.read()


def main() -> int:
    if not os.environ.get("BARK_URL"):
        print("请先在仓库 Secrets 里配置 BARK_URL", file=sys.stderr)
        return 2

    raw = fetch_body()
    if raw.lstrip().startswith("<"):
        print("API 返回 HTML", file=sys.stderr)
        return 1
    data = json.loads(raw)
    new_fp, bark_body = fingerprint_for_today(data)

    old_fp: str | None = None
    if STATE_PATH.is_file():
        try:
            old = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            old_fp = old.get("fingerprint")
        except (json.JSONDecodeError, OSError):
            old_fp = None

    if old_fp is not None and old_fp != new_fp:
        if new_fp.strip():
            print("指纹变化且今日有空投，发送 Bark …")
            title = "Alpha123 今日空投"
            # Bark 对 URL 长度有限制，正文过长则截断
            if len(bark_body) > 3500:
                bark_body = bark_body[:3490] + "…"
            try:
                send_bark(title, bark_body)
            except urllib.error.URLError as e:
                print(f"Bark 请求失败: {e}", file=sys.stderr)
                return 1
        else:
            print("指纹变化但今日无空投，不发送 Bark。")

    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fingerprint": new_fp,
        "updated_utc": datetime.now(timezone.utc).isoformat(),
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if not STATE_PATH.is_file() or STATE_PATH.read_text(encoding="utf-8") != text:
        STATE_PATH.write_text(text, encoding="utf-8")
        print("已写入状态文件（将由 workflow 决定是否提交）。")
    else:
        print("指纹未变，跳过写文件。")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.URLError as e:
        print(f"网络错误: {e}", file=sys.stderr)
        raise SystemExit(1)
