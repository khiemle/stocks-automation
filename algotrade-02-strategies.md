# Algotrade Knowledge Hub - Tổng hợp Chiến lược Giao dịch Thuật toán

> Tổng hợp từ các bài viết trên hub.algotrade.vn. Nội dung được tổng hợp và diễn giải bằng lời riêng, kết hợp thuật ngữ tiếng Việt và tiếng Anh.

---

## Bài 05: Giao dịch Bán tự động (Semi-Automated Trading)

**Nguồn:** [hub.algotrade.vn/knowledge-hub/giao-dich-ban-tu-dong](https://hub.algotrade.vn/knowledge-hub/giao-dich-ban-tu-dong/)

### Khái niệm cốt lõi

Giao dịch bán tự động là mô hình kết hợp giữa con người và máy tính trong quá trình ra quyết định giao dịch. Con người vẫn giữ vai trò chủ đạo -- đặc biệt trong việc xử lý các loại thông tin định tính hoặc dữ liệu phi cấu trúc mà máy chưa xử lý được -- trong khi máy tính hỗ trợ tăng tốc độ phản hồi, đảm bảo tính ổn định và nâng cao độ chính xác.

### Ba hình thức bán tự động phổ biến

1. **Bộ lọc cổ phiếu (Stock Filtering)**
   - Độ phức tạp: rất đơn giản
   - Đây là ứng dụng phổ biến nhất của giao dịch bán tự động. Nhà đầu tư thiết lập các tiêu chí lọc (ví dụ: P/E < 15, tăng trưởng doanh thu > 20%) và hệ thống tự động lọc ra danh sách cổ phiếu phù hợp từ hàng trăm mã trên sàn.
   - Ứng dụng thực tế tại Việt Nam: các công cụ lọc cổ phiếu trên SSI iBoard, VNDirect, hoặc TradingView với bộ lọc tùy chỉnh.

2. **Đặt lệnh theo lịch trình (Scheduled Position Opening/Closing)**
   - Độ phức tạp: đơn giản
   - Nhà giao dịch đã xác định trước hành động cần thực hiện khi một số điều kiện thị trường được thỏa mãn. Thay vì phải liên tục theo dõi màn hình để chờ tín hiệu, hệ thống tự động giám sát và thực thi khi điều kiện xuất hiện.
   - Ví dụ: đặt lệnh mua tự động khi giá VN30F1M chạm mức hỗ trợ 1,200 điểm trong phiên giao dịch sáng.

3. **Gợi ý giao dịch (Trading Suggestions)**
   - Hệ thống có khả năng phân tích và đưa ra khuyến nghị giao dịch, nhưng bắt buộc phải có xác nhận của con người trước khi đặt lệnh.
   - Đây là mô hình "human-in-the-loop" -- giúp giảm rủi ro từ những quyết định hoàn toàn tự động trong khi vẫn tận dụng sức mạnh tính toán.

### Nhận xét về ứng dụng tại Việt Nam

Mô hình bán tự động phù hợp với đa số nhà đầu tư cá nhân tại Việt Nam vì: (a) chưa cần đầu tư lớn vào hạ tầng kỹ thuật, (b) cho phép nhà đầu tư học dần về algo trading trước khi chuyển sang tự động hóa hoàn toàn, và (c) phù hợp với đặc điểm thị trường Việt Nam nơi nhiều thông tin định tính (tin tức nội bộ, chính sách) vẫn cần sự đánh giá của con người.

---

## Bài 07: Phân biệt hai nhóm thuật toán (Distinguishing Two Algorithm Groups)

**Nguồn:** [hub.algotrade.vn/knowledge-hub/distinguish-two-algorithmic-trading-categories](https://hub.algotrade.vn/knowledge-hub/distinguish-two-algorithmic-trading-categories/)

### Hai nhóm thuật toán chính

Algotrade phân chia thuật toán giao dịch thành hai nhóm lớn với mục đích sử dụng khác nhau hoàn toàn:

#### Nhóm 1: Thuật toán tìm kiếm Alpha (Alpha-Seeking Algorithms)

- Mục tiêu: Tìm kiếm lợi nhuận vượt trội so với thị trường (alpha).
- Đây là nhóm thuật toán được nhiều người quan tâm nhất, nhưng trên thực tế lại khó phát triển và vận hành ổn định.
- Trong hàng ngàn lựa chọn và một thị trường liên tục biến động, việc tìm được thuật toán thực sự sinh lời bền vững là rất thách thức.
- Quy mô ứng dụng thực tế còn nhỏ, mặc dù nhận được nhiều sự chú ý từ cộng đồng.

#### Nhóm 2: Thuật toán thực thi giao dịch (Execution Algorithms)

- Mục tiêu: Tối ưu hóa quá trình thực hiện lệnh giao dịch -- giảm chi phí, giảm tác động thị trường (market impact), và đảm bảo tốc độ.
- Ít được biết đến hơn nhưng lại dễ triển khai hơn và ổn định hơn.
- Được sử dụng rộng rãi bởi các quỹ đầu tư và nhà đầu tư chuyên nghiệp với khối lượng giao dịch lớn.
- Các thuật toán tiêu biểu: VWAP, TWAP, POV (Percentage of Volume).
- Thuật toán thực thi không phải là trò chơi tổng không (zero-sum game) vì nó thực sự giảm chi phí cho tất cả bên tham gia.

### So sánh hai nhóm

| Tiêu chí | Alpha-Seeking | Execution |
|----------|--------------|-----------|
| Mục tiêu | Sinh lời vượt trội | Giảm chi phí thực thi |
| Độ khó phát triển | Cao | Trung bình |
| Tính ổn định | Thấp (phụ thuộc thị trường) | Cao |
| Quy mô sử dụng | Nhỏ | Lớn (institutional) |
| Đối tượng chính | Trader cá nhân, hedge fund | Quỹ đầu tư, tổ chức |

### Ý nghĩa thực tiễn

Nhà đầu tư mới bắt đầu nên xem xét thuật toán thực thi trước vì dễ áp dụng và mang lại giá trị rõ ràng. Thuật toán tìm kiếm alpha đòi hỏi kiến thức sâu về thống kê, tài chính định lượng và khả năng backtest kỹ lưỡng.

---

## Bài 08: Thuật toán Thực thi Tối ưu hóa Chi phí Giao dịch (Execution Algorithms for Cost Optimization)

**Nguồn:** [hub.algotrade.vn/knowledge-hub/chien-luoc-thuc-thi-toi-uu-hoa-chi-phi-giao-dich](https://hub.algotrade.vn/knowledge-hub/chien-luoc-thuc-thi-toi-uu-hoa-chi-phi-giao-dich/)

### Vấn đề cần giải quyết

Khi giao dịch với khối lượng lớn, việc đặt một lệnh duy nhất sẽ tạo ra market impact -- đẩy giá bất lợi và tăng chi phí thực thi. Các thuật toán thực thi được thiết kế để giải quyết vấn đề này bằng cách chia nhỏ lệnh và đưa vào thị trường theo chiến lược cụ thể.

### Ba thuật toán thực thi phổ biến

#### 1. VWAP (Volume-Weighted Average Price)
- **Công thức:** VWAP = Tổng(Giá x Khối lượng) / Tổng(Khối lượng) trong kỳ tính toán.
- **Cơ chế:** Chia khối lượng giao dịch cần thực hiện thành các lệnh nhỏ hơn và đưa vào thị trường theo tỷ lệ khối lượng dự kiến của thị trường tại từng thời điểm.
- **Mục tiêu:** Đạt được giá thực thi trung bình xấp xỉ VWAP của thị trường trong ngày.
- **Ưu điểm:** Phù hợp với cổ phiếu có thanh khoản trung bình đến cao.

#### 2. TWAP (Time-Weighted Average Price)
- **Cơ chế:** Chia đều khối lượng giao dịch theo các khoảng thời gian bằng nhau, không quan tâm đến khối lượng thị trường.
- **Mục tiêu:** Đạt giá trung bình theo thời gian.
- **Ưu điểm:** Đơn giản, dễ triển khai. Phù hợp khi không có dữ liệu khối lượng lịch sử đáng tin cậy.

#### 3. POV (Percentage of Volume)
- **Cơ chế:** Thực hiện lệnh theo một tỷ lệ phần trăm cố định của khối lượng giao dịch thị trường. Khi thị trường giao dịch nhiều hơn, thuật toán giao dịch nhiều hơn và ngược lại.
- **Mục tiêu:** Giới hạn tác động thị trường bằng cách duy trì tỷ lệ tham gia ổn định.
- **Ưu điểm:** Tự động điều chỉnh theo thanh khoản thực tế.

### Các loại chi phí giao dịch được tối ưu

- **Slippage (trượt giá):** Chênh lệch giữa giá mong muốn và giá thực thi thực tế.
- **Market impact:** Tác động của lệnh giao dịch lớn lên giá thị trường.
- **Delay cost (chi phí trễ):** Phát sinh khi có độ trễ từ lúc ra quyết định đến lúc lệnh được thực thi. Hệ thống algo có thể tối ưu xuống dưới 60 mili giây.

### Ứng dụng tại thị trường Việt Nam

Với quy mô tài khoản lớn hoặc giao dịch khối lượng cao trên sàn HOSE/HNX, việc sử dụng VWAP/TWAP/POV có thể giảm đáng kể chi phí trượt giá -- đặc biệt quan trọng với các cổ phiếu có thanh khoản thấp như mid-cap và small-cap Việt Nam.

---

## Bài 10: Chiến lược Momentum / Quán tính giá (Price Momentum Strategy)

**Nguồn:** [hub.algotrade.vn/knowledge-hub/chien-luoc-quan-tinh-gia](https://hub.algotrade.vn/knowledge-hub/chien-luoc-quan-tinh-gia/)

### Nguyên lý cơ bản

Chiến lược quán tính giá dựa trên quan sát rằng những cổ phiếu đã tăng giá mạnh trong quá khứ có xu hướng tiếp tục tăng trong ngắn hạn, và ngược lại với cổ phiếu giảm. Logic là "mua cao, bán cao hơn" -- hoàn toàn trái ngược với phân tích cơ bản truyền thống (mua rẻ, bán đắt).

### Cơ chế hoạt động

- **Mua (Long):** Chọn các cổ phiếu có hiệu suất giá tốt nhất trong kỳ vừa qua (ví dụ: top 10% tăng giá trong 6 tháng).
- **Bán (Short):** Chọn các cổ phiếu có hiệu suất giá kém nhất.
- **Kỳ nắm giữ:** Thường từ vài tuần đến vài tháng (khác với day trading).

### Các chỉ báo kỹ thuật hỗ trợ

Dựa trên nội dung Algotrade về các chỉ báo phân tích kỹ thuật:

- **Moving Average Crossover:** Khi đường MA ngắn hạn (5 ngày) cắt lên trên MA dài hạn (20 hoặc 60 ngày) = tín hiệu mua. Cắt xuống dưới = tín hiệu bán.
- **RSI (Relative Strength Index):** Đo sức mạnh xu hướng. RSI > 70 có thể chỉ báo overbought nhưng với momentum trader, đây là tín hiệu xu hướng mạnh.
- **MACD:** Kết hợp với moving average để xác nhận xu hướng và timing.

### Rủi ro chính

- **Giả định cơ bản có thể sai:** Chiến lược giả định xu hướng sẽ kéo dài đủ lâu để hoàn thành giao dịch, nhưng thị trường có thể đảo chiều bất ngờ.
- **Whipsaw risk:** Trong thị trường đi ngang (sideways), tín hiệu momentum thường cho kết quả sai.
- **Drawdown lớn:** Khi xu hướng đảo chiều đột ngột (ví dụ: crash), vị thế momentum có thể chịu lỗ nặng.

### Đặc thù thị trường Việt Nam

- Thị trường Việt Nam có tính momentum khá rõ trong các pha tăng/giảm mạnh (ví dụ: 2021-2022).
- Không có cơ chế bán khống (short selling) trên thị trường cơ sở, nên chỉ áp dụng được chiều long. Trên thị trường phái sinh (VN30F), có thể áp dụng cả hai chiều.
- Cần lưu ý thanh khoản và biên độ giá trần/sàn (+-7% trên HOSE) khi thiết kế thuật toán.

---

## Bài 11: Chiến lược Mean Reversion / Hồi quy trung vị

**Nguồn:** [hub.algotrade.vn/knowledge-hub/chien-luoc-dau-tu-dao-nguoc-ve-gia-tri-trung-binh](https://hub.algotrade.vn/knowledge-hub/chien-luoc-dau-tu-dao-nguoc-ve-gia-tri-trung-binh/)

### Nguyên lý cơ bản

Chiến lược hồi quy trung vị dựa trên niềm tin rằng giá chứng khoán về dài hạn sẽ quay trở lại gần giá trị nội tại (intrinsic value) hoặc giá trị trung bình của nó. Khi giá quá thấp so với giá trị nội tại -- mở vị thế mua. Khi giá quá cao -- mở vị thế bán hoặc chốt lời.

Đây là chiến lược đối lập trực tiếp với Momentum: thay vì theo xu hướng, mean reversion đi ngược xu hướng ngắn hạn với kỳ vọng giá sẽ "hồi quy".

### Kỹ năng cốt lõi cần có

Nhà đầu tư theo chiến lược này cần có khả năng ước tính giá trị trung bình hoặc giá trị nội tại một cách đáng tin cậy. Đây là thách thức lớn nhất vì:

- Nhiều yếu tố vĩ mô và vi mô đồng thời tác động lên giá trị nội tại của doanh nghiệp.
- Bất kỳ thay đổi nào về kinh tế vĩ mô, thị trường toàn cầu, chính sách chính phủ, ngành và đối thủ đều có thể tác động đáng kể.
- Các yếu tố này rất khó đo lường và ước tính chính xác.

### Các công cụ thường dùng

- **Bollinger Bands:** Khi giá chạm band dưới = cơ hội mua (giá "quá rẻ" so với trung bình). Chạm band trên = cơ hội bán.
- **Z-Score:** Đo khoảng cách của giá hiện tại so với trung bình tính theo độ lệch chuẩn. Z-score > +2 hoặc < -2 thường được coi là tín hiệu giao dịch.
- **RSI:** RSI < 30 = oversold (cơ hội mua). RSI > 70 = overbought (cơ hội bán).

### Rủi ro lớn nhất

Rủi ro lớn nhất của chiến lược hồi quy trung vị là: sau nhiều năm nghiên cứu, nhà đầu tư có thể vẫn không bao giờ tìm được phương pháp đúng để tính giá trị nội tại. Một cổ phiếu "rẻ" có thể tiếp tục rẻ hơn (value trap), và một cổ phiếu "đắt" có thể tiếp tục tăng vì có yếu tố tăng trưởng mà mô hình không nhận ra.

### Đặc thù thị trường Việt Nam

- Algotrade ghi nhận cơ hội phát triển thuật toán hồi quy trung vị liên quan đến thị trường phái sinh Việt Nam, đặc biệt sau các thay đổi về cách tính giá đáo hạn phái sinh.
- Cơ hội tốt trên thị trường phái sinh nơi basis (chênh lệch giữa giá tương lai và giá hiện tại) có xu hướng hồi quy về 0 trước ngày đáo hạn.

---

## Bài 12: Tổng quan các Chiến lược Giao dịch Thuật toán (Trading Strategy Overview)

**Nguồn:** [hub.algotrade.vn/knowledge-hub/cac-chien-luoc-giao-dich-thuat-toan](https://hub.algotrade.vn/knowledge-hub/cac-chien-luoc-giao-dich-thuat-toan/)

### Bản đồ tổng thể các nhóm chiến lược

Algotrade phân loại các chiến lược giao dịch thuật toán thành các nhóm chính sau:

#### 1. Chiến lược Quán tính giá (Momentum)
- Mua cổ phiếu đang tăng, bán cổ phiếu đang giảm.
- Giả định: xu hướng hiện tại sẽ tiếp tục.

#### 2. Chiến lược Hồi quy trung vị (Mean Reversion)
- Giao dịch ngược xu hướng ngắn hạn.
- Giả định: giá sẽ quay về giá trị trung bình.

#### 3. Chiến lược Trung lập thị trường (Market Neutral)
- Đồng thời mở vị thế mua và bán để trung hòa rủi ro thị trường.
- Giao dịch theo cặp (pairs trading) là dạng phổ biến nhất.

#### 4. Chống lại thống kê (Statistical Arbitrage)
- Mở rộng từ pairs trading, sử dụng mô hình thống kê-toán học với hỗ trợ máy tính.
- Khai thác cơ hội từ biến động giá tương đối bất thường giữa các cổ phiếu.

#### 5. Chênh lệch giá (Arbitrage / Price Spread)
- Tận dụng chênh lệch giá tạm thời của cùng một tài sản trên hai thị trường khác nhau.
- Lợi nhuận thấp nhưng rủi ro cũng rất thấp.

#### 6. Hành động trước khi quỹ tái cân bằng (Front-Running ETF/Index Rebalancing)
- Dự đoán hành động của các quỹ ETF dựa trên bản cáo bạch công khai.
- Giao dịch mô phỏng trước thời điểm tái cân bằng để hưởng lợi.

#### 7. Chiến lược Hướng sự kiện (Event-Driven)
- Khai thác sự thiếu hiệu quả của thị trường xung quanh các sự kiện doanh nghiệp: M&A, tái cơ cấu, mua lại cổ phần, cổ tức bất thường.

#### 8. Đầu tư theo yếu tố / Smart Beta (Factor-Based Investing)
- Xây dựng danh mục đầu tư theo quy trình hệ thống, dựa trên các yếu tố cơ bản: thanh khoản (liquidity), giá trị (value), chất lượng (quality).

#### 9. Giao dịch tần suất cao (High-Frequency Trading - HFT)
- Thực hiện lượng lớn giao dịch trong thời gian cực ngắn (mili giây, micro giây).
- Cần hạ tầng kỹ thuật tốt (co-location, low-latency network).

### Mối quan hệ giữa các chiến lược

Các chiến lược không tồn tại độc lập mà thường được kết hợp. Ví dụ: một thuật toán có thể kết hợp momentum signal để xác định hướng giao dịch và VWAP execution để tối ưu chi phí đặt lệnh. Market neutral có thể được xây dựng từ hai vị thế momentum ngược chiều.

---

## Bài 13: Chiến lược Market Neutral / Trung lập Thị trường

**Nguồn:** [hub.algotrade.vn/knowledge-hub/chien-luoc-trung-lap-thi-truong](https://hub.algotrade.vn/knowledge-hub/chien-luoc-trung-lap-thi-truong/)

### Định nghĩa và đặc điểm

Chiến lược trung lập thị trường là nhóm chiến lược trong đó nhà đầu tư đồng thời mở vị thế mua (long) và bán (short) nhằm triệt tiêu tác động của rủi ro thị trường chung lên danh mục. Hai đặc điểm chính:

1. **Có thể sinh lời bất kể thị trường tăng hay giảm** -- vì lợi nhuận đến từ chênh lệch hiệu suất giữa hai vị thế, không phải từ hướng đi của thị trường.
2. **Cùng lúc mở các vị thế ngược nhau với mức rủi ro thị trường tương đương** -- đảm bảo beta của danh mục gần bằng 0.

### Ví dụ minh họa cụ thể (bối cảnh Việt Nam)

Algotrade đưa ví dụ thực tế: Nhà đầu tư chọn danh mục 5 cổ phiếu thuộc VN30 (gọi là "VN05"): FPT, HPG, TCB, VIC, VPB. Nhà đầu tư đánh giá VN05 sẽ có hiệu suất tốt hơn VN30 Index và quyết định đầu tư 600 triệu đồng theo chiến lược trung lập thị trường:

- **Long 300 triệu:** Mua danh mục VN05
- **Short 300 triệu:** Bán hợp đồng tương lai VN30F (hoặc tương đương)
- **Kết quả:** Lợi nhuận = (Hiệu suất VN05) - (Hiệu suất VN30). Nếu VN05 tăng 10% và VN30 tăng 7%, lợi nhuận = 3% trên tổng vị thế, bất kể thị trường tăng hay giảm.

### Giao dịch theo cặp (Pairs Trading)

- Là dạng đơn giản và phổ biến nhất của market neutral.
- Tìm các cặp cổ phiếu có lịch sử giá tương quan cao (ví dụ: HPG và HSG cùng ngành thép).
- Khi tương quan giá lệch khỏi mức trung bình dài hạn, mua cổ phiếu đang underperform và bán cổ phiếu đang outperform.
- Kỳ vọng sai lệch chỉ là tạm thời và giá sẽ hội tụ trở lại.

### Thách thức tại thị trường Việt Nam

- Không có cơ chế bán khống cổ phiếu trên thị trường cơ sở -- cần sử dụng phái sinh (VN30F) hoặc chứng quyền (covered warrants) để tạo vị thế short.
- Thanh khoản của thị trường phái sinh còn hạn chế, có thể ảnh hưởng đến khả năng thực thi.
- Cần quản lý margin và chi phí vay rất cẩn thận.

---

## Bài 14: Chiến lược Event-Driven / Hướng sự kiện

**Nguồn:** [hub.algotrade.vn/knowledge-hub/cac-chien-luoc-giao-dich-thuat-toan](https://hub.algotrade.vn/knowledge-hub/cac-chien-luoc-giao-dich-thuat-toan/)

### Nguyên lý cơ bản

Chiến lược hướng sự kiện khai thác sự thiếu hiệu quả của thị trường xung quanh các sự kiện doanh nghiệp. Nhà đầu tư nghiên cứu các tình huống xoay quanh sự kiện và đánh giá tác động lên giá cổ phiếu, từ đó xác định cơ hội.

### Các loại sự kiện thường được khai thác

#### 1. Mua bán và Sáp nhập (M&A / Merger Arbitrage)
- Khi thông tin M&A được công bố, giá cổ phiếu mục tiêu thường chưa phản ánh đầy đủ giá đề nghị mua.
- Cơ hội: Mua cổ phiếu mục tiêu khi giá còn thấp hơn giá đề nghị, hưởng chênh lệch khi giao dịch hoàn tất.
- Rủi ro: Giao dịch M&A có thể thất bại.

#### 2. Tái cơ cấu (Restructuring)
- Thông báo tái cơ cấu thường tạo ra biến động giá mạnh.
- Thuật toán có thể phân tích nhanh thông tin và đặt lệnh trước khi thị trường phản ứng hoàn toàn.

#### 3. Mua lại cổ phần (Share Buyback)
- Khi công ty mua lại cổ phiếu của mình, thường tạo áp lực tăng giá.
- Thuật toán giám sát thông báo mua lại và thực thi giao dịch theo.

#### 4. Cổ tức bất thường (Extraordinary Dividends)
- Cổ tức cao bất thường tác động mạnh đến giá cổ phiếu trước và sau ngày GDKHQ.
- Dữ liệu cổ tức (tiền mặt, cổ phiếu, cổ phiếu thưởng) được sử dụng làm input cho thuật toán.

#### 5. Tái cân bằng quỹ chỉ số (ETF/Index Rebalancing)
- Các quỹ ETF phải công khai quy tắc tái cân bằng.
- Nhà đầu tư dự đoán hành động của quỹ và giao dịch trước (front-running).
- Tại Việt Nam, các quỹ như VFMVN30 ETF, SSIAM VNX50 ETF công bố lịch tái cân bằng định kỳ.

### Ứng dụng algo cho event-driven tại Việt Nam

- **Tự động hóa thu thập dữ liệu sự kiện:** Giám sát thông báo từ HOSE, HNX, các công ty chứng khoán.
- **NLP và xử lý tin tức:** Phân tích tự động các thông báo doanh nghiệp để phát hiện sự kiện sớm nhất.
- **Tốc độ thực thi:** Trong event-driven, ai phản ứng nhanh hơn sẽ có lợi thế. Thuật toán có thể đặt lệnh trong vài chục mili giây sau khi sự kiện được công bố.

---

## Bài 15: Chiến lược Market Making / Tạo lập Thị trường

**Nguồn:** [hub.algotrade.vn/knowledge-hub/chien-luoc-tao-lap-thi-truong](https://hub.algotrade.vn/knowledge-hub/chien-luoc-tao-lap-thi-truong/)

### Định nghĩa

Market making là chiến lược đồng thời đặt lệnh mua (bid) và lệnh bán (ask) tại các mức giá tốt nhất, nhằm kiếm lợi nhuận từ chênh lệch giá giữa hai chiều giao dịch (bid-ask spread).

### Cơ chế hoạt động

- Nhà tạo lập thị trường liên tục duy trì lệnh ở cả hai phía của sổ lệnh.
- **Lợi nhuận đến từ:** Giả định chứng khoán sẽ khớp ở cả hai chiều mua và bán. Chênh lệch giữa giá mua và giá bán (spread) chính là lợi nhuận.
- **Rủi ro chính:** Nếu chỉ khớp lệnh một chiều, nhà đầu tư sẽ giữ quá nhiều vị thế ở chiều ngược lại trong khi giá dịch chuyển bất lợi -- dẫn đến thua lỗ lớn.

### Vai trò của Market Maker

- Về bản chất, nhà tạo lập thị trường cung cấp thanh khoản cho thị trường.
- Đổi lại, họ hưởng lợi từ spread.
- Đây là mối quan hệ đôi bên cùng có lợi: thị trường có thanh khoản tốt hơn, nhà đầu tư khác có thể giao dịch dễ dàng hơn.

### Yêu cầu kỹ thuật

- Cần hệ thống đặt lệnh tốc độ cao và ổn định.
- Quản lý tồn kho (inventory management) là yếu tố then chốt -- phải cân bằng vị thế liên tục.
- Cần mô hình định giá thời gian thực để xác định spread hợp lý.

### Đặc thù thị trường Việt Nam

- **Thị trường cơ sở (HOSE/HNX):** Quy định T+1.5 (hiện nay đang chuyển sang T+2) nghĩa là cổ phiếu đã mua chưa thể bán ngay. Để thực hiện market making, nhà đầu tư cần có sẵn vị thế cổ phiếu từ trước để có thể đặt lệnh bán đồng thời với lệnh mua.
- **Thị trường phái sinh:** Với quy định T+0, việc thực hiện market making trên phái sinh (VN30F) đơn giản và khả thi hơn nhiều. Nhà đầu tư có thể mua và bán trong cùng phiên.
- **Thách thức:** Biên độ giá trần/sàn giới hạn lợi nhuận spread. Thanh khoản thị trường phái sinh còn hạn chế so với các thị trường phát triển.

---

## Bài 16: Chiến lược Scalping / Lướt sóng siêu ngắn

**Nguồn:** [hub.algotrade.vn/knowledge-hub/chien-luoc-luot-song-sieu-ngan](https://hub.algotrade.vn/knowledge-hub/chien-luoc-luot-song-sieu-ngan/)

### Định nghĩa

Scalping là chiến lược chuyên biệt tập trung vào khung thời gian siêu ngắn để đóng và mở vị thế, nhằm kiếm những khoản lợi nhuận rất nhỏ trên mỗi giao dịch. "Nghệ thuật tích lũy nhiều khoản lợi nhuận nhỏ trong thời gian ngắn."

### Đặc điểm chính

- **Tần suất giao dịch rất cao:** Có thể hàng trăm đến hàng ngàn lệnh mỗi ngày.
- **Tỷ lệ thắng cao:** Nhà scalper kỳ vọng tỷ lệ giao dịch có lợi nhuận rất cao (thường > 60-70%).
- **Lợi nhuận mỗi giao dịch rất nhỏ:** Chỉ cần vài tick hoặc vài phần trăm.
- **Thời gian giữ vị thế cực ngắn:** Từ vài giây đến vài phút.

### Yêu cầu kỹ thuật nghiêm ngặt

1. **Cổng đặt lệnh ổn định:** Cần có thể xử lý hàng ngàn giao dịch mỗi ngày mà không bị gián đoạn.
2. **Nguồn dữ liệu tốt:** Dữ liệu thời gian thực (real-time tick data) là yếu tố hết sức cần thiết để đưa ra quyết định chính xác.
3. **Độ trễ thấp (Low latency):** Mỗi mili giây đều quan trọng. Hệ thống cần được tối ưu về tốc độ.
4. **Tự động hóa cao:** Giao dịch thủ công không thể đáp ứng được tần suất và tốc độ yêu cầu.

### Yếu tố chi phí -- thách thức lớn nhất

- Với lợi nhuận siêu nhỏ trên mỗi giao dịch, chi phí giao dịch (phí, thuế) trở thành yếu tố quyết định.
- Nếu chi phí mỗi giao dịch cao hơn lợi nhuận kỳ vọng, chiến lược sẽ thua lỗ.
- **Phí giao dịch tại Việt Nam:** Phí môi giới (0.15-0.35%), thuế bán (0.1%) -- tổng chi phí có thể lên đến 0.25-0.45% mỗi chiều. Đây là rào cản lớn cho scalping trên thị trường cơ sở.
- **Phái sinh có lợi thế:** Phí giao dịch phái sinh thấp hơn nhiều và không có thuế bán, nên scalping trên VN30F khả thi hơn.

### So sánh Scalping với Market Making

| Tiêu chí | Scalping | Market Making |
|----------|----------|---------------|
| Hướng giao dịch | Một chiều (theo xu hướng siêu ngắn) | Hai chiều (đồng thời mua và bán) |
| Nguồn lợi nhuận | Biến động giá ngắn hạn | Bid-ask spread |
| Rủi ro tồn kho | Thấp (vị thế ngắn) | Cao (có thể bị kẹt một chiều) |
| Tần suất | Rất cao | Rất cao |

### Liên hệ với HFT (High-Frequency Trading)

Scalping và HFT có nhiều điểm tương đồng: cả hai đều tập trung vào tốc độ, tần suất cao và lợi nhuận nhỏ trên mỗi giao dịch. HFT có thể được xem là phiên bản "công nghệ cao" của scalping, với thời gian giữ vị thế có khi chỉ bằng mili giây và yêu cầu hạ tầng co-location, FPGA, hoặc thiết kế mạch chuyên dụng.

---

## Tổng kết và Mối liên hệ giữa các Chiến lược

| STT | Chiến lược | Khả thi tại VN (Cơ sở) | Khả thi tại VN (Phái sinh) | Độ khó |
|-----|-----------|----------------------|---------------------------|--------|
| 1 | Momentum | Cao (chỉ long) | Rất cao (long + short) | Trung bình |
| 2 | Mean Reversion | Trung bình | Cao | Cao |
| 3 | Market Neutral | Thấp (cần short) | Trung bình | Cao |
| 4 | Event-Driven | Cao | Trung bình | Trung bình |
| 5 | Market Making | Thấp (T+1.5) | Cao (T+0) | Rất cao |
| 6 | Scalping | Thấp (chi phí cao) | Trung bình | Cao |

**Ghi chú chung:**
- Thị trường phái sinh Việt Nam (VN30F) là nơi khả thi nhất để áp dụng đa số các chiến lược algo do cơ chế T+0 và chi phí thấp hơn.
- Thị trường cơ sở phù hợp nhất với momentum (long-only) và event-driven.
- Tất cả các chiến lược đều cần backtest kỹ lưỡng và quản lý rủi ro chặt chẽ trước khi áp dụng vốn thật.

---

*Tài liệu tổng hợp từ hub.algotrade.vn -- Algotrade Knowledge Hub. Nội dung đã được tổng hợp và diễn giải, không sao chép nguyên văn.*
# Algotrade Knowledge Hub - Strategy Batch 2
## Extracted Content from hub.algotrade.vn

**Source:** https://hub.algotrade.vn/
**Note:** The article numbering on hub.algotrade.vn differs from the initially requested titles. The actual Vietnamese titles and their mappings are documented below.

---

## Article 19: Chiến lược Hành động trước tái cân bằng quỹ chỉ số (Index Rebalancing Strategy / Front-Running ETF Strategy)

**URL:** https://hub.algotrade.vn/knowledge-hub/chien-luoc-hanh-dong-truoc-tai-can-bang-quy-chi-so/

### Khái niệm (Concept)
Chiến lược hành động trước tái cân bằng quỹ chỉ số (Front-running index fund rebalancing strategy) là gì:

Mọi quỹ đại chúng phải công bố bản cáo bạch đầu tư. Đặc biệt hơn, các quỹ chỉ số phải công bố chi tiết các quy tắc tái cân bằng. Bằng cách tuân thủ chính xác các quy tắc công khai này, nhà đầu tư có thể dự báo những gì các quỹ sắp triển khai và kiếm lợi nhuận bằng cách hành động trước.

Ở Mỹ, những nhà đầu tư theo chiến lược này đã bỏ túi khoảng 04 tỷ đô la mỗi năm. Các nhà nghiên cứu cũng phát hiện ra rằng hầu hết các quỹ chỉ số của Mỹ thông báo trước kế hoạch tái cân bằng của họ và thực hiện các giao dịch ở mức giá đóng cửa vào những ngày tái cân bằng chỉ số, để giảm thiểu lỗi sai lệch.

### Đặc điểm chính (Key characteristics)
- Chiến lược rất ngắn hạn
- Để tối ưu hóa việc sử dụng vốn, cần kết hợp chiến lược này với các chiến lược khác
- Đòi hỏi giao dịch liên tục, do đó phí và thuế có thể tăng lên nhiều lần so với thông thường
- Trong thị trường giảm giá, bất kỳ chiến lược nắm giữ vị thế mua nào cũng có thể bị thua lỗ nghiêm trọng

### Ứng dụng tại thị trường chứng khoán Việt Nam (Vietnamese Market Application)
Trong số các quỹ chỉ số ở Việt Nam, DCVFMVN DIAMOND ETF (FUEVFVND) là quỹ được biết đến nhiều nhất và có tốc độ tăng vốn nhanh nhất. Mục tiêu đầu tư của quỹ là theo sát biến động với chỉ số DIAMOND.

**Quy tắc để cổ phiếu được chọn vào DIAMOND INDEX (2022):**
- Có tối thiểu 3 tháng niêm yết và giao dịch trên HOSE
- Giá trị vốn hóa điều chỉnh free float tối thiểu 2.000 tỷ đồng
- Giá trị giao dịch khớp lệnh tối thiểu đạt 8 tỷ và khối lượng giao dịch khớp lệnh đạt 100.000 cổ phiếu (đối với cổ phiếu thuộc VNDiamond kỳ trước) hoặc 10 tỷ và 200.000 cổ phiếu (đối với cổ phiếu không thuộc VNDiamond kỳ trước)
- Số cổ phiếu trong rổ chỉ số tối thiểu là 10
- FOL của các cổ phiếu thuộc VNDiamond kỳ trước tối thiểu đạt 80%
- FOL = Sở hữu của nhà đầu tư nước ngoài / Tỷ lệ giới hạn được phép nắm giữ của nhà đầu tư nước ngoài (FLA)
- Các cổ phiếu thuộc VNDiamond kỳ trước có 0 <= P/E <= 3 lần P/E bình quân, các cổ phiếu không thuộc rổ VNDiamond kỳ trước có 0 <= P/E <= 2 lần P/E bình quân
- Giới hạn tỷ trọng 40% đối với 1 ngành

**Ghi chú thực hiện:** Việc dự báo thường được thực hiện bởi CTCP Chứng khoán SSI và CTCP Chứng khoán VNDIRECT, nhưng nếu dự báo trước báo cáo của các tổ chức này thì sẽ tối ưu hóa được lợi nhuận.

### Phòng vệ rủi ro
Có thể xem xét sử dụng chiến lược trung lập thị trường, điển hình là kết hợp mua chứng khoán cơ sở và bán chứng khoán phái sinh với tỷ trọng như nhau.

---

## Article 20: Chiến lược Chênh lệch giá (Arbitrage Strategy)

**URL:** https://hub.algotrade.vn/knowledge-hub/chien-luoc-chenh-lech-gia/

### Khái niệm (Concept)
Chênh lệch giá (arbitrage) là chiến lược tận dụng sự khác biệt tạm thời về giá của cùng một loại tài sản ở hai thị trường khác nhau để giao dịch và thu được lợi nhuận mà không phải chịu nhiều rủi ro. Nhà đầu tư thực hiện chiến lược chênh lệch giá bằng cách mua tài sản ở thị trường đang có giá thấp, và đồng thời bán tài sản đó ở thị trường có giá cao hơn.

### Hai đặc điểm chính (Two Key Characteristics)
1. **Chỉ thực hiện khi có sự mất cân bằng về giá của tài sản** - Đây là điều kiện quan trọng nhất:
   - Cùng một tài sản nhưng đang được giao dịch với giá khác nhau trên hai thị trường khác nhau
   - Hoặc, hai tài sản có dòng tiền kỳ vọng trong tương lai giống nhau nhưng đang được giao dịch ở các mức giá khác nhau

2. **Thực hiện giao dịch đồng thời** - Việc mua và bán cùng một loại tài sản phải diễn ra cùng lúc; nếu thời điểm mua và thời điểm bán khác nhau quá nhiều, nhà đầu tư sẽ phải chịu rủi ro đáng kể.

### Liên hệ với lý thuyết thị trường hiệu quả
Chiến lược chênh lệch giá có liên quan chặt chẽ đến lý thuyết thị trường hiệu quả - lý thuyết này nói rằng thị trường hiệu quả một cách hoàn hảo khi mọi thông tin trong quá khứ và hiện tại liên quan đến tài sản sẽ được phản ánh một cách nhanh chóng và hợp lý vào giá. Nói cách khác, thị trường hiệu quả sẽ không có cơ hội để tận dụng kinh doanh chênh lệch giá.

### Thực tiễn tại Việt Nam (Vietnamese Market Reality)
- Hiện chiến lược chênh lệch giá gần như không tồn tại ở thị trường chứng khoán Việt Nam
- Các cơ hội chênh lệch giá thường hiện hữu rõ ràng hơn trên thị trường ngoại hối, tiền số, và ở những cổ phiếu được giao dịch cùng lúc trên hai thị trường như Mỹ, châu Âu
- Cơ hội chỉ dành cho các ngân hàng quốc tế với khả năng sử dụng và quy đổi liên tục nhiều loại ngoại tệ khác nhau

### Ví dụ: Bitcoin ở Hàn Quốc (2017)
Vào năm 2017, giá một bitcoin ở Hàn Quốc cao hơn trên thế giới đến 50%. Các cá nhân/tổ chức có thể mua bán liên tục một cách hợp pháp và kiếm được lợi nhuận cực kỳ lớn mà hoàn toàn không có rủi ro. Trên thực tế rất nhiều cá nhân/tổ chức biết đến cơ hội này nhưng hầu hết không thể tận dụng nó.

### Tiềm năng tương lai
Tại Việt Nam, vào tháng 5/2022, văn bản hợp tác giữa UBCKNN với NYSE xây dựng cơ chế để các nhà đầu tư tham gia hai thị trường chứng khoán đã được ký kết, có thể mở ra cơ hội kinh doanh chênh lệch giá ở cả hai thị trường.

### Rào cản
- Thời gian tồn tại của các cơ hội kinh doanh chênh lệch giá diễn ra rất ngắn, đôi khi chỉ trong vài giây
- Phương thức đặt lệnh truyền thống sẽ khó nắm bắt cơ hội
- Mức chênh lệch giá phải lớn hơn chi phí giao dịch

---

## Article 21: Chiến lược Lưới (Grid Strategy)

**URL:** https://hub.algotrade.vn/knowledge-hub/chien-luoc-luoi/

### Khái niệm (Concept)
Chiến lược lưới thiết lập một "lưới giá" liên tục mua và bán ở các mức giá được định trước để thu được lợi nhuận trong bất kỳ thị trường nào. Chiến lược lưới hoạt động tốt nhất trong một thị trường đi ngang dao động lớn.

### Đặc điểm chính (Key Characteristics)
- Có thể kiếm được lợi nhuận trong thị trường dao động ngang
- Có nguy cơ thua lỗ lớn trong thị trường có xu hướng

### Ví dụ minh họa (Example)
Thiết lập lưới trung lập trên cổ phiếu FPT:
- Giá tham chiếu khởi điểm của lưới: 87.200 đồng
- Bước lưới: 800 đồng
- Bước giá chốt lời: 800 đồng

---

## Article 22: Chiến lược Beta vượt trội (Smart Beta Strategy)

**URL:** https://hub.algotrade.vn/knowledge-hub/chien-luoc-beta-vuot-troi/

### Khái niệm (Concept)
Chiến lược đầu tư Beta vượt trội, hay đầu tư theo yếu tố là chiến lược xây dựng danh mục đầu tư theo một quy trình có hệ thống, dựa trên quy tắc sử dụng các yếu tố cơ bản của doanh nghiệp như thanh khoản, giá trị, chất lượng để làm tiêu chí ra quyết định đầu tư.

Beta vượt trội là chiến lược mở rộng của chiến lược đầu tư thụ động. Với đầu tư thụ động, nhà đầu tư chỉ cần mua toàn bộ cổ phiếu thành phần của một rổ chỉ số theo tỷ trọng vốn hóa thị trường và nắm giữ trong dài hạn nhằm đạt được lợi nhuận tương đương với chỉ số tham chiếu.

Còn với beta vượt trội, tỷ trọng danh mục được xác định dựa trên các yếu tố cơ bản thay vì theo vốn hóa thị trường. Mục đích chính là tăng tỷ trọng các cổ phiếu có tiềm năng sinh lời cao, ngược lại giảm tỷ trọng các cổ phiếu ít tiềm năng hơn, từ đó, tạo ra danh mục có lợi nhuận vượt trội hơn so với chiến lược đầu tư thụ động.

### Lý thuyết (Theory)
Về mặt lý thuyết, beta vượt trội là sự kết hợp những tính chất của chiến lược đầu tư thụ động và chiến lược đầu tư năng động.

### Ví dụ chiến lược (Strategy Example)
Giả định nhà đầu tư tin rằng trong dài hạn, những cổ phiếu với P/E thấp có khuynh hướng tạo ra tỷ suất sinh lời cao hơn so với trung bình toàn thị trường. Vận dụng lập luận này vào thị trường cổ phiếu, lấy chỉ số VN-Index làm đối chuẩn:

Mua toàn bộ cổ phiếu thành phần của VN-Index và nắm giữ dài hạn, tỷ trọng xác định theo quy tắc: P/E càng thấp thì tỷ trọng càng cao theo tỷ lệ tương ứng.

---

## Article 23: Chiến lược Truy vết (Tracking / Algorithm Detection Strategy)

**URL:** https://hub.algotrade.vn/knowledge-hub/chien-luoc-truy-vet/

### Khái niệm (Concept)
Truy vết là nhóm thuật toán đặc biệt với mục tiêu cụ thể là phát hiện các thuật toán đang giao dịch khác. Truy vết thuật toán thường nhắm vào các thuật toán giao dịch khối lượng lớn và liên tục như: TWAP, VWAP, POV. Ít phổ biến hơn, thuật toán truy vết còn có thể phát hiện các thuật toán tạo lập thị trường hoặc các thuật toán quán tính giá.

### Dữ liệu đầu vào (Input Data)
Dữ liệu tick theo thời gian thực cùng với sổ lệnh (order book) của tất cả các chứng khoán đang được giao dịch.

### Nguyên tắc hoạt động (Operating Principle)
Dựa vào các lệnh khớp và sổ lệnh để tìm ra các mô hình có tính lặp đi lặp lại cao hơn nhiều so với tần suất ngẫu nhiên. Khi đã xác định được mô hình dự đoán, nếu mô hình trên tiếp tục diễn ra thì thuật toán truy vết xem như đã xác định được một thuật toán khác.

### Các mô hình giao dịch thường xuất hiện (Common Trading Patterns)
1. **TWAP** - Các lệnh cách nhau theo một khoảng thời gian cố định. Sắp xếp các lệnh khớp và tìm ra các lệnh tương đương về khối lượng mà có khoảng cách giữa các lệnh cách nhau một khoảng thời gian gần bằng hằng số.

2. **Chẻ lệnh (Order Splitting)** - Rất nhiều lệnh khớp với khối lượng nhỏ trong cùng một khoảng thời gian nhỏ hơn một giây. Một mô hình đơn giản về số lệnh khớp trong khoảng thời gian 5 giây thường sẽ tìm ra các hình thức chẻ lệnh khác nhau.

3. **Tạo lập thị trường (Market Making)** - Thuật toán tạo lập thị trường thường hoạt động rất mạnh mẽ ở giá chờ mua 1 và giá chờ bán 1. Tất cả chứng khoán có tần suất đặt lệnh liên tục ở giá chờ mua 1 và giá chờ bán 1 thì thường có sự tham gia của một thuật toán tạo lập thị trường.

4. **Quán tính giá (Momentum)** - Các thuật toán quán tính giá thường được áp dụng mạnh mẽ trên thị trường chứng khoán phái sinh. Đặc điểm chung: mua khi thị trường có xu hướng lên và bán khi thị trường có xu hướng xuống. Khi thuật toán được kích hoạt thường tạo ra một khoảng trượt giá lớn.

### Ứng dụng thuật toán truy vết (Applications)
- Khi phát hiện giao dịch của tổ chức lớn: nắm giữ vị thế cùng chiều với các tổ chức này ở một số lượng hợp lý
- Khi phát hiện thuật toán tạo lập thị trường: sử dụng chiến lược quán tính giá đúng các thời điểm then chốt
- Khi phát hiện thuật toán quán tính giá: sử dụng chiến lược lướt sóng siêu ngắn sẽ là tối ưu

### Phòng thủ thuật toán truy vết (Defense Against Detection)
Nhóm thuật toán "tàng hình" (stealth) là nhóm thuật toán nhằm hỗ trợ trong quá trình thực thi để tránh bị các thuật toán truy vết phát hiện. Nguyên tắc cơ bản: thêm vào một số biến ngẫu nhiên trong phương trình sẽ có tác dụng khá tốt trong việc phòng vệ các thuật toán truy vết.

---

## Article 08: Thuật toán thực thi tối ưu hóa chi phí giao dịch (Execution Algorithms: VWAP, TWAP, POV)

**URL:** https://hub.algotrade.vn/knowledge-hub/chien-luoc-thuc-thi-toi-uu-hoa-chi-phi-giao-dich/

### Vấn đề chính (Core Problem)
Tại một thời điểm bất kỳ, nếu một nhà đầu tư thực hiện một lệnh giao dịch mua/bán cổ phiếu với khối lượng quá lớn so với thanh khoản thường ngày thì sẽ ngay lập tức làm mất cân bằng cung cầu và giá cổ phiếu dịch chuyển ngắn hạn theo hướng bất lợi với chính nhà đầu tư đó.

Lệnh giao dịch có khối lượng càng lớn so với thanh khoản hiện tại của cổ phiếu, sự tác động tới giá thị trường theo hướng bất lợi càng cao.

### Thuật toán VWAP (Volume Weighted Average Price)
Cả hai thuật toán VWAP và TWAP đều chia khối lượng cổ phiếu cần giao dịch thành các lệnh nhỏ hơn và gửi chúng vào thị trường theo một lịch trình đã được xác định trước để đảm bảo giao dịch được hoàn thành trong một khoảng thời gian cụ thể.

VWAP: Công thức = Tổng(Pi * Qi) / Tổng(Qi)
- Pi là giá khớp lệnh giao dịch i
- Qi là khối lượng khớp lệnh của giao dịch i

### Thuật toán TWAP (Time Weighted Average Price)
Đặc tính của thuật toán TWAP là các lệnh cách nhau theo một khoảng thời gian cố định. Thuật toán chia các lệnh thành các phần bằng nhau và liên tục gửi chúng vào thị trường với khoảng thời gian bằng nhau giữa các lệnh (thường là mỗi 5 phút). Nhà đầu tư phải chia lệnh đủ nhỏ để vượt qua tác động thanh khoản thị trường.

### Thuật toán POV (Percentage of Volume)
Thuật toán POV thực hiện giao dịch theo một tỷ lệ phần trăm đã định trước của thanh khoản thực tế của thị trường cho đến khi đạt được khối lượng mong muốn. Khi khối lượng giao dịch trên thị trường tăng, thuật toán giao dịch nhiều cổ phiếu hơn và ngược lại.

**Ví dụ:** Nếu nhà đầu tư cần mua 5.000.000 cổ phiếu FPT sử dụng thuật toán POV với tỷ lệ tham gia 10%, thì cứ mỗi 10.000 cổ phiếu FPT được giao dịch trên thị trường, thuật toán sẽ mua 1.000 cổ phiếu cho đến khi đạt mục tiêu 5.000.000.

**Ưu điểm:** Giữ khối lượng lệnh mua đưa vào thị trường tỷ lệ với thanh khoản hiện tại của thị trường (duy trì khoảng 10%), từ đó giảm thiểu tác động giá thị trường.

**Nhược điểm:** Nhà đầu tư có thể không hoàn thành giao dịch trong khung thời gian chỉ định nếu thanh khoản thị trường không thuận lợi.

---

## Article 09: 06 yếu tố tạo nên một thuật toán giao dịch hoàn chỉnh (6 Elements of a Complete Trading Algorithm)

**URL:** https://hub.algotrade.vn/knowledge-hub/cac-yeu-to-tao-nen-mot-chien-luoc-giao-dich-thuat-toan-hoan-chinh/

### 6 Yếu tố (6 Elements)

1. **Điểm mở vị thế (Entry Point)** - Thời điểm mua hay bán là yêu cầu tối thiểu của bất kỳ thuật toán giao dịch nào. Lưu ý: điểm mở vị thế không đồng nghĩa với việc mở được vị thế. Trong nhiều chiến lược giao dịch tỷ lệ mở được vị thế so với số điểm mở vị thế có thể dưới mức 10%.

2. **Điểm chốt lời (Take Profit)** - Thời điểm hay điều kiện chốt lời, tái cơ cấu danh mục là điều kiện bắt buộc tiếp theo. Trong một số điều kiện đặc biệt, thuật toán có thể chốt lời không theo hàm lợi nhuận mà theo hàm thời gian để lợi nhuận mang tính ngẫu nhiên cao hơn.

3. **Điểm cắt lỗ (Stop Loss)** - Phần lớn chiến lược giao dịch thuật toán đều có điểm dừng hoặc cắt lỗ. Tâm lý khó chấp nhận thua lỗ và quan điểm "chưa cắt lỗ là chưa thua" khiến nhà đầu tư có xu hướng bỏ qua yếu tố này. Hiện tượng này đặc biệt phổ biến trong các chiến lược hồi quy trung vị (mean reversion) và chiến lược lướt sóng siêu ngắn (scalping).

4. **Thị trường mục tiêu (Target Market)** - Mỗi chứng khoán đều có đặc điểm riêng. Vì mỗi chứng khoán thu hút các nhóm nhà đầu tư, nhà giao dịch, quỹ khác nhau, nên không bao giờ giả định các chứng khoán khác nhau sẽ có hoạt động tương tự nhau.

5. **Tỷ trọng vị thế (Position Sizing)** - Trong bối cảnh giao dịch thuật toán ở Việt Nam, 95% việc thực thi thuật toán không cân nhắc đến tỷ trọng vị thế mà mua/bán toàn bộ tài khoản ngay khi có điểm mở vị thế. Hành vi mua/bán toàn bộ tài khoản rất có thể dẫn đến sụp đổ cả hệ thống giao dịch trong vòng 03 năm.

6. **Chiến lược thực thi giao dịch (Execution Strategy)** - Là phiên bản nâng cao của việc dùng lệnh thị trường trong tất cả tình huống để hạn chế chi phí trượt giá. Chi phí trượt giá ảnh hưởng rất lớn đến hiệu suất toàn hệ thống, đặc biệt là đối với tài khoản lớn. Thay vì sử dụng lệnh thị trường, có thể sử dụng các thuật toán như VWAP, TWAP. Trong giao dịch thật, ALGOTRADE sử dụng thuật toán POV nâng cấp cho phép giao dịch tần suất cao khi có lợi thế về giá.

---

## Article 41: Đánh giá thực thi giao dịch với đối chuẩn TWAP và VWAP (Evaluating Trade Execution with TWAP and VWAP Benchmarks)

**URL:** https://hub.algotrade.vn/knowledge-hub/su-dung-doi-chuan-twap-va-vwap-de-danh-gia-qua-trinh-thuc-thi-giao-dich/

### Khái niệm (Concept)
Đánh giá thực thi giao dịch là quá trình định lượng và so sánh mức độ hiệu quả của các chiến lược thực thi giao dịch, dựa vào đó để đưa ra những lựa chọn phù hợp nhằm đạt được mục đích giao dịch, đồng thời giảm thiểu các chi phí giao dịch.

### Đối chuẩn VWAP
VWAP là giá trung bình có trọng số theo khối lượng của tất cả các giao dịch được thực hiện trong giai đoạn tính toán.

**Công thức:** VWAP = Sum(Pi * Qi) / Sum(Qi)
- Pi là giá khớp lệnh giao dịch i
- Qi là khối lượng khớp lệnh của giao dịch i

Vì VWAP đã hàm chứa tất cả các hoạt động thị trường, cung và cầu của tất cả những người tham gia thị trường, nên nó cung cấp một thước đo hợp lý để đánh giá quá trình thực thi giao dịch.

### Công thức đánh giá hiệu suất
Hiệu suất = S * (VWAP - P) / VWAP
- P là giá khớp lệnh trung bình
- S là chiều mở vị thế (S = 1: vị thế mua, S = -1: vị thế bán)

**Ví dụ:** Nhà đầu tư thực hiện lệnh mua với giá khớp lệnh trung bình là 20.500 VND, VWAP trong ngày giao dịch là 20.000 VND.
Hiệu suất = 1 * (20.000 - 20.500) / 20.000 = -2.5%
=> Hiệu suất âm cho thấy đã mua ở giá cao hơn mức trung bình thị trường.

---

## Article 25: Tài chính hành vi trong hình thành giả thuyết thuật toán (Behavioral Finance in Algorithm Hypothesis Formation)

**URL:** https://hub.algotrade.vn/knowledge-hub/tai-chinh-hanh-vi-trong-hinh-thanh-gia-thuyet-thuat-toan/

**Note:** The initially requested "25 Tong ket chien luoc" (Strategy Summary) does not exist on hub.algotrade.vn. Article 25 is actually about Behavioral Finance. The site's article list ends at 25 for Section II (Hypothesis Formation), then continues with other sections (Data, Backtesting, Optimization, etc.) up to article 64.

### Khái niệm Tài chính hành vi (Behavioral Finance Concept)
Tài chính hành vi nghiên cứu cách con người đưa ra quyết định, xem xét các yếu tố tâm lý gây ảnh hưởng và làm thiên lệch quá trình ra quyết định của họ.

Lý thuyết kinh tế và tài chính truyền thống giả định rằng các cá nhân tham gia thị trường luôn hành động hợp lý. Trong thực tế, khi đối mặt với quá nhiều thông tin cần xử lý và liên tục cập nhật, mọi người thường không có đủ thời gian cũng như khả năng để đi đến một quyết định hoàn toàn tối ưu. Họ hài lòng với việc đưa ra một lựa chọn "đủ tốt" hơn là đưa ra một lựa chọn "tối ưu".

### Hai nhóm thiên kiến hành vi (Two Groups of Behavioral Biases)

**1. Lỗi về nhận thức (Cognitive Errors)**
Những lỗi cơ bản về thống kê, lỗi xử lý thông tin, hoặc liên quan đến năng lực ghi nhớ khiến quyết định đi chệch khỏi tính hợp lý. Có thể điều chỉnh hoặc loại bỏ thông qua thông tin, sự giáo dục, và lời khuyên tốt hơn.

Gồm 2 loại:
- **Thiên kiến niềm tin mù quáng (Belief Perseverance Bias)** - Kết quả của sự khó chịu về mặt tinh thần xảy ra khi thông tin mới xung đột với niềm tin hoặc nhận thức đã có trước đó. Mọi người có khả năng sẽ bỏ qua hoặc sửa đổi các thông tin mâu thuẫn và chỉ xem xét các thông tin xác nhận niềm tin hiện có.

- **Lỗi xử lý nhận thức (Processing Errors)** - Thông tin được xử lý và sử dụng một cách phi logic hoặc không hợp lý.

**2. Thiên kiến cảm xúc (Emotional Biases)**
(The article discusses this second category in detail on the source page)

---

## Summary of Article Mapping

The user's requested article titles did not exactly match the hub.algotrade.vn numbering. Here is the mapping:

| Requested Title | Actual Article on hub.algotrade.vn |
|---|---|
| 17 Chiến lược Index Rebalancing | **19.** Chiến lược: Hành động trước tái cân bằng quỹ chỉ số |
| 18 Chiến lược Arbitrage | **20.** Chiến lược: Chênh lệch giá |
| 19 Chiến lược Grid | **21.** Chiến lược: Lưới |
| 20 Chiến lược Smart Beta | **22.** Chiến lược: Beta vượt trội |
| 21 Chiến lược Tracking | **23.** Chiến lược: Truy vết |
| 22 Thuật toán VWAP | **08.** Thuật toán thực thi tối ưu hóa chi phí giao dịch (covers VWAP) |
| 23 Thuật toán TWAP | **08.** Same article as above (covers TWAP) + **41.** Đánh giá thực thi giao dịch với đối chuẩn TWAP và VWAP |
| 24 Thuật toán POV | **08.** Same article as above (covers POV) + **09.** 06 yếu tố tạo nên một thuật toán giao dịch hoàn chỉnh |
| 25 Tổng kết chiến lược | **25.** Tài chính hành vi trong hình thành giả thuyết thuật toán (NOT a strategy summary) |

**Note:** The hub.algotrade.vn Knowledge Hub has a different numbering scheme from the requested articles. VWAP, TWAP, and POV are all covered in Article 08 together as "execution optimization algorithms" rather than as separate articles. Article 25 is about Behavioral Finance, not a strategy summary.

---

## Complete Table of Contents from hub.algotrade.vn Knowledge Hub

### I. Tổng quan giao dịch thuật toán (Algorithmic Trading Overview)
01-06: Basic concepts, advantages, risks, components, semi-automated trading, 9 development steps

### II. Hình thành giả thuyết thuật toán (Algorithm Hypothesis Formation)
07. Phân biệt hai nhóm thuật toán
08. Thuật toán thực thi tối ưu hóa chi phí giao dịch (VWAP, TWAP, POV)
09. 06 yếu tố tạo nên một thuật toán giao dịch hoàn chỉnh
10. Khác biệt giữa chứng khoán cơ sở và chứng khoán phái sinh
11. Hướng dẫn hình thành giả thuyết thuật toán
12. Tổng quan các chiến lược giao dịch
13. Chiến lược: Trung lập thị trường (Market Neutral)
14. Chiến lược: Quán tính giá (Momentum)
15. Chiến lược: Hồi quy trung vị (Mean Reversion)
16. Chiến lược: Hướng sự kiện (Event-Driven)
17. Chiến lược: Tạo lập thị trường (Market Making)
18. Chiến lược: Lướt sóng siêu ngắn (Scalping)
19. Chiến lược: Hành động trước tái cân bằng quỹ chỉ số (Index Rebalancing Front-Running)
20. Chiến lược: Chênh lệch giá (Arbitrage)
21. Chiến lược: Lưới (Grid)
22. Chiến lược: Beta vượt trội (Smart Beta)
23. Chiến lược: Truy vết (Tracking/Algorithm Detection)
24. Giao dịch thuật toán công nghệ cao
25. Tài chính hành vi trong hình thành giả thuyết thuật toán

### III-XII: Additional sections covering Data, Backtesting, Optimization, Forward Testing, Live Trading, Evaluation Criteria, Multi-Algorithm Optimization, Practical Trading, Intel Center, and Algotrade Lab.
