import os
import time
import requests
import threading
import json
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

TG_TOKEN = os.environ.get('TG_TOKEN', '')
TG_CHAT_ID = os.environ.get('TG_CHAT_ID', '')
CLAUDE_KEY = os.environ.get('CLAUDE_KEY', '')

# ── YARDIMCI ──
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

def ai(prompt, max_tokens=200):
    if not CLAUDE_KEY:
        return ''
    try:
        res = requests.post(
            'https://api.anthropic.com/v1/messages',
            headers={'Content-Type':'application/json','x-api-key':CLAUDE_KEY,'anthropic-version':'2023-06-01'},
            json={'model':'claude-haiku-4-5-20251001','max_tokens':max_tokens,'messages':[{'role':'user','content':prompt}]},
            timeout=15
        )
        return res.json().get('content',[{}])[0].get('text','').strip()
    except Exception as e:
        print(f'AI error: {e}')
        return ''

def get_price(sym):
    sym = sym.upper().replace('USDT','').replace('/','').strip()
    try:
        res = requests.get(f'https://api.binance.com/api/v3/ticker/24hr?symbol={sym}USDT', timeout=8)
        d = res.json()
        if 'lastPrice' not in d:
            return None
        return {'sym':sym,'price':float(d['lastPrice']),'change':float(d['priceChangePercent']),'volume':float(d['quoteVolume'])/1e6,'high':float(d['highPrice']),'low':float(d['lowPrice'])}
    except Exception as e:
        print(f'get_price {sym}: {e}')
        return None

def get_klines(sym, interval='1h', limit=20):
    sym = sym.upper().replace('USDT','').replace('/','').strip()
    try:
        res = requests.get(f'https://api.binance.com/api/v3/klines?symbol={sym}USDT&interval={interval}&limit={limit}', timeout=8)
        return res.json()
    except:
        return []

def calc_rsi(klines, period=14):
    try:
        closes = [float(k[4]) for k in klines]
        if len(closes) < period+1:
            return 50
        gains,losses = [],[]
        for i in range(1,len(closes)):
            diff = closes[i]-closes[i-1]
            gains.append(max(diff,0))
            losses.append(max(-diff,0))
        ag = sum(gains[-period:])/period
        al = sum(losses[-period:])/period
        return round(100-(100/(1+ag/al)),1) if al else 100
    except:
        return 50

def get_fg():
    try:
        res = requests.get('https://api.alternative.me/fng/?limit=1', timeout=5)
        d = res.json()
        return d['data'][0]['value'], d['data'][0]['value_classification']
    except:
        return '—','—'

def get_top24(sort='change', direction='desc', limit=5):
    try:
        res = requests.get('https://api.binance.com/api/v3/ticker/24hr', timeout=10)
        data = res.json()
        usdt = [d for d in data if d['symbol'].endswith('USDT') and not d['symbol'].startswith('UP') and not d['symbol'].startswith('DOWN')]
        usdt.sort(key=lambda x: float(x.get(sort,'0')), reverse=(direction=='desc'))
        return usdt[:limit]
    except:
        return []

def fmt(p):
    if p is None: return '$—'
    return f'${p:,.0f}' if p>100 else f'${p:.4f}'

def sign(n):
    return '+' if n>0 else ''

# ── KULLANICI VERİSİ ──
user_data = {}  # chat_id → {'lang':'tr','alarms':[],'scores':[],'silent':False}

def get_user(chat_id):
    if chat_id not in user_data:
        user_data[chat_id] = {'lang':'tr','alarms':[],'scores':[],'silent':False,'streak':0,'wins':0,'losses':0}
    return user_data[chat_id]

