import os
import sys
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone, timedelta

import yfinance as yf
from dotenv import load_dotenv

load_dotenv()

TICKERS = ['META', 'SLM', 'NVDA', 'FMCC', 'FNMA', 'UBER', 'TSLA', 'GOOG', 'AMD', 'AMZN', 'TSM', 'ASML']
GMAIL_USER = os.environ['GMAIL_USER']
GMAIL_APP_PASSWORD = os.environ['GMAIL_APP_PASSWORD']
TO_EMAIL = 'harrisonsade@gmail.com'

# open  = morning briefing, last 24h news (overnight)
# close = end-of-day briefing, last 10h news (full trading day)
MODE = 'close' if '--close' in sys.argv else 'open'
NEWS_LOOKBACK_HOURS = 10 if MODE == 'close' else 24


def fmt_price(val):
    if val is None:
        return 'N/A'
    return f'${val:,.2f}'


def fmt_market_cap(val):
    if val is None:
        return 'N/A'
    if val >= 1e12:
        return f'${val / 1e12:.2f}T'
    if val >= 1e9:
        return f'${val / 1e9:.2f}B'
    return f'${val / 1e6:.0f}M'


def get_stock_data(symbol):
    try:
        t = yf.Ticker(symbol)
        hist = t.history(period='5d')
        if hist.empty:
            print(f'  {symbol}: no history returned')
            return None

        price = hist['Close'].iloc[-1]
        prev_close = hist['Close'].iloc[-2] if len(hist) >= 2 else price
        change = price - prev_close
        change_pct = (change / prev_close * 100) if prev_close else 0

        # Day range from today's session
        day_high = hist['High'].iloc[-1]
        day_low = hist['Low'].iloc[-1]
        volume = hist['Volume'].iloc[-1]

        try:
            info = t.fast_info
            market_cap = getattr(info, 'market_cap', None)
            week_high = getattr(info, 'fifty_two_week_high', None)
            week_low = getattr(info, 'fifty_two_week_low', None)
        except Exception:
            market_cap = week_high = week_low = None

        cutoff = datetime.now(timezone.utc) - timedelta(hours=NEWS_LOOKBACK_HOURS)
        articles = []
        try:
            for item in (t.news or []):
                if not isinstance(item, dict):
                    continue
                pub_ts = item.get('providerPublishTime', 0)
                pub_dt = datetime.fromtimestamp(pub_ts, tz=timezone.utc)
                if pub_dt >= cutoff:
                    articles.append({
                        'title': item.get('title', ''),
                        'publisher': item.get('publisher', ''),
                        'link': item.get('link', ''),
                        'time': pub_dt.strftime('%b %d, %I:%M %p ET'),
                    })
        except Exception as e:
            print(f'  {symbol}: news fetch error: {e}')

        return {
            'symbol': symbol,
            'price': price,
            'change': change,
            'change_pct': change_pct,
            'market_cap': market_cap,
            'week_high': week_high,
            'week_low': week_low,
            'day_high': day_high,
            'day_low': day_low,
            'volume': volume,
            'news': articles[:6],
        }
    except Exception as e:
        print(f'  {symbol}: error: {e}')
        return None


def fmt_volume(val):
    if val is None:
        return 'N/A'
    if val >= 1e6:
        return f'{val / 1e6:.2f}M'
    if val >= 1e3:
        return f'{val / 1e3:.0f}K'
    return str(int(val))


