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

## Điều phối bằng Airflow

DAG `vnstock_elt` ([dags/vnstock_elt_dag.py](dags/vnstock_elt_dag.py)) chạy lúc **15:30 các ngày thứ 2 đến thứ 6** (giờ VN), sau khi phiên ATC đóng cửa:

| Task | Việc làm |
|---|---|
| `check_day` | Bỏ qua cuối tuần. Với ngày thường, kiểm tra đã có nến ngày của mã đầu tiên chưa, nên tự nhận biết ngày lễ mà không cần lịch nghỉ. Không phải ngày giao dịch thì cả run được đánh dấu *skipped*, không phải *failed* |
| `ingest_vnstock` | Gọi vnstock (giá lấy incremental) và lưu tạm vào `/tmp` trong container |
| `load_bronze` | Append vào `bronze.*` trên Supabase, gắn `batch_id` = `run_id`, xoá file tạm |
| `dbt_silver` | `dbt build` cho test nguồn Bronze, các model Silver và test của chúng |
| `dbt_gold` | `dbt build` cho các model Gold và test |
| `notify` | Luôn chạy (`all_done`): gửi thông báo thành công, bỏ qua hoặc thất bại qua Slack/Email. Nếu có task lỗi thì notify cũng fail để run được đánh dấu failed |

```powershell
docker compose up -d --build     # http://localhost:8081  (user: admin, mật khẩu: AIRFLOW_ADMIN_PASSWORD, mặc định admin)
docker compose logs -f airflow
docker compose down
```

- Airflow chạy một container duy nhất (`airflow standalone`). vnstock và dbt nằm trong một virtualenv riêng (`/opt/pipeline-venv`) để không xung đột dependency với Airflow.
- **Kết nối Supabase từ Docker:** host `db.<ref>.supabase.co` chỉ có IPv6, mà Docker Desktop không đi ra được IPv6. Vì vậy container dùng **Session Pooler** (IPv4). Thêm vào `.env`:
  ```dotenv
  SUPABASE_POOLER_HOST=aws-0-<region>.pooler.supabase.com
  SUPABASE_POOLER_USER=postgres.<project-ref>
  ```
  Giá trị lấy ở Supabase Dashboard → Connect → Session pooler.
- **Thông báo** (không bắt buộc, thêm vào `.env`): `SLACK_WEBHOOK_URL`, hoặc `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `NOTIFY_EMAIL_TO` (Gmail thì dùng App Password). Nếu không cấu hình thì thông báo chỉ được ghi vào log của task.
- **Chạy tay / backfill:** vào *Trigger DAG w/ config*, truyền `{"force": true}` để bỏ qua bước kiểm tra ngày, hoặc `{"full_refresh": true}` để lấy lại toàn bộ giá từ `START_DATE`.
- Port 8081 được chọn để không đụng Airflow của project khác đang dùng 8080. Có thể đổi bằng biến `AIRFLOW_PORT`.

## Analytics & BI

**Streamlit** ([app/streamlit_app.py](app/streamlit_app.py)) đọc tầng Gold và có 4 tab: giá và hiệu suất tương đối, định giá P/E và P/B theo ngày, tài chính theo quý, khối ngoại.

```powershell
pip install -r app/requirements.txt
streamlit run app/streamlit_app.py      # đọc DATABASE_URL từ .env
```

Khi deploy lên Streamlit Community Cloud, đặt `DATABASE_URL` trong *Secrets* và dùng chuỗi kết nối Session Pooler (IPv4).

**Power BI:** xem [docs/powerbi.md](docs/powerbi.md), gồm cách kết nối, các quan hệ trong mô hình, measure DAX và gợi ý các trang báo cáo.

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
