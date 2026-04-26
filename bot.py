import os
import json
import time
import requests
import threading
from flask import Flask, request, jsonify

app = Flask(__name__)

# ── AYARLAR ──
TG_TOKEN = os.environ.get('TG_TOKEN', '')
TG_CHAT_ID = os.environ.get('TG_CHAT_ID', '')
CLAUDE_KEY = os.environ.get('CLAUDE_KEY', '')
ALLOWED_CHAT = TG_CHAT_ID  # Sadece senin kanalın

# ── YARDIMCI FONKSİYONLAR ──
def tg_send(text, chat_id=None):
    chat = chat_id or TG_CHAT_ID
    try:
        requests.post(
            f'https://api.telegram.org/bot{TG_TOKEN}/sendMessage',
            json={'chat_id': chat, 'text': text, 'parse_mode': 'HTML'},
            timeout=10
        )
    except Exception as e:
        print(f'TG send error: {e}')

def claude(prompt, max_tokens=300):
    try:
        res = requests.post(
            'https://api.anthropic.com/v1/messages',
            headers={
                'Content-Type': 'application/json',
                'x-api-key': CLAUDE_KEY,
                'anthropic-version': '2023-06-01'
            },
            json={
                'model': 'claude-haiku-4-5-20251001',
                'max_tokens': max_tokens,
                'messages': [{'role': 'user', 'content': prompt}]
            },
            timeout=15
        )
        data = res.json()
        return data.get('content', [{}])[0].get('text', '').strip()
    except Exception as e:
        print(f'Claude error: {e}')
        return ''

def binance_price(symbol):
    symbol = symbol.upper().replace('USDT','').replace('/','').strip()
    urls_to_try = [
        f'https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}USDT',
        f'https://api1.binance.com/api/v3/ticker/24hr?symbol={symbol}USDT',
    ]
    for url in urls_to_try:
        try:
            res = requests.get(url, timeout=8, headers={'User-Agent': 'TradingBot/1.0'})
            if res.status_code != 200:
                continue
            d = res.json()
            if 'lastPrice' not in d:
                continue
            return {
                'price': float(d['lastPrice']),
                'change': float(d['priceChangePercent']),
                'volume': float(d['quoteVolume']) / 1e6,
                'high': float(d['highPrice']),
                'low': float(d['lowPrice'])
            }
        except Exception as e:
            print(f'binance_price error: {e}')
            continue
    return None

def binance_klines(symbol, interval='1h', limit=20):
    symbol = symbol.upper().replace('USDT','').replace('/','').strip()
    try:
        res = requests.get(
            f'https://api.binance.com/api/v3/klines?symbol={symbol}USDT&interval={interval}&limit={limit}',
            timeout=8,
            headers={'User-Agent': 'TradingBot/1.0'}
        )
        if res.status_code == 200:
            return res.json()
        return []
    except Exception as e:
        print(f'binance_klines error: {e}')
        return []

def calc_rsi(klines, period=14):
    try:
        closes = [float(k[4]) for k in klines]
        if len(closes) < period + 1:
            return 50
        gains, losses = [], []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i-1]
            gains.append(max(diff, 0))
            losses.append(max(-diff, 0))
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        if avg_loss == 0:
            return 100
        rs = avg_gain / avg_loss
        return round(100 - (100 / (1 + rs)), 1)
    except:
        return 50

def fear_greed():
    try:
        res = requests.get('https://api.alternative.me/fng/?limit=1', timeout=5)
        d = res.json()
        return d['data'][0]['value'], d['data'][0]['value_classification']
    except:
        return '—', '—'

# ── KOMUT İŞLEYİCİLER ──
def cmd_analiz(sym):
    sym = sym.replace('USDT', '').replace('/', '').upper()
    if not sym:
        sym = 'BTC'
    d = binance_price(sym)
    if not d:
        return f'❌ {sym} verisi alınamadı. Coin adını kontrol et.'
    klines = binance_klines(sym)
    rsi = calc_rsi(klines)
    price_str = f"${d['price']:,.0f}" if d['price'] > 100 else f"${d['price']:.4f}"
    prompt = f"""Kripto trader asistanısın. {sym}/USDT için Türkçe kısa analiz yaz. Max 200 karakter, emoji kullan.
Fiyat: {price_str}, 24s: %{d['change']:.2f}, Hacim: ${d['volume']:.1f}M, RSI: {rsi}
24s Yüksek: ${d['high']:.4f}, Düşük: ${d['low']:.4f}
Sadece analizi yaz."""
    ai = claude(prompt, 200)
    return f"""🔬 <b>{sym}/USDT ANALİZ</b>

💰 {price_str}
📊 24s: <b>{'+'if d['change']>0 else ''}{d['change']:.2f}%</b>
📈 RSI: <b>{rsi}</b>
💧 Hacim: ${d['volume']:.1f}M
📉 24s: {f"${d['low']:.4f}"} — {f"${d['high']:.4f}"}

🤖 <i>{ai}</i>

⏰ Trading Hub Pro Bot"""