LANGS = {
    'tr': {'analiz':'🔬 ANALİZ','tahmin':'🔮 TAHMİN','piyasa':'📊 PİYASA','risk':'💰 RİSK',
           'kazanan':'🟢 KAZANANLAR','kaybeden':'🔴 KAYBEDENLER','hacim':'💧 EN YÜKSEK HACİM',
           'strateji':'🎯 GÜNLÜK STRATEJİ','plan':'📅 HAFTALIK PLAN','egit':'📚 DERS',
           'psikoloji':'🧘 PSİKOLOJİ','ozet':'📋 ÖZET','funding':'⚠️ FUNDING RATE',
           'dominans':'₿ BTC DOMİNANSI','destek':'📐 DESTEK/DİRENÇ',
           'korelasyon':'🔗 KORELASYON','no_data':'Veri alınamadı','bot_name':'Trading Hub Pro Bot'},
    'ru': {'analiz':'🔬 АНАЛИЗ','tahmin':'🔮 ПРОГНОЗ','piyasa':'📊 РЫНОК','risk':'💰 РИСК',
           'kazanan':'🟢 ЛИДЕРЫ','kaybeden':'🔴 АУТСАЙДЕРЫ','hacim':'💧 ТОП ОБЪЁМ',
           'strateji':'🎯 СТРАТЕГИЯ ДНЯ','plan':'📅 ПЛАН НЕДЕЛИ','egit':'📚 ОБУЧЕНИЕ',
           'psikoloji':'🧘 ПСИХОЛОГИЯ','ozet':'📋 СВОДКА','funding':'⚠️ ФИНАНСИРОВАНИЕ',
           'dominans':'₿ ДОМИНАЦИЯ BTC','destek':'📐 ПОДДЕРЖКА/СОПРОТИВЛЕНИЕ',
           'korelasyon':'🔗 КОРРЕЛЯЦИЯ','no_data':'Данные недоступны','bot_name':'Trading Hub Pro Bot'},
    'en': {'analiz':'🔬 ANALYSIS','tahmin':'🔮 PREDICTION','piyasa':'📊 MARKET','risk':'💰 RISK',
           'kazanan':'🟢 GAINERS','kaybeden':'🔴 LOSERS','hacim':'💧 TOP VOLUME',
           'strateji':'🎯 DAILY STRATEGY','plan':'📅 WEEKLY PLAN','egit':'📚 LESSON',
           'psikoloji':'🧘 PSYCHOLOGY','ozet':'📋 SUMMARY','funding':'⚠️ FUNDING RATE',
           'dominans':'₿ BTC DOMINANCE','destek':'📐 SUPPORT/RESISTANCE',
           'korelasyon':'🔗 CORRELATION','no_data':'Data unavailable','bot_name':'Trading Hub Pro Bot'},
    'uz': {'analiz':'🔬 TAHLIL','tahmin':'🔮 BASHORAT','piyasa':'📊 BOZOR','risk':'💰 XAVF',
           'kazanan':'🟢 YUTGANLAR','kaybeden':'🔴 YUTQAZGANLAR','hacim':'💧 ENG YUQORI HAJM',
           'strateji':'🎯 KUNLIK STRATEGIYA','plan':'📅 HAFTALIK REJA','egit':'📚 DARS',
           'psikoloji':'🧘 PSIXOLOGIYA','ozet':'📋 XULOSA','funding':'⚠️ MOLIYALASHTIRISH',
           'dominans':'₿ BTC DOMINANSIYA','destek':'📐 QOLAB/QARSHILIK',
           'korelasyon':'🔗 KORRELYATSIYA','no_data':'Maʼlumot yoʼq','bot_name':'Trading Hub Pro Bot'},
}

def L(chat_id, key):
    lang = get_user(chat_id).get('lang','tr')
    return LANGS.get(lang,LANGS['tr']).get(key, LANGS['tr'].get(key,key))

# ── KOMUTLAR ──

def cmd_analiz(sym, chat_id):
    sym = sym.upper().replace('USDT','').replace('/','').strip() or 'BTC'
    d = get_price(sym)
    if not d:
        return f'❌ <b>{sym}</b> {L(chat_id,"no_data")}'
    klines = get_klines(sym)
    rsi = calc_rsi(klines)
    price_str = fmt(d['price'])
    s = sign(d['change'])
    ai_txt = ai(f"Kripto trader asistanısın. {sym}/USDT Türkçe kısa analiz, max 150 karakter, emoji. Fiyat:{price_str} 24s:{s}{d['change']:.2f}% RSI:{rsi}", 150)
    r = f"<b>{L(chat_id,'analiz')} — {sym}/USDT</b>\n\n"
    r += f"💰 {price_str}\n📊 24s: <b>{s}{d['change']:.2f}%</b>\n📈 RSI: <b>{rsi}</b>\n💧 Hacim: ${d['volume']:.1f}M\n📉 {fmt(d['low'])} — {fmt(d['high'])}"
    if ai_txt: r += f"\n\n🤖 <i>{ai_txt}</i>"
    return r + "\n\n⏰ Trading Hub Pro Bot"

def cmd_risk(usdt_str, lev_str, chat_id):
    try: usdt = float(usdt_str) if usdt_str else 100
    except: usdt = 100
    try: lev = float(lev_str) if lev_str else 10
    except: lev = 10
    pos = usdt*lev
    liq = round(100/lev*0.85,1)
    r = f"<b>{L(chat_id,'risk')} HESABI</b>\n\n"
    r += f"💵 Teminat: <b>${usdt:,.0f}</b>\n⚡ Kaldıraç: <b>{lev}x</b>\n📊 Pozisyon: <b>${pos:,.0f}</b>\n"
    r += f"💥 Likidasyon: <b>-%{liq}</b>\n🎯 TP1 (1:2): <b>+${usdt*2:,.0f}</b>\n🎯 TP2 (1:4): <b>+${usdt*4:,.0f}</b>\n"
    r += f"\n⚠️ Max risk: Sermayenin %1-2'si"
    return r

def cmd_tahmin(sym, chat_id):
    sym = sym.upper().replace('USDT','').replace('/','').strip() or 'BTC'
    d = get_price(sym)
    if not d: return f'❌ {sym} {L(chat_id,"no_data")}'
    klines = get_klines(sym,'4h',10)
    rsi = calc_rsi(klines)
    closes = [float(k[4]) for k in klines] if klines else []
    trend = 'yukarı' if len(closes)>1 and closes[-1]>closes[0] else 'aşağı'
    s = sign(d['change'])
    ai_txt = ai(f"{sym}/USDT 24s tahmin. Türkçe, max 150 karakter, emoji, risk uyarısı. Fiyat:{fmt(d['price'])} RSI:{rsi} 4H:{trend} 24s:{s}{d['change']:.2f}%", 150)
    r = f"<b>{L(chat_id,'tahmin')} — {sym}/USDT</b>\n\n"
    r += f"💰 {fmt(d['price'])}\n📊 RSI: {rsi} | 4H: {trend}\n📈 24s: {s}{d['change']:.2f}%"
    if ai_txt: r += f"\n\n🤖 <i>{ai_txt}</i>"
    return r + "\n\n⚠️ Yatırım tavsiyesi değildir."

