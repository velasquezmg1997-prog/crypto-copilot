import time
import requests
import schedule
import pandas as pd
from google import genai

TELEGRAM_BOT_TOKEN = "8707588324:AAG8-CSWk4fbXnF4xWFomfQDVn4r9qgJ6_8"
TELEGRAM_CHAT_ID = "5331405922"
GEMINI_API_KEY = "AQ.Ab8RN6KcXhS-uBUkLIeB9bp93tLjyY5tGQnAdMxG5CKlDy31VQ"

PARES_MONITOREADOS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", 
    "XRPUSDT", "ADAUSDT", "AVAXUSDT", "NEARUSDT", "LINKUSDT", "SUIUSDT"
]

client = genai.Client(api_key=GEMINI_API_KEY)

def obtener_datos_con_indicadores(symbol, interval="15m"):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit=300"
    response = requests.get(url).json()

    df = pd.DataFrame(response, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'
    ])
    
    df['close'] = df['close'].astype(float)
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    df['volume'] = df['volume'].astype(float)

    df['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema_21'] = df['close'].ewm(span=21, adjust=False).mean()
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()

    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))

    ema_12 = df['close'].ewm(span=12, adjust=False).mean()
    ema_26 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = ema_12 - ema_26
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']

    df['bb_middle'] = df['close'].rolling(window=20).mean()
    std = df['close'].rolling(window=20).std()
    df['bb_upper'] = df['bb_middle'] + (std * 2)
    df['bb_lower'] = df['bb_middle'] - (std * 2)

    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.rolling(window=14).mean()

    df['vol_sma_20'] = df['volume'].rolling(window=20).mean()

    precio_actual = df['close'].iloc[-1]
    ema_9_actual = df['ema_9'].iloc[-2]
    ema_21_actual = df['ema_21'].iloc[-2]
    ema_200_actual = df['ema_200'].iloc[-2]
    rsi_actual = df['rsi'].iloc[-2]
    macd_actual = df['macd'].iloc[-2]
    macd_signal_actual = df['macd_signal'].iloc[-2]
    macd_hist_actual = df['macd_hist'].iloc[-2]
    bb_upper = df['bb_upper'].iloc[-2]
    bb_lower = df['bb_lower'].iloc[-2]
    bb_middle = df['bb_middle'].iloc[-2]
    atr_actual = df['atr'].iloc[-2]
    
    volumen_actual = df['volume'].iloc[-2]
    volumen_promedio = df['vol_sma_20'].iloc[-2]
    volumen_alto = volumen_actual > (volumen_promedio * 1.2)

    ema_9_prev = df['ema_9'].iloc[-3]
    ema_21_prev = df['ema_21'].iloc[-3]

    cruce = "SIN_CRUCE"
    if ema_9_prev <= ema_21_prev and ema_9_actual > ema_21_actual:
        cruce = "CRUCE_ALCISTA"
    elif ema_9_prev >= ema_21_prev and ema_9_actual < ema_21_actual:
        cruce = "CRUCE_BAJISTA"

    tendencia_macro = "ALCISTA" if precio_actual > ema_200_actual else "BAJISTA"

    score_long = 0
    score_short = 0

    if cruce == "CRUCE_ALCISTA" and tendencia_macro == "ALCISTA":
        score_long += 30
    if cruce == "CRUCE_BAJISTA" and tendencia_macro == "BAJISTA":
        score_short += 30

    if 45 <= rsi_actual < 68:
        score_long += 15
    if 32 < rsi_actual <= 55:
        score_short += 15

    if macd_actual > macd_signal_actual and macd_hist_actual > 0:
        score_long += 20
    if macd_actual < macd_signal_actual and macd_hist_actual < 0:
        score_short += 20

    if precio_actual > bb_middle and precio_actual < bb_upper:
        score_long += 20
    if precio_actual < bb_middle and precio_actual > bb_lower:
        score_short += 20

    if volumen_alto:
        score_long += 15
        score_short += 15

    es_entrada_valida = False
    tipo_operacion = "NINGUNA"
    score_final = 0

    if score_long >= 70:
        es_entrada_valida = True
        tipo_operacion = "LONG 🟢"
        score_final = score_long
        stop_loss = precio_actual - (1.5 * atr_actual)
        tp1 = precio_actual + (1.0 * atr_actual)
        tp2 = precio_actual + (2.0 * atr_actual)
    elif score_short >= 70:
        es_entrada_valida = True
        tipo_operacion = "SHORT 🔴"
        score_final = score_short
        stop_loss = precio_actual + (1.5 * atr_actual)
        tp1 = precio_actual - (1.0 * atr_actual)
        tp2 = precio_actual - (2.0 * atr_actual)
    else:
        stop_loss = tp1 = tp2 = 0

    return {
        "par": symbol,
        "precio_actual": precio_actual,
        "ema_200": ema_200_actual,
        "rsi": rsi_actual,
        "macd_hist": macd_hist_actual,
        "volumen_alto": volumen_alto,
        "cruce": cruce,
        "tendencia_macro": tendencia_macro,
        "score_confluencia": score_final,
        "es_entrada_valida": es_entrada_valida,
        "tipo_operacion": tipo_operacion,
        "stop_loss": stop_loss,
        "tp1": tp1,
        "tp2": tp2
    }

def analizar_con_ia(datos):
    prompt = f"""
    Actúa como un Copiloto de Trading Senior. Redacta una ALERTA EN TELEGRAM para {datos['par']}:
    - Entrada: {datos['tipo_operacion']}
    - Precio: ${datos['precio_actual']:,.4f}
    - Confluencia: {datos['score_confluencia']}%
    - Stop Loss: ${datos['stop_loss']:,.4f}
    - TP1: ${datos['tp1']:,.4f} | TP2: ${datos['tp2']:,.4f}
    """
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        return response.text
    except Exception:
        return (
            f"🚨 **ALERTA DE ENTRADA ({datos['tipo_operacion']}) - {datos['par']}**\n\n"
            f"🔥 **Confluencia Técnica:** {datos['score_confluencia']}%\n"
            f"📈 **Tendencia Macro:** {datos['tendencia_macro']} | **RSI:** {datos['rsi']:.1f}\n\n"
            f"🎯 **Parámetros Técnicos Adaptativos (ATR):**\n"
            f"- **Precio Entrada:** ${datos['precio_actual']:,.4f}\n"
            f"- **Stop Loss:** ${datos['stop_loss']:,.4f}\n"
            f"- **Take Profit 1:** ${datos['tp1']:,.4f}\n"
            f"- **Take Profit 2:** ${datos['tp2']:,.4f}"
        )

def enviar_telegram(mensaje):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "Markdown"}
    res = requests.post(url, json=payload)
    if res.status_code != 200:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": mensaje})

def ejecutar_escaneo():
    print("🔍 Escaneando 10 activos (15m)...")
    for par in PARES_MONITOREADOS:
        try:
            datos = obtener_datos_con_indicadores(par, interval="15m")
            if datos['es_entrada_valida']:
                analisis = analizar_con_ia(datos)
                enviar_telegram(analisis)
                print(f"📲 Señal de {par} enviada a Telegram.")
        except Exception as e:
            print(f"❌ Error en {par}: {e}")

# Programar ejecución cada 15 minutos en el servidor
schedule.every(15).minutes.do(ejecutar_escaneo)

if __name__ == "__main__":
    print("🚀 Servidor en la nube iniciado. Monitoreando 24/7...")
    ejecutar_escaneo()  # Ejecución inicial
    while True:
        schedule.run_pending()
        time.sleep(1)