import os
import requests
import pandas as pd
import numpy as np
import ccxt

# Configuración de pares y parámetros (Formato Estándar CCXT)
SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "ADA/USDT", "AVAX/USDT", "NEAR/USDT", "LINK/USDT", "SUI/USDT"]
TIMEFRAME = "15m"
LIMIT = 300

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Inicializar cliente de KuCoin (Libre de geobloqueos en EE. UU. / Cloud)
exchange = ccxt.kucoin({
    'enableRateLimit': True
})

def enviar_telegram(mensaje):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Variables de Telegram no configuradas.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
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
    
    # MACD
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = exp1 - exp2
    df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    
    return df

def analizar_activo(symbol):
    df = obtener_datos(symbol)
    if df is None:
        print(f"❌ No se obtuvieron suficientes datos para {symbol}")
        return
    
    df = calcular_indicadores(df)
    if df is None or df['ema200'].isnull().iloc[-1]:
        print(f"❌ Datos insuficientes tras cálculo para {symbol}")
        return

    last = df.iloc[-1]
    precio = last['close']
    ema = last['ema200']
    rsi = last['rsi']
    macd = last['macd']
    signal = last['signal']

    puntos = 0
    detalles = []

    if precio > ema:
        puntos += 35
        detalles.append("Tendencia Alcista (Precio > EMA 200)")
    
    if rsi > 50:
        puntos += 35
        detalles.append("Impulso Alcista (RSI > 50)")

    if macd > signal:
        puntos += 30
        detalles.append("Cruce MACD Alcista")

    if puntos >= 70:
        msg = f"🚀 *SEÑAL ALCISTA DETECTADA*\n\n" \
              f"📌 *Activo:* `{symbol}`\n" \
              f"📊 *Confluencia:* `{puntos}%`\n" \
              f"💵 *Precio Actual:* `{precio:.4f}`\n\n" \
              f"🔍 *Razones:*\n" + "\n".join([f"• {d}" for d in detalles])
        enviar_telegram(msg)
        print(f"📲 Señal de {symbol} enviada a Telegram ({puntos}%).")
    else:
        print(f"ℹ️ {symbol}: Confluencia del {puntos}% (Sin señal).")

def main():
    print("🔍 Escaneando 10 activos (15m)...")
    for symbol in SYMBOLS:
        analizar_activo(symbol)
    print("✅ Escaneo finalizado correctamente.")

if __name__ == "__main__":
    main()
