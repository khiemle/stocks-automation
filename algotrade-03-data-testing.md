# Algotrade Knowledge Hub - Articles 26-36
## Extracted from hub.algotrade.vn

---

# NHÓM III: DỮ LIỆU (DATA) - Articles 26-30

---

## 26. Dữ liệu chuẩn trong giao dịch thuật toán
**URL:** https://hub.algotrade.vn/knowledge-hub/du-lieu-chuan-trong-giao-dich-thuat-toan/

### Dữ liệu thị trường
Nhóm dữ liệu thị trường bao gồm các thông tin cơ bản sau:
- Mã chứng khoán
- Thời gian khớp lệnh
- Giá khớp lệnh
- Khối lượng khớp lệnh
- Giá chờ mua 1, 2, 3 (10 bước giá cho HNX và UPCOM)
- Khối lượng chờ mua 1, 2, 3 (10 bước giá cho HNX và UPCOM)
- Giá chờ bán 1, 2, 3 (10 bước giá cho HNX và UPCOM)
- Khối lượng chờ bán 1, 2, 3 (10 bước giá cho HNX và UPCOM)

Từ nhóm dữ liệu này, có thể áp dụng hầu hết các chiến lược phân tích kỹ thuật hoặc đồ thị OHLC (mở-cao-thấp-đóng). Đây cũng là nhóm dữ liệu cơ bản và phổ biến nhất được bán theo các gói dữ liệu tại Việt Nam.

Dữ liệu giao dịch còn được phân thành nhóm nhỏ tùy theo tính chất giao dịch bao gồm: dữ liệu giao dịch cổ đông nội bộ, dữ liệu giao dịch khối ngoại, và dữ liệu giao dịch thỏa thuận.

### Dữ liệu báo cáo tài chính
Nhóm dữ liệu này bao gồm:
- Báo cáo kết quả kinh doanh
- Bảng cân đối kế toán
- Báo cáo lưu chuyển tiền tệ trực tiếp hoặc gián tiếp

### Dữ liệu cổ tức - ESOP
Chính sách phân phối lợi nhuận công ty cùng chương trình ESOP tác động không nhỏ đến tâm lý nhà đầu tư trong dài hạn.

### Dữ liệu vĩ mô
Dữ liệu lạm phát, lãi suất, tăng trưởng kinh tế, xuất nhập khẩu, tỷ giá, đơn đặt hàng, cung tiền, giải ngân đầu tư công là các dữ liệu vĩ mô quan trọng.

### Dữ liệu hàng hóa
Mỗi ngành và doanh nghiệp cụ thể sẽ có liên quan mật thiết đến giá hàng hóa đầu vào và giá hàng hóa đầu ra. Một số giá hàng hóa phổ biến: dầu, vàng, đậu nành, cà phê, thịt.

### Dữ liệu chỉ số (Index)
Một cổ phiếu riêng lẻ hoặc một ngành cụ thể thường có sự tương quan nhất định với chỉ số chung của thị trường cũng như các chỉ số đại diện trên thế giới.

---

## 27. Hướng dẫn làm sạch dữ liệu
**URL:** https://hub.algotrade.vn/knowledge-hub/huong-dan-lam-sach-du-lieu/

Dữ liệu sạch, chính xác, đầy đủ là nền tảng căn bản của hệ thống giao dịch thuật toán. Dữ liệu quá khứ không chính xác sẽ ảnh hưởng đến quá trình đánh giá hiệu quả thuật toán.

### Các lỗi dữ liệu thường gặp
- Lỗi lập trình khi thu thập dữ liệu
- Lỗi mất dữ liệu một phần
- Lỗi nguồn dữ liệu gốc
- Lỗi nhập liệu thủ công
- Trường dữ liệu rỗng
- Sai lệch về thời gian
- Điều chỉnh dữ liệu quá khứ

Tại Việt Nam, lỗi dữ liệu ngoài phạm vi giá và khối lượng xuất hiện với tần suất cao.

### Hướng dẫn làm sạch dữ liệu

**Chuẩn hóa dữ liệu:**
- Định nghĩa chuẩn dữ liệu
- Chuẩn hóa dữ liệu
- Xác định nguồn dữ liệu cơ sở (vd: HNX là nguồn dữ liệu cơ sở cho thị trường phái sinh VN)

**Kiểm định dữ liệu:**
- Xác định dữ liệu thiếu
- Xác định dữ liệu trùng
- Xác định dữ liệu bất thường
- Xác định dữ liệu không hợp lệ

---

## 28. Quản lý dữ liệu trong giao dịch thuật toán
**URL:** https://hub.algotrade.vn/knowledge-hub/quan-ly-du-lieu-trong-giao-dich-thuat-toan/

