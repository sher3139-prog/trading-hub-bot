import os
import time
import requests
import threading
from flask import Flask, request, jsonify

app = Flask(__name__)

TG_TOKEN = os.environ.get('TG_TOKEN', '')
TG_CHAT_ID = os.environ.get('TG_CHAT_ID', '')
CLAUDE_KEY = os.environ.get('CLAUDE_KEY', '')

def tg_send(text, chat_id=None):
    chat = chat_id or TG_CHAT_ID
    try:
        requests.post(
            f'https://api.telegram.org/bot{TG_TOKEN}/sendMessage',
            json={'chat_id': chat, 'text': text, 'parse_mode': 'HTML'},
            timeout=10
        )
    except Exception as e:
        print(f'TG error: {e}')

def claude_ai(prompt, max_tokens=200):
    if not CLAUDE_KEY:
        return ''
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
        d = res.json()
        return d.get('content', [{}])[0].get('text', '').strip()
    except Exception as e:
        print(f'Claude error: {e}')
        return ''

def get_price(sym):
    sym = sym.upper().replace('USDT','').replace('/','').strip()
    try:
        res = requests.get(
            f'https://api.binance.com/api/v3/ticker/24hr?symbol={sym}USDT',
            timeout=8
        )
        d = res.json()
        if 'lastPrice' not in d:
            print(f'Binance error {sym}: {d}')
            return None
        return {
            'sym': sym,
            'price': float(d['lastPrice']),
            'change': float(d['priceChangePercent']),
            'volume': float(d['quoteVolume']) / 1e6,
            'high': float(d['highPrice']),
            'low': float(d['lowPrice'])
        }
    except Exception as e:
        print(f'get_price error {sym}: {e}')
        return None

def get_klines(sym, interval='1h', limit=20):
    sym = sym.upper().replace('USDT','').replace('/','').strip()
    try:
        res = requests.get(
            f'https://api.binance.com/api/v3/klines?symbol={sym}USDT&interval={interval}&limit={limit}',
            timeout=8
        )
        return res.json()
    except Exception as e:
        print(f'get_klines error {sym}: {e}')
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
        ag = sum(gains[-period:]) / period
        al = sum(losses[-period:]) / period
        if al == 0:
            return 100
        return round(100 - (100 / (1 + ag/al)), 1)
    except:
        return 50

def get_fg():
    try:
        res = requests.get('https://api.alternative.me/fng/?limit=1', timeout=5)
        d = res.json()
        return d['data'][0]['value'], d['data'][0]['value_classification']
    except:
        return '—', '—'

def fmt_price(p):
    if p is None:
        return '$—'
    return f'${p:,.0f}' if p > 100 else f'${p:.4f}'

def cmd_analiz(sym):
    sym = sym.upper().replace('USDT','').replace('/','').strip() or 'BTC'
    d = get_price(sym)
    if not d:
        return f'❌ <b>{sym}</b> verisi alınamadı.\nÖrnek: /analiz ETH'
    klines = get_klines(sym)
    rsi = calc_rsi(klines)
    price_str = fmt_price(d['price'])
    sign = '+' if d['change'] > 0 else ''
    prompt = f"Kripto trader asistanısın. {sym}/USDT Türkçe kısa analiz, max 150 karakter, emoji. Fiyat:{price_str} 24s:{sign}{d['change']:.2f}% Hacim:${d['volume']:.1f}M RSI:{rsi}"
    ai = claude_ai(prompt, 150)
    result = f"🔬 <b>{sym}/USDT ANALİZ</b>\n\n"
    result += f"💰 {price_str}\n"
    result += f"📊 24s: <b>{sign}{d['change']:.2f}%</b>\n"
    result += f"📈 RSI: <b>{rsi}</b>\n"
    result += f"💧 Hacim: ${d['volume']:.1f}M\n"
    result += f"📉 Aralık: {fmt_price(d['low'])} — {fmt_price(d['high'])}"
    if ai:
        result += f"\n\n🤖 <i>{ai}</i>"
    result += "\n\n⏰ Trading Hub Pro Bot"
    return result