def cmd_piyasa(chat_id):
    btc = get_price('BTC')
    eth = get_price('ETH')
    bnb = get_price('BNB')
    fg_val, fg_label = get_fg()
    r = f"<b>{L(chat_id,'piyasa')} GENEL DURUM</b>\n\n"
    for coin, d in [('BTC',btc),('ETH',eth),('BNB',bnb)]:
        if d:
            s = sign(d['change'])
            r += f"{'₿' if coin=='BTC' else 'Ξ' if coin=='ETH' else '◆'} {coin}: <b>{fmt(d['price'])}</b> {s}{d['change']:.2f}%\n"
    r += f"😰 F&G: <b>{fg_val} — {fg_label}</b>"
    ai_txt = ai(f"Kripto piyasası genel durum. Türkçe, max 120 karakter, emoji. BTC:{fmt(btc['price']) if btc else '—'} F&G:{fg_val}", 120)
    if ai_txt: r += f"\n\n🤖 <i>{ai_txt}</i>"
    return r + "\n\n⏰ Trading Hub Pro Bot"

def cmd_kazanan(chat_id):
    data = get_top24('priceChangePercent','desc',5)
    if not data: return f'❌ {L(chat_id,"no_data")}'
    r = f"<b>{L(chat_id,'kazanan')} (24s)</b>\n\n"
    for i,d in enumerate(data):
        sym = d['symbol'].replace('USDT','')
        chg = float(d['priceChangePercent'])
        r += f"{i+1}. <b>{sym}</b> 🟢 +{chg:.2f}%\n"
    return r + "\n⏰ Trading Hub Pro Bot"

def cmd_kaybeden(chat_id):
    data = get_top24('priceChangePercent','asc',5)
    if not data: return f'❌ {L(chat_id,"no_data")}'
    r = f"<b>{L(chat_id,'kaybeden')} (24s)</b>\n\n"
    for i,d in enumerate(data):
        sym = d['symbol'].replace('USDT','')
        chg = float(d['priceChangePercent'])
        r += f"{i+1}. <b>{sym}</b> 🔴 {chg:.2f}%\n"
    return r + "\n⏰ Trading Hub Pro Bot"

def cmd_hacim(chat_id):
    data = get_top24('quoteVolume','desc',5)
    if not data: return f'❌ {L(chat_id,"no_data")}'
    r = f"<b>{L(chat_id,'hacim')} (24s)</b>\n\n"
    for i,d in enumerate(data):
        sym = d['symbol'].replace('USDT','')
        vol = float(d['quoteVolume'])/1e6
        chg = float(d['priceChangePercent'])
        r += f"{i+1}. <b>{sym}</b> ${vol:.0f}M {'🟢' if chg>0 else '🔴'}{sign(chg)}{chg:.2f}%\n"
    return r + "\n⏰ Trading Hub Pro Bot"

def cmd_rsi(sym, chat_id):
    sym = sym.upper().replace('USDT','').replace('/','').strip() or 'BTC'
    klines_1h = get_klines(sym,'1h',20)
    klines_4h = get_klines(sym,'4h',20)
    klines_1d = get_klines(sym,'1d',20)
    rsi_1h = calc_rsi(klines_1h)
    rsi_4h = calc_rsi(klines_4h)
    rsi_1d = calc_rsi(klines_1d)
    def rsi_emoji(v):
        if v<=30: return '🟢 Aşırı satım'
        if v>=70: return '🔴 Aşırı alım'
        return '🟡 Nötr'
    return (f"📈 <b>{sym}/USDT RSI ANALİZİ</b>\n\n"
            f"⏰ 1H: <b>{rsi_1h}</b> {rsi_emoji(rsi_1h)}\n"
            f"⏰ 4H: <b>{rsi_4h}</b> {rsi_emoji(rsi_4h)}\n"
            f"⏰ 1D: <b>{rsi_1d}</b> {rsi_emoji(rsi_1d)}\n\n"
            f"⏰ Trading Hub Pro Bot")

def cmd_destek(sym, chat_id):
    sym = sym.upper().replace('USDT','').replace('/','').strip() or 'BTC'
    klines = get_klines(sym,'1d',10)
    if not klines: return f'❌ {sym} {L(chat_id,"no_data")}'
    highs = [float(k[2]) for k in klines]
    lows = [float(k[3]) for k in klines]
    closes = [float(k[4]) for k in klines]
    H,L,C = max(highs),min(lows),closes[-1]
    P = (H+L+C)/3
    R1,R2,R3 = 2*P-L, P+(H-L), H+2*(P-L)
    S1,S2,S3 = 2*P-H, P-(H-L), L-2*(H-P)
    d = get_price(sym)
    cur = d['price'] if d else C
    return (f"<b>{L(chat_id,'destek')} — {sym}/USDT</b>\n\n"
            f"💰 Şu an: {fmt(cur)}\n\n"
            f"🔴 R3: {fmt(R3)}\n🔴 R2: {fmt(R2)}\n🔴 R1: {fmt(R1)}\n"
            f"⚪ <b>Pivot: {fmt(P)}</b>\n"
            f"🟢 S1: {fmt(S1)}\n🟢 S2: {fmt(S2)}\n🟢 S3: {fmt(S3)}\n\n"
            f"⏰ Trading Hub Pro Bot")

