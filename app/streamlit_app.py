"""VNStock analytics app on top of the dbt Gold layer in Supabase.

    streamlit run app/streamlit_app.py

Connection: DATABASE_URL (or PGHOST/PGUSER/PGPASSWORD...) from the environment / .env,
or `DATABASE_URL` in .streamlit/secrets.toml when deployed on Streamlit Community Cloud.
"""
from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote_plus

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

# Categorical slots in fixed order; a symbol keeps its color whatever the filter selects.
SERIES_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
POSITIVE, NEGATIVE = "#2a78d6", "#e34948"  # diverging poles for net foreign flow
MUTED = "#8a8984"

st.set_page_config(page_title="VNStock Analytics", page_icon="📈", layout="wide")


def _database_url() -> str:
    try:
        if "DATABASE_URL" in st.secrets:
            return st.secrets["DATABASE_URL"]
    except FileNotFoundError:
        pass
    if os.getenv("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    host, user, password = os.getenv("PGHOST"), os.getenv("PGUSER"), os.getenv("PGPASSWORD")
    if not (host and user and password):
        st.error("Chưa cấu hình kết nối database: đặt DATABASE_URL trong .env hoặc .streamlit/secrets.toml.")
        st.stop()
    return (
        f"postgresql://{quote_plus(user)}:{quote_plus(password)}@{host}:{os.getenv('PGPORT', '5432')}"
        f"/{os.getenv('PGDATABASE', 'postgres')}?sslmode=require"
    )


@st.cache_resource
def _engine():
    return create_engine(_database_url(), pool_pre_ping=True)


@st.cache_data(ttl=3600, show_spinner="Đang tải dữ liệu từ Supabase...")
def load_data() -> dict[str, pd.DataFrame]:
    with _engine().connect() as conn:
        daily = pd.read_sql("SELECT * FROM gold.mart_stock_daily ORDER BY symbol, trading_date", conn, parse_dates=["trading_date"])
        financials = pd.read_sql("SELECT * FROM gold.fact_financial_statements ORDER BY symbol, report_year, report_quarter", conn)
        companies = pd.read_sql("SELECT * FROM gold.dim_companies ORDER BY symbol", conn)
    return {"daily": _decimals_to_float(daily), "financials": _decimals_to_float(financials), "companies": _decimals_to_float(companies)}


def _decimals_to_float(frame: pd.DataFrame) -> pd.DataFrame:
    """Postgres NUMERIC arrives as decimal.Decimal objects; convert those columns to floats."""
    from decimal import Decimal

    for column in frame.columns:
        values = frame[column].dropna()
        if frame[column].dtype == object and not values.empty and isinstance(values.iloc[0], Decimal):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def _layout(fig: go.Figure, title: str, yaxis_title: str = "", height: int = 380) -> go.Figure:
    fig.update_layout(
        title=title, height=height, hovermode="x unified", margin=dict(l=10, r=10, t=50, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1),
        yaxis_title=yaxis_title,
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.15)", zeroline=False)
    return fig


def _pct(value: float | None) -> str:
    return "—" if value is None or pd.isna(value) else f"{value:+.2%}"


data = load_data()
daily, financials, companies = data["daily"], data["financials"], data["companies"]
if daily.empty:
    st.warning("Gold chưa có dữ liệu. Hãy chạy pipeline (Airflow DAG `vnstock_elt`) trước.")
    st.stop()

all_symbols = sorted(daily["symbol"].unique())
color_of = {symbol: SERIES_COLORS[i % len(SERIES_COLORS)] for i, symbol in enumerate(all_symbols)}

# ---- Filters: one row above the charts ----
st.title("📈 VNStock Analytics")
st.caption(f"Nguồn: Supabase `gold` · dữ liệu đến {daily['trading_date'].max():%d/%m/%Y} · giá đã điều chỉnh, đơn vị nghìn đồng")
filter_symbols, filter_range, filter_focus = st.columns([3, 2, 1])
symbols = filter_symbols.multiselect("Mã cổ phiếu", all_symbols, default=all_symbols)
range_label = filter_range.segmented_control("Khoảng thời gian", ["1T", "3T", "6T", "1N", "YTD", "Tất cả"], default="6T")
focus = filter_focus.selectbox("Mã chi tiết", symbols or all_symbols)
if not symbols:
    st.info("Chọn ít nhất một mã.")
    st.stop()

end = daily["trading_date"].max()
start = {
    "1T": end - timedelta(days=30), "3T": end - timedelta(days=91), "6T": end - timedelta(days=182),
    "1N": end - timedelta(days=365), "YTD": pd.Timestamp(end.year, 1, 1),
}.get(range_label or "Tất cả", daily["trading_date"].min())
view = daily[daily["symbol"].isin(symbols) & (daily["trading_date"] >= start)]

# ---- Stat tiles: latest session per symbol ----
latest = view.sort_values("trading_date").groupby("symbol").tail(1).set_index("symbol")
tiles = st.columns(len(symbols))
for tile, symbol in zip(tiles, symbols):
    if symbol not in latest.index:
        continue
    row = latest.loc[symbol]
    tile.metric(
        label=f"{symbol} · {row['exchange']}",
        value=f"{row['close'] * 1000:,.0f} đ",
        delta=_pct(row["daily_return"]),
        help=f"P/E {row['pe_daily']:.1f} · P/B {row['pb_daily']:.2f}" if pd.notna(row["pe_daily"]) else None,
    )

tab_price, tab_valuation, tab_fundamentals, tab_foreign = st.tabs(["Giá & hiệu suất", "Định giá", "Tài chính", "Khối ngoại"])

with tab_price:
    left, right = st.columns(2)
    # Relative performance: every symbol rebased to 100 so they share one axis
    fig = go.Figure()
    for symbol in symbols:
        s = view[view["symbol"] == symbol]
        if s.empty:
            continue
        rebased = s["close"] / s["close"].iloc[0] * 100
        fig.add_trace(go.Scatter(x=s["trading_date"], y=rebased, name=symbol, mode="lines",
                                 line=dict(color=color_of[symbol], width=2),
                                 hovertemplate="%{y:.1f}"))
    fig.add_hline(y=100, line=dict(color=MUTED, width=1, dash="dot"))
    left.plotly_chart(_layout(fig, "Hiệu suất tương đối (đầu kỳ = 100)"), width="stretch")

    s = view[view["symbol"] == focus]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=s["trading_date"], y=s["close"], name="Giá đóng cửa", line=dict(color=color_of[focus], width=2)))
    fig.add_trace(go.Scatter(x=s["trading_date"], y=s["ma_20"], name="MA20", line=dict(color=MUTED, width=1.5)))
    fig.add_trace(go.Scatter(x=s["trading_date"], y=s["ma_50"], name="MA50", line=dict(color=MUTED, width=1.5, dash="dash")))
    right.plotly_chart(_layout(fig, f"{focus}: giá và đường trung bình", "nghìn đồng"), width="stretch")

    summary = view.groupby("symbol").agg(
        first_close=("close", "first"), last_close=("close", "last"),
        volatility_20=("volatility_20", "last"), avg_value=("traded_value_vnd", "mean"),
    )
    summary["return"] = summary["last_close"] / summary["first_close"] - 1
    running_max = view.groupby("symbol")["close"].cummax()
    summary["max_drawdown"] = (view["close"] / running_max - 1).groupby(view["symbol"]).min()
    st.dataframe(
        summary[["return", "max_drawdown", "volatility_20", "avg_value"]],
        column_config={
            "return": st.column_config.NumberColumn("Lợi nhuận kỳ", format="percent"),
            "max_drawdown": st.column_config.NumberColumn("Sụt giảm tối đa", format="percent"),
            "volatility_20": st.column_config.NumberColumn("Biến động 20 phiên (năm hoá)", format="percent"),
            "avg_value": st.column_config.NumberColumn("GTGD trung bình (đ)", format="compact"),
        },
        width="stretch",
    )

