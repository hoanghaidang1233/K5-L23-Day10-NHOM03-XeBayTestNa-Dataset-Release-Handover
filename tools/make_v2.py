#!/usr/bin/env python3
"""Tạo lô bàn giao v2 (sản phẩm detection) từ v1 + errors.json, KHÔNG sửa delivery/.

  python tools/make_v2.py --run runs/r3007 [--errors runs/r3007/errors.json]

Ghi runs/r<seed>/handover/<release_id>_v2/ gồm images/, labels/, rework_queue.csv, manifest.csv,
label_summary.csv, truyvet.csv, README.txt. Sau đó chạy:

  python scripts/pack_release.py runs/r<seed>/handover/<release_id>_v2
  python scripts/lineage.py record --event release --release-id <release_id>_v2 --parent <release_id>
  python scripts/check_handover.py --run runs/r<seed>

Quy tắc (GUIDE Pha 4):
- Sửa ngay trong v2: wrong_hash (ảnh mở được → ghi hash mới; hỏng → rework), guideline_mismatch
  (guideline theo job), scene_leak (cả cảnh về một split).
- Lỗi nhãn detection hoặc thiếu file → rework_queue.csv, bỏ khỏi v2.
- Lỗi chỉ ở panoptic → ảnh ở lại v2, ghi vào README Ghi chú để báo team panoptic.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path

DET_REWORK = {"missing_image", "invalid_class", "bbox_out_of_bounds", "duplicate_box",
              "class_swap", "bbox_drift", "missing_box"}
PANOPTIC_ONLY = {"invalid_category_id", "thing_overlap", "category_swap", "instance_merge"}
FIX_IN_V2 = {"wrong_hash", "guideline_mismatch", "scene_leak"}
THRESHOLD = 0.02  # Day 7: > 2% ảnh lỗi thì không Release

ACTION = {
    "missing_image": "giao lại file ảnh còn thiếu, rồi kiểm lại nhãn",
    "wrong_hash": "ảnh hỏng/không khớp: lấy lại ảnh gốc, rồi kiểm lại nhãn",
    "invalid_class": "gán lại lớp hợp lệ (0-79) cho box sai",
    "bbox_out_of_bounds": "vẽ lại box nằm trong ảnh",
    "duplicate_box": "xoá box bị lặp",
    "class_swap": "gán lại đúng lớp cho box bị nhầm",
    "bbox_drift": "vẽ lại box khớp vật",
    "missing_box": "bổ sung box cho vật bị thiếu",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def image_ok(path: Path, size: tuple[int, int] | None) -> bool:
    """Mở ảnh kiểm: giải mã được hết và đúng kích thước khai trong panoptic.json."""
    try:
        from PIL import Image
    except ImportError:  # không có Pillow: chỉ kiểm marker JPEG đầu/cuối
        b = path.read_bytes()
        return b[:2] == b"\xff\xd8" and b.rstrip(b"\x00")[-2:] == b"\xff\xd9"
    try:
        with Image.open(path) as im:
            im.load()
            return size is None or im.size == size
    except Exception:
        return False


def job_ranges(jobs: list[dict]) -> str:
    """'v1.2 (J01-J03), v1.3 (J04-J10)' theo thứ tự job."""
    groups: list[tuple[str, list[str]]] = []
    for j in jobs:
        if groups and groups[-1][0] == j["guideline"]:
            groups[-1][1].append(j["job_id"])
        else:
            groups.append((j["guideline"], [j["job_id"]]))
    return ", ".join(f"{g} ({ids[0]}-{ids[-1]})" if len(ids) > 1 else f"{g} ({ids[0]})" for g, ids in groups)


def main() -> int:
    ap = argparse.ArgumentParser(description="Tạo lô bàn giao v2")
    ap.add_argument("--run", required=True, help="runs/r<seed>")
    ap.add_argument("--errors", help="mặc định <run>/errors.json")
    args = ap.parse_args()

    run = Path(args.run)
    d = run / "delivery"
    errors = json.loads(Path(args.errors or run / "errors.json").read_text(encoding="utf-8"))["errors"]
    rid = json.loads((d / "release.json").read_text(encoding="utf-8"))["release_id"]
    man = json.loads((d / "manifest.json").read_text(encoding="utf-8"))["items"]
    meta = {m["image"]: m for m in json.loads((d / "metadata.json").read_text(encoding="utf-8"))["items"]}
    jobs_list = read_csv(d / "jobs.csv")
    jobs = {j["job_id"]: j for j in jobs_list}
    names80 = {int(ln.split(" ", 1)[0]): ln.split(" ", 1)[1].strip()
               for ln in (d / "classes.txt").read_text(encoding="utf-8").splitlines() if ln.strip()}
    sizes = {Path(im["file_name"]).stem: (im["width"], im["height"])
             for im in json.loads((d / "panoptic.json").read_text(encoding="utf-8"))["images"]}

    unknown = sorted({e["type"] for e in errors} - DET_REWORK - PANOPTIC_ONLY - FIX_IN_V2)
    if unknown:
        raise SystemExit(f"errors.json có loại lỗi lạ: {unknown}")

    # --- phân loại ảnh ---
    rework: dict[str, str] = {}          # ảnh -> loại lỗi
    panoptic_notes: list[tuple[str, str]] = []
    hash_fixed, guideline_fixed = [], []
    for e in errors:
        t, name = e["type"], e["target"]
        if t == "scene_leak":
            continue
        if name not in man:
            print(f"  ! bỏ qua {t} {name}: không có trong manifest")
            continue
        if t in DET_REWORK:
            rework[name] = t
        elif t in PANOPTIC_ONLY:
            panoptic_notes.append((name, t))
        elif t == "guideline_mismatch":
            guideline_fixed.append(name)
        elif t == "wrong_hash":
            img = d / man[name]["image"]
            if img.is_file() and image_ok(img, sizes.get(name)):
                hash_fixed.append(name)
            else:
                rework[name] = t
    # ảnh thiếu file luôn phải vào rework, kể cả khi errors.json bỏ sót
    for name, it in man.items():
        if not (d / it["image"]).is_file() and name not in rework:
            print(f"  ! {name}: thiếu file ảnh nhưng errors.json không ghi missing_image")
            rework[name] = "missing_image"

    # --- scene_leak: đưa cả cảnh về split chiếm đa số (hoà thì train) ---
    scene_imgs: dict[str, list[str]] = {}
    for name in man:
        scene_imgs.setdefault(meta[name]["scene_id"], []).append(name)
    split_of = {name: meta[name]["split"] for name in man}
    leak_fixed = []
    for sc, imgs in sorted(scene_imgs.items()):
        c = Counter(meta[n]["split"] for n in imgs)
        if len(c) > 1:
            target = max(sorted(c), key=lambda s: (c[s], s == "train"))
            for n in imgs:
                split_of[n] = target
            leak_fixed.append(f"{sc} -> {target}")
    reported_leaks = {e["target"] for e in errors if e["type"] == "scene_leak"}
    missed = {s.split(" ")[0] for s in leak_fixed} - reported_leaks
    if missed:
        print(f"  ! cảnh rò train/val nhưng errors.json không ghi scene_leak: {sorted(missed)}")

    # --- ghi v2 ---
    v2 = run / "handover" / f"{rid}_v2"
    if v2.exists():
        shutil.rmtree(v2)
    (v2 / "images").mkdir(parents=True)
    (v2 / "labels").mkdir()
    keep = sorted(n for n in man if n not in rework)
    for n in keep:
        shutil.copyfile(d / man[n]["image"], v2 / "images" / Path(man[n]["image"]).name)
        shutil.copyfile(d / man[n]["label"], v2 / "labels" / Path(man[n]["label"]).name)

    write_csv(v2 / "rework_queue.csv", ["image", "type", "annotator", "reviewer", "action"],
              [[n, t, jobs[meta[n]["job_id"]]["annotator"], jobs[meta[n]["job_id"]]["reviewer"], ACTION[t]]
               for n, t in sorted(rework.items())])

    files = sorted(p for sub in ("images", "labels") for p in (v2 / sub).iterdir() if p.is_file())
    write_csv(v2 / "manifest.csv", ["file", "sha256"], [[p.relative_to(v2).as_posix(), sha(p)] for p in files])

    counts: Counter = Counter()
    for n in keep:
        for ln in (v2 / "labels" / Path(man[n]["label"]).name).read_text(encoding="utf-8").splitlines():
            if ln.strip():
                c = int(float(ln.split()[0]))
                counts[names80.get(c, str(c))] += 1
    order = [names80[i] for i in sorted(names80) if counts[names80[i]]] + sorted(k for k in counts if k not in names80.values())
    write_csv(v2 / "label_summary.csv", ["class", "count"],
              [[k, counts[k]] for k in order] + [["TOTAL", sum(counts.values())]])

    write_csv(v2 / "truyvet.csv", ["image", "scene_id", "split", "job_id", "annotator", "reviewer", "guideline"],
              [[n, meta[n]["scene_id"], split_of[n], meta[n]["job_id"], jobs[meta[n]["job_id"]]["annotator"],
                jobs[meta[n]["job_id"]]["reviewer"], jobs[meta[n]["job_id"]]["guideline"]] for n in keep])

    # --- README.txt ---
    n_err = len({e["target"] for e in errors})
    rate = n_err / len(man)
    v1 = "Hold" if rate > THRESHOLD else "Release"
    v1_why = (f"{rate:.1%} ảnh lỗi > ngưỡng 2%, không Release; training run dùng v1 cần xem lại/train lại"
              if v1 == "Hold" else f"{rate:.1%} ảnh lỗi ≤ ngưỡng 2%")
    v2_why = (f"tách {len(rework)} ảnh lỗi nhãn detection/thiếu file sang rework_queue; "
              f"sửa {len(hash_fixed)} hash, {len(guideline_fixed)} guideline theo job, {len(leak_fixed)} cảnh rò split; "
              f"còn {len(panoptic_notes)} ảnh lỗi panoptic (nhãn detection đúng) chờ team panoptic")
    by_person: dict[str, list[str]] = {}
    for n in sorted(rework):
        j = jobs[meta[n]["job_id"]]
        by_person.setdefault(f"{j['annotator']}/{j['reviewer']}", []).append(n)
    notes = [
        "split: " + ("; ".join(leak_fixed) if leak_fixed else "không có cảnh rò train/val")
        + " (cả cảnh về split chiếm đa số, ghi trong truyvet.csv)",
        "hash: " + (", ".join(hash_fixed) + " đã mở ảnh kiểm (giải mã được, đúng kích thước), ảnh nguyên vẹn, chỉ manifest v1 sai, manifest.csv ghi hash mới"
                    if hash_fixed else "không có ảnh nào chỉ sai hash"),
        "guideline: lấy theo job trong jobs.csv" + (f" (sửa {', '.join(guideline_fixed)})" if guideline_fixed else ""),
        "rework: " + ("; ".join(f"{p}: {', '.join(v)}" for p, v in by_person.items()) if by_person else "không có"),
        "panoptic (ở lại v2, báo team panoptic): " + (", ".join(f"{n} ({t})" for n, t in sorted(panoptic_notes)) if panoptic_notes else "không có"),
    ]
    readme = [
        f"Release: {rid}_v2",
        f"Parent: {rid}",
        f"Số ảnh: {len(keep)}",
        f"Số nhãn: {sum(counts.values())}",
        f"Guideline: {job_ranges(jobs_list)}",
        f"QC v1: {n_err}/{len(man)} = {rate * 100:.1f}%".replace(".", ","),
        f"Kết luận v1: {v1} — {v1_why}",
        f"Kết luận v2: Release — {v2_why}",
        "Ghi chú: " + " | ".join(notes),
    ]
    (v2 / "README.txt").write_text("\n".join(readme) + "\n", encoding="utf-8")

    print(f"{v2}: {len(keep)} ảnh, {sum(counts.values())} nhãn, rework {len(rework)}, "
          f"panoptic {len(panoptic_notes)}, QC v1 {n_err}/{len(man)} => {v1}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
