# Chạy baseline và paper v2 song song

Giữ nguyên chương trình, thư mục, `.env` và database đang chạy. Paper v2 chạy ở một checkout mới, database mới và không gửi Telegram. Module này chỉ dùng GET market data công khai; không có đặt lệnh, API giao dịch hay quản lý tài khoản.

## Hai luồng

| Luồng | Cách chạy | Dữ liệu |
|---|---|---|
| A – baseline | Chương trình cũ đang chạy | Giữ kết quả cũ và tiếp tục như hiện tại |
| B – corrected paper | `python -m signal_bot.validation` ở checkout mới | `data/paper_v2.db`, kết quả forward mới |

B giữ nguyên các giá trị bộ lọc trong `.env` bạn sao chép, không tự hạ RSI. B sửa kế hoạch giá theo tick size, xác nhận entry trước khi chấm điểm và neo thời hạn ban SHORT vào thời điểm đóng lệnh gây ban. Do thay đổi này ảnh hưởng cả tập tín hiệu lẫn mô hình thực thi, B có strategy version riêng; không phải một thử nghiệm chỉ thay đổi duy nhất execution engine.

Hai process scan độc lập có thể khác thời điểm và thứ tự tín hiệu. Không diễn giải chênh lệch A/B thành tác động nhân quả chính xác của một bộ lọc. Nếu cần đối chiếu cùng một tín hiệu, phải xây dựng thêm feed ứng viên dùng chung. Không đồng thời nới RSI trong phép thử này.

## Cài và kiểm tra một vòng trên Windows PowerShell

Từ thư mục cha của project hiện tại, clone branch này vào thư mục mới:

```powershell
git clone --branch paper-shadow-validation https://github.com/Khangtran94/Personal_Trading_System.git Personal_Trading_System_PaperV2
cd Personal_Trading_System_PaperV2
uv sync
```

Sao chép `.env` đang dùng từ project cũ sang checkout mới **trên máy của bạn** để giữ đúng score/RSI/filter thực tế. Không gửi nội dung `.env` lên GitHub hay vào chat. Chương trình mới bỏ qua `DATABASE_URL` khi chọn nơi ghi paper; `--db` mới là nơi ghi. Telegram bị tắt trong runner kể cả khi `.env` có token. Các API key không được sử dụng cho paper v2.

Đặt đường dẫn database thật của bản A. Đây là đường dẫn để kiểm tra cách ly, không dùng để sửa hay nhập các bản ghi cũ:

```powershell
$baselineDb = 'C:\YOUR_EXISTING_PROJECT\data\signals.db'
uv run python -m signal_bot.validation --baseline-db "$baselineDb" --db data/paper_v2.db --once
```

Thay đường dẫn ví dụ bằng file chương trình A đang ghi; không mặc định rằng tên file upload là tên database đang chạy. `--once` có thể không phát tín hiệu nếu ngoài giờ hoạt động hoặc không có setup. Sau khi kiểm tra log và đường dẫn:

```powershell
uv run python -m signal_bot.validation --baseline-db "$baselineDb" --db data/paper_v2.db
```

Giữ cửa sổ này mở. Chương trình kiểm tra vị thế rồi scan tuần tự, chờ 5 phút giữa các vòng. Ngoài giờ active chỉ tracker chạy. Ctrl+C dừng B; A vẫn độc lập. Chỉ chạy một process B cho mỗi database; khóa OS ngăn process thứ hai. Có thêm một scanner nên tổng số request tăng, không tăng tốc scan; tuân thủ Retry-After/rate-limit và dừng B khi bị hạn chế.

## Xem kết quả, lưu log, xuất dữ liệu

```powershell
uv run python -m signal_bot.validation --db data/paper_v2.db --summary
uv run python -m signal_bot.validation --db data/paper_v2.db --export-csv data/paper_v2_export_001.csv
```

Summary/export chỉ đọc dữ liệu, không gọi mạng. Export mặc định chỉ lấy WIN/LOSS/TIMEOUT đã khớp và đóng để dùng trên dashboard hiện tại. Thêm `--export-all` khi muốn audit cả các trạng thái khác. UNFILLED, INVALID, REVIEW và vị thế đang mở không tính vào 700. CSV export có `result`, `r_multiple`, `net_r`, versions và config hash; R gross và assumed net được phân biệt. `r_multiple` là gross, đặt cùng cost adjustment tương ứng trên dashboard. Không phê duyệt một cohort chỉ vì đủ 700 nếu vẫn còn REVIEW hoặc khoảng thiếu dữ liệu chưa giải quyết.

