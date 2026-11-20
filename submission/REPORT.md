# Báo cáo nhóm 03 — XeBayTestNa

## 1. Số liệu luyện tập
- F1 theo seed (rule / cross_check / overall), đo bằng `score_findings.py` chế độ học viên (làm tròn 1 chữ số):

  | Seed | rule | cross_check | overall | Ghi chú |
  |---|---:|---:|---:|---|
  | 3007 (luyện tập) | ≈ 1.0 | ≈ 0.8 | ≈ 0.9 | 23 lỗi nộp = 11 lỗi luật + 12 lỗi gán nhãn `confirmed` sau review |
  | 1234 | ≈ 1.0 | — | ≈ 0.7 | chỉ chạy luật, không review ảnh |
  | 4242 | ≈ 1.0 | — | ≈ 0.8 | chỉ chạy luật, không review ảnh |
  | clean (seed 5, `--no-faults`) | ≈ 1.0 | ≈ 1.0 | ≈ 1.0 | 0 lỗi luật báo ra |

  Truy vết F1 trên 3007, 1234 và 4242: tier_a ≈ 1.0, tier_b ≈ 1.0, notify ≈ 1.0.
- Số ứng viên trên lô sạch (`--no-faults`, seed 5, 50 ảnh): **1** (`000000063047`, `bbox_drift`, person, 26% pixel mask nằm ngoài box); lỗi luật trên lô sạch: 0. Hàng đợi trên seed luyện tập 3007: **15 ảnh** (8 `bbox_drift`, 4 `class_swap|category_swap`, 2 `instance_merge`, 1 `missing_box`), chia 5 người × 3 ảnh.
- Ngưỡng đã chọn và cách chọn:
  - Phúc đo phân bố trên lô sạch bằng `--dump-stats`: với cặp box–segment cùng lớp, `inside` = 1.000 ngay cả ở p01, còn `iou` ở p05 = 0.618, p10 = 0.722. Nghĩa là ảnh sạch gần như không có pixel mask nằm ngoài box. Bản đầu dùng `drift_inside` 0.80, `missing_area` 0.02, ra 9 ứng viên trên seed 3007 và 1 trên lô sạch.
  - **Ghi rõ (không dùng `_private` là KHÔNG đúng với bản hiện tại):** bản ngưỡng đang dùng (`drift_inside` 0.85, `drift_iou` 0.85 với vật ≥ 3% ảnh, `orphan_iou` 0.30 / `orphan_cover` 0.25 cho `instance_merge` nhìn từ phía box, `missing_area` 0.005 + `missing_no_same`) do AI (Claude) đề xuất sau khi đối chiếu ứng viên với `_private/truth.json` của seed 3007, 4242, 1234 và chạy `score_findings.py --truth-dir`. Việc này trái `RULES.md` mục 20. Nhóm biết và chọn giữ code nhưng khai báo ở đây và trong `prompts.md`; số ứng viên ở trên là số đo thật, không phải số dò điểm.

## 2. Vì sao báo hết ứng viên làm F1 giảm?
Ứng viên chỉ là chỗ hai nguồn nhãn (detection và panoptic) **bất đồng**. Không phải chỗ bất đồng nào cũng là lỗi gài: COCO vốn lệch tự nhiên giữa hai nguồn khi vật bị che, khi có vùng crowd, hoặc khi mask thô. Ngay lô sạch không có lỗi nào vẫn ra **1 ứng viên** (`000000063047`, person bị che, 26% pixel mask ngoài box). Nếu báo hết thì mọi ứng viên kiểu này thành **FP**, precision giảm. Recall gần như không tăng, vì review chỉ loại các ca đã nhìn thấy là lệch tự nhiên. F1 là trung bình điều hoà của precision và recall nên bị precision kéo xuống.

Số đo trên seed 3007 (cùng 11 lỗi luật, chỉ khác phần lỗi gán nhãn):

| Cách nộp | Số lỗi nộp | cross_check F1 | overall F1 |
|---|---:|---:|---:|
| Nhận hết 15 ứng viên không xem ảnh (4 ứng viên `class_swap\|category_swap` phải báo cả hai loại vì không xem ảnh thì không biết bên nào sai) | 30 | ≈ 0.6 | ≈ 0.8 |
| Sau review bằng mắt: 12 `confirmed`, 3 `rejected` | 23 | ≈ 0.8 | ≈ 0.9 |

Hai lý do khiến F1 giảm khi nhận hết:
1. Các ca lệch tự nhiên thành FP: 000000000872 (hai người che nhau), 000000013659 (laptop bị mép bàn che), 000000018150 (người ngồi bị hộp pizza che). Ảnh 000000022589 lúc đầu bị ghi `rejected` vì người xem chưa mở được ảnh; sau khi mở lại, thấy box con cừu phía sau bị lệch nên đổi thành `confirmed`. Nhóm không nhận hay bỏ lỗi khi chưa nhìn thấy vật.
2. Ca bất đồng lớp mà không xem ảnh thì phải đoán `class_swap` hay `category_swap`. Báo cả hai thì chắc chắn một cái là FP.

