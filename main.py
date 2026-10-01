import os
import time
import json
import base64
import requests
import pandas as pd
import numpy as np
import ccxt
from datetime import datetime, timezone, timedelta

# Configuración específica por tipo de activo
CONFIG_ACTIVOS = {
    "BTC/USDT":  {"atr_sl": 1.2, "rr_tp1": 2.0, "rr_tp2": 3.5, "adx_min": 20},
    "ETH/USDT":  {"atr_sl": 1.2, "rr_tp1": 2.0, "rr_tp2": 3.5, "adx_min": 20},
    "SOL/USDT":  {"atr_sl": 1.6, "rr_tp1": 2.0, "rr_tp2": 3.5, "adx_min": 25},
    "BNB/USDT":  {"atr_sl": 1.4, "rr_tp1": 2.0, "rr_tp2": 3.5, "adx_min": 22},
    "XRP/USDT":  {"atr_sl": 1.6, "rr_tp1": 2.0, "rr_tp2": 3.5, "adx_min": 25},
    "ADA/USDT":  {"atr_sl": 1.6, "rr_tp1": 2.0, "rr_tp2": 3.5, "adx_min": 25},
    "AVAX/USDT": {"atr_sl": 1.6, "rr_tp1": 2.0, "rr_tp2": 3.5, "adx_min": 25},
    "NEAR/USDT": {"atr_sl": 1.6, "rr_tp1": 2.0, "rr_tp2": 3.5, "adx_min": 25},
    "LINK/USDT": {"atr_sl": 1.6, "rr_tp1": 2.0, "rr_tp2": 3.5, "adx_min": 25},
    "SUI/USDT":  {"atr_sl": 2.0, "rr_tp1": 2.0, "rr_tp2": 3.5, "adx_min": 28},
}

TIMEFRAME_OPERATIVO = "15m"
TIMEFRAME_MACRO = "1h"
LIMIT = 300

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = "velasquezmg1997-prog/crypto-copilot"
FILE_PATH = "cooldown.json"

COOLDOWN_SEGUNDOS = 1800  # 30 minutos

exchange = ccxt.kucoin({'enableRateLimit': True})

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
        if not sha:
            requests.post(url, headers=headers, json=payload, timeout=10)
        else:
            requests.put(url, headers=headers, json=payload, timeout=10)
    except Exception as e:
        print(f"Error guardando cooldowns en GitHub: {e}")

def enviar_telegram(mensaje, symbol):
    ultimas_alertas = cargar_cooldowns_github()
    tiempo_actual = time.time()

    if symbol in ultimas_alertas:
        tiempo_transcurrido = tiempo_actual - ultimas_alertas[symbol]
        if tiempo_transcurrido < COOLDOWN_SEGUNDOS:
            minutos_restantes = int((COOLDOWN_SEGUNDOS - tiempo_transcurrido) / 60)
            print(f"⏳ Cooldown activo para {symbol}. Faltan {minutos_restantes} min.")
            return

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠ Variables de Telegram no configuradas.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
        ultimas_alertas[symbol] = tiempo_actual
        guardar_cooldowns_github(ultimas_alertas)
        print(f"📲 Alerta enviada para {symbol}.")
    except Exception as e:
        print(f"Error enviando mensaje a Telegram: {e}")

def obtener_datos(symbol, timeframe):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=LIMIT)
        if not ohlcv or len(ohlcv) < 200:
            return None
        
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        cols = ['open', 'high', 'low', 'close', 'volume']
        df[cols] = df[cols].astype(float)
        return df
    except Exception as e:
        print(f"Error obteniendo datos de {symbol} ({timeframe}): {e}")
        return None

def calcular_vwap(df):
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    tp_vol = typical_price * df['volume']
    cum_tp_vol = tp_vol.cumsum()
    cum_vol = df['volume'].cumsum()
    vwap = cum_tp_vol / (cum_vol + 1e-10)
    return vwap

def calcular_indicadores(df):
    if df is None or len(df) < 200:
        return None
    
    # EMAs
    df['ema9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema21'] = df['close'].ewm(span=21, adjust=False).mean()
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-10)
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # MACD
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = exp1 - exp2
    df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['hist'] = df['macd'] - df['signal']
    
    # ATR
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean()

    # Volumen y VWAP
    df['vol_sma'] = df['volume'].rolling(20).mean()
    df['vwap'] = calcular_vwap(df)

    # ADX
    plus_dm = df['high'].diff()
    minus_dm = df['low'].diff()
    plus_dm = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0.0)
    minus_dm = np.where((minus_dm > plus_dm) & (minus_dm > 0), minus_dm, 0.0)
    
    tr14 = tr.rolling(14).sum()
    plus_di = 100 * (pd.Series(plus_dm).rolling(14).sum() / (tr14 + 1e-10))
    minus_di = 100 * (pd.Series(minus_dm).rolling(14).sum() / (tr14 + 1e-10))
    dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
    df['adx'] = dx.rolling(14).mean()
    
    # Estructura: Máximos y Mínimos recientes
    df['highest_5'] = df['high'].shift(1).rolling(5).max()
    df['lowest_5'] = df['low'].shift(1).rolling(5).min()

    return df