### Hai nhóm dữ liệu trong giao dịch thuật toán
- **Dữ liệu giao dịch đầu vào:** dữ liệu thị trường, dữ liệu tài chính, dữ liệu hàng hóa, v.v.
- **Dữ liệu giao dịch đầu ra:** dữ liệu được sinh ra khi hệ thống giao dịch thuật toán vận hành (tín hiệu mua bán, thông tin đặt lệnh).

### Hai tiêu chí quan trọng khi lựa chọn nguồn thu thập dữ liệu

**Độ trễ:** Khoảng thời gian sai biệt giữa thời điểm dữ liệu được tạo ra và thời điểm thuật toán nhận được thông tin đó. Độ trễ là khía cạnh then chốt của dữ liệu giao dịch theo thời gian thực.

**Độ hoàn chỉnh (độ phủ):** Tỷ lệ dữ liệu ghi nhận được từ một nguồn dữ liệu so với dữ liệu thực tế. Ví dụ: 336/360 ~ 93.33%.

### Lưu trữ và quản lý dữ liệu
- **Đưa ra khái niệm đúng:** Phải đưa ra khái niệm chuẩn cho những gì cần lưu trữ (giá, lệnh, tín hiệu, khớp lệnh, v.v.)
- **Lựa chọn công nghệ:** Công cụ phù hợp và kỹ năng sử dụng thuần thục công nghệ quan trọng hơn việc chọn công nghệ nào.
- **Quản lý kho lưu trữ dữ liệu:**
  - Kho lưu trữ tạm thời (cho giao dịch trong ngày): Redis, in-memory database
  - Cơ sở dữ liệu (cho dữ liệu lịch sử): Postgres, MySQL, ELK (Elastic Search, Logstash, Kibana)

---

## 29. API giao dịch chứng khoán tại thị trường Việt Nam
**URL:** https://hub.algotrade.vn/knowledge-hub/api-tren-thi-truong-chung-khoan-viet-nam/

### API là gì
Giao diện lập trình ứng dụng (API) là một tập hợp các định nghĩa và giao thức cho phép hai ứng dụng phần mềm giao tiếp với nhau. Ở Việt Nam thực thi quy trình này đạt tần suất xấp xỉ 02 giây.

### Phân loại API
- REST API: chỉ trả lại dữ liệu khi có yêu cầu
- FIX API: trả dữ liệu ngay lập tức khi có thay đổi
- RPC API: trả dữ liệu ngay lập tức khi có thay đổi

### API giao dịch chứng khoán hiện có trên thị trường Việt Nam
- BSC: đơn vị tiên phong trong việc cung cấp API mở
- DNSE: tập trung chuyên sâu trong việc hỗ trợ giao dịch thuật toán thông qua API cũng như phần mềm AmiBroker
- SSI: vừa ra mắt dịch vụ cung cấp API

### Nhà giao dịch nên lựa chọn API nào
- SSI, BSC: phù hợp với nhà giao dịch có nhu cầu làm quen với giao dịch thuật toán và yêu cầu sự ổn định
- DNSE: phù hợp với nhà giao dịch khối lượng lớn

---

## 30. Quy trình tìm kiếm nguồn dữ liệu nhanh nhất
**URL:** https://hub.algotrade.vn/knowledge-hub/quy-trinh-tim-kiem-nguon-du-lieu-nhanh-nhat-tren-thi-truong-chung-khoan-viet-nam/

### Tại sao càng nhanh, càng hiệu quả
Đối với một số chiến lược giao dịch (tạo lập thị trường, lướt sóng siêu ngắn, kinh doanh chênh lệch giá), nguồn dữ liệu nhanh nhất đồng nghĩa với rất nhiều lợi nhuận.

### Nguồn dữ liệu hiện có trên thị trường chứng khoán Việt Nam
Có bốn nhóm cung cấp dữ liệu:
- Bảng giá của công ty chứng khoán (ít nhất 50 nguồn)
- Trang tin tức (Cafef, Stockbiz, v.v.)
- Dịch vụ cung cấp dữ liệu (Fialda, Fireant, Cophieu68)
- API

### Nhóm dữ liệu nào nhanh nhất
- API - nhóm tốt nhất
- Dịch vụ cung cấp dữ liệu - tốt
- Bảng giá của công ty chứng khoán - trung bình
- Trang tin tức - chậm

### Phương pháp xác nhận nguồn dữ liệu nhanh nhất
Thu thập tất cả các FIX API và RPC API sẵn có, sau đó sử dụng một thuật toán đơn giản để đếm số lần mỗi API "nhanh nhất". API có điểm cuối cùng cao nhất là nguồn dữ liệu nhanh nhất.