Muốn giữ log, dùng PowerShell `*>` hoặc `Tee-Object`; log không chứa secrets cấu hình. Ví dụ:

```powershell
uv run python -m signal_bot.validation --baseline-db "$baselineDb" --db data/paper_v2.db *> data/paper_v2.log
```

## Quy tắc mô phỏng công khai

- Vẫn dùng công thức EMA/ATR, RR và các filter đang cấu hình. Tính giá từ EMA/ATR chưa làm tròn rồi chuẩn hóa `PRICE_FILTER.tickSize` theo từng coin. Lưu tick size trên từng vị thế. RR đo từ giá fill thực tế có thể khác `RR_RATIO`, vì công thức TP gốc được đặt từ mép vùng entry.
- Entry là limit tại midpoint đã chuẩn hóa tick. Bắt đầu xét từ nến 5 phút đầu tiên mở sau thời điểm phát tín hiệu; không tận dụng high/low trước tín hiệu của nến đang chạy. Đây là giả định trễ bảo thủ, không phải khớp lệnh thực.
- Mặc định chờ entry 60 phút. Không khớp thì UNFILLED. Limit marketable ở đầu nến được fill ở giá open tốt hơn; nếu gap vượt cả entry và SL thì REVIEW.
- Entry và SL cùng nến: tính SL bảo thủ. Entry intrabar và TP cùng nến mà không biết thứ tự: REVIEW, không tự nhận WIN. Với vị thế đã mở, cùng nến chạm SL/TP thì SL trước. Gap qua SL có thể mất hơn -1R. Gap qua TP chỉ nhận giá TP.
- Thời hạn giữ mặc định 8 giờ tính từ nến fill. Fill/exit time chỉ có độ phân giải nến 5 phút; không suy luận được thời điểm khớp intrabar chính xác. Muốn giải quyết REVIEW cần dữ liệu nhỏ hơn và phiên bản mô hình riêng.
- Mặc định trừ **0.05R/lệnh đã khớp** như một giả định tổng chi phí. Đây không phải phí Binance thực tế và chưa tự tính funding/slippage/liquidation theo tài khoản. Có thể chọn `--cost-r 0.1`, nhưng phải dùng DB mới nếu cấu hình cohort thay đổi.
- Fetch lịch sử theo `startTime`/`endTime`, có phân trang. Phải liên tục từ cursor đã lưu; nến thiếu, OHLC sai hoặc lỗi API được gắn `data_issue`, giữ cursor và không tự đóng lệnh. Retry sau tiếp tục backfill. OHLC đã dùng được cache trong DB; nếu endpoint trả dữ liệu đã cache khác đi, gắn lỗi để kiểm tra.
- Ban SHORT hết hạn từ exit time của sự kiện thua, không từ thời điểm scan lại. Cooldown và lịch sử nằm trong DB nên restart không xóa chúng.
- Lưu `strategy_version`, `execution_model_version`, config hash, hash source Python, phiên bản Python/dependencies và snapshot cấu hình không chứa secrets. Cấu hình, source hoặc môi trường tính toán đổi thì runner từ chối tiếp tục DB cũ; dùng file DB mới. Dùng branch cố định cho phép thử; thay thuật toán phải tăng version.
- Không quản lý vốn, không tính portfolio equity/mark-to-market. Vị thế chồng lấn vẫn là nhiều tín hiệu paper độc lập. Compound thực tế phải có mô phỏng giới hạn vốn và tổng rủi ro riêng.

## Kết quả cũ

Giữ nguyên database cũ. Không tự sửa bản ghi risk=0, không ghi đè WIN/LOSS cũ và không nhập kết quả cũ vào cohort v2. Chúng vẫn là kết quả legacy; tái đánh giá cần OHLC và cấu hình lịch sử, được báo cáo riêng, không coi là forward v2.

## Kiểm thử

```powershell
uv run --extra dev pytest -q
```

Fixtures dùng OHLC giả lập và SQLite tạm, không gọi sàn hoặc Telegram. Kiểm tra fill, timeout, gap SL, cùng nến entry/TP, nến thiếu/backfill, tick size coin giá thấp, hết hạn ban sau restart, chống ghi nhầm DB, phiên bản cohort, pagination và cách ly notifier/repository cũ.