def cmd_funding(chat_id):
    pairs = ['BTCUSDT','ETHUSDT','BNBUSDT','SOLUSDT','XRPUSDT','DOGEUSDT']
    r = f"<b>{L(chat_id,'funding')}</b>\n\n"
    for sym in pairs:
        try:
            res = requests.get(f'https://fapi.binance.com/fapi/v1/premiumIndex?symbol={sym}', timeout=5)
            d = res.json()
            rate = float(d['lastFundingRate'])*100
            name = sym.replace('USDT','')
            emoji = '🔴' if rate>0.05 else '🟢' if rate<-0.05 else '⚪'
            r += f"{emoji} <b>{name}</b>: {sign(rate)}{rate:.4f}%\n"
        except:
            continue
    return r + "\n⏰ Trading Hub Pro Bot"

def cmd_dominans(chat_id):
    try:
        res = requests.get('https://api.coingecko.com/api/v3/global', timeout=8)
        d = res.json()['data']
        btc_dom = d['market_cap_percentage']['btc']
        eth_dom = d['market_cap_percentage']['eth']
        total = d['total_market_cap']['usd']/1e12
        r = f"<b>{L(chat_id,'dominans')}</b>\n\n"
        r += f"₿ BTC: <b>{btc_dom:.1f}%</b>\nΞ ETH: <b>{eth_dom:.1f}%</b>\n"
        r += f"💰 Toplam piyasa: <b>${total:.2f}T</b>"
        ai_txt = ai(f"BTC dominansı {btc_dom:.1f}%. Türkçe, max 100 karakter, kripto piyasası için ne anlam ifade eder?", 100)
        if ai_txt: r += f"\n\n🤖 <i>{ai_txt}</i>"
        return r + "\n\n⏰ Trading Hub Pro Bot"
    except Exception as e:
        return f'❌ Dominans verisi alınamadı: {str(e)[:50]}'

def cmd_karsilastir(sym1, sym2, chat_id):
    sym1 = sym1.upper().replace('USDT','').strip() or 'BTC'
    sym2 = sym2.upper().replace('USDT','').strip() or 'ETH'
    d1 = get_price(sym1)
    d2 = get_price(sym2)
    k1 = get_klines(sym1)
    k2 = get_klines(sym2)
    rsi1 = calc_rsi(k1)
    rsi2 = calc_rsi(k2)
    if not d1 or not d2:
        return f'❌ {L(chat_id,"no_data")}'
    winner = sym1 if d1['change'] > d2['change'] else sym2
    r = f"<b>{L(chat_id,'korelasyon')} — {sym1} vs {sym2}</b>\n\n"
    r += f"₿ <b>{sym1}</b>: {fmt(d1['price'])} | {sign(d1['change'])}{d1['change']:.2f}% | RSI:{rsi1}\n"
    r += f"Ξ <b>{sym2}</b>: {fmt(d2['price'])} | {sign(d2['change'])}{d2['change']:.2f}% | RSI:{rsi2}\n\n"
    r += f"🏆 Bugün daha iyi: <b>{winner}</b>"
    ai_txt = ai(f"{sym1} vs {sym2} karşılaştırma. Türkçe, max 120 karakter, emoji. {sym1}:{sign(d1['change'])}{d1['change']:.2f}% RSI:{rsi1} | {sym2}:{sign(d2['change'])}{d2['change']:.2f}% RSI:{rsi2}", 120)
    if ai_txt: r += f"\n\n🤖 <i>{ai_txt}</i>"
    return r + "\n\n⏰ Trading Hub Pro Bot"

def cmd_strateji(chat_id):
    btc = get_price('BTC')
    fg_val, fg_label = get_fg()
    saat = datetime.utcnow().hour
    seans = 'London 🇬🇧' if 7<=saat<13 else 'New York 🇺🇸' if 13<=saat<21 else 'Asya 🌏'
    prompt = f"""Trading koçusun. Bugün için Türkçe kısa strateji önerileri yaz. Max 200 karakter, emoji kullan.
BTC: {fmt(btc['price']) if btc else '—'} ({sign(btc['change']) if btc else ''}{btc['change']:.2f if btc else 0}%)
Fear&Greed: {fg_val} ({fg_label})
Aktif seans: {seans}"""
    ai_txt = ai(prompt, 200)
    r = f"<b>{L(chat_id,'strateji')}</b>\n\n"
    r += f"📅 {datetime.utcnow().strftime('%d.%m.%Y')}\n"
    r += f"⏰ Seans: {seans}\n"
    r += f"😰 F&G: {fg_val} — {fg_label}\n"
    if ai_txt: r += f"\n🤖 <i>{ai_txt}</i>"
    return r + "\n\n⏰ Trading Hub Pro Bot"