def cmd_risk(usdt_str, lev_str):
    try:
        usdt = float(usdt_str) if usdt_str else 100
        lev = float(lev_str) if lev_str else 10
    except:
        usdt, lev = 100, 10
    pos = usdt * lev
    liq = round(100 / lev * 0.85, 1)
    result = f"💰 <b>RİSK HESABI</b>\n\n"
    result += f"💵 Teminat: <b>${usdt:,.0f}</b>\n"
    result += f"⚡ Kaldıraç: <b>{lev}x</b>\n"
    result += f"📊 Pozisyon: <b>${pos:,.0f}</b>\n"
    result += f"💥 Likidasyon: <b>-%{liq}</b>\n"
    result += f"🎯 TP1 (1:2): <b>+${usdt*2:,.0f}</b>\n"
    result += f"🎯 TP2 (1:4): <b>+${usdt*4:,.0f}</b>\n\n"
    result += f"⚠️ Max risk: Sermayenin %1-2'si"
    return result

def cmd_tahmin(sym):
    sym = sym.upper().replace('USDT','').replace('/','').strip() or 'BTC'
    d = get_price(sym)
    if not d:
        return f'❌ {sym} verisi alınamadı.'
    klines = get_klines(sym, '4h', 10)
    rsi = calc_rsi(klines)
    closes = [float(k[4]) for k in klines] if klines else []
    trend = 'yukarı' if len(closes) > 1 and closes[-1] > closes[0] else 'aşağı'
    sign = '+' if d['change'] > 0 else ''
    prompt = f"{sym}/USDT 24s tahmin. Türkçe, max 150 karakter, emoji, risk uyarısı ekle. Fiyat:{fmt_price(d['price'])} RSI:{rsi} 4H:{trend} 24s:{sign}{d['change']:.2f}%"
    ai = claude_ai(prompt, 150)
    result = f"🔮 <b>{sym}/USDT 24s TAHMİN</b>\n\n"
    result += f"💰 {fmt_price(d['price'])}\n"
    result += f"📊 RSI: {rsi} | 4H: {trend}\n"
    result += f"📈 24s: {sign}{d['change']:.2f}%"
    if ai:
        result += f"\n\n🤖 <i>{ai}</i>"
    result += "\n\n⚠️ Yatırım tavsiyesi değildir."
    return result

def cmd_piyasa():
    btc = get_price('BTC')
    eth = get_price('ETH')
    fg_val, fg_label = get_fg()
    btc_str = fmt_price(btc['price']) if btc else '—'
    eth_str = fmt_price(eth['price']) if eth else '—'
    btc_chg = f"{'+' if btc and btc['change']>0 else ''}{btc['change']:.2f}%" if btc else '—'
    eth_chg = f"{'+' if eth and eth['change']>0 else ''}{eth['change']:.2f}%" if eth else '—'
    prompt = f"Kripto piyasası genel durum. Türkçe, max 150 karakter, emoji. BTC:{btc_str}({btc_chg}) ETH:{eth_str}({eth_chg}) F&G:{fg_val}"
    ai = claude_ai(prompt, 150)
    result = f"📊 <b>PİYASA GENEL DURUM</b>\n\n"
    result += f"₿ BTC: <b>{btc_str}</b> {btc_chg}\n"
    result += f"Ξ ETH: <b>{eth_str}</b> {eth_chg}\n"
    result += f"😰 F&G: <b>{fg_val} — {fg_label}</b>"
    if ai:
        result += f"\n\n🤖 <i>{ai}</i>"
    result += "\n\n⏰ Trading Hub Pro Bot"
    return result

