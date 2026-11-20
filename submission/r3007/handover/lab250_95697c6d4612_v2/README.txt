Release: lab250_95697c6d4612_v2
Parent: lab250_95697c6d4612
Số ảnh: 239
Số nhãn: 1643
Guideline: v1.2 (J01-J04), v1.3 (J05-J10)
QC v1: 21/250 = 8,4%
Kết luận v1: Hold — 8.4% ảnh lỗi > ngưỡng 2%, không Release; training run dùng v1 cần xem lại/train lại
Kết luận v2: Release — tách 11 ảnh lỗi nhãn detection/thiếu file sang rework_queue; sửa 2 hash, 2 guideline theo job, 1 cảnh rò split; còn 6 ảnh lỗi panoptic (nhãn detection đúng) chờ team panoptic
Ghi chú: split: scene_214 -> val (cả cảnh về split chiếm đa số, ghi trong truyvet.csv) | hash: 000000006723, 000000020247 đã mở ảnh kiểm (giải mã được, đúng kích thước), ảnh nguyên vẹn, chỉ manifest v1 sai, manifest.csv ghi hash mới | guideline: lấy theo job trong jobs.csv (sửa 000000002157, 000000003553) | rework: A02/Q01: 000000001818, 000000004134; A05/Q03: 000000005529, 000000007511; A04/Q01: 000000007795, 000000009483; A04/Q02: 000000013546, 000000013923; A03/Q01: 000000022192, 000000022589; A05/Q01: 000000023272 | panoptic (ở lại v2, báo team panoptic): 000000006763 (instance_merge), 000000013291 (instance_merge), 000000013659 (thing_overlap), 000000019742 (category_swap), 000000022192 (thing_overlap), 000000023781 (category_swap)
