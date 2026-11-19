# Bảo mật khi làm việc

> Trả lời gắn với lô bạn vừa bàn giao, không chép slide. Mỗi mục vài câu.

## 1. Ca USB: hết giờ, muốn chép lô về nhà làm tiếp
```
Lô chứa ảnh người thật và metadata nội bộ của nhóm, nên không được chép ra usb, gửi qua email cá nhân hay nhò người khác làm hộ.

Hết giờ, ghi rõ công việc còn rang dở trong REPORT.md.
```

## 2. Năm việc: được hay không
```
Được phép mở job được giao trên máy công ty nhằm đảm bảo dữ liệu không bị lọt ra ngoài.

Không chụp màn hình gửi người quen do dữ liệu chứa ảnh có người thật và metadata nội bộ

Không chép lô ra USB, dữ liệu rời khỏi khu vực nội bộ, khó kiểm soát.

Không dán nhãn thật lên chatbot, việc này là đưa dữ liệu nội bộ ra dịch vụ bên ngoài.

Không đưa tài khoản CVAT cho đồng nghiệp, do chia sẻ tài khoản làm mất truy vết ai đã sửa nhãn
```
## 3. Ca khuôn mặt: thấy mặt người rõ trong lô, guideline yêu cầu làm mờ
```
Khi thấy khuôn mặt người nhìn rõ trong ảnh 000000025096.jpg, nhóm đặt trạng thái lô là Hold, ghi lại tên ảnh và vị trí trong lô, rồi báo người phụ trách. Nhóm không tự làm mờ hay xoá ảnh vì hai lý do: làm mờ thay đổi file làm sai sha256 trong manifest và phá vỡ truy vết; xoá ảnh làm mất bằng chứng và không đúng quy trình bàn giao.
```