"""Chia hàng đợi review thành 5 file CSV và gộp lại thành review_log.csv, có kiểm định dạng.

Chia (mỗi người một file, giống thứ tự --part k/5 của viewer):
  python tools/review_parts.py chia --candidates runs/r9999/candidates.json --out runs/r9999/review

Gộp (kiểm lỗi trước khi ghi; có lỗi thì in ra và không ghi file):
  python tools/review_parts.py gop --parts runs/r9999/review --out runs/r9999/review_log.csv

Kiểm khi gộp: verdict phải là confirmed/rejected; type phải là một loại lỗi gán nhãn
(dòng swap phải chọn class_swap hoặc category_swap); ghi chú >= 20 ký tự và có tên người xem;
ghi chú có dấu phẩy mà không bọc ngoặc kép thì tự ghép lại và cảnh báo.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

NGUOI = ["1-Dang", "2-Khanh", "3-Quan", "4-Phuc", "5-Trinh"]
LOAI = {"class_swap", "category_swap", "bbox_drift", "missing_box", "instance_merge"}
VERDICT = {"confirmed", "rejected"}


def chia(candidates: Path, out: Path) -> int:
    data = json.loads(candidates.read_text(encoding="utf-8"))
    cands = data.get("candidates", data) if isinstance(data, dict) else data
    for c in cands:
        c.setdefault("target", c.get("image"))
    cands = sorted(cands, key=lambda c: (c["target"], c["type"]))   # cùng thứ tự với viewer.py
    out.mkdir(parents=True, exist_ok=True)
    for k, ten in enumerate(NGUOI):
        p = out / f"{ten}.csv"
        if p.exists():
            print(f"bỏ qua {p}: đã có (không ghi đè bài đang điền)")
            continue
        phan = cands[k::len(NGUOI)]
        with p.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["image", "type", "verdict", "note"])
            for c in phan:
                typ = "" if "swap" in c["type"] else c["type"]   # swap: người xem tự chọn loại
                w.writerow([c["target"], typ, "", f"({ten.split('-')[1]} xem) "])
        print(f"{p}: {len(phan)} ảnh (viewer --part {k + 1}/{len(NGUOI)})")
    return 0


def gop(parts: Path, out: Path) -> int:
    rows, loi, canh_bao = [], [], []
    for p in sorted(parts.glob("*.csv")):
        doc = list(csv.reader(p.open(encoding="utf-8-sig")))
        for i, r in enumerate(doc[1:], start=2):
            if not any(x.strip() for x in r):
                continue
            if len(r) > 4:
                canh_bao.append(f"{p.name}:{i} ghi chú có dấu phẩy chưa bọc ngoặc kép, đã tự ghép lại")
                r = r[:3] + [",".join(r[3:])]
            r = [x.strip() for x in r] + [""] * (4 - len(r))
            img, typ, ver, note = r[:4]
            noi = f"{p.name}:{i} ({img})"
            if ver not in VERDICT:
                loi.append(f"{noi}: verdict '{ver}' phải là confirmed hoặc rejected")
            if typ not in LOAI:
                loi.append(f"{noi}: type '{typ}' phải là một trong {sorted(LOAI)}")
            if len(note) < 20:
                loi.append(f"{noi}: ghi chú quá ngắn ({len(note)} ký tự), phải nói rõ thấy gì")
            if "xem)" not in note:
                canh_bao.append(f"{noi}: ghi chú chưa có tên người xem, ví dụ '(Ten xem) ...'")
            thap = note.lower()
            if "bạn " in thap or "thiếu ảnh" in thap or "không có ảnh" in thap:
                canh_bao.append(f"{noi}: ghi chú giống câu trả lời của AI hoặc chưa xem ảnh; "
                                "người xem phải tự mở ảnh và ghi điều mình thấy (RULES.md mục 26)")
            rows.append([img, typ, ver, note])
    for c in canh_bao:
        print("CẢNH BÁO", c)
    for e in loi:
        print("LỖI", e)
    if loi:
        print(f"=> {len(loi)} lỗi, CHƯA ghi {out}. Sửa các file trong {parts} rồi chạy lại.")
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["image", "type", "verdict", "note"])
        w.writerows(rows)
    print(f"=> {len(rows)} dòng -> {out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Chia và gộp review_log theo 5 người")
    sub = ap.add_subparsers(dest="lenh", required=True)
    a = sub.add_parser("chia")
    a.add_argument("--candidates", required=True, type=Path)
    a.add_argument("--out", required=True, type=Path)
    b = sub.add_parser("gop")
    b.add_argument("--parts", required=True, type=Path)
    b.add_argument("--out", required=True, type=Path)
    x = ap.parse_args()
    return chia(x.candidates, x.out) if x.lenh == "chia" else gop(x.parts, x.out)


if __name__ == "__main__":
    sys.exit(main())