def cmd_plan(chat_id):
    prompt = """Kripto trading koçusun. Haftalık trading planı yaz. Türkçe, max 250 karakter, emoji kullan.
Pazartesi-Cuma için günlük odak noktaları, risk yönetimi ve hedefler."""
    ai_txt = ai(prompt, 250)
    r = f"<b>{L(chat_id,'plan')}</b>\n\n"
    if ai_txt: r += f"🤖 <i>{ai_txt}</i>"
    return r + "\n\n⏰ Trading Hub Pro Bot"

def cmd_egit(konu, chat_id):
    konular = {
        'rsi': 'RSI indikatörü nasıl kullanılır?',
        'sl': 'Stop Loss nedir ve nasıl belirlenir?',
        'tp': 'Take Profit nasıl hesaplanır?',
        'ob': 'Order Block nedir?',
        'fvg': 'Fair Value Gap (FVG) nedir?',
        'bos': 'Break of Structure (BOS) nedir?',
        'risk': 'Risk yönetimi temelleri nelerdir?',
        'kaldıraç': 'Kaldıraç kullanımında dikkat edilmesi gerekenler?',
        'psikoloji': 'Trading psikolojisi nasıl yönetilir?',
    }
    konu_lower = konu.lower() if konu else 'rsi'
    soru = konular.get(konu_lower, f'{konu} hakkında kripto trading dersi ver.')
    ai_txt = ai(f"Kripto trading öğretmenisin. {soru} Türkçe, basit, max 250 karakter, emoji kullan.", 250)
    r = f"<b>{L(chat_id,'egit')} — {konu_lower.upper()}</b>\n\n"
    if ai_txt: r += f"📚 <i>{ai_txt}</i>\n\n"
    r += "💡 Konular: rsi, sl, tp, ob, fvg, bos, risk, kaldıraç, psikoloji"
    return r + "\n\n⏰ Trading Hub Pro Bot"

def cmd_psikoloji(chat_id):
    user = get_user(chat_id)
    wins = user.get('wins',0)
    losses = user.get('losses',0)
    streak = user.get('streak',0)
    total = wins + losses
    wr = round(wins/total*100) if total > 0 else 0
    durum = 'kazanç serisinde' if streak > 0 else f'{abs(streak)} kayıp serisi' if streak < 0 else 'nötr'
    prompt = f"Trading psikoloji koçusun. Trader durumu: {wins} kazanç, {losses} kayıp, %{wr} win rate, {durum}. Türkçe, max 200 karakter, empatik ve motive edici."
    ai_txt = ai(prompt, 200)
    r = f"<b>{L(chat_id,'psikoloji')}</b>\n\n"
    r += f"✅ Kazanç: {wins} | ❌ Kayıp: {losses}\n"
    r += f"🏆 Win Rate: %{wr}\n"
    r += f"📊 Durum: {durum}\n"
    if ai_txt: r += f"\n🤖 <i>{ai_txt}</i>"
    return r + "\n\n⏰ Trading Hub Pro Bot"

def cmd_ozet(chat_id):
    btc = get_price('BTC')
    eth = get_price('ETH')
    fg_val, fg_label = get_fg()
    kazanan = get_top24('priceChangePercent','desc',3)
    kaybeden = get_top24('priceChangePercent','asc',3)
    k_list = ', '.join([d['symbol'].replace('USDT','') for d in kazanan])
    kb_list = ', '.join([d['symbol'].replace('USDT','') for d in kaybeden])
    prompt = f"Kripto piyasası günlük özet. Türkçe, max 200 karakter, emoji. BTC:{sign(btc['change']) if btc else ''}{btc['change']:.2f if btc else 0}% ETH:{sign(eth['change']) if eth else ''}{eth['change']:.2f if eth else 0}% F&G:{fg_val} Kazananlar:{k_list} Kaybedenler:{kb_list}"
    ai_txt = ai(prompt, 200)
    r = f"<b>{L(chat_id,'ozet')}</b>\n\n"
    if btc: r += f"₿ BTC: {fmt(btc['price'])} {sign(btc['change'])}{btc['change']:.2f}%\n"
    if eth: r += f"Ξ ETH: {fmt(eth['price'])} {sign(eth['change'])}{eth['change']:.2f}%\n"
    r += f"😰 F&G: {fg_val} — {fg_label}\n"
    r += f"🟢 Kazananlar: {k_list}\n🔴 Kaybedenler: {kb_list}"
    if ai_txt: r += f"\n\n🤖 <i>{ai_txt}</i>"
    return r + "\n\n⏰ Trading Hub Pro Bot"

def cmd_alarm_ekle(sym, fiyat, chat_id):
    sym = sym.upper().replace('USDT','').strip()
    try:
        fiyat_f = float(fiyat)
    except:
        return '❌ Geçersiz fiyat. Örnek: /alarm BTC 95000'
    user = get_user(chat_id)
    d = get_price(sym)
    cur = d['price'] if d else 0
    direction = 'above' if fiyat_f > cur else 'below'
    user['alarms'].append({'sym':sym,'price':fiyat_f,'dir':direction,'chat':chat_id})
    return f"🔔 <b>ALARM KURULDU</b>\n\n📊 {sym}/USDT\n🎯 Hedef: {fmt(fiyat_f)}\n📍 Şu an: {fmt(cur)}\n{'📈 Üstüne çıkınca' if direction=='above' else '📉 Altına inince'} bildirim gelecek.\n\n⏰ Trading Hub Pro Bot"