def cmd_risk(usdt_str, leverage_str):
    try:
        usdt = float(usdt_str) if usdt_str else 100
        lev = float(leverage_str) if leverage_str else 10
    except:
        usdt, lev = 100, 10
    pos = usdt * lev
    liq_pct = round(100 / lev * 0.85, 1)
    tp1 = round(usdt * 2, 1)
    tp2 = round(usdt * 4, 1)
    return f"""💰 <b>RİSK HESABI</b>

💵 Teminat: <b>${usdt}</b>
⚡ Kaldıraç: <b>{lev}x</b>
📊 Pozisyon: <b>${pos:,.0f}</b>
💥 Likidasyon: <b>-%{liq_pct}</b>
🎯 TP1 (1:2): <b>+${tp1}</b>
🎯 TP2 (1:4): <b>+${tp2}</b>

⚠️ Max risk: Sermayenin %1-2'si"""

def cmd_tahmin(sym):
    sym = sym.replace('USDT', '').upper()
    if not sym:
        sym = 'BTC'
    d = binance_price(sym)
    klines_4h = binance_klines(sym, '4h', 10)
    if not d:
        return f'❌ {sym} verisi alınamadı.'
    rsi = calc_rsi(klines_4h)
    closes_4h = [float(k[4]) for k in klines_4h]
    trend = 'yukarı' if closes_4h and closes_4h[-1] > closes_4h[0] else 'aşağı'
    price_str = f"${d['price']:,.0f}" if d['price'] > 100 else f"${d['price']:.4f}"
    prompt = f"""Kripto analistsin. {sym}/USDT için 24 saatlik beklenti yaz. Türkçe, max 180 karakter, emoji kullan.
Fiyat: {price_str}, RSI: {rsi}, 4H trend: {trend}, 24s değişim: %{d['change']:.2f}
Risk uyarısı ekle. Sadece tahmini yaz."""
    ai = claude(prompt, 180)
    return f"""🔮 <b>{sym}/USDT 24s TAHMİN</b>

💰 Şu an: {price_str}
📊 RSI: {rsi} | 4H: {trend}
📈 24s: {'+'if d['change']>0 else ''}{d['change']:.2f}%

🤖 <i>{ai}</i>

⚠️ Yatırım tavsiyesi değildir.
⏰ Trading Hub Pro Bot"""

def cmd_haber():
    try:
        import feedparser
        feeds = [
            'https://cointelegraph.com/rss',
            'https://coindesk.com/arc/outboundfeeds/rss/'
        ]
        items = []
        for url in feeds:
            feed = feedparser.parse(url)
            for entry in feed.entries[:3]:
                items.append(entry.title)
            if len(items) >= 5:
                break
        if not items:
            return '📰 Haberler alınamadı.'
        titles_text = ' | '.join(items[:5])
        prompt = f"""Bu kripto haberlerini Türkçe özetle. Max 200 karakter. Piyasaya etkisini belirt. Emoji kullan.
{titles_text[:400]}"""
        ai = claude(prompt, 200)
        news_list = '\n'.join([f'• {t[:70]}' for t in items[:5]])
        return f"""📰 <b>SON KRİPTO HABERLERİ</b>

{news_list}

🤖 <i>{ai}</i>

⏰ Trading Hub Pro Bot"""
    except Exception as e:
        return f'📰 Haberler alınamadı: {str(e)}'

def cmd_neal():
    pairs = ['BTC', 'ETH', 'BNB', 'SOL', 'XRP', 'DOGE', 'ADA', 'AVAX', 'DOT', 'LINK']
    signals = []
    for sym in pairs:
        try:
            klines = binance_klines(sym, '1h', 20)
            if not klines:
                continue
            rsi = calc_rsi(klines)
            closes = [float(k[4]) for k in klines]
            cur = closes[-1]
            # EMA 20
            ema = closes[0]
            k_val = 2 / (20 + 1)
            for c in closes:
                ema = c * k_val + ema * (1 - k_val)
            signal = 'LONG' if cur > ema and rsi < 60 else 'SHORT' if cur < ema and rsi > 40 else None
            if signal:
                score = 0
                if signal == 'LONG' and rsi < 45: score += 2
                if signal == 'SHORT' and rsi > 55: score += 2
                if signal == 'LONG' and cur > ema * 1.001: score += 1
                if signal == 'SHORT' and cur < ema * 0.999: score += 1
                signals.append({'sym': sym, 'signal': signal, 'rsi': rsi, 'score': score})
        except:
            continue
    signals.sort(key=lambda x: x['score'], reverse=True)
    top = signals[:3]
    if not top:
        return '📊 Şu an güçlü sinyal bulunamadı.'
    prompt = f"""Kripto trader asistanısın. Bu sinyallerden hangisi en iyi? Türkçe, max 150 karakter.
{' | '.join([f"{s['sym']} {s['signal']} RSI:{s['rsi']}" for s in top])}"""
    ai = claude(prompt, 150)
    list_txt = '\n'.join([f"{i+1}. <b>{s['sym']}</b> {'📈' if s['signal']=='LONG' else '📉'} {s['signal']} | RSI:{s['rsi']}" for i, s in enumerate(top)])
    return f"""🏆 <b>EN GÜÇLÜ SİNYALLER</b>

{list_txt}

🤖 <i>{ai}</i>

⏰ Trading Hub Pro Bot"""

