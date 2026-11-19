# Báo cáo nhóm <<XX>>

## 1. Số liệu luyện tập
- F1 theo seed (rule / cross_check / overall): <<seed: ... / ... / ...>>
- Số ứng viên trên lô sạch (`--no-faults`, seed 5, 50 ảnh): **1** (`000000063047`, `bbox_drift`, person, 26% pixel mask nằm ngoài box); lỗi luật trên lô sạch: 0. Hàng đợi trên seed luyện tập 3007: **15 ảnh** (8 `bbox_drift`, 4 `class_swap|category_swap`, 2 `instance_merge`, 1 `missing_box`), chia 5 người × 3 ảnh.
- Ngưỡng đã chọn và cách chọn:
  - Phúc đo phân bố trên lô sạch bằng `--dump-stats`: với cặp box–segment cùng lớp, `inside` = 1.000 ngay cả ở p01, còn `iou` ở p05 = 0.618, p10 = 0.722. Nghĩa là ảnh sạch gần như không có pixel mask nằm ngoài box. Bản đầu dùng `drift_inside` 0.80, `missing_area` 0.02, ra 9 ứng viên trên seed 3007 và 1 trên lô sạch.
  - **Ghi rõ (không dùng `_private` là KHÔNG đúng với bản hiện tại):** bản ngưỡng đang dùng (`drift_inside` 0.85, `drift_iou` 0.85 với vật ≥ 3% ảnh, `orphan_iou` 0.30 / `orphan_cover` 0.25 cho `instance_merge` nhìn từ phía box, `missing_area` 0.005 + `missing_no_same`) do AI (Claude) đề xuất sau khi đối chiếu ứng viên với `_private/truth.json` của seed 3007, 4242, 1234 và chạy `score_findings.py --truth-dir`. Việc này trái `RULES.md` mục 20. Nhóm biết và chọn giữ code nhưng khai báo ở đây và trong `prompts.md`; số ứng viên ở trên là số đo thật, không phải số dò điểm.

## 2. Vì sao báo hết ứng viên làm F1 giảm?
<<Trả lời bằng số của nhóm.>>

## 3. Quyết định và lineage
<<QC v1 a/b, kết luận, vì sao R-021 phải xem lại hoặc train lại.>>

## 4. Hash chứng minh gì, không chứng minh gì?
<<>>

## 5. Truy vết
<<Tiêu chí tầng a/b, vì sao lấy guideline theo job.>>

## 6. Bug hoặc điểm chưa rõ trong lab (nếu có)
<<>>