def cmd_alarmlar(chat_id):
    user = get_user(chat_id)
    alarms = user.get('alarms', [])
    if not alarms:
        return '🔔 Aktif alarminiz yok.\n/alarm BTC 95000 — alarm kur'
    r = "🔔 <b>AKTİF ALARMLARINIZ</b>\n\n"
    for i,a in enumerate(alarms):
        r += f"{i+1}. <b>{a['sym']}</b> {'📈' if a['dir']=='above' else '📉'} {fmt(a['price'])}\n"
    return r + "\n⏰ Trading Hub Pro Bot"

def cmd_alarm_iptal(sym, chat_id):
    sym = sym.upper().replace('USDT','').strip()
    user = get_user(chat_id)
    before = len(user['alarms'])
    user['alarms'] = [a for a in user['alarms'] if a['sym'] != sym]
    after = len(user['alarms'])
    removed = before - after
    if removed > 0:
        return f'✅ {sym} alarmı iptal edildi.'
    return f'❌ {sym} için aktif alarm yok.'

def cmd_dil(lang, chat_id):
    lang = lang.lower()
    valid = {'tr':'Türkçe 🇹🇷','ru':'Русский 🇷🇺','en':'English 🇬🇧','uz':"O'zbek 🇺🇿"}
    if lang not in valid:
        return '❌ Geçersiz dil. Kullanım: /dil tr | ru | en | uz'
    get_user(chat_id)['lang'] = lang
    return f'✅ Dil değiştirildi: <b>{valid[lang]}</b>'

def cmd_sessiz(chat_id):
    user = get_user(chat_id)
    user['silent'] = True
    return '🔕 Bildirimler kapatıldı. Açmak için: /aktif'

def cmd_aktif(chat_id):
    user = get_user(chat_id)
    user['silent'] = False
    return '🔔 Bildirimler açıldı!'

def cmd_skor(chat_id):
    user = get_user(chat_id)
    wins = user.get('wins',0)
    losses = user.get('losses',0)
    total = wins + losses
    wr = round(wins/total*100) if total>0 else 0
    level = '🏆 Pro' if wr>=70 else '⭐ Orta' if wr>=50 else '📚 Başlangıç'
    return (f"🎯 <b>TRADING SKORU</b>\n\n"
            f"✅ Kazanç: {wins}\n❌ Kayıp: {losses}\n"
            f"📊 Win Rate: <b>%{wr}</b>\n"
            f"🏅 Seviye: <b>{level}</b>\n\n"
            f"Sonuçlarını eklemek için:\n/kazandim veya /kaybettim\n\n⏰ Trading Hub Pro Bot")

def cmd_kazandim(chat_id):
    user = get_user(chat_id)
    user['wins'] = user.get('wins',0) + 1
    user['streak'] = user.get('streak',0) + 1 if user.get('streak',0)>=0 else 1
    streak = user['streak']
    msg = f"✅ <b>Kazanç kaydedildi!</b>\n\nToplam kazanç: {user['wins']}"
    if streak >= 3:
        msg += f"\n\n🔥 {streak} kazanç serisi! Harika gidiyorsun!"
    return msg

def cmd_kaybettim(chat_id):
    user = get_user(chat_id)
    user['losses'] = user.get('losses',0) + 1
    user['streak'] = user.get('streak',0) - 1 if user.get('streak',0)<=0 else -1
    streak = abs(user['streak'])
    msg = f"❌ <b>Kayıp kaydedildi.</b>\n\nToplam kayıp: {user['losses']}"
    if streak >= 3:
        msg += f"\n\n⚠️ {streak} kayıp serisi! Mola ver, strateji gözden geçir."
        ai_txt = ai("Trader 3+ kayıp serisi yaşadı. Türkçe, max 100 karakter, empatik ve motive edici.", 100)
        if ai_txt: msg += f"\n\n🤖 <i>{ai_txt}</i>"
    return msg

def cmd_quiz(chat_id):
    sorular = [
        ("RSI 30'un altında ne anlama gelir?", "Aşırı satım (oversold) — alım fırsatı olabilir"),
        ("BTC dominansı yüksekken altcoinler ne yapar?", "Genellikle düşer, BTC baskısı altında kalır"),
        ("Funding rate negatif olunca ne olur?", "Short pozisyonlar uzun pozisyonlara ödeme yapar — long lehine"),
        ("Order Block nedir?", "Kurumsal alıcı/satıcıların büyük emirler bıraktığı mum bölgesi"),
        ("Stop Loss neden önemlidir?", "Kayıpları sınırlar, hesabı korur, disiplin sağlar"),
        ("FVG (Fair Value Gap) nedir?", "Fiyatın hızlı geçtiği ve doldurmaya geldiği boşluk"),
    ]
    import random
    soru, cevap = random.choice(sorular)
    return (f"🎮 <b>KRİPTO QUIZ</b>\n\n"
            f"❓ <b>{soru}</b>\n\n"
            f"<tg-spoiler>💡 Cevap: {cevap}</tg-spoiler>\n\n"
            f"⏰ Trading Hub Pro Bot")

