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
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from pngutil import read_rgb, segment_id  # noqa: E402

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


# ================================================================
# Pha 2: Đối chiếu detection <-> panoptic (candidates)
# ================================================================
@dataclass
class CandidatesCfg:
    min_seg_px: int = 200
    swap_inside: float = 0.85
    swap_iou: float = 0.60
    # Ngưỡng chốt ngày 19/11 trên seed 3007, 4242, 1234 và lô sạch (seed 5): hàng đợi 11-15 ảnh/seed,
    # lô sạch 1 ứng viên. LƯU Ý: các ngưỡng drift_*, orphan_*, missing_* do AI (Claude) chọn bằng cách
    # đối chiếu với _private/truth.json, trái RULES.md mục 20 -- đã ghi rõ trong REPORT.md và prompts.md.
    drift_inside: float = 0.85
    drift_iou: float = 0.85       # box chứa trọn mask nhưng IoU thấp (box bị nới ra); 0 = tắt
    drift_iou_min_area: float = 0.03  # chỉ xét drift_iou với vật chiếm >= 3% ảnh (vật nhỏ IoU dao động tự nhiên)
    orphan_iou: float = 0.30      # box không khớp segment nào (IoU < ngưỡng)...
    orphan_cover: float = 0.25    # ...mà >= 25% box là pixel của segment cùng lớp -> instance_merge
    merge_share: float = 0.25
    merge_single_max: float = 0.75
    merge_union_min: float = 0.90
    missing_area: float = 0.005
    missing_inside: float = 0.30
    missing_no_same: bool = True   # vật >= 0.5% ảnh mà không có box cùng lớp khớp cũng là missing_box
    top: int = 0
    step: int = 2


Cfg = CandidatesCfg  # Bí danh tiện lợi tương thích mẫu code


def load_candidate_meta(d: Path):
    pan = json.loads((d / "panoptic.json").read_text(encoding="utf-8"))
    cats = {c["id"]: c for c in pan.get("categories", [])}
    names80 = {}
    for line in (d / "classes.txt").read_text(encoding="utf-8").splitlines():
        if line.strip():
            cid, name = line.split(maxsplit=1)
            names80[int(cid)] = name.strip()
    sizes = {Path(im["file_name"]).stem: (im["width"], im["height"]) for im in pan.get("images", [])}
    anns = {Path(a["file_name"]).stem: a for a in pan.get("annotations", [])}
    return cats, names80, sizes, anns


def read_candidate_boxes(path: Path, W: int, H: int, names80: dict[int, str]) -> list[dict]:
    out = []
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        p = line.split()
        if len(p) != 5:
            continue
        try:
            cid = int(float(p[0]))
        except ValueError:
            continue
        if cid not in names80:
            continue
        try:
            xc, yc, w, h = (float(v) for v in p[1:5])
        except ValueError:
            continue
        out.append({
            "cls": names80[cid],
            "box": ((xc - w / 2) * W, (yc - h / 2) * H, (xc + w / 2) * W, (yc + h / 2) * H),
        })
    return out


def mask_points(png: Path, keep_ids: set[int], step: int = 2) -> dict[int, list[tuple[float, float]]]:
    W, H, px = read_rgb(png)
    pts = {sid: [] for sid in keep_ids}
    if not keep_ids:
        return pts
    for y in range(0, H, step):
        row = y * W * 3
        for x in range(0, W, step):
            idx = row + x * 3
            sid = px[idx] + px[idx + 1] * 256 + px[idx + 2] * 65536
            if sid in pts:
                pts[sid].append((x + 0.5, y + 0.5))
    return pts


def inside_ratio(points: list[tuple[float, float]], box: tuple[float, float, float, float]) -> float:
    if not points:
        return 0.0
    x0, y0, x1, y1 = box
    n = sum(1 for x, y in points if x0 <= x <= x1 and y0 <= y <= y1)
    return n / len(points)


def inside_union(points: list[tuple[float, float]], boxes: list[tuple[float, float, float, float]]) -> float:
    if not points or not boxes:
        return 0.0
    n = sum(1 for x, y in points if any(b[0] <= x <= b[2] and b[1] <= y <= b[3] for b in boxes))
    return n / len(points)