def build_html(stocks):
    today = datetime.now().strftime('%A, %B %d, %Y')
    valid = [s for s in stocks if s is not None]

    is_close = MODE == 'close'
    header_label = 'Market Close Briefing' if is_close else 'Morning Portfolio Briefing'
    header_sub = 'Final prices &middot; Full day headlines &middot; Data via Yahoo Finance' if is_close else 'Prices as of previous close &middot; Overnight headlines &middot; Data via Yahoo Finance'
    delivery_note = 'Delivered at 1:00 PM PT &middot; Market Close' if is_close else 'Delivered at 6:31 AM PT &middot; Market Open'

    # Portfolio snapshot table rows
    table_rows = ''
    for s in valid:
        color = '#16a34a' if s['change_pct'] >= 0 else '#dc2626'
        arrow = '&#9650;' if s['change_pct'] >= 0 else '&#9660;'
        sign = '+' if s['change'] >= 0 else ''
        vol = fmt_volume(s.get('volume'))
        day_range = f"{fmt_price(s.get('day_low'))} &ndash; {fmt_price(s.get('day_high'))}"
        table_rows += f"""
            <tr style="border-bottom:1px solid #f1f5f9;">
                <td style="padding:11px 16px;font-weight:700;font-size:14px;color:#111827;">{s['symbol']}</td>
                <td style="padding:11px 16px;font-size:14px;color:#374151;">{fmt_price(s['price'])}</td>
                <td style="padding:11px 16px;font-size:14px;font-weight:600;color:{color};">{arrow} {abs(s['change_pct']):.2f}%</td>
                <td style="padding:11px 16px;font-size:14px;font-weight:600;color:{color};">{sign}{fmt_price(s['change'])}</td>
                <td style="padding:11px 16px;font-size:13px;color:#6b7280;">{day_range}</td>
                <td style="padding:11px 16px;font-size:13px;color:#6b7280;">{vol}</td>
                <td style="padding:11px 16px;font-size:14px;color:#6b7280;">{fmt_market_cap(s['market_cap'])}</td>
            </tr>"""

    # Per-stock news cards
    news_cards = ''
    for s in valid:
        color = '#16a34a' if s['change_pct'] >= 0 else '#dc2626'
        bg = '#f0fdf4' if s['change_pct'] >= 0 else '#fff1f2'
        arrow = '&#9650;' if s['change_pct'] >= 0 else '&#9660;'
        sign = '+' if s['change'] >= 0 else ''
        week_range = (f"{fmt_price(s['week_low'])} &ndash; {fmt_price(s['week_high'])}"
                      if s['week_low'] and s['week_high'] else 'N/A')

        if s['news']:
            articles_html = ''
            for a in s['news']:
                articles_html += f"""
                <tr>
                    <td style="padding:10px 0;border-bottom:1px solid #f1f5f9;vertical-align:top;">
                        <a href="{a['link']}" style="color:#1d4ed8;text-decoration:none;font-size:14px;font-weight:500;line-height:1.4;">{a['title']}</a>
                        <div style="color:#9ca3af;font-size:12px;margin-top:4px;">{a['publisher']} &middot; {a['time']}</div>
                    </td>
                </tr>"""
            news_body = f'<table style="width:100%;border-collapse:collapse;">{articles_html}</table>'
        else:
            window = "today's session" if is_close else "the past 24 hours"
            news_body = f'<p style="color:#9ca3af;font-size:13px;font-style:italic;margin:0;">No headlines during {window}.</p>'

        news_cards += f"""
        <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e5e7eb;border-radius:12px;margin-bottom:16px;background:#ffffff;border-collapse:separate;">
            <tr>
                <td style="padding:18px 20px;border-bottom:1px solid #e5e7eb;background:{bg};border-radius:12px 12px 0 0;">
                    <table width="100%" cellpadding="0" cellspacing="0">
                        <tr>
                            <td>
                                <span style="font-size:18px;font-weight:800;color:#111827;">{s['symbol']}</span>
                                <span style="font-size:17px;color:#374151;margin-left:10px;">{fmt_price(s['price'])}</span>
                                <span style="font-size:15px;color:{color};font-weight:600;margin-left:8px;">{arrow} {abs(s['change_pct']):.2f}% ({sign}{fmt_price(s['change'])})</span>
                            </td>
                            <td style="text-align:right;font-size:12px;color:#6b7280;white-space:nowrap;">
                                Mkt Cap: {fmt_market_cap(s['market_cap'])}<br>
                                52-Wk: {week_range}
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
            <tr>
                <td style="padding:14px 20px;">
                    <div style="font-size:11px;font-weight:700;color:#9ca3af;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:10px;">Headlines</div>
                    {news_body}
                </td>
            </tr>
        </table>"""

    headlines_label = "Today's Headlines" if is_close else "Overnight Headlines"

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;">
<tr><td align="center" style="padding:24px 12px;">
<table width="700" cellpadding="0" cellspacing="0" style="max-width:700px;width:100%;">

    <!-- Header -->
    <tr>
        <td style="background:linear-gradient(135deg,#0f172a 0%,#1e3a5f 100%);border-radius:16px;padding:28px 32px;">
            <div style="color:#94a3b8;font-size:12px;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px;">{header_label}</div>
            <div style="color:#ffffff;font-size:24px;font-weight:800;">{today}</div>
            <div style="color:#64748b;font-size:13px;margin-top:6px;">{header_sub}</div>
        </td>
    </tr>

    <tr><td style="height:20px;"></td></tr>

    <!-- Snapshot Table -->
    <tr>
        <td style="background:#ffffff;border:1px solid #e5e7eb;border-radius:12px;overflow:hidden;">
            <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
                <tr style="background:#f8fafc;">
                    <td style="padding:12px 16px;font-size:11px;font-weight:700;color:#9ca3af;text-transform:uppercase;letter-spacing:0.06em;">Ticker</td>
                    <td style="padding:12px 16px;font-size:11px;font-weight:700;color:#9ca3af;text-transform:uppercase;letter-spacing:0.06em;">Price</td>
                    <td style="padding:12px 16px;font-size:11px;font-weight:700;color:#9ca3af;text-transform:uppercase;letter-spacing:0.06em;">Chg %</td>
                    <td style="padding:12px 16px;font-size:11px;font-weight:700;color:#9ca3af;text-transform:uppercase;letter-spacing:0.06em;">Chg $</td>
                    <td style="padding:12px 16px;font-size:11px;font-weight:700;color:#9ca3af;text-transform:uppercase;letter-spacing:0.06em;">Day Range</td>
                    <td style="padding:12px 16px;font-size:11px;font-weight:700;color:#9ca3af;text-transform:uppercase;letter-spacing:0.06em;">Volume</td>
                    <td style="padding:12px 16px;font-size:11px;font-weight:700;color:#9ca3af;text-transform:uppercase;letter-spacing:0.06em;">Mkt Cap</td>
                </tr>
                {table_rows}
            </table>
        </td>
    </tr>

    <tr><td style="height:24px;"></td></tr>

    <!-- Section label -->
    <tr>
        <td style="font-size:12px;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:0.06em;padding-bottom:12px;">
            {headlines_label}
        </td>
    </tr>

    <!-- News Cards -->
    <tr><td>{news_cards}</td></tr>

    <!-- Footer -->
    <tr>
        <td style="text-align:center;color:#94a3b8;font-size:12px;padding:16px 0 8px;border-top:1px solid #e5e7eb;">
            {delivery_note} &middot; Juno Capital Partners
        </td>
    </tr>

</table>
</td></tr>
</table>
</body>
</html>"""


def send_email(html):
    label = 'Market Close Briefing' if MODE == 'close' else 'Morning Briefing'
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f'{label} — {datetime.now().strftime("%b %d, %Y")}'
    msg['From'] = GMAIL_USER
    msg['To'] = TO_EMAIL
    msg.attach(MIMEText(html, 'html'))

    with smtplib.SMTP('smtp.gmail.com', 587) as server:
        server.ehlo()
        server.starttls()
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, TO_EMAIL, msg.as_string())

    print(f'Email sent to {TO_EMAIL}')


def main():
    label = 'close' if MODE == 'close' else 'open'
    print(f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] Mode: {label} | Fetching {len(TICKERS)} tickers...')
    stocks = [get_stock_data(t) for t in TICKERS]
    print('Building email...')
    html = build_html(stocks)
    print('Sending...')
    send_email(html)
    print('Done.')


if __name__ == '__main__':
    main()