def cmd_neal(chat_id):
    pairs = ['BTC','ETH','BNB','SOL','XRP','DOGE','ADA','AVAX','DOT','LINK']
    signals = []
    for sym in pairs:
        try:
            klines = get_klines(sym,'1h',20)
            if not klines: continue
            rsi = calc_rsi(klines)
            closes = [float(k[4]) for k in klines]
            cur = closes[-1]
            ema = closes[0]
            k_val = 2/(20+1)
            for c in closes: ema = c*k_val + ema*(1-k_val)
            if cur>ema and rsi<60: sig = 'LONG'
            elif cur<ema and rsi>40: sig = 'SHORT'
            else: continue
            score = 0
            if sig=='LONG' and rsi<45: score+=2
            if sig=='SHORT' and rsi>55: score+=2
            signals.append({'sym':sym,'signal':sig,'rsi':rsi,'score':score})
        except: continue
    signals.sort(key=lambda x:x['score'],reverse=True)
    top = signals[:3]
    if not top: return '📊 Şu an güçlü sinyal bulunamadı.'
    list_txt = '\n'.join([f"{i+1}. <b>{s['sym']}</b> {'📈' if s['signal']=='LONG' else '📉'} {s['signal']} | RSI:{s['rsi']}" for i,s in enumerate(top)])
    ai_txt = ai(f"En iyi sinyal hangisi? Türkçe, max 100 karakter. {' | '.join([s['sym']+' '+s['signal'] for s in top])}", 100)
    r = f"🏆 <b>EN GÜÇLÜ SİNYALLER</b>\n\n{list_txt}"
    if ai_txt: r += f"\n\n🤖 <i>{ai_txt}</i>"
    return r + "\n\n⏰ Trading Hub Pro Bot"

def cmd_haber(chat_id):
    try:
        import feedparser
        items = []
        for url in ['https://cointelegraph.com/rss','https://coindesk.com/arc/outboundfeeds/rss/']:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:3]:
                    items.append(entry.title)
                if len(items)>=5: break
            except: continue
        if not items: return '📰 Haberler alınamadı.'
        news_list = '\n'.join([f'• {t[:70]}' for t in items[:5]])
        ai_txt = ai(f"Bu kripto haberleri Türkçe özetle. Max 150 karakter, emoji. {' | '.join(items[:3])[:300]}", 150)
        r = f"📰 <b>SON KRİPTO HABERLERİ</b>\n\n{news_list}"
        if ai_txt: r += f"\n\n🤖 <i>{ai_txt}</i>"
        return r + "\n\n⏰ Trading Hub Pro Bot"
    except Exception as e:
        return f'📰 Haberler alınamadı: {str(e)[:50]}'

def cmd_yardim(chat_id):
    return (
        "🤖 <b>Trading Hub Pro Bot — Komutlar</b>\n\n"
        "<b>📊 ANALİZ</b>\n"
        "/analiz BTC — Detaylı analiz\n"
        "/rsi ETH — RSI analizi\n"
        "/destek SOL — Destek/Direnç\n"
        "/karsilastir BTC ETH — Karşılaştır\n\n"
        "<b>📈 PİYASA</b>\n"
        "/piyasa — Genel durum\n"
        "/kazanan — En çok yükselenler\n"
        "/kaybeden — En çok düşenler\n"
        "/hacim — En yüksek hacimler\n"
        "/funding — Funding rate\n"
        "/dominans — BTC dominansı\n"
        "/ozet — Günlük özet\n\n"
        "<b>💡 SİNYAL & TAHMİN</b>\n"
        "/neal — En güçlü sinyaller\n"
        "/tahmin BTC — 24s tahmin\n\n"
        "<b>💰 HESAP</b>\n"
        "/risk 100 10 — Risk hesabı\n\n"
        "<b>🔔 ALARM</b>\n"
        "/alarm BTC 95000 — Alarm kur\n"
        "/alarmlar — Aktif alarmlar\n"
        "/alarmiptal BTC — İptal\n\n"
        "<b>🧠 AI & EĞİTİM</b>\n"
        "/strateji — Günlük strateji\n"
        "/plan — Haftalık plan\n"
        "/egit rsi — Ders al\n"
        "/psikoloji — Ruh hali analizi\n"
        "/quiz — Kripto sorusu\n\n"
        "<b>🎯 TAKİP</b>\n"
        "/kazandim — Kazanç ekle\n"
        "/kaybettim — Kayıp ekle\n"
        "/skor — Trading skorum\n\n"
        "<b>⚙️ AYARLAR</b>\n"
        "/dil tr|ru|en|uz — Dil seç\n"
        "/sessiz — Bildirimleri kapat\n"
        "/aktif — Bildirimleri aç\n"
        "/yardim — Bu menü\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📱 Trading Hub Pro v21\n"
        "🤖 Claude AI destekli"
    )

