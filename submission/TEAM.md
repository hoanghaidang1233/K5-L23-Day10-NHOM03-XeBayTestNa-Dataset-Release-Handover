# Nhóm <<03-XeBayTestNa>>

- Seed luyện tập: 3007
- Repo: <<URL>>

| Họ và tên | MSHV | Tài khoản GitHub | Phần chính |
|---|---|---|---|
| HOÀNG HẢI ĐĂNG | 2A202603189 | hoanghaidang1233 | bàn giao v2 · lineage · nộp bài |
| TRỊNH VINH KHÁNH | 2A202603220 | ks1610 | Validator luật (file + detection) · bảo mật |
| TRẦN NGỌC QUÂN | 2A202603250 | quanngoctran | Validator luật (metadata + panoptic) · truy vết |
| NGUYỄN THIÊN PHÚC | 2A202603339 | phucnt31 | Đối chiếu det ↔ panoptic (candidates) · đo lô sạch, chọn ngưỡng |
| NGUYỄN KHÁNH TRÌNH | 2A202603026 | khanhtrinhkt2014 | Công cụ xem ảnh · điều phối review · REPORT |

> Cả 5 người đều xem ảnh ở Pha 2 (hàng đợi chia đều) và ở đề ẩn. Mỗi người tự ghi prompt AI của mình vào `prompts.md` và có ít nhất 2 commit.

## Chi tiết công việc

### Hoàng Hải Đăng —  bàn giao v2, lineage
- P0: tạo repo, mời thành viên, tải dữ liệu, chạy `run_lab.py --seeds 3007` (một lần duy nhất), đổi tiêu đề README.
- P3: tính QC v1 (`số lỗi/250`), ghi lineage HOLD v1, chạy `lineage.py impact` (kỳ vọng `R-021: affected=True`).
- P4: viết `tools/make_v2.py` tạo `handover/<release_id>_v2/`: `images/`, `labels/`, `rework_queue.csv`, `manifest.csv`, `label_summary.csv`, `truyvet.csv`, `README.txt`; chạy `pack_release.py`, ghi lineage release v2 (có parent), `check_handover.py` hết FAIL.
- Cuối: `export_submission.py`, commit/push, nộp link LMS; đề ẩn: kiểm đủ 4 file trong `submission/de_an/` và push.
- Commit dự kiến: `P0: chia viec`, `P3: lineage HOLD`, `P4: make_v2 + handover`.

### Trịnh Vinh Khánh — validator luật (file + detection), bảo mật
- P1: viết khung `validator/validate.py` (argparse, đọc `manifest.json`, `classes.txt`, ghi `errors.json`/`rules.json`).
- Luật: `missing_image`, `wrong_hash` (sha256 trên bytes, mở `rb`), `invalid_class` (ngoài 0–79), `bbox_out_of_bounds`, `duplicate_box` (cùng lớp, cùng kích thước, tâm lệch 1–2 px).
- Kiểm: F1 luật ≈ 1.0 trên seed 3007 + ít nhất 1 seed khác; lô sạch `runs/clean` không báo lỗi luật.
- P6a: viết `security.md` (ca USB, năm việc, ca khuôn mặt: Hold + báo người phụ trách, nêu tên ảnh có mặt người).
- Commit dự kiến: `P1: rule checks file/detection`, `P6: security.md`.

### Trần Ngọc Quân — validator luật (metadata + panoptic), truy vết
- P1: `scene_leak` (target `scene_id`), `guideline_mismatch` (so với guideline của job trong `jobs.csv`), `invalid_category_id`, `thing_overlap` (đếm pixel mask bằng `scripts/pngutil.py`, id = R + G·256 + B·256², bỏ id 0, so với `area`).
- Đảm bảo mỗi ảnh chỉ mang tối đa một lỗi khi ghép với phần của Khánh.
- P5: viết `tools/trace_query.py` → `trace.json` (`tier_a`, `tier_b`, `notify`), guideline lấy theo job; dùng lại cho đề ẩn.
- Commit dự kiến: `P1: metadata + panoptic rules`, `P5: trace_query`.

### Nguyễn Thiên Phúc — đối chiếu detection ↔ panoptic
- P2: thêm `--candidates` vào validator: đổi box YOLO sang pixel, ghép lớp qua tên, đếm pixel mask trong box, bỏ `iscrowd`.
- Sinh ứng viên: `class_swap`/`category_swap`, `bbox_drift`, `missing_box`, `instance_merge` (kèm số đo để người xem hiểu).
- Đo số ứng viên trên lô sạch (`inject_release.py --seed 5 --no-faults --out runs/clean`), chọn ngưỡng để hàng đợi xem hết được; ghi số liệu cho REPORT. Không dùng `_private`.
- Đề ẩn: chạy validator, chỉnh ngưỡng nhanh nếu hàng đợi quá lớn.
- Commit dự kiến: `P2: candidates matching`, `P2: tune thresholds on clean`.

### Nguyễn Khánh Trình — xem ảnh, review, REPORT
- P1–P2: viết `tools/viewer.py` (Pillow) vẽ box detection + bbox/viền segment panoptic có tên lớp, phóng to ảnh nhỏ.
- P2: chia hàng đợi cho 5 người, gộp `review_log.csv` (ghi chú ≥ 20 ký tự, nói thấy gì, ai xem; `rejected` kèm lý do), chạy `merge_review.py` → `errors.json`, `score_findings.py`.
- Viết `REPORT.md`: F1 theo nhóm lỗi, số ứng viên lô sạch, vì sao báo hết ứng viên làm F1 giảm, lineage/R-021, hash chứng minh gì/không, tiêu chí truy vết.
- Đề ẩn: chạy viewer cho cả hàng đợi, gộp log và chốt `errors.json`.
- Commit dự kiến: `P2: viewer tool`, `P2: review_log + merge`, `REPORT`.

## Đề ẩn (40 phút)
| Phút | Đăng | Khánh | Quân | Phúc | Trình |
|---|---|---|---|---|---|
| 0–5 | giải nén `de_an.zip` | | chạy `trace_query.py` | chạy validator + candidates | chạy viewer, chia hàng đợi |
| 5–30 | xem ảnh phần 1 | xem ảnh phần 2 | xem ảnh phần 3 | xem ảnh phần 4 | xem ảnh phần 5 |
| 30–40 | kiểm file, commit, push | | | | gộp log, `merge_review.py` |