def cmd_neal():
    pairs = ['BTC','ETH','BNB','SOL','XRP','DOGE','ADA','AVAX','DOT','LINK']
    signals = []
    for sym in pairs:
        try:
            klines = get_klines(sym, '1h', 20)
            if not klines:
                continue
            rsi = calc_rsi(klines)
            closes = [float(k[4]) for k in klines]
            cur = closes[-1]
            ema = closes[0]
            k_val = 2/(20+1)
            for c in closes:
                ema = c*k_val + ema*(1-k_val)
            if cur > ema and rsi < 60:
                sig = 'LONG'
            elif cur < ema and rsi > 40:
                sig = 'SHORT'
            else:
                continue
            score = 0
            if sig=='LONG' and rsi < 45: score += 2
            if sig=='SHORT' and rsi > 55: score += 2
            signals.append({'sym':sym,'signal':sig,'rsi':rsi,'score':score})
        except:
            continue
    signals.sort(key=lambda x: x['score'], reverse=True)
    top = signals[:3]
    if not top:
        return '📊 Şu an güçlü sinyal bulunamadı.'
    list_txt = '\n'.join([
        f"{i+1}. <b>{s['sym']}</b> {'📈' if s['signal']=='LONG' else '📉'} {s['signal']} | RSI:{s['rsi']}"
        for i,s in enumerate(top)
    ])
    prompt = f"Bu sinyallerden en iyi hangisi? Türkçe, max 100 karakter, emoji. {' | '.join([s['sym']+' '+s['signal'] for s in top])}"
    ai = claude_ai(prompt, 100)
    result = f"🏆 <b>EN GÜÇLÜ SİNYALLER</b>\n\n{list_txt}"
    if ai:
        result += f"\n\n🤖 <i>{ai}</i>"
    result += "\n\n⏰ Trading Hub Pro Bot"
    return result

def cmd_haber():
    try:
        import feedparser
        items = []
        for url in ['https://cointelegraph.com/rss','https://coindesk.com/arc/outboundfeeds/rss/']:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:3]:
                    items.append(entry.title)
                if len(items) >= 5:
                    break
            except:
                continue
        if not items:
            return '📰 Haberler alınamadı.'
        news_list = '\n'.join([f'• {t[:70]}' for t in items[:5]])
        prompt = f"Bu kripto haberleri Türkçe özetle. Max 150 karakter, emoji. {' | '.join(items[:3])[:300]}"
        ai = claude_ai(prompt, 150)
        result = f"📰 <b>SON KRİPTO HABERLERİ</b>\n\n{news_list}"
        if ai:
            result += f"\n\n🤖 <i>{ai}</i>"
        result += "\n\n⏰ Trading Hub Pro Bot"
        return result
    except Exception as e:
        return f'📰 Haberler alınamadı: {str(e)[:50]}'

def cmd_yardim():
    return (
        "🤖 <b>Trading Hub Pro Bot — Komutlar</b>\n\n"
        "/analiz BTC — Detaylı analiz\n"
        "/neal — En güçlü sinyaller\n"
        "/risk 100 10 — Risk hesabı\n"
        "/tahmin ETH — 24s tahmin\n"
        "/haber — Son haberler\n"
        "/piyasa — Genel piyasa\n"
        "/yardim — Bu menü\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📱 Trading Hub Pro v21\n"
        "🤖 Claude AI destekli"
    )

offset = 0

def process_update(update):
    chat_id = ''
    try:
        msg = update.get('message', {})
        text = msg.get('text', '').strip()
        chat_id = str(msg.get('chat', {}).get('id', ''))
        if not text or not text.startswith('/'):
            return
        parts = text.split()
        cmd = parts[0].lower().split('@')[0]
        args = parts[1:]
        print(f'CMD:{cmd} ARGS:{args} CHAT:{chat_id}')
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
            reply = f'❓ Bilinmeyen komut: <code>{cmd}</code>\n\n' + cmd_yardim()
        tg_send(reply, chat_id)
    except Exception as e:
        print(f'process_update error: {e}')
        if chat_id:
            tg_send(f'❌ Hata oluştu: {str(e)[:100]}', chat_id)

def polling_loop():
    global offset
    print('✅ Bot polling başladı...')
    while True:
        try:
            res = requests.get(
                f'https://api.telegram.org/bot{TG_TOKEN}/getUpdates',
                params={'offset': offset+1, 'timeout': 25},
                timeout=30
            )
            data = res.json()
            if data.get('ok') and data.get('result'):
                for upd in data['result']:
                    offset = upd['update_id']
                    threading.Thread(target=process_update, args=(upd,), daemon=True).start()
        except Exception as e:
            print(f'Polling error: {e}')
            time.sleep(5)

@app.route('/')
def home():
    return jsonify({'status': 'Trading Hub Pro Bot ✅', 'version': 'v21'})

@app.route('/health')
def health():
    return jsonify({'ok': True})

if __name__ == '__main__':
    threading.Thread(target=polling_loop, daemon=True).start()
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