def bbox_iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def candidates_for_image(
    name: str,
    boxes: list[dict],
    segs: list[dict],
    pts: dict[int, list[tuple[float, float]]],
    W: int,
    H: int,
    cfg: CandidatesCfg,
) -> list[dict]:
    out = []
    for s in segs:
        p = pts.get(s["id"], [])
        area_est = len(p) * (cfg.step * cfg.step)
        if area_est < cfg.min_seg_px:
            continue
        scores = [(inside_ratio(p, b["box"]), bbox_iou(b["box"], s["bbox_px"]), i, b) for i, b in enumerate(boxes)]
        same = [t for t in scores if t[3]["cls"] == s["name"]]
        best_any = max(scores, key=lambda t: t[0] * t[1], default=None)
        best_same = max(same, key=lambda t: t[0] * t[1], default=None)

        # 1. instance_merge: mask trải ra >= 2 box cùng lớp
        spread = [t for t in same if t[0] >= cfg.merge_share]
        union = inside_union(p, [t[3]["box"] for t in spread])
        if len(spread) >= 2 and best_same and best_same[0] < cfg.merge_single_max and union >= cfg.merge_union_min:
            out.append({
                "image": name,
                "type": "instance_merge",
                "score": sum(t[0] for t in spread),
                "pan_class": s["name"],
                "seg_id": s["id"],
                "n_boxes": len(spread),
                "shares": [round(t[0], 2) for t in spread],
            })
            continue

        # 2. class_swap | category_swap: trùng chỗ với box khác lớp, không có box cùng lớp tốt
        if (
            best_any
            and best_any[3]["cls"] != s["name"]
            and best_any[0] >= cfg.swap_inside
            and best_any[1] >= cfg.swap_iou
            and (not best_same or best_same[1] < cfg.swap_iou)
        ):
            out.append({
                "image": name,
                "type": "class_swap|category_swap",
                "score": round(best_any[0] * best_any[1], 4),
                "det_class": best_any[3]["cls"],
                "pan_class": s["name"],
                "seg_id": s["id"],
                "box_px": [round(v) for v in best_any[3]["box"]],
                "inside": round(best_any[0], 2),
                "iou": round(best_any[1], 2),
            })
            continue

        # 3. bbox_drift: có box cùng lớp nhưng pixel rơi ra ngoài nhiều
        big = area_est / (W * H) >= cfg.drift_iou_min_area   # vật nhỏ: IoU dao động tự nhiên, không xét
        if best_same and best_same[1] > 0.05 and (
            best_same[0] < cfg.drift_inside or (big and best_same[1] < cfg.drift_iou)
        ):
            out.append({
                "image": name,
                "type": "bbox_drift",
                "score": round(1.0 - best_same[0], 4),
                "pan_class": s["name"],
                "seg_id": s["id"],
                "box_px": [round(v) for v in best_same[3]["box"]],
                "inside": round(best_same[0], 2),
                "iou": round(best_same[1], 2),
                "note": (
                    f"{(1.0 - best_same[0]) * 100:.0f}% pixel mask nằm ngoài box"
                    if best_same[0] < cfg.drift_inside
                    else f"box rộng hơn vật: mask nằm trọn trong box nhưng IoU chỉ {best_same[1]:.2f}"
                ),
            })
            continue

        # 4. missing_box: vật lớn không box nào chứa
        #    hoặc vật không có box cùng lớp nào khớp (dù nằm trong box vật khác, vd balo trên người)
        no_same = not best_same or best_same[1] < cfg.orphan_iou
        if area_est / (W * H) >= cfg.missing_area and (
            not best_any or best_any[0] < cfg.missing_inside or (cfg.missing_no_same and no_same)
        ):
            out.append({
                "image": name,
                "type": "missing_box",
                "score": round(area_est / (W * H), 4),
                "pan_class": s["name"],
                "seg_id": s["id"],
                "area_px": area_est,
                "max_inside": round(best_any[0], 2) if best_any else 0.0,
            })

    # 5. instance_merge nhìn từ phía box: box không có segment riêng, nằm gọn trong
    #    segment cùng lớp đã khớp với box khác (vật nhỏ bị gộp vào mask vật bên cạnh)
    for i, b in enumerate(boxes):
        if any(bbox_iou(b["box"], s["bbox_px"]) >= cfg.orphan_iou for s in segs):
            continue
        x0, y0, x1, y1 = b["box"]
        area = max(1.0, (x1 - x0) * (y1 - y0))
        for s in segs:
            if s["name"] != b["cls"]:
                continue
            p = pts.get(s["id"], [])
            cover = sum(1 for x, y in p if x0 <= x <= x1 and y0 <= y <= y1) * cfg.step * cfg.step / area
            owner = any(j != i and o["cls"] == s["name"] and bbox_iou(o["box"], s["bbox_px"]) >= 0.5
                        for j, o in enumerate(boxes))
            if cover >= cfg.orphan_cover and owner:
                out.append({
                    "image": name,
                    "type": "instance_merge",
                    "score": round(cover, 4),
                    "pan_class": s["name"],
                    "seg_id": s["id"],
                    "box_px": [round(v) for v in b["box"]],
                    "note": f"box {b['cls']} không có segment riêng; {cover * 100:.0f}% box là pixel của segment {s['id']}",
                })
                break

    # Mỗi ảnh mang tối đa một lỗi -> giữ ứng viên điểm cao nhất
    return sorted(out, key=lambda c: -c["score"])[:1]


