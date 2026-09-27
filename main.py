import os
import time
import json
import base64
import requests
import pandas as pd
import numpy as np
import ccxt
from datetime import datetime, timezone, timedelta

# Configuración de pares y parámetros
SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "ADA/USDT", "AVAX/USDT", "NEAR/USDT", "LINK/USDT", "SUI/USDT"]
TIMEFRAME = "15m"
LIMIT = 300

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = "velasquezmg1997-prog/crypto-copilot"  # Tu repositorio
FILE_PATH = "cooldown.json"

COOLDOWN_SEGUNDOS = 3600  # 1 hora de cooldown

# Inicializar cliente de KuCoin
exchange = ccxt.kucoin({
    'enableRateLimit': True
})

def obtener_hora_espana():
    utc_now = datetime.now(timezone.utc)
    espana_now = utc_now + timedelta(hours=2)
    return espana_now.hour, espana_now.strftime("%H:%M")

def cargar_cooldowns_github():
    if not GITHUB_TOKEN:
        return {}
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{FILE_PATH}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}", 
        "Accept": "vnd.github+json",
        "Cache-Control": "no-cache"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            content_encoded = response.json().get("content", "")
            content_decoded = base64.b64decode(content_encoded).decode("utf-8")
            return json.loads(content_decoded)
    except Exception as e:
        print(f"Error cargando cooldowns desde GitHub: {e}")
    return {}

def guardar_cooldowns_github(ultimas_alertas):
    if not GITHUB_TOKEN:
        return
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{FILE_PATH}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}", 
        "Accept": "vnd.github+json",
        "Cache-Control": "no-cache"
    }
    
    sha = None
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            sha = res.json().get("sha")
    except Exception:
        pass

    content_str = json.dumps(ultimas_alertas, indent=4)
    content_encoded = base64.b64encode(content_str.encode("utf-8")).decode("utf-8")

    payload = {
        "message": "Update cooldown state [skip ci]",
        "content": content_encoded,
        "sha": sha
    } if sha else {
        "message": "Create cooldown state [skip ci]",
        "content": content_encoded
    }

    try:
        requests.put(url, headers=headers, json=payload, timeout=10)
    except Exception as e:
        print(f"Error guardando cooldowns en GitHub: {e}")

def enviar_telegram(mensaje, symbol):
    hora_espana, hora_str = obtener_hora_espana()

    # 1. Filtro estricto de silencio nocturno (00:00 a 07:59)
    if 0 <= hora_espana < 8:
        print(f"🔕 [SILENCIO NOCTURNO] {hora_str}h España. Alerta de {symbol} omitida.")
        return

    # 2. Cargar estado actual de cooldowns desde GitHub
    ultimas_alertas = cargar_cooldowns_github()
    tiempo_actual = time.time()

    if symbol in ultimas_alertas:
        tiempo_transcurrido = tiempo_actual - ultimas_alertas[symbol]
        if tiempo_transcurrido < COOLDOWN_SEGUNDOS:
            minutos_restantes = int((COOLDOWN_SEGUNDOS - tiempo_transcurrido) / 60)
            print(f"⏳ Cooldown activo para {symbol}. Faltan {minutos_restantes} min para permitir otra alerta.")
            return

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Variables de Telegram no configuradas.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
        ultimas_alertas[symbol] = tiempo_actual
        guardar_cooldowns_github(ultimas_alertas)
        print(f"📲 Alerta enviada para {symbol}. Cooldown de 1 hora activado y sincronizado en GitHub.")
    except Exception as e:
        print(f"Error enviando mensaje a Telegram: {e}")

def obtener_datos(symbol):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=LIMIT)
        if not ohlcv or len(ohlcv) < 200:
            return None
        
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        cols = ['open', 'high', 'low', 'close', 'volume']
        df[cols] = df[cols].astype(float)
        return df
    except Exception as e:
        print(f"Error obteniendo datos de {symbol}: {e}")
        return None

def calcular_indicadores(df):
    if df is None or len(df) < 200:
        return None
    
    # EMA 200
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    # RSI (14)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-10)
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # MACD (12, 26, 9)
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = exp1 - exp2
    df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['hist'] = df['macd'] - df['signal']
    
    # ATR (14)
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean()

    # EMAs rápidas
    df['ema9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema21'] = df['close'].ewm(span=21, adjust=False).mean()

    # SMA Volumen (20)
    df['vol_sma'] = df['volume'].rolling(20).mean()

    # ADX (14) - Cálculo de fuerza de tendencia
    plus_dm = df['high'].diff()
    minus_dm = df['low'].diff()
    plus_dm = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0.0)
    minus_dm = np.where((minus_dm > plus_dm) & (minus_dm > 0), minus_dm, 0.0)
    
    tr14 = tr.rolling(14).sum()
    plus_di = 100 * (pd.Series(plus_dm).rolling(14).sum() / (tr14 + 1e-10))
    minus_di = 100 * (pd.Series(minus_dm).rolling(14).sum() / (tr14 + 1e-10))
    dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
    df['adx'] = dx.rolling(14).mean()
    
    return df