def analizar_activo(symbol):
    config = CONFIG_ACTIVOS.get(symbol, {"atr_sl": 1.5, "rr_tp1": 2.0, "rr_tp2": 3.5, "adx_min": 25})

    # 1. ANALISIS MACRO (1 Hora)
    df_macro = obtener_datos(symbol, TIMEFRAME_MACRO)
    if df_macro is None:
        return
    df_macro['ema200'] = df_macro['close'].ewm(span=200, adjust=False).mean()
    macro_close = df_macro['close'].iloc[-1]
    macro_ema200 = df_macro['ema200'].iloc[-1]

    tendencia_macro = "BULLISH" if macro_close > macro_ema200 else "BEARISH"

    # 2. ANALISIS OPERATIVO (15 Minutos)
    df = obtener_datos(symbol, TIMEFRAME_OPERATIVO)
    if df is None:
        return
    
    df = calcular_indicadores(df)
    if df is None or df['ema200'].isnull().iloc[-1] or df['adx'].isnull().iloc[-1]:
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
    vwap = last['vwap']
    highest_5 = last['highest_5']
    lowest_5 = last['lowest_5']

    symbol_clean = symbol.replace("/", "")

    # --- CONDICIONES DE ENTRADA LONG (PRO) ---
    cond_long = (
        tendencia_macro == "BULLISH" and        # 1. Filtro Macro 1h
        precio > ema200 and                    # 2. Tendencia 15m
        precio > vwap and                      # 3. Control Comprador (VWAP)
        ema9 > ema21 and                       # 4. Cruce de EMAs
        rsi > 52 and                           # 5. Momentum RSI
        macd_hist > 0 and                      # 6. Momentum MACD
        volume > vol_sma and                   # 7. Confirmación de Volumen
        adx > config['adx_min'] and            # 8. Fuerza de Tendencia Adaptativa
        precio > highest_5                     # 9. Breakout Estructural
    )

    if cond_long:
        distancia_sl = config['atr_sl'] * atr
        stop_loss = precio - distancia_sl
        take_profit1 = precio + (distancia_sl * config['rr_tp1'])
        take_profit2 = precio + (distancia_sl * config['rr_tp2'])
        riesgo_pct = ((precio - stop_loss) / precio) * 100

        msg = (
            f"```ORDER_SIGNAL\n"
            f"PAIR: {symbol_clean}\n"
            f"TYPE: LONG\n"
            f"ENTRY: {precio:.4f}\n"
            f"SL: {stop_loss:.4f}\n"
            f"TP1: {take_profit1:.4f}\n"
            f"TP2: {take_profit2:.4f}\n"
            f"END_SIGNAL```\n\n"
            f"🚨 *ALERTA PRO (LONG 🟢) - {symbol_clean} {TIMEFRAME_OPERATIVO}*\n\n"
            f"📊 *Filtro Macro (1h):* Alcista 🟢\n"
            f"🔥 *ADX:* `{adx:.1f}` | *VWAP:* `${vwap:.4f}`\n\n"
            f"🎯 *Parámetros Adaptativos (R:B 1:{config['rr_tp1']}):*\n"
            f"• *Entrada:* `${precio:.4f}`\n"
            f"• *Stop Loss:* `${stop_loss:.4f}` (~`{riesgo_pct:.2f}%`)\n"
            f"• *Take Profit 1:* `${take_profit1:.4f}`\n"
            f"• *Take Profit 2:* `${take_profit2:.4f}`"
        )
        enviar_telegram(msg, symbol)
        return

    # --- CONDICIONES DE ENTRADA SHORT (PRO) ---
    cond_short = (
        tendencia_macro == "BEARISH" and       # 1. Filtro Macro 1h
        precio < ema200 and                    # 2. Tendencia 15m
        precio < vwap and                      # 3. Control Vendedor (VWAP)
        ema9 < ema21 and                       # 4. Cruce de EMAs
        rsi < 48 and                           # 5. Momentum RSI
        macd_hist < 0 and                      # 6. Momentum MACD
        volume > vol_sma and                   # 7. Confirmación de Volumen
        adx > config['adx_min'] and            # 8. Fuerza de Tendencia Adaptativa
        precio < lowest_5                      # 9. Breakout Estructural
    )

    if cond_short:
        distancia_sl = config['atr_sl'] * atr
        stop_loss = precio + distancia_sl
        take_profit1 = precio - (distancia_sl * config['rr_tp1'])
        take_profit2 = precio - (distancia_sl * config['rr_tp2'])
        riesgo_pct = ((stop_loss - precio) / precio) * 100

        msg = (
            f"```ORDER_SIGNAL\n"
            f"PAIR: {symbol_clean}\n"
            f"TYPE: SHORT\n"
            f"ENTRY: {precio:.4f}\n"
            f"SL: {stop_loss:.4f}\n"
            f"TP1: {take_profit1:.4f}\n"
            f"TP2: {take_profit2:.4f}\n"
            f"END_SIGNAL```\n\n"
            f"🚨 *ALERTA PRO (SHORT 🔴) - {symbol_clean} {TIMEFRAME_OPERATIVO}*\n\n"
            f"📊 *Filtro Macro (1h):* Bajista 🔴\n"
            f"🔥 *ADX:* `{adx:.1f}` | *VWAP:* `${vwap:.4f}`\n\n"
            f"🎯 *Parámetros Adaptativos (R:B 1:{config['rr_tp1']}):*\n"
            f"• *Entrada:* `${precio:.4f}`\n"
            f"• *Stop Loss:* `${stop_loss:.4f}` (~`{riesgo_pct:.2f}%`)\n"
            f"• *Take Profit 1:* `${take_profit1:.4f}`\n"
            f"• *Take Profit 2:* `${take_profit2:.4f}`"
        )
        enviar_telegram(msg, symbol)
        return

    print(f"ℹ️ {symbol}: Sin confluencia profesional suficiente.")

def main():
    _, hora_str = obtener_hora_espana()
    print(f"🕒 Escaneando con modelo Pro a las {hora_str}hs...")
    for symbol in CONFIG_ACTIVOS.keys():
        analizar_activo(symbol)
    print("✅ Escaneo finalizado.")

if __name__ == "__main__":
    main()
