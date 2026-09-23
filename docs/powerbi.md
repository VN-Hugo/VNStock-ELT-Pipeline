# Kết nối Power BI với tầng Gold

Power BI đọc trực tiếp schema `gold` trên Supabase (PostgreSQL). Tầng Gold đã tính sẵn mọi chỉ số, nên Power BI chỉ cần dựng quan hệ và viết vài measure.

## 1. Kết nối

0. **Cài chứng chỉ CA của Supabase (làm một lần).** Nếu bỏ qua bước này, Power BI sẽ báo
   `The remote certificate is invalid according to the validation procedure`. Lý do là Supabase ký
   chứng chỉ bằng CA riêng (*Supabase Root 2021 CA*), mà CA này không có sẵn trong Windows.
   - Supabase Dashboard → **Project Settings → Database → SSL Configuration → Download certificate** (file `prod-ca-2021.crt`).
   - PowerShell (không cần quyền Admin, chỉ cài cho user hiện tại):
     ```powershell
     Import-Certificate -FilePath "$HOME\Downloads\prod-ca-2021.crt" -CertStoreLocation Cert:\CurrentUser\Root
     ```
     Windows sẽ hỏi xác nhận. Kiểm tra tên chứng chỉ là *Supabase Root 2021 CA* rồi bấm **Yes**.
   - Tắt hẳn Power BI Desktop rồi mở lại.
   - Không nên tắt *Encrypt connection* để né lỗi, vì khi đó mật khẩu và dữ liệu sẽ đi qua mạng mà không được mã hoá.
1. Power BI Desktop → **Get data** → **PostgreSQL database**.
2. **Server:** dùng Session Pooler (IPv4), vì host `db.<ref>.supabase.co` chỉ có IPv6:
   `aws-0-<region>.pooler.supabase.com:5432` (lấy ở Supabase Dashboard → Connect → Session pooler).
   **Database:** `postgres`.
3. **Data connectivity mode:** *Import*. Dữ liệu mỗi ngày chỉ cập nhật một lần sau 15:30, nên Import nhanh hơn DirectQuery.
4. Đăng nhập kiểu *Database*: user `postgres.<project-ref>` cùng mật khẩu database.
5. Chọn các bảng trong `gold`: `dim_companies`, `dim_date`, `fact_stock_prices`, `fact_financial_statements`, `mart_stock_daily`.

> Nên tạo một role chỉ có quyền đọc cho BI thay vì dùng user `postgres`:
> ```sql
> CREATE ROLE bi_reader LOGIN PASSWORD '<mật khẩu mạnh>';
> GRANT USAGE ON SCHEMA gold TO bi_reader;
> GRANT SELECT ON ALL TABLES IN SCHEMA gold TO bi_reader;
> ALTER DEFAULT PRIVILEGES IN SCHEMA gold GRANT SELECT ON TABLES TO bi_reader;
> ```
> Khi đăng nhập qua pooler, user sẽ là `bi_reader.<project-ref>`.

## 2. Mô hình (Model view)

| Từ (nhiều) | Đến (một) | Cột |
|---|---|---|
| `fact_stock_prices` | `dim_companies` | `symbol` |
| `fact_stock_prices` | `dim_date` | `trading_date` → `date_key` |
| `fact_financial_statements` | `dim_companies` | `symbol` |
| `fact_financial_statements` | `dim_date` | `quarter_end_date` → `date_key` |

- Đánh dấu `dim_date` là **Date table** (Table tools → Mark as date table → `date_key`).
- Có thể dùng riêng `mart_stock_daily` như một bảng phẳng cho các trang tổng quan, không cần quan hệ.
- Lọc theo `dim_date[is_trading_day] = TRUE` để biểu đồ đường không bị gãy ở cuối tuần và ngày lễ.

## 3. Measure gợi ý (DAX)

```DAX
Giá đóng cửa (đ) = SUM ( fact_stock_prices[close] ) * 1000

-- Dùng trong visual có symbol trên trục hoặc legend (tính riêng từng mã)
Lợi nhuận kỳ =
VAR FirstDay = FIRSTNONBLANK ( dim_date[date_key], CALCULATE ( SUM ( fact_stock_prices[close] ) ) )
VAR LastDay  = LASTNONBLANK  ( dim_date[date_key], CALCULATE ( SUM ( fact_stock_prices[close] ) ) )
RETURN
    DIVIDE (
        CALCULATE ( SUM ( fact_stock_prices[close] ), dim_date[date_key] = LastDay ),
        CALCULATE ( SUM ( fact_stock_prices[close] ), dim_date[date_key] = FirstDay )
    ) - 1

GTGD (tỷ đ) = DIVIDE ( SUM ( fact_stock_prices[traded_value_vnd] ), 1e9 )

Khối ngoại mua ròng (cp) = SUM ( fact_stock_prices[foreign_net_vol] )

P/E hiện tại =
CALCULATE ( AVERAGE ( mart_stock_daily[pe_daily] ), LASTDATE ( mart_stock_daily[trading_date] ) )
```

## 4. Trang báo cáo gợi ý

1. **Tổng quan thị trường:** thẻ KPI (giá, % thay đổi, P/E) theo mã, biểu đồ đường hiệu suất tương đối, bảng xếp hạng lợi nhuận kỳ.
2. **Định giá:** P/E và P/B theo ngày (`mart_stock_daily`), scatter ROE với P/B.
3. **Tài chính:** cột doanh thu và lợi nhuận theo quý, tăng trưởng YoY. Lọc riêng ngân hàng (`is_bank`), vì doanh thu của ngân hàng là tổng thu nhập hoạt động.
4. **Khối ngoại:** cột mua/bán ròng theo ngày, bảng room còn lại (`dim_companies[foreign_room_pct]`).

## Lưu ý khi đọc số

- `close`, `open`... là **giá đã điều chỉnh**, đơn vị **nghìn đồng**.
- Dữ liệu khối ngoại chỉ có từ ngày pipeline bắt đầu chụp bảng giá, các ngày trước để trống.
- Muốn ghép BCTC với giá thì dùng `available_date`, hoặc dùng luôn `mart_stock_daily`, để tránh look-ahead bias.
