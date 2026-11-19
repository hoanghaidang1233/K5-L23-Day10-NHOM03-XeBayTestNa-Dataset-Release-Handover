#!/usr/bin/env python3
"""Truy vết ticket của team AI -> trace.json (tier_a, tier_b, notify).

  python tools/trace_query.py runs/r3007/delivery --out runs/r3007/trace.json
  python tools/trace_query.py delivery --out submission/de_an/trace.json      # đề ẩn

Tiêu chí (GUIDE Pha 5, DELIVERY mục 3):
  - Lớp bị đổi quy tắc: lấy từ guideline/changelog.md (mục phiên bản mới nhất), đối chiếu tên lớp
    với ticket và classes.txt.
  - Job "guideline cũ": guideline ghi ở JOB (jobs.csv) khác phiên bản mới nhất. Không dùng
    guideline_version của từng ảnh trong metadata.json (có thể chính là lỗi guideline_mismatch).
  - "Có lớp đó": ít nhất một box detection của lớp đó trong labels/ của lô.
  - tier_a: ảnh thoả điều kiện, nằm trong các cảnh ticket nêu.
  - tier_b: ảnh thoả điều kiện, ở các cảnh khác (chưa ai báo).
  - notify: annotator + reviewer của các job chứa ảnh tầng a và b.

Chỉ đọc thư mục delivery truyền vào, chỉ dùng thư viện chuẩn. Có thể ép giá trị bằng
--class / --scenes / --old nếu ticket hoặc changelog viết khác mẫu.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

VERSION_RE = re.compile(r"^##\s*(v\d+(?:\.\d+)*)", re.M)
BACKTICK_RE = re.compile(r"`([^`]+)`")
SCENE_RE = re.compile(r"\bscene_[A-Za-z0-9]+\b")


def vkey(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v))


def load_items(path: Path, key: str = "image") -> dict[str, dict]:
    """manifest.json / metadata.json: chấp nhận {"items": {stem: rec}} hoặc {"items": [rec,...]}."""
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("items", data) if isinstance(data, dict) else data
    if isinstance(items, dict):
        return {str(k): v for k, v in items.items() if isinstance(v, dict)}
    return {Path(str(r[key])).stem: r for r in items if isinstance(r, dict) and key in r}


def load_classes(path: Path) -> dict[str, int]:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            cid, name = line.split(maxsplit=1)
            out[name.strip()] = int(cid)
    return out


def parse_changelog(text: str, class_names: set[str]) -> tuple[str | None, set[str]]:
    """Trả về (phiên bản mới nhất, các lớp được nêu trong mục của phiên bản đó)."""
    heads = [(m.group(1), m.start()) for m in VERSION_RE.finditer(text)]
    if not heads:
        return None, set()
    newest, start = max(heads, key=lambda h: vkey(h[0]))
    later = [pos for _v, pos in heads if pos > start]
    section = text[start: min(later) if later else len(text)]
    return newest, {n for n in BACKTICK_RE.findall(section) if n in class_names}


def main() -> int:
    ap = argparse.ArgumentParser(description="Truy vết ticket team AI -> trace.json")
    ap.add_argument("delivery", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--class", dest="cls", action="append", help="ép tên lớp bị đổi quy tắc (lặp được)")
    ap.add_argument("--scenes", nargs="*", help="ép danh sách cảnh team AI nêu")
    ap.add_argument("--old", nargs="*", help="ép các phiên bản guideline coi là cũ")
    args = ap.parse_args()
    d: Path = args.delivery

    classes = load_classes(d / "classes.txt")
    manifest = load_items(d / "manifest.json")
    metadata = load_items(d / "metadata.json")
    with (d / "jobs.csv").open(encoding="utf-8", newline="") as f:
        jobs = {r["job_id"].strip(): {k: (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f)}

    ticket = (d / "incoming" / "ticket.md").read_text(encoding="utf-8")
    changelog_p = d / "guideline" / "changelog.md"
    changelog = changelog_p.read_text(encoding="utf-8") if changelog_p.is_file() else ""

    newest, changed = parse_changelog(changelog, set(classes))
    ticket_classes = {n for n in BACKTICK_RE.findall(ticket) if n in classes}

    # Lớp bị đổi quy tắc: ưu tiên giao của changelog và ticket; thiếu một bên thì dùng bên còn lại.
    if args.cls:
        rule_classes = set(args.cls)
    else:
        rule_classes = (changed & ticket_classes) or changed or ticket_classes
    unknown = rule_classes - set(classes)
    if not rule_classes or unknown:
        raise SystemExit(f"Không xác định được lớp bị đổi quy tắc (tìm thấy {sorted(rule_classes)}); dùng --class")
    rule_ids = {classes[n] for n in rule_classes}

    scenes = set(args.scenes) if args.scenes else set(SCENE_RE.findall(ticket))
    if not scenes:
        raise SystemExit("Ticket không nêu cảnh nào (scene_...); dùng --scenes")

    if args.old:
        old_versions = set(args.old)
    else:
        if newest is None:
            newest = max((j["guideline"] for j in jobs.values()), key=vkey)
        old_versions = {j["guideline"] for j in jobs.values() if j["guideline"] != newest}
    old_jobs = {jid for jid, j in jobs.items() if j["guideline"] in old_versions}

    tier_a, tier_b, used_jobs = [], [], set()
    for stem, item in sorted(manifest.items()):
        meta = metadata.get(stem)
        if not meta:
            continue
        job_id = str(meta.get("job_id", "")).strip()
        if job_id not in old_jobs:
            continue
        label = d / item.get("label", f"labels/{stem}.txt")
        if not label.is_file():
            continue
        has_cls = False
        for line in label.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if parts and parts[0].lstrip("-").isdigit() and int(parts[0]) in rule_ids:
                has_cls = True
                break
        if not has_cls:
            continue
        (tier_a if str(meta.get("scene_id", "")).strip() in scenes else tier_b).append(stem)
        used_jobs.add(job_id)

    notify = sorted({p for jid in used_jobs for p in (jobs[jid]["annotator"], jobs[jid]["reviewer"]) if p})
    out = {"tier_a": tier_a, "tier_b": tier_b, "notify": notify}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"lớp đổi quy tắc: {sorted(rule_classes)} · guideline mới: {newest} · cũ: {sorted(old_versions)}", file=sys.stderr)
    print(f"cảnh ticket nêu: {sorted(scenes)} · job guideline cũ: {sorted(old_jobs)}", file=sys.stderr)
    print(f"tier_a {len(tier_a)} ảnh · tier_b {len(tier_b)} ảnh · notify {notify} -> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