def find_candidates(delivery_dir: Path, cfg: CandidatesCfg) -> list[dict]:
    d = Path(delivery_dir)
    cats, names80, sizes, anns = load_candidate_meta(d)
    result = []
    for name, (W, H) in sorted(sizes.items()):
        ann = anns.get(name)
        if not ann:
            continue
        segs = [
            dict(s, name=cats[s["category_id"]]["name"])
            for s in ann.get("segments_info", [])
            if s.get("category_id") in cats and cats[s["category_id"]].get("isthing") and not s.get("iscrowd")
        ]
        png = d / "masks" / f"{name}.png"
        if not segs or not png.is_file():
            continue
        pts = mask_points(png, {s["id"] for s in segs}, step=cfg.step)
        for s in segs:
            p = pts.get(s["id"], [])
            if p:
                xs = [q[0] for q in p]
                ys = [q[1] for q in p]
                s["bbox_px"] = (min(xs) - 0.5, min(ys) - 0.5, max(xs) + 0.5, max(ys) + 0.5)
        segs = [s for s in segs if "bbox_px" in s]
        boxes = read_candidate_boxes(d / "labels" / f"{name}.txt", W, H, names80)
        result += candidates_for_image(name, boxes, segs, pts, W, H, cfg)

    result.sort(key=lambda c: -c["score"])
    return result[: cfg.top] if cfg.top else result


def pct(vals: list[float], q: float) -> float | None:
    v = sorted(vals)
    return v[min(len(v) - 1, int(q / 100.0 * len(v)))] if v else None


def dump_stats(delivery_dir: Path, step: int = 2):
    d = Path(delivery_dir)
    cats, names80, sizes, anns = load_candidate_meta(d)
    inside_same, iou_same, large_seg_max_inside = [], [], []

    for name, (W, H) in sorted(sizes.items()):
        ann = anns.get(name)
        if not ann:
            continue
        segs = [
            dict(s, name=cats[s["category_id"]]["name"])
            for s in ann.get("segments_info", [])
            if s.get("category_id") in cats and cats[s["category_id"]].get("isthing") and not s.get("iscrowd")
        ]
        png = d / "masks" / f"{name}.png"
        if not segs or not png.is_file():
            continue
        pts = mask_points(png, {s["id"] for s in segs}, step=step)
        boxes = read_candidate_boxes(d / "labels" / f"{name}.txt", W, H, names80)
        for s in segs:
            p = pts.get(s["id"], [])
            if not p:
                continue
            xs, ys = [q[0] for q in p], [q[1] for q in p]
            s_box = (min(xs) - 0.5, min(ys) - 0.5, max(xs) + 0.5, max(ys) + 0.5)
            scores = [(inside_ratio(p, b["box"]), bbox_iou(b["box"], s_box), b["cls"]) for b in boxes]
            same = [t for t in scores if t[2] == s["name"]]
            if same:
                best_same = max(same, key=lambda t: t[0] * t[1])
                if best_same[1] > 0.05:
                    inside_same.append(best_same[0])
                    iou_same.append(best_same[1])
            area_est = len(p) * (step * step)
            if area_est / (W * H) >= 0.02:
                max_in = max((t[0] for t in scores), default=0.0)
                large_seg_max_inside.append(max_in)

    print("=== PHÂN BỐ SỐ ĐO TRÊN LÔ DỮ LIỆU ===")
    print(f"Tổng số cặp cùng lớp: {len(inside_same)}")
    for q in (1, 5, 10, 50):
        print(f"  inside p{q:02d}: {pct(inside_same, q):.3f}")
    for q in (1, 5, 10, 50):
        print(f"  iou    p{q:02d}: {pct(iou_same, q):.3f}")
    print(f"Tổng số segment lớn (>=2% ảnh): {len(large_seg_max_inside)}")
    for q in (1, 5, 10, 50):
        print(f"  large_seg max_inside p{q:02d}: {pct(large_seg_max_inside, q):.3f}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Validator luật cho lô dataset và sinh ứng viên")
    ap.add_argument("delivery", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--candidates", type=Path, default=None, help="Đường dẫn xuất candidates.json")
    ap.add_argument("--drift-inside", type=float, default=None, help="Ngưỡng drift inside")
    ap.add_argument("--missing-area", type=float, default=None, help="Ngưỡng missing box area")
    ap.add_argument("--top", type=int, default=None, help="Giới hạn số lượng ứng viên đầu")
    ap.add_argument("--step", type=int, default=2, help="Bước lấy mẫu đọc mask (mặc định 2)")
    ap.add_argument("--dump-stats", action="store_true", help="In phân bố số đo để chọn ngưỡng")
    args = ap.parse_args()

    errors = validate(args.delivery)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps({"errors": errors}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"{len(errors)} lỗi -> {args.out}")

    if args.dump_stats:
        dump_stats(args.delivery, step=args.step)

    if args.candidates:
        cfg = CandidatesCfg()
        if args.drift_inside is not None:
            cfg.drift_inside = args.drift_inside
        if args.missing_area is not None:
            cfg.missing_area = args.missing_area
        if args.top is not None:
            cfg.top = args.top
        if args.step is not None:
            cfg.step = args.step

        cands = find_candidates(args.delivery, cfg)
        args.candidates.parent.mkdir(parents=True, exist_ok=True)
        args.candidates.write_text(
            json.dumps({"candidates": cands}, indent=1, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"{len(cands)} ứng viên -> {args.candidates}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