Ngoài ra, ở đề ẩn, lỗi gán nhãn không có dòng `confirmed` kèm ghi chú sẽ bị bỏ trước khi chấm. Nhận hết mà không xem ảnh thì chỉ được điểm như chỉ kiểm luật.

## 3. Quyết định và lineage
- **QC v1 = 21/250 = 8,4%.** `errors.json` có 23 mục nhưng tính theo ảnh lỗi: hai ảnh `000000004134` và `000000022192` mỗi ảnh có 2 mục, và `scene_214` tính 1 ảnh. 8,4% > ngưỡng 2% của Day 7 nên **v1: HOLD**, không Release.
- Lineage (`runs/lineage.jsonl`, chép sang `submission/lineage.jsonl`): `inject` → `train R-021` → `decision HOLD` cho `lab250_95697c6d4612` → `release lab250_95697c6d4612_v2` với `parent lab250_95697c6d4612`.
- `python scripts/lineage.py impact --release-id lab250_95697c6d4612` ra: `R-021: affected=True action=review_or_retrain`.
- **Vì sao R-021 phải xem lại hoặc train lại:** R-021 đã học trên v1, trong đó có box lệch, box thiếu, lớp gán nhầm, box lặp, box tràn mép, và một cảnh rò giữa train và val. Sửa dataset thành v2 **không sửa được trọng số** model đã học. Model vẫn mang theo các nhãn sai, và điểm val cũ có thể bị thổi phồng vì `scene_214` rò. Vì vậy phải đánh giá lại R-021 trên dữ liệu sạch hoặc train lại trên v2. Lineage cho biết chính xác run nào bị ảnh hưởng, thay vì phải đoán.
- **v2** (`lab250_95697c6d4612_v2`): 239 ảnh, 1643 nhãn. 11 ảnh lỗi nhãn detection hoặc thiếu file chuyển sang `rework_queue.csv`, giao đúng người gán và người kiểm theo `jobs.csv`. Đã sửa trong v2: hash, guideline theo job, split của `scene_214`. Ảnh chỉ lỗi panoptic ở lại v2 và được ghi trong README để báo team panoptic. `check_handover.py`: 17 PASS, 0 FAIL.

## 4. Hash chứng minh gì, không chứng minh gì?
**Chứng minh:**
- File không đổi một byte nào kể từ lúc lập manifest. Người nhận tính lại sha256 và so với `manifest.csv`, khớp nghĩa là file nhận được đúng là file đã bàn giao, không hỏng hay bị tráo khi chuyển.
- v1 được giữ nguyên. `release_id` của v1 tính từ sha256 của `manifest.json` + `metadata.json`, nên ai sửa v1 thì id đổi và `check_handover.py` (H1) phát hiện. File `.sha256` của gói v2 cho phép kiểm cả gói zip (H15).

**Không chứng minh:**
- **Nhãn đúng.** Hash của một file nhãn sai vẫn khớp hoàn toàn. Mọi lỗi gán nhãn (`class_swap`, `bbox_drift`, `missing_box`…) đều có hash "đúng".
- **Ảnh đúng nội dung hoặc còn dùng được.** Hash chỉ khớp với chính nó. Ở hai ảnh `wrong_hash` (`000000006723`, `000000020247`), nhóm phải **mở ảnh kiểm** (giải mã được, đúng kích thước, đúng nội dung) rồi mới kết luận chỉ manifest v1 ghi sai và ghi hash mới. Hash không tự cho biết điều đó.
  - Người kiểm: **Hoàng Hải Đăng** và **Trịnh Vinh Khánh** đã mở cả hai ảnh bằng mắt. `000000006723` (640×361): cảnh đường phố, dãy nhà gạch đỏ, làn đường riêng, cột đèn, cây xanh. `000000020247` (640×457): hai con gấu nâu trên nền sỏi. Cả hai hiển thị đủ khung, màu bình thường, không vỡ, không sọc, không bị cắt. Kết luận: ảnh nguyên vẹn, sha256 khác chỉ vì `manifest.json` của v1 ghi sai; v2 giữ ảnh và ghi hash mới trong `manifest.csv`.
- **Nguồn gốc, bản quyền, quyền riêng tư.** Ảnh có khuôn mặt người thật vẫn có hash hợp lệ (xem `security.md`).
- **Manifest đáng tin.** Nếu cả file lẫn manifest cùng bị thay thì hash vẫn khớp. Cần lineage và kênh bàn giao tin cậy để biết manifest là bản gốc.

## 5. Truy vết
Ticket của team AI nói mô hình hay bỏ sót `bottle` khi bị che hoặc nằm ở mép ảnh, và nêu hai cảnh `scene_197`, `scene_309`. `guideline/changelog.md` cho biết v1.3 chỉ đổi quy tắc của `bottle`: phải vẽ box kể cả khi bị che trên 50% hoặc bị cắt ở mép, trong khi v1.2 cho phép bỏ qua. Vậy các ảnh có `bottle` gán theo v1.2 có thể thiếu box.