with tab_valuation:
    left, right = st.columns(2)
    for column, title, target in [("pe_daily", "P/E theo ngày", left), ("pb_daily", "P/B theo ngày", right)]:
        fig = go.Figure()
        for symbol in symbols:
            s = view[view["symbol"] == symbol]
            fig.add_trace(go.Scatter(x=s["trading_date"], y=s[column], name=symbol, mode="lines",
                                     line=dict(color=color_of[symbol], width=2), hovertemplate="%{y:.2f}"))
        target.plotly_chart(_layout(fig, title), width="stretch")
    st.caption("P/E, P/B theo ngày = vốn hoá hằng ngày / lợi nhuận TTM (hoặc giá trị sổ sách) của BCTC **đã công bố** tại ngày đó "
               "(ghép theo `available_date` = cuối quý + 45 ngày, tránh look-ahead bias).")
    st.dataframe(
        latest[["company_name", "industry", "market_cap_vnd", "pe_daily", "pb_daily", "roe", "net_margin", "latest_report_period"]],
        column_config={
            "company_name": "Công ty", "industry": "Ngành",
            "market_cap_vnd": st.column_config.NumberColumn("Vốn hoá (đ)", format="compact"),
            "pe_daily": st.column_config.NumberColumn("P/E", format="%.2f"),
            "pb_daily": st.column_config.NumberColumn("P/B", format="%.2f"),
            "roe": st.column_config.NumberColumn("ROE", format="percent"),
            "net_margin": st.column_config.NumberColumn("Biên LN ròng", format="percent"),
            "latest_report_period": "Kỳ BCTC",
        },
        width="stretch",
    )

