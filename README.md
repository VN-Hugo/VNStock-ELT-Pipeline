# VNStock ELT Pipeline

Pipeline ELT cho dữ liệu chứng khoán Việt Nam: gọi API **vnstock**, nạp thẳng dữ liệu thô vào schema `bronze` trên **Supabase (PostgreSQL)**, rồi dùng **dbt** dựng các tầng Silver và Gold.

![Architecture](img/Architecture.png)

## Cài đặt

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Tạo file `.env` ở thư mục gốc (file này không được commit):

```dotenv
DATABASE_URL=postgresql://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres
PGHOST=db.<project-ref>.supabase.co
PGPORT=5432
PGUSER=postgres
PGPASSWORD=<password>
PGDATABASE=postgres
VNSTOCK_API_KEY=
VNSTOCK_SOURCE=VCI
STOCK_SYMBOLS=VCB,FPT,HPG,VNM
START_DATE=2024-01-01
```

## Nạp dữ liệu vào Bronze

Không có file trung gian: dữ liệu từ vnstock được ghi thẳng vào các bảng `bronze.*`. Loader tự tạo schema và bảng khi chạy lần đầu.

```powershell
python run_pipeline.py run --mock          # chạy thử với dữ liệu mẫu, không gọi API, không ghi DB
python run_pipeline.py run                 # vnstock -> Supabase bronze
python run_pipeline.py run --full-refresh  # lấy lại toàn bộ giá từ START_DATE
python run_pipeline.py check-day           # hôm nay có phải phiên giao dịch và đã có dữ liệu chưa
```

- **Nạp tăng dần (incremental):** giá chỉ được lấy từ ngày mới nhất đã có trong Bronze lùi lại 5 ngày, để bắt kịp các lần nguồn sửa dữ liệu. Chạy lần đầu thì lấy từ `START_DATE`.
- Mỗi dòng Bronze có `ingestion_date`, `extracted_at` và `batch_id` (run id của Airflow) để truy vết.

## Chạy dbt

Profile dbt đọc các biến `PGHOST`, `PGUSER`, `PGPASSWORD`, `PGPORT` và `PGDATABASE` từ environment. Trên PowerShell, nạp chúng từ `.env` trước khi chạy dbt:

```powershell
Get-Content .env | Where-Object { $_ -match '^\s*([^#][^=]*)=(.*)$' } | ForEach-Object { Set-Item "env:$($Matches[1].Trim())" $Matches[2].Trim() }
dbt debug --project-dir dbt --profiles-dir dbt
dbt build --project-dir dbt --profiles-dir dbt
```

`sources.yml` đọc các bảng raw trong schema `bronze`; Silver tạo staging views và Gold tạo dimensions, facts cùng market summary.

## Nguồn dữ liệu và lưu ý

| Bảng Bronze | Nguồn vnstock | Ghi chú |
|---|---|---|
| `companies_raw` | `Company.overview()` | Loại công ty (`is_bank`), số cổ phiếu, % sở hữu nước ngoài và room (chỉ có giá trị hiện tại) |
| `historical_prices_raw` | `Quote.history()` | Giá **đã điều chỉnh**, đơn vị **nghìn đồng** (65.18 = 65.180 đ) |
| `financial_statements_raw` | `Finance.income_statement()` + `Company.ratio_summary()` | 8 quý gần nhất (giới hạn bản cộng đồng); P/E, P/B, ROE, ROA, D/E, vốn hóa |
| `foreign_trading_raw` | `Trading(source="KBS").price_board()` | Mua/bán của khối ngoại trong phiên hiện tại |

- **P/E, P/B** lấy từ `Company.ratio_summary()`. Không dùng `Finance.ratio()` vì hàm này chỉ trả về 4 quý cũ nhất (2018), không trùng kỳ nào với báo cáo kết quả kinh doanh.
- **Khối ngoại:** vnstock bản miễn phí không có API lấy lịch sử, nên pipeline chụp bảng giá mỗi lần chạy và tích lũy dần. Lịch sử chỉ bắt đầu từ ngày chạy đầu tiên, các ngày trước đó để `NULL`. Nên chạy pipeline **mỗi ngày sau 15:00** để có đủ số liệu của phiên. Với giai đoạn trước đó, dùng `dim_companies.foreign_ownership_pct` và `foreign_room_pct` thay thế.
- **Tránh look-ahead bias:** khi nối báo cáo tài chính với giá, hãy nối theo `available_date` (ngày kết thúc quý + 45 ngày), không nối theo `quarter_end_date`.
- **Ngân hàng** (`is_bank = true`): `revenue` là tổng thu nhập hoạt động, không phải doanh thu thuần, nên chỉ so sánh ngân hàng với ngân hàng.
- Bronze chỉ append, không ghi đè. Silver giữ bản trích xuất mới nhất cho mỗi khóa, còn loader tự thêm cột mới vào các bảng Bronze đã có.

## Test

```powershell
python -m pytest -q
```