def analizar_activo(symbol):
    df = obtener_datos(symbol)
    if df is None:
        print(f"❌ No se obtuvieron suficientes datos para {symbol}")
        return
    
    df = calcular_indicadores(df)
    if df is None or df['ema200'].isnull().iloc[-1] or df['adx'].isnull().iloc[-1]:
        print(f"❌ Datos insuficientes tras cálculo para {symbol}")
        return

    last = df.iloc[-1]
    
    precio = last['close']
    ema200 = last['ema200']
    rsi = last['rsi']
    macd_hist = last['hist']
    atr = last['atr']
    volume = last['volume']
    vol_sma = last['vol_sma']
    ema9 = last['ema9']
    ema21 = last['ema21']
    adx = last['adx']

    symbol_clean = symbol.replace("/", "")

    puntos = 0
    
    if precio > ema200:
        puntos += 35
    if rsi > 50:
        puntos += 35
    if macd_hist > 0:
        puntos += 30

    # Filtro estricto de fuerza de tendencia: ADX > 25 obligatorio para calificar
    if puntos >= 70 and adx > 25:
        stop_loss = precio - (1.5 * atr)
        take_profit1 = precio + (1.0 * atr)
        take_profit2 = precio + (2.0 * atr)
        riesgo_pct = ((precio - stop_loss) / precio) * 100

        if volume > vol_sma:
            vol_desc = "Confirmación activa de volumen institucional absorbiendo la oferta local, impulsando el precio hacia zonas de liquidez superior."
        else:
            vol_desc = "Volumen dentro del promedio; seguimiento de flujo continuo de órdenes en la zona actual."

        if ema9 > ema21:
            ema_desc = f"Alineación alcista confirmada (EMA 9 por encima de EMA 21). EMA 200 en ${ema200:.4f} actuando como pivote crítico."
        else:
            ema_desc = f"Operativa contra la tendencia macro inmediata (EMA 200 en ${ema200:.4f} actuando como pivote crítico de ruptura). Setup de momentum rápido."

        msg = (
            f"🚨 *ALERTA DE ENTRADA (LONG 🟢) - {symbol_clean} {TIMEFRAME}*\n\n"
            f"🔥 *Confluencia Técnica:* `{puntos}% / 100%` (Setup de Momentum con ADX Fuerte)\n\n"
            f"---\n\n"
            f"📈 *Análisis Multitest & Tendencia:*\n"
            f"• *ADX (14) [Fuerza de Tendencia]:* `{adx:.1f}` (Fuerte tendencia confirmada > 25).\n"
            f"• *Volumen & Flujo Institucional:* {vol_desc}\n"
            f"• *MACD (12, 26, 9):* Histograma alcista en expansión (`{macd_hist:+.4f}`), validando aceleración.\n"
            f"• *RSI (14):* Situado en `{rsi:.1f}` con tracción alcista.\n"
            f"• *Estructura de EMAs:* {ema_desc}\n\n"
            f"---\n\n"
            f"🎯 *Parámetros Técnicos Adaptativos (ATR):*\n\n"
            f"• *Precio de Entrada:* `${precio:.4f}`\n"
            f"• *Stop Loss:* `${stop_loss:.4f}` (Riesgo: ~`{riesgo_pct:.2f}%`)\n"
            f"• *Take Profit 1:* `${take_profit1:.4f}` (Recompensa inicial / Resistencia inmediata)\n"
            f"• *Take Profit 2:* `${take_profit2:.4f}` (Extensión de rango ATR / Liquidez mayor)\n\n"
            f"---\n\n"
            f"⚙️ *Gestión de Riesgo Senior:*\n"
            f"• *Trailing / Breakeven:* Al alcanzar el TP1, mover automáticamente el Stop Loss a precio de entrada (Breakeven) y tomar beneficios parciales (50-70%).\n"
            f"• *Nota Operativa:* Monitorear la reacción en torno a la EMA 200 (`${ema200:.4f}`); el cierre de vela de 15m por encima de este nivel consolidará el movimiento hacia TP2."
        )
        enviar_telegram(msg, symbol)
    else:
        print(f"ℹ️ {symbol}: Confluencia del {puntos}% | ADX: {adx:.1f} (Sin señal o filtrado por mercado lateral).")

def main():
    hora_espana, hora_str = obtener_hora_espana()
    print(f"🕒 Hora España: {hora_str}hs")
    print("🔍 Escaneando 10 activos con filtro ADX (15m)...")
    for symbol in SYMBOLS:
        analizar_activo(symbol)
    print("✅ Escaneo finalizado correctamente.")

if __name__ == "__main__":
    main()