Tại ALGOTRADE, điểm số hàng ngày được sử dụng để xác định nguồn dữ liệu nhanh nhất hiện tại, nguồn dữ liệu này sẽ tự động được sử dụng làm nguồn dữ liệu chính vào ngày giao dịch tiếp theo.

---

# NHÓM IV: KIỂM THỬ DỮ LIỆU QUÁ KHỨ (BACKTESTING) - Articles 31-33

---

## 31. Nền tảng triết học giai đoạn kiểm thử
**URL:** https://hub.algotrade.vn/knowledge-hub/nen-tang-triet-hoc-trong-giai-doan-kiem-thu-du-lieu-qua-khu/

Năm triết lý ứng dụng trong giai đoạn kiểm thử:

### 1. Kết quả kiểm thử dữ liệu quá khứ luôn luôn có thể tối ưu hóa để trở nên hoàn hảo
Bất kỳ thuật toán nào cũng có thể trở thành chén thánh với sự kết hợp vừa đúng của các tổ hợp tham số trong kiểm thử dữ liệu quá khứ.

### 2-5. (Nội dung tiếp theo của bài viết bao gồm các triết lý khác về kiểm thử dữ liệu quá khứ)

---

## 32. Các lỗi nghiêm trọng trong giai đoạn kiểm thử dữ liệu quá khứ
**URL:** https://hub.algotrade.vn/knowledge-hub/cac-loi-nghiem-trong-trong-giai-doan-kiem-thu-du-lieu-qua-khu/

Giai đoạn kiểm thử dữ liệu quá khứ có mục tiêu cung cấp cho các nhà giao dịch thuật toán một góc nhìn về tương lai.

### Hiện tượng quá khớp (Overfitting)
Đây là lỗi phổ biến nhất:
- Mua ở mức giá thấp nhất của nến và ngược lại
- Có kiến thức về các sự kiện trong tương lai hoặc sử dụng dữ liệu trong tương lai để đưa ra quyết định hiện tại
- Tìm bộ tham số tốt nhất

### Không bao gồm chi phí giao dịch
Chi phí giao dịch trên thị trường thật giảm tỷ suất lợi nhuận rất đáng kể. Tại ngày 03/06/2022, tổng chi phí giao dịch phái sinh cả hai chiều tương đương 0,12% giá trị giao dịch. Hiệu suất đầu tư sẽ giảm 30% vào cuối năm chỉ tính theo chi phí giao dịch.

### (Các lỗi nghiêm trọng khác được trình bày trong bài viết gốc)

---

## 33. Mô-đun kiểm thử dữ liệu quá khứ
**URL:** https://hub.algotrade.vn/knowledge-hub/loi-ich-va-huong-phat-trien-mo-dun-kiem-thu-du-lieu-qua-khu/

Kiểm thử dữ liệu quá khứ là tính năng cơ bản của các phần mềm hỗ trợ bên thứ ba như AmiBroker, TradingView và MetaTrader.

### Lợi ích của mô-đun kiểm thử dữ liệu quá khứ
- Chuẩn hóa đầu ra của giai đoạn kiểm thử
- Lập trình một lần duy nhất nhưng có thể sử dụng đồng thời cho kiểm thử và giao dịch môi trường thật
- Hạn chế lỗi xảy ra do thay đổi môi trường kiểm thử

### Hướng phát triển mô-đun kiểm thử dữ liệu quá khứ
Mô-đun kiểm thử được chia thành ba phần:

**1. Giả lập công ty chứng khoán:** Thành lập một công ty chứng khoán giả lập nhận lệnh, khớp lệnh hoặc hủy lệnh của thuật toán cần kiểm thử.

**2. Lập trình thuật toán:** Cùng một đoạn mã lập trình có thể ứng dụng trong mọi công đoạn: kiểm thử dữ liệu quá khứ, kiểm thử dữ liệu tương lai và vận hành trên môi trường thật.

**3. Báo cáo:** Các thông số cơ bản cần có:
- Đường tổng tài sản theo thời gian
- Lợi nhuận
- Maximum drawdown
- Tỷ lệ Sharpe
- Tỷ lệ số lần mở vị thế có lợi nhuận/thua lỗ
- Giá trị kỳ vọng khi có lợi nhuận
- Giá trị kỳ vọng khi thua lỗ
- Chuỗi lợi nhuận dài nhất
- Chuỗi thua lỗ dài nhất
- Thống kê drawdown

### Hướng triển khai giả lập công ty chứng khoán
- Xây dựng công ty chứng khoán giả lập có thể nhận lệnh, hủy lệnh, trả kết quả khớp lệnh và tình trạng tài khoản thông qua API
- Xác định một lệnh bất kỳ có khớp không và khớp bao nhiêu
- Lưu tất cả thông tin vào cơ sở dữ liệu

