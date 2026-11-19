#!/usr/bin/env python3
"""Vẽ box detection (đỏ) + bbox/viền segment panoptic (xanh) cho từng ứng viên.

  python tools/viewer.py <delivery> --candidates c.json --out review_png [--part 2/5] [--only a,b] [--crop]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw

RED, BLUE, YELLOW = (255, 40, 40), (40, 160, 255), (255, 220, 0)


def load_classes(d: Path) -> dict[int, str]:
    out = {}
    for line in (d / "classes.txt").read_text(encoding="utf-8").splitlines():
        if line.strip():
            i, name = line.strip().split(" ", 1)
            out[int(i)] = name.strip()
    return out


def load_candidates(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):  # {"candidates": [...]} hoặc {"errors": [...]}
        data = data.get("candidates") or data.get("errors") or []
    return data


def yolo_boxes(d: Path, stem: str, W: int, H: int, classes: dict[int, str]):
    p = d / "labels" / f"{stem}.txt"
    if not p.exists():
        return []
    boxes = []
    for line in p.read_text(encoding="utf-8").split("\n"):
        parts = line.split()
        if len(parts) != 5:
            continue
        c, xc, yc, w, h = int(parts[0]), *map(float, parts[1:])
        boxes.append((classes.get(c, f"?{c}"), (xc - w / 2) * W, (yc - h / 2) * H, (xc + w / 2) * W, (yc + h / 2) * H))
    return boxes


def mask_outline(mask: Image.Image, seg_ids: set[int]) -> list[tuple[int, int]]:
    """Trả về pixel biên của các segment (id = R + G*256 + B*256^2)."""
    W, H = mask.size
    px = mask.convert("RGB").load()
    ids = [[0] * W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            r, g, b = px[x, y]
            ids[y][x] = r + g * 256 + b * 65536
    pts = []
    for y in range(H):
        for x in range(W):
            v = ids[y][x]
            if v in seg_ids and (
                x == 0 or y == 0 or x == W - 1 or y == H - 1
                or ids[y][x - 1] != v or ids[y][x + 1] != v or ids[y - 1][x] != v or ids[y + 1][x] != v
            ):
                pts.append((x, y))
    return pts


def render(d, cand, classes, cats, anns, out: Path, crop: bool):
    stem = cand["target"]
    img_p = d / "images" / f"{stem}.jpg"
    if not img_p.exists():
        print(f"bỏ qua {stem}: thiếu ảnh")
        return
    img = Image.open(img_p).convert("RGB")
    W, H = img.size
    draw = ImageDraw.Draw(img)
    ann = anns.get(stem, {"segments_info": []})
    segs = [s for s in ann["segments_info"] if cats.get(s["category_id"], {}).get("isthing", 1)]
    # viền mask
    mp = d / "masks" / f"{stem}.png"
    if mp.exists():
        for pt in mask_outline(Image.open(mp), {s["id"] for s in segs if not s.get("iscrowd")}):
            draw.point(pt, fill=YELLOW)
    for s in segs:
        x, y, w, h = s["bbox"]
        name = cats.get(s["category_id"], {}).get("name", f"?{s['category_id']}")
        draw.rectangle([x, y, x + w, y + h], outline=BLUE, width=2)
        draw.text((x + 2, y + h - 12), f"P:{name}" + (" crowd" if s.get("iscrowd") else ""), fill=BLUE)
    for name, x0, y0, x1, y1 in yolo_boxes(d, stem, W, H, classes):
        draw.rectangle([x0, y0, x1, y1], outline=RED, width=2)
        draw.text((x0 + 2, y0 + 2), f"D:{name}", fill=RED)
    info = " ".join(f"{k}={v}" for k, v in cand.items() if k != "target")
    draw.rectangle([0, 0, min(W, 8 * len(info) + 8), 14], fill=(0, 0, 0))
    draw.text((4, 2), info, fill=(255, 255, 255))
    if crop and "bbox" in cand:  # nếu candidates có bbox vùng nghi [x,y,w,h]
        x, y, w, h = cand["bbox"]
        m = 0.3 * max(w, h)
        img = img.crop((max(0, x - m), max(0, y - m), min(W, x + w + m), min(H, y + h + m)))
    k = 3 if min(img.size) < 300 else 2 if min(img.size) < 600 else 1
    if k > 1:
        img = img.resize((img.width * k, img.height * k), Image.NEAREST)
    img.save(out / f"{stem}_{cand['type']}.png")


def main() -> int:
    ap = argparse.ArgumentParser(description="Vẽ ứng viên để review bằng mắt")
    ap.add_argument("delivery")
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--out", default="review_png")
    ap.add_argument("--part", default="1/1", help="k/n: chỉ vẽ phần thứ k trong n phần")
    ap.add_argument("--only", default="", help="danh sách tên ảnh, cách nhau dấu phẩy")
    ap.add_argument("--crop", action="store_true")
    a = ap.parse_args()

    d, out = Path(a.delivery), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    classes = load_classes(d)
    pan = json.loads((d / "panoptic.json").read_text(encoding="utf-8"))
    cats = {c["id"]: c for c in pan["categories"]}
    anns = {Path(x["file_name"]).stem: x for x in pan["annotations"]}

    cands = sorted(load_candidates(Path(a.candidates)), key=lambda c: (c["target"], c["type"]))
    if a.only:
        keep = set(a.only.split(","))
        cands = [c for c in cands if c["target"] in keep]
    k, n = map(int, a.part.split("/"))
    cands = cands[k - 1::n]
    for c in cands:
        render(d, c, classes, cats, anns, out, a.crop)
    print(f"đã vẽ {len(cands)} ứng viên (phần {k}/{n}) -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())