# ── ALARM KONTROL (arka plan) ──
def check_alarms_loop():
    while True:
        try:
            for chat_id, user in list(user_data.items()):
                if user.get('silent'): continue
                for alarm in list(user.get('alarms',[])):
                    d = get_price(alarm['sym'])
                    if not d: continue
                    cur = d['price']
                    hit = (alarm['dir']=='above' and cur>=alarm['price']) or (alarm['dir']=='below' and cur<=alarm['price'])
                    if hit:
                        tg_send(f"🔔 <b>ALARM TETİKLENDİ!</b>\n\n📊 <b>{alarm['sym']}/USDT</b>\n💰 {fmt(cur)}\n🎯 Hedef: {fmt(alarm['price'])}\n{'📈 Üstüne çıktı!' if alarm['dir']=='above' else '📉 Altına indi!'}\n\n⏰ Trading Hub Pro Bot", alarm['chat'])
                        user['alarms'].remove(alarm)
        except Exception as e:
            print(f'Alarm check error: {e}')
        time.sleep(30)

# ── POLLING ──
offset = 0

def process_update(update):
    chat_id = ''
    try:
        msg = update.get('message',{})
        text = msg.get('text','').strip()
        chat_id = str(msg.get('chat',{}).get('id',''))
        if not text or not text.startswith('/'): return
        parts = text.split()
        cmd = parts[0].lower().split('@')[0]
        args = parts[1:]
        print(f'CMD:{cmd} ARGS:{args}')

        if cmd=='/analiz': reply=cmd_analiz(args[0] if args else 'BTC',chat_id)
        elif cmd=='/rsi': reply=cmd_rsi(args[0] if args else 'BTC',chat_id)
        elif cmd=='/destek': reply=cmd_destek(args[0] if args else 'BTC',chat_id)
        elif cmd=='/karsilastir': reply=cmd_karsilastir(args[0] if args else 'BTC',args[1] if len(args)>1 else 'ETH',chat_id)
        elif cmd=='/piyasa': reply=cmd_piyasa(chat_id)
        elif cmd=='/kazanan': reply=cmd_kazanan(chat_id)
        elif cmd=='/kaybeden': reply=cmd_kaybeden(chat_id)
        elif cmd=='/hacim': reply=cmd_hacim(chat_id)
        elif cmd=='/funding': reply=cmd_funding(chat_id)
        elif cmd=='/dominans': reply=cmd_dominans(chat_id)
        elif cmd=='/ozet': reply=cmd_ozet(chat_id)
        elif cmd in ['/neal','/ne_al']: reply=cmd_neal(chat_id)
        elif cmd=='/tahmin': reply=cmd_tahmin(args[0] if args else 'BTC',chat_id)
        elif cmd=='/risk': reply=cmd_risk(args[0] if args else '100',args[1] if len(args)>1 else '10',chat_id)
        elif cmd=='/alarm': reply=cmd_alarm_ekle(args[0] if args else 'BTC',args[1] if len(args)>1 else '0',chat_id)
        elif cmd=='/alarmlar': reply=cmd_alarmlar(chat_id)
        elif cmd=='/alarmiptal': reply=cmd_alarm_iptal(args[0] if args else '',chat_id)
        elif cmd=='/strateji': reply=cmd_strateji(chat_id)
        elif cmd=='/plan': reply=cmd_plan(chat_id)
        elif cmd=='/egit': reply=cmd_egit(args[0] if args else 'rsi',chat_id)
        elif cmd=='/psikoloji': reply=cmd_psikoloji(chat_id)
        elif cmd=='/quiz': reply=cmd_quiz(chat_id)
        elif cmd=='/kazandim': reply=cmd_kazandim(chat_id)
        elif cmd=='/kaybettim': reply=cmd_kaybettim(chat_id)
        elif cmd=='/skor': reply=cmd_skor(chat_id)
        elif cmd=='/dil': reply=cmd_dil(args[0] if args else 'tr',chat_id)
        elif cmd=='/sessiz': reply=cmd_sessiz(chat_id)
        elif cmd=='/aktif': reply=cmd_aktif(chat_id)
        elif cmd=='/haber': reply=cmd_haber(chat_id)
        elif cmd in ['/yardim','/start','/help']: reply=cmd_yardim(chat_id)
        else: reply=f'❓ Bilinmeyen komut: <code>{cmd}</code>\n\n'+cmd_yardim(chat_id)

        tg_send(reply, chat_id)
    except Exception as e:
        print(f'process_update error: {e}')
        if chat_id:
            tg_send(f'❌ Hata: {str(e)[:100]}', chat_id)

def polling_loop():
    global offset
    print('✅ Bot polling başladı...')
    while True:
        try:
            res = requests.get(
                f'https://api.telegram.org/bot{TG_TOKEN}/getUpdates',
                params={'offset':offset+1,'timeout':25},
                timeout=30
            )
            data = res.json()
            if data.get('ok') and data.get('result'):
                for upd in data['result']:
                    offset = upd['update_id']
                    threading.Thread(target=process_update,args=(upd,),daemon=True).start()
        except Exception as e:
            print(f'Polling error: {e}')
            time.sleep(5)

@app.route('/')
def home():
    return jsonify({'status':'Trading Hub Pro Bot ✅','version':'v21','commands':30})

@app.route('/health')
def health():
    return jsonify({'ok':True})

if __name__ == '__main__':
    threading.Thread(target=polling_loop,daemon=True).start()
    threading.Thread(target=check_alarms_loop,daemon=True).start()
    port = int(os.environ.get('PORT',10000))
    app.run(host='0.0.0.0',port=port,debug=False)