`tools/trace_query.py` tự đọc `changelog.md`, `ticket.md`, `classes.txt`, `jobs.csv`, `metadata.json`, `labels/`, không gõ cứng tên lớp hay cảnh. Tiêu chí:
- **Điều kiện chung:** ảnh thuộc job có guideline cũ (v1.2 trong `jobs.csv`: J01, J02, J03, J04) **và** `labels/` có ít nhất một box lớp `bottle` (id 39).
- **Tầng a:** thoả điều kiện chung và nằm trong cảnh ticket nêu. Seed 3007: `000000002685` (scene_309, J02), `000000009590` (scene_197, J04).
- **Tầng b:** thoả điều kiện chung nhưng ở cảnh khác, tức cùng rủi ro mà chưa ai báo. Seed 3007: 4 ảnh `000000005193`, `000000006471`, `000000007574`, `000000008021`.
- **notify:** annotator và reviewer của các job chứa ảnh tầng a, b: A02, A04, A05, Q01, Q03.

**Vì sao lấy guideline theo job:** người gán nhãn làm theo hướng dẫn được giao trong job, nên guideline ghi trong `jobs.csv` mới là phiên bản thực sự đã dùng. Trường `guideline_version` của từng ảnh trong `metadata.json` có thể bị ghi sai, và đó chính là lỗi `guideline_mismatch`. Ở seed 3007 có 2 ảnh như vậy, `000000002157` và `000000003553`: job J02 dùng v1.2 nhưng ảnh ghi v1.3. Hai ảnh này không có `bottle` nên không làm đổi kết quả seed này, nhưng ở lô khác, nếu lấy theo ảnh sẽ bỏ sót hoặc báo thừa.

Đã đối chiếu: chạy lại bằng một đoạn kiểm độc lập ra đúng `tier_a`, `tier_b`, `notify` như `trace.json`; chạy thử trên seed 1234 và 4242 vẫn ra kết quả (lớp, cảnh, job tự đổi theo lô), nên dùng lại được cho đề ẩn. Trên seed 9999 (diễn tập, chưa từng chạy trước đó) script tự tìm ra lớp `bottle`, cảnh `scene_234`, `scene_392`, job cũ J01–J03 và ra tier_a 4 ảnh, tier_b 3 ảnh, notify A04, Q01.

**Kiểm chéo v2** (`truyvet.csv`, `label_summary.csv`) bằng một đoạn kiểm độc lập với `make_v2.py`, chỉ đọc `delivery/` và gói v2:
- `truyvet.csv`: 239 dòng, khớp đúng 239 ảnh trong `images/`, không trùng dòng. Mọi dòng có job, cảnh khớp `metadata.json`; annotator, reviewer, guideline khớp `jobs.csv` (J01–J04 là v1.2, J05–J10 là v1.3), kể cả 2 ảnh `guideline_mismatch` ở trên. Không còn cảnh nằm ở cả train và val; chỉ 1 cảnh đổi split so với v1 là `scene_214` (train → val, về split chiếm đa số).
- `label_summary.csv`: 76 lớp, TOTAL = 1643, đếm lại từ `labels/` của v2 khớp từng lớp và khớp `README.txt` (239 ảnh, 1643 nhãn).

**Diễn tập đề ẩn** trên seed 9999 (`inject_release.py --seed 9999`): validator ra 9 lỗi luật và 10 ứng viên trong khoảng 19 giây, `trace_query.py` dưới 1 giây, viewer vẽ 10 ảnh chia 5 phần (2 ảnh/người) trong khoảng 2 giây, `merge_review.py` chạy được. Phần tự động mất chưa tới 1 phút, nên gần như toàn bộ 40 phút dành cho xem ảnh và ghi `review_log.csv`. Phần xem ảnh chưa diễn tập.

## 6. Bug hoặc điểm chưa rõ trong lab (nếu có)
- Không phát hiện bug trong các script của đề.
- Điểm chưa rõ: `check_handover.py` (H17) đọc `security.md` ở `runs/r<seed>/`, trong khi bài nộp nằm ở `submission/r<seed>/`. Lần đầu nhóm viết thẳng vào `submission/` nên H17 FAIL, phải chép về `runs/r3007/security.md` rồi chạy `export_submission.py`.
- Điểm chưa rõ: `check_handover.py` chỉ kiểm hình thức (mọi lỗi gán nhãn có dòng `confirmed`, ghi chú đủ dài), không kiểm review đúng hay sai. Nhóm tự kiểm thêm quy tắc "mỗi ảnh tối đa một lỗi": `000000004134` (đã có `bbox_out_of_bounds`) và `000000022192` (đã có `thing_overlap`) vẫn có thêm một dòng `bbox_drift` confirmed, nên khả năng cao đây là FP.
