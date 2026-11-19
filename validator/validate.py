#!/usr/bin/env python3
"""Validator luật cho lô dataset: 9 loại lỗi luật.

Chỉ dùng thư viện chuẩn và scripts/pngutil.py.
Chỉ đọc thư mục delivery truyền vào; không đọc _private/, data_source/, annotation COCO; không dùng mạng.

Usage:
    python validator/validate.py <delivery_dir> --out <errors.json>
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from pngutil import read_rgb  # noqa: E402

# Ngưỡng dùng chung cho mọi seed. Chỉnh trên lô sạch (inject_release.py --no-faults),
# không chỉnh theo đáp án.
BOX_EDGE_TOL = 1e-6   # sai số (theo tỉ lệ 0-1) cho box vượt mép ảnh
DUP_SIZE_TOL = 1.0    # px: hai box được coi là cùng kích thước nếu lệch <= giá trị này
DUP_SHIFT_TOL = 2.0   # px: lệch tâm tối đa của box bị lặp
AREA_TOL = 0          # px: area khai nhiều hơn số pixel thật quá mức này là lỗi


# ---------- nạp dữ liệu ----------
def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def to_stem_dict(data, name: str, key: str = "image") -> dict[str, dict]:
    """Chuẩn hoá về dict stem -> record.

    Chấp nhận ba dạng:
      - {"items": {stem: record}}           (manifest.json)
      - {"items": [record, ...]}            (metadata.json, record có khoá `key`)
      - {stem: record}                      (dạng phẳng)
    """
    items = data.get("items", data) if isinstance(data, dict) else data
    if isinstance(items, dict):
        return items
    if isinstance(items, list):
        out: dict[str, dict] = {}
        for rec in items:
            if not isinstance(rec, dict) or key not in rec:
                raise ValueError(f"{name}: phần tử thiếu khoá {key!r}: {rec!r}")
            out[str(Path(rec[key]).stem)] = rec
        return out
    raise ValueError(f"{name}: không nhận dạng được cấu trúc")


def load_classes(path: Path) -> set[int]:
    ids = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            cid, _name = line.split(maxsplit=1)   # tên lớp có thể có dấu cách
            ids.add(int(cid))
    return ids


def load_delivery(d: Path) -> dict:
    manifest = to_stem_dict(load_json(d / "manifest.json"), "manifest.json")
    metadata = to_stem_dict(load_json(d / "metadata.json"), "metadata.json", key="image")
    panoptic = load_json(d / "panoptic.json")

    jobs: dict[str, dict] = {}
    with (d / "jobs.csv").open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            jobs[row["job_id"].strip()] = row

    image_size = {
        Path(im["file_name"]).stem: (im["width"], im["height"]) for im in panoptic["images"]
    }
    categories = {c["id"] for c in panoptic["categories"]}
    segments = {
        Path(ann["file_name"]).stem: ann["segments_info"] for ann in panoptic["annotations"]
    }
    return {
        "dir": d,
        "manifest": manifest,
        "metadata": metadata,
        "jobs": jobs,
        "image_size": image_size,
        "categories": categories,
        "segments": segments,
        "classes": load_classes(d / "classes.txt"),
    }


# ---------- tiện ích ----------
def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()   # bytes, không phải text


def read_boxes(path: Path) -> list[tuple[str, float, float, float, float]]:
    """(cls_str, x, y, w, h), chuẩn hoá 0-1. Dòng hỏng giữ cls để invalid_class bắt."""
    if not path.is_file():
        return []
    boxes = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if not parts:
            continue
        try:
            x, y, w, h = (float(v) for v in parts[1:5])
        except ValueError:
            x = y = w = h = 0.0
        boxes.append((parts[0], x, y, w, h))
    return boxes


# ---------- 7 luật theo ảnh (rule trả về loại lỗi hoặc None) ----------
def r_missing_image(stem, item, boxes, ctx):
    for key in ("image", "label", "mask"):
        if not (ctx["dir"] / item[key]).is_file():
            return "missing_image"
    return None


def r_wrong_hash(stem, item, boxes, ctx):
    for key in ("image", "label", "mask"):
        if sha256_of(ctx["dir"] / item[key]) != item[f"{key}_sha256"]:
            return "wrong_hash"
    return None


def r_invalid_class(stem, item, boxes, ctx):
    for cls, *_ in boxes:
        try:
            cid = int(cls)
        except ValueError:
            return "invalid_class"
        if cid not in ctx["classes"]:
            return "invalid_class"
    return None


def r_bbox_out_of_bounds(stem, item, boxes, ctx):
    for _, x, y, w, h in boxes:
        if (
            x - w / 2 < -BOX_EDGE_TOL
            or y - h / 2 < -BOX_EDGE_TOL
            or x + w / 2 > 1 + BOX_EDGE_TOL
            or y + h / 2 > 1 + BOX_EDGE_TOL
        ):
            return "bbox_out_of_bounds"
    return None


def r_duplicate_box(stem, item, boxes, ctx):
    size = ctx["image_size"].get(stem)
    if not size:
        return None
    W, H = size
    px = [(int(c), x * W, y * H, w * W, h * H) for c, x, y, w, h in boxes]   # invalid_class đã chạy trước
    for i, a in enumerate(px):
        for b in px[i + 1 :]:
            if a[0] != b[0]:
                continue
            if (
                abs(a[3] - b[3]) <= DUP_SIZE_TOL
                and abs(a[4] - b[4]) <= DUP_SIZE_TOL
                and abs(a[1] - b[1]) <= DUP_SHIFT_TOL
                and abs(a[2] - b[2]) <= DUP_SHIFT_TOL
            ):
                return "duplicate_box"
    return None


def r_guideline_mismatch(stem, item, boxes, ctx):
    meta = ctx["metadata"].get(stem)
    if not meta:
        return None
    job = ctx["jobs"].get(str(meta.get("job_id", "")).strip())
    if job is None:
        return None
    if str(meta.get("guideline_version", "")).strip() != job["guideline"].strip():
        return "guideline_mismatch"
    return None


def r_invalid_category_id(stem, item, boxes, ctx):
    for seg in ctx["segments"].get(stem, []):
        if seg["category_id"] not in ctx["categories"]:
            return "invalid_category_id"
    return None


def r_thing_overlap(stem, item, boxes, ctx):
    segs = ctx["segments"].get(stem, [])
    if not segs:
        return None
    _w, _h, pixels = read_rgb(ctx["dir"] / item["mask"])
    counts: Counter = Counter()
    for (r, g, b), n in Counter(zip(pixels[0::3], pixels[1::3], pixels[2::3])).items():
        counts[r + g * 256 + b * 65536] += n      # id segment = R + G*256 + B*256^2
    for seg in segs:
        if seg["area"] > counts.get(seg["id"], 0) + AREA_TOL:
            return "thing_overlap"
    return None


PER_IMAGE_RULES = [
    r_missing_image,
    r_wrong_hash,
    r_invalid_class,
    r_bbox_out_of_bounds,
    r_duplicate_box,
    r_guideline_mismatch,
    r_invalid_category_id,
    r_thing_overlap,
]


# ---------- luật theo cảnh ----------
def scene_leaks(ctx) -> list[str]:
    """Cảnh có ảnh ở cả train và val (target = scene_id)."""
    splits: dict[str, set] = defaultdict(set)
    for meta in ctx["metadata"].values():
        splits[meta["scene_id"]].add(meta["split"])
    return [scene for scene in sorted(splits) if len(splits[scene]) > 1]


# ---------- điều phối ----------
def validate(delivery: Path) -> list[dict]:
    ctx = load_delivery(delivery)
    errors = []
    for stem, item in sorted(ctx["manifest"].items()):
        boxes = read_boxes(delivery / item["label"])
        for rule in PER_IMAGE_RULES:
            kind = rule(stem, item, boxes, ctx)
            if kind:
                errors.append({"type": kind, "target": stem})
                break                              # mỗi ảnh tối đa một lỗi
    for scene in scene_leaks(ctx):
        errors.append({"type": "scene_leak", "target": scene})
    return sorted(errors, key=lambda e: (e["type"], e["target"]))


def main() -> int:
    ap = argparse.ArgumentParser(description="Validator luật cho lô dataset")
    ap.add_argument("delivery", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    errors = validate(args.delivery)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps({"errors": errors}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"{len(errors)} lỗi -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())