Lưu ý tại thị trường Việt Nam: khối lượng và dữ liệu khớp không quan sát được là điểm cần lưu ý.

---

# NHÓM V: TỐI ƯU HÓA (OPTIMIZATION) - Articles 34-36

---

## 34. Tối ưu thuật toán giao dịch
**URL:** https://hub.algotrade.vn/knowledge-hub/toi-uu-thuat-toan-giao-dich/

Để sẵn sàng giao dịch trong môi trường thật, một thuật toán giao dịch phải có nền tảng lý luận.

Quá trình tối ưu hóa bắt đầu bằng việc đưa ra một giả thuyết dưới dạng một thuật toán sơ khởi. Thuật toán sơ khởi này được kiểm tra và tối ưu trên một khoảng dữ liệu quá khứ đủ dài (khoảng dữ liệu trong mẫu).

Yêu cầu cho thuật toán tinh chỉnh tối ưu:
- Tốt trong mẫu
- Có hiệu quả tương đương lúc kiểm nghiệm trong mẫu khi đưa vào vận hành thực tế

### Tìm thuật toán tinh chỉnh tối ưu

**1. Thêm luật biến thiên:** Thay vì chọn giá trị tham số cố định, nên tạo ra luật là hàm biến thiên theo chỉ số thống kê phản ánh tình trạng thị trường. Ví dụ: độ dao động của VN30.

**2. Tìm kiếm trên không gian tham số:** 
- Tìm kiếm trên lưới
- Tìm kiếm tham số ưu tiên
- Thuật toán tìm kiếm nâng cao

Ví dụ: thuật toán hồi quy dự đoán giá đóng cửa VN30F1M, với N (số ngày) và Alpha (ngưỡng xác định mở vị thế). 25 giá trị x 7 giá trị = 175 bộ tham số.

---

## 35. Các kỹ thuật tránh hiện tượng quá khớp
**URL:** https://hub.algotrade.vn/knowledge-hub/cac-ky-thuat-tranh-hien-tuong-qua-khop/

### Hiện tượng quá khớp là gì
Trong thống kê, hiện tượng quá khớp là kết quả của phép phân tích quá chính xác trên một tập dữ liệu cụ thể, qua đó thất bại khi so khớp với tập dữ liệu khác hoặc dự đoán tương lai.

Đối với giao dịch thuật toán, hiện tượng quá khớp xảy ra vì một thuật toán tinh chỉnh sử dụng các luật và giá trị tham số làm tăng hiệu suất giai đoạn kiểm thử trong mẫu chỉ do ngẫu nhiên.

### (Các kỹ thuật tránh hiện tượng quá khớp được trình bày chi tiết trong bài viết gốc, bao gồm các phương pháp chia tập dữ liệu, cross-validation, v.v.)

---

## 36. Kiểm định thuật toán sau tối ưu hóa
**URL:** https://hub.algotrade.vn/knowledge-hub/kiem-dinh-thuat-toan-sau-toi-uu-hoa/

Tại một thời điểm, một thuật toán giao dịch được cho là có giá trị nếu còn khả năng sinh lời như dự định khi được áp dụng trên thị trường mục tiêu trong tương lai.

### Kiểm định thuật toán trên tập dữ liệu ngoài mẫu
Cần khả năng đánh giá tỉ mỉ hiệu quả thuật toán trên tập dữ liệu ngoài mẫu và tìm kiếm, giải thích những điểm không tương đồng khi so sánh với hiệu quả của thuật toán trên tập dữ liệu trong mẫu.

Hiệu quả được đánh giá bằng cách phân tích toàn diện hồ sơ giao dịch bao gồm:
- Đường tổng tài sản theo thời gian
- Thống kê về giao dịch mua, giao dịch bán, giao dịch thắng, giao dịch thua
- Những lần tổng tài sản giảm
- Maximum drawdown (MDD) - đánh giá rủi ro
- Lợi nhuận hàng tháng - đánh giá phần thưởng

Một thuật toán không có giá trị nếu hồ sơ giao dịch trên tập dữ liệu ngoài mẫu xuất hiện những kết quả bất thường:
- Thuật toán liên tiếp thua trong thời gian dài
- Có quá nhiều đợt giảm mạnh
- Độ lệch chuẩn của lợi nhuận hàng ngày tăng nhiều
- Phần thưởng và rủi ro không tương đồng với hồ sơ trong mẫu

Cách phổ biến để phát hiện sự không tương đồng: dùng MDD như là tín hiệu. Thuật toán sẽ được cho là không còn giá trị khi trải qua một đợt giảm mạnh vượt qua một bội số được định nghĩa trước của MDD trên tập dữ liệu trong mẫu.

---

*Extracted from hub.algotrade.vn on 2026-04-17*