def cmd_piyasa():
    fg_val, fg_label = fear_greed()
    btc = binance_price('BTC')
    eth = binance_price('ETH')
    prompt = f"""Kripto piyasası için Türkçe kısa genel değerlendirme yaz. Max 180 karakter, emoji kullan.
BTC: ${btc['price']:,.0f} (%{btc['change']:.2f}), ETH: ${eth['price']:,.0f} (%{eth['change']:.2f}), F&G: {fg_val} ({fg_label})"""
    ai = claude(prompt, 180)
    btc_str = f"${btc['price']:,.0f}" if btc else '—'
    eth_str = f"${eth['price']:,.0f}" if eth else '—'
    return f"""📊 <b>PİYASA GENEL DURUM</b>

₿ BTC: <b>{btc_str}</b> {'+'if btc and btc['change']>0 else ''}{btc['change']:.2f if btc else 0}%
Ξ ETH: <b>{eth_str}</b> {'+'if eth and eth['change']>0 else ''}{eth['change']:.2f if eth else 0}%
😰 F&G: <b>{fg_val} — {fg_label}</b>

🤖 <i>{ai}</i>

⏰ Trading Hub Pro Bot"""

def cmd_yardim():
    return """🤖 <b>Trading Hub Pro Bot — Komutlar</b>

/analiz [COIN] — Detaylı analiz
Örnek: /analiz BTC

/neal — En güçlü sinyaller

/risk [USDT] [KALDIRAÇ] — Risk hesabı
Örnek: /risk 100 10

/tahmin [COIN] — 24 saatlik tahmin
Örnek: /tahmin ETH

/haber — Son kripto haberleri

/piyasa — Genel piyasa durumu

/yardim — Bu menü

━━━━━━━━━━━━━━━━━━━━
📱 Trading Hub Pro v21
🤖 Claude AI destekli"""

# ── TELEGRAM POLLING ──
offset = 0

def process_update(update):
    msg = update.get('message', {})
    text = msg.get('text', '')
    chat_id = str(msg.get('chat', {}).get('id', ''))
    if not text or not text.startswith('/'):
        return
    parts = text.strip().split()
    cmd = parts[0].lower().split('@')[0]
    args = parts[1:]
    print(f'Komut: {cmd} | Args: {args} | Chat: {chat_id}')
    try:
        if cmd == '/analiz':
            reply = cmd_analiz(args[0] if args else 'BTC')
        elif cmd in ['/neal', '/ne_al']:
            reply = cmd_neal()
        elif cmd == '/risk':
            reply = cmd_risk(args[0] if args else '100', args[1] if len(args)>1 else '10')
        elif cmd == '/tahmin':
            reply = cmd_tahmin(args[0] if args else 'BTC')
        elif cmd == '/haber':
            reply = cmd_haber()
        elif cmd == '/piyasa':
            reply = cmd_piyasa()
        elif cmd in ['/yardim', '/start', '/help']:
            reply = cmd_yardim()
        else:
            reply = f'❓ Bilinmeyen komut: {cmd}\n\n' + cmd_yardim()
        tg_send(reply, chat_id)
    except Exception as e:
        print(f'Komut hatası: {e}')
        tg_send(f'❌ Hata oluştu: {str(e)[:100]}', chat_id)

def polling_loop():
    global offset
    print('Bot polling başladı...')
    while True:
        try:
            res = requests.get(
                f'https://api.telegram.org/bot{TG_TOKEN}/getUpdates',
                params={'offset': offset + 1, 'timeout': 30},
                timeout=35
            )
            data = res.json()
            if data.get('ok') and data.get('result'):
                for update in data['result']:
                    offset = update['update_id']
                    threading.Thread(target=process_update, args=(update,), daemon=True).start()
        except Exception as e:
            print(f'Polling hata: {e}')
            time.sleep(5)

# ── FLASK ENDPOINTS ──
@app.route('/')
def home():
    return jsonify({'status': 'Trading Hub Pro Bot çalışıyor ✅', 'version': 'v21'})

@app.route('/health')
def health():
    return jsonify({'ok': True})

@app.route('/webhook', methods=['POST'])
def webhook():
    """Trading Hub Pro APK'dan gelen sinyaller"""
    data = request.json
    if not data:
        return jsonify({'ok': False})
    signal_type = data.get('signal', '')
    coin = data.get('coin', '')
    price = data.get('price', '')
    msg_parts = [f'⚔️ <b>ARMY SİNYAL — {signal_type}</b>', f'📊 {coin}', f'💰 ${price}']
    if data.get('tp'):
        msg_parts.append(f'🎯 TP: ${data["tp"]}')
    if data.get('sl'):
        msg_parts.append(f'🛡 SL: ${data["sl"]}')
    tg_send('\n'.join(msg_parts))
    return jsonify({'ok': True})

if __name__ == '__main__':
    # Polling thread başlat
    poll_thread = threading.Thread(target=polling_loop, daemon=True)
    poll_thread.start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