with tab_fundamentals:
    f = financials[financials["symbol"] == focus].copy()
    if bool(companies.set_index("symbol").get("is_bank", pd.Series(dtype=bool)).get(focus, False)):
        st.info(f"{focus} là ngân hàng: \"doanh thu\" là tổng thu nhập hoạt động, chỉ nên so sánh với ngân hàng khác.")
    left, right = st.columns(2)
    for column, title, target in [("revenue", "Doanh thu theo quý", left), ("profit", "Lợi nhuận sau thuế theo quý", right)]:
        fig = go.Figure(go.Bar(
            x=f["report_period"], y=f[column] / 1e9, marker=dict(color=color_of[focus], cornerradius=4),
            customdata=f[f"{column}_growth_yoy"], hovertemplate="%{y:,.0f} tỷ đ<br>YoY %{customdata:+.1%}<extra></extra>",
        ))
        target.plotly_chart(_layout(fig, f"{focus}: {title}", "tỷ đồng"), width="stretch")
    st.dataframe(
        f[["report_period", "available_date", "revenue_growth_yoy", "profit_growth_yoy", "pe_ratio", "pb_ratio", "roe", "net_margin"]],
        column_config={
            "report_period": "Kỳ", "available_date": "Ngày dùng được",
            "revenue_growth_yoy": st.column_config.NumberColumn("DT YoY", format="percent"),
            "profit_growth_yoy": st.column_config.NumberColumn("LN YoY", format="percent"),
            "roe": st.column_config.NumberColumn("ROE", format="percent"),
            "net_margin": st.column_config.NumberColumn("Biên LN ròng", format="percent"),
        },
        hide_index=True, width="stretch",
    )

with tab_foreign:
    flows = view[view["foreign_net_vol"].notna()]
    if flows.empty:
        st.info("Chưa có dữ liệu khối ngoại trong khoảng này. Pipeline chụp bảng giá mỗi ngày giao dịch, "
                "nên lịch sử chỉ bắt đầu từ ngày chạy đầu tiên.")
    else:
        s = flows[flows["symbol"] == focus]
        fig = go.Figure(go.Bar(
            x=s["trading_date"], y=s["foreign_net_vol"],
            marker=dict(color=[POSITIVE if v >= 0 else NEGATIVE for v in s["foreign_net_vol"]], cornerradius=4),
            hovertemplate="Mua ròng %{y:,.0f} cp<extra></extra>",
        ))
        fig.add_hline(y=0, line=dict(color=MUTED, width=1))
        st.plotly_chart(_layout(fig, f"{focus}: khối ngoại mua/bán ròng (cổ phiếu) · xanh = mua ròng, đỏ = bán ròng"), width="stretch")
    st.dataframe(
        companies.set_index("symbol").loc[symbols, ["foreign_ownership_pct", "foreign_ownership_limit_pct", "foreign_room_pct"]],
        column_config={
            "foreign_ownership_pct": st.column_config.NumberColumn("Sở hữu nước ngoài", format="percent"),
            "foreign_ownership_limit_pct": st.column_config.NumberColumn("Giới hạn (room tối đa)", format="percent"),
            "foreign_room_pct": st.column_config.NumberColumn("Room còn lại", format="percent"),
        },
        width="stretch",
    )
