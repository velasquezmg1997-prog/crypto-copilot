```text
import os
import os
import time
import json
import base64
import requests
import pandas as pd
import numpy as np
import ccxt
from datetime import datetime
from zoneinfo import ZoneInfo


# ============================================================
# CONFIGURACIÓN
# ============================================================

CONFIG_ACTIVOS = {
    "BTC/USDT": {
        "adx_min": 20,
        "atr_mult": 1.2
    },
    "ETH/USDT": {
        "adx_min": 20,
        "atr_mult": 1.2
    },
    "BNB/USDT": {
        "adx_min": 22,
        "atr_mult": 1.4
    },
    "SOL/USDT": {
        "adx_min": 25,
        "atr_mult": 1.6
    },
    "XRP/USDT": {
        "adx_min": 25,
        "atr_mult": 1.6
    },
    "ADA/USDT": {
        "adx_min": 25,
        "atr_mult": 1.6
    },
    "AVAX/USDT": {
        "adx_min": 25,
        "atr_mult": 1.6
    },
    "NEAR/USDT": {
        "adx_min": 25,
        "atr_mult": 1.6
    },
    "LINK/USDT": {
        "adx_min": 25,
        "atr_mult": 1.6
    },
    "SUI/USDT": {
        "adx_min": 28,
        "atr_mult": 2.0
    }
}


TIMEFRAME_OPERATIVO = "15m"
TIMEFRAME_MACRO = "1h"

LIMIT = 300

COOLDOWN_SEGUNDOS = 1800


# ============================================================
# VARIABLES DE ENTORNO
# ============================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

GITHUB_USER = "velasquezmg1997-prog"
GITHUB_REPO = "crypto-copilot"
GITHUB_FILE = "cooldown.json"


# ============================================================
# EXCHANGE
# ============================================================

exchange = ccxt.kucoin({
    "enableRateLimit": True
})


# ============================================================
# HORA ESPAÑA
# ============================================================

def obtener_hora_espana():

    ahora = datetime.now(
        ZoneInfo("Europe/Madrid")
    )

    return ahora.strftime("%d/%m/%Y %H:%M:%S")


# ============================================================
# GITHUB - COOLDOWN
# ============================================================

def cargar_cooldown():

    url = (
        f"https://api.github.com/repos/"
        f"{GITHUB_USER}/{GITHUB_REPO}/contents/{GITHUB_FILE}"
    )

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=20
        )

        if response.status_code == 200:

            data = response.json()

            contenido = base64.b64decode(
                data["content"]
            ).decode("utf-8")

            return (
                json.loads(contenido),
                data["sha"]
            )

        elif response.status_code == 404:

            return {}, None

        else:

            print(
                f"⚠️ Error cargando cooldown: "
                f"{response.status_code}"
            )

            return {}, None

    except Exception as e:

        print(
            f"⚠️ Error cargando cooldown: {e}"
        )

        return {}, None


def guardar_cooldown(cooldown, sha):

    url = (
        f"https://api.github.com/repos/"
        f"{GITHUB_USER}/{GITHUB_REPO}/contents/{GITHUB_FILE}"
    )

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }

    contenido = json.dumps(
        cooldown,
        indent=2
    )

    encoded = base64.b64encode(
        contenido.encode("utf-8")
    ).decode("utf-8")

    payload = {
        "message": "Actualizar cooldown",
        "content": encoded
    }

    if sha:
        payload["sha"] = sha

    try:

        response = requests.put(
            url,
            headers=headers,
            json=payload,
            timeout=20
        )

        if response.status_code in [200, 201]:

            print("💾 Cooldown guardado correctamente.")

            return True

        else:

            print(
                f"⚠️ Error guardando cooldown: "
                f"{response.status_code}"
            )

            print(response.text)

            return False

    except Exception as e:

        print(
            f"⚠️ Error guardando cooldown: {e}"
        )

        return False


# ============================================================
# TELEGRAM
# ============================================================

def enviar_telegram(mensaje):

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:

        print(
            "⚠️ TELEGRAM_TOKEN o TELEGRAM_CHAT_ID "
            "no están configurados."
        )

        return False

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensaje
    }

    try:

        response = requests.post(
            url,
            json=payload,
            timeout=20
        )

        if response.status_code == 200:

            print("📨 Telegram enviado correctamente.")

            return True

        else:

            print(
                f"⚠️ Error Telegram: "
                f"{response.status_code}"
            )

            print(response.text)

            return False

    except Exception as e:

        print(
            f"⚠️ Error enviando Telegram: {e}"
        )

        return False


# ============================================================
# OBTENER DATOS
# ============================================================

def obtener_datos(simbolo, timeframe):

    try:

        ohlcv = exchange.fetch_ohlcv(
            simbolo,
            timeframe=timeframe,
            limit=LIMIT
        )

        if not ohlcv:

            print(
                f"⚠️ Sin datos para {simbolo} "
                f"{timeframe}"
            )

            return None

        df = pd.DataFrame(
            ohlcv,
            columns=[
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume"
            ]
        )

        if len(df) < 200:

            print(
                f"⚠️ Datos insuficientes para "
                f"{simbolo} {timeframe}: "
                f"{len(df)} velas"
            )

            return None

        columnas_numericas = [
            "open",
            "high",
            "low",
            "close",
            "volume"
        ]

        for columna in columnas_numericas:

            df[columna] = pd.to_numeric(
                df[columna],
                errors="coerce"
            )

        df["timestamp"] = pd.to_datetime(
            df["timestamp"],
            unit="ms",
            utc=True
        )

        df = df.sort_values(
            "timestamp"
        ).reset_index(drop=True)

        return df

    except Exception as e:

        print(
            f"❌ Error obteniendo datos "
            f"{simbolo} {timeframe}: {e}"
        )

        return None


# ============================================================
# VWAP
# ============================================================

def calcular_vwap(df):

    precio_tipico = (
        df["high"] +
        df["low"] +
        df["close"]
    ) / 3

    volumen_precio = (
        precio_tipico *
        df["volume"]
    )

    vwap = (
        volumen_precio.cumsum() /
        df["volume"].cumsum()
    )

    return vwap


# ============================================================
# INDICADORES
# ============================================================

def calcular_indicadores(df):

    df = df.copy()

    # --------------------------------------------------------
    # EMAs
    # --------------------------------------------------------

    df["ema9"] = (
        df["close"]
        .ewm(span=9, adjust=False)
        .mean()
    )

    df["ema21"] = (
        df["close"]
        .ewm(span=21, adjust=False)
        .mean()
    )

    df["ema200"] = (
        df["close"]
        .ewm(span=200, adjust=False)
        .mean()
    )

    # --------------------------------------------------------
    # RSI
    # --------------------------------------------------------

    delta = df["close"].diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = (
        gain.rolling(14)
        .mean()
    )

    avg_loss = (
        loss.rolling(14)
        .mean()
    )

    rs = avg_gain / avg_loss.replace(
        0,
        np.nan
    )

    df["rsi"] = (
        100 -
        (100 / (1 + rs))
    )

    # --------------------------------------------------------
    # MACD
    # --------------------------------------------------------

    ema12 = (
        df["close"]
        .ewm(span=12, adjust=False)
        .mean()
    )

    ema26 = (
        df["close"]
        .ewm(span=26, adjust=False)
        .mean()
    )

    df["macd"] = ema12 - ema26

    df["macd_signal"] = (
        df["macd"]
        .ewm(span=9, adjust=False)
        .mean()
    )

    df["macd_hist"] = (
        df["macd"] -
        df["macd_signal"]
    )

    # --------------------------------------------------------
    # ATR
    # --------------------------------------------------------

    high_low = (
        df["high"] -
        df["low"]
    )

    high_close = (
        df["high"] -
        df["close"].shift(1)
    ).abs()

    low_close = (
        df["low"] -
        df["close"].shift(1)
    ).abs()

    true_range = pd.concat(
        [
            high_low,
            high_close,
            low_close
        ],
        axis=1
    ).max(axis=1)

    df["atr"] = (
        true_range
        .rolling(14)
        .mean()
    )

    # --------------------------------------------------------
    # VOLUMEN
    # --------------------------------------------------------

    df["volume_sma20"] = (
        df["volume"]
        .rolling(20)
        .mean()
    )

    # --------------------------------------------------------
    # VWAP
    # --------------------------------------------------------

    df["vwap"] = calcular_vwap(df)

    # --------------------------------------------------------
    # ADX
    # --------------------------------------------------------

    up_move = df["high"].diff()

    down_move = (
        df["low"].shift(1) -
        df["low"]
    )

    plus_dm = np.where(
        (up_move > down_move) &
        (up_move > 0),
        up_move,
        0.0
    )

    minus_dm = np.where(
        (down_move > up_move) &
        (down_move > 0),
        down_move,
        0.0
    )

    plus_dm = pd.Series(
        plus_dm,
        index=df.index
    )

    minus_dm = pd.Series(
        minus_dm,
        index=df.index
    )

    tr14 = (
        true_range
        .rolling(14)
        .sum()
    )

    plus_dm14 = (
        plus_dm
        .rolling(14)
        .sum()
    )

    minus_dm14 = (
        minus_dm
        .rolling(14)
        .sum()
    )

    plus_di = (
        100 *
        plus_dm14 /
        tr14
    )

    minus_di = (
        100 *
        minus_dm14 /
        tr14
    )

    dx = (
        100 *
        (plus_di - minus_di).abs() /
        (plus_di + minus_di)
    )

    df["adx"] = (
        dx
        .rolling(14)
        .mean()
    )

    # --------------------------------------------------------
    # ESTRUCTURA
    # --------------------------------------------------------

    df["highest_5"] = (
        df["high"]
        .rolling(5)
        .max()
        .shift(1)
    )

    df["lowest_5"] = (
        df["low"]
        .rolling(5)
        .min()
        .shift(1)
    )

    return df


# ============================================================
# ÚLTIMA VELA CERRADA
# ============================================================

def obtener_ultima_vela_cerrada(df):

    if len(df) < 2:

        return None

    return df.iloc[-2]


# ============================================================
# RESUMEN DE CONDICIONES
# ============================================================

def mostrar_resumen(
    direccion,
    condiciones
):

    total = len(condiciones)

    cumplidas = sum(
        1 for valor in condiciones.values()
        if valor
    )

    print(
        f"{direccion}: "
        f"{cumplidas}/{total}"
    )

    return cumplidas


# ============================================================
# ANALIZAR ACTIVO
# ============================================================

def analizar_activo(
    simbolo,
    configuracion,
    cooldown
):

    print()
    print("=" * 70)
    print(f"🪙 ANALIZANDO {simbolo}")
    print("=" * 70)

    # --------------------------------------------------------
    # COOLDOWN
    # --------------------------------------------------------

    ahora_timestamp = time.time()

    ultimo_signal = cooldown.get(
        simbolo,
        0
    )

    if (
        ahora_timestamp -
        ultimo_signal
        < COOLDOWN_SEGUNDOS
    ):

        restante = int(
            COOLDOWN_SEGUNDOS -
            (
                ahora_timestamp -
                ultimo_signal
            )
        )

        print(
            f"⏳ Cooldown activo. "
            f"Restan aproximadamente "
            f"{restante // 60} min."
        )

        return None

    # --------------------------------------------------------
    # DATOS 15M
    # --------------------------------------------------------

    df_15m = obtener_datos(
        simbolo,
        TIMEFRAME_OPERATIVO
    )

    if df_15m is None:

        return None

    # --------------------------------------------------------
    # DATOS 1H
    # --------------------------------------------------------

    df_1h = obtener_datos(
        simbolo,
        TIMEFRAME_MACRO
    )

    if df_1h is None:

        return None

    # --------------------------------------------------------
    # INDICADORES
    # --------------------------------------------------------

    df_15m = calcular_indicadores(
        df_15m
    )

    df_1h = calcular_indicadores(
        df_1h
    )

    # --------------------------------------------------------
    # ÚLTIMA VELA CERRADA
    # --------------------------------------------------------

    vela_15m = obtener_ultima_vela_cerrada(
        df_15m
    )

    vela_1h = obtener_ultima_vela_cerrada(
        df_1h
    )

    if vela_15m is None or vela_1h is None:

        print(
            "⚠️ No se pudo obtener "
            "la última vela cerrada."
        )

        return None

    # --------------------------------------------------------
    # TIMESTAMPS
    # --------------------------------------------------------

    timestamp_15m = vela_15m["timestamp"]

    timestamp_1h = vela_1h["timestamp"]

    print(
        f"🕯️ Vela 15m analizada: "
        f"{timestamp_15m}"
    )

    print(
        f"🕯️ Vela 1h analizada: "
        f"{timestamp_1h}"
    )

    # --------------------------------------------------------
    # VALORES
    # --------------------------------------------------------

    precio = float(
        vela_15m["close"]
    )

    ema9 = float(
        vela_15m["ema9"]
    )

    ema21 = float(
        vela_15m["ema21"]
    )

    ema200 = float(
        vela_15m["ema200"]
    )

    vwap = float(
        vela_15m["vwap"]
    )

    rsi = float(
        vela_15m["rsi"]
    )

    macd_hist = float(
        vela_15m["macd_hist"]
    )

    volumen = float(
        vela_15m["volume"]
    )

    volumen_sma20 = float(
        vela_15m["volume_sma20"]
    )

    adx = float(
        vela_15m["adx"]
    )

    atr = float(
        vela_15m["atr"]
    )

    highest_5 = float(
        vela_15m["highest_5"]
    )

    lowest_5 = float(
        vela_15m["lowest_5"]
    )

    macro_close = float(
        vela_1h["close"]
    )

    macro_ema200 = float(
        vela_1h["ema200"]
    )

    # --------------------------------------------------------
    # VALIDACIÓN DE DATOS
    # --------------------------------------------------------

    valores = [
        precio,
        ema9,
        ema21,
        ema200,
        vwap,
        rsi,
        macd_hist,
        volumen,
        volumen_sma20,
        adx,
        atr,
        highest_5,
        lowest_5,
        macro_close,
        macro_ema200
    ]

    if any(
        not np.isfinite(valor)
        for valor in valores
    ):

        print(
            "⚠️ Indicadores incompletos "
            "o no válidos."
        )

        return None

    # --------------------------------------------------------
    # MACRO
    # --------------------------------------------------------

    macro_bullish = (
        macro_close >
        macro_ema200
    )

    macro_bearish = (
        macro_close <
        macro_ema200
    )

    print()

    print(
        f"💰 Precio: {precio:.6f}"
    )

    print(
        f"📊 Macro: "
        f"{'BULLISH' if macro_bullish else 'BEARISH'}"
    )

    print(
        f"EMA9: {ema9:.6f}"
    )

    print(
        f"EMA21: {ema21:.6f}"
    )

    print(
        f"EMA200: {ema200:.6f}"
    )

    print(
        f"VWAP: {vwap:.6f}"
    )

    print(
        f"RSI: {rsi:.2f}"
    )

    print(
        f"MACD Hist: {macd_hist:.6f}"
    )

    print(
        f"Volumen: {volumen:.4f}"
    )

    print(
        f"Volumen SMA20: "
        f"{volumen_sma20:.4f}"
    )

    print(
        f"ADX: {adx:.2f}"
    )

    print(
        f"ATR: {atr:.6f}"
    )

    print(
        f"Highest 5: {highest_5:.6f}"
    )

    print(
        f"Lowest 5: {lowest_5:.6f}"
    )

    # ========================================================
    # CONDICIONES LONG
    # ========================================================

    condiciones_long = {

        "Macro 1h alcista":
            macro_bullish,

        "Precio > EMA200":
            precio > ema200,

        "Precio > VWAP":
            precio > vwap,

        "EMA9 > EMA21":
            ema9 > ema21,

        "RSI > 52":
            rsi > 52,

        "MACD Hist > 0":
            macd_hist > 0,

        "Volumen > SMA20":
            volumen > volumen_sma20,

        "ADX > mínimo":
            adx > configuracion["adx_min"],

        "Breakout > Highest 5":
            precio > highest_5
    }

    # ========================================================
    # CONDICIONES SHORT
    # ========================================================

    condiciones_short = {

        "Macro 1h bajista":
            macro_bearish,

        "Precio < EMA200":
            precio < ema200,

        "Precio < VWAP":
            precio < vwap,

        "EMA9 < EMA21":
            ema9 < ema21,

        "RSI < 48":
            rsi < 48,

        "MACD Hist < 0":
            macd_hist < 0,

        "Volumen > SMA20":
            volumen > volumen_sma20,

        "ADX > mínimo":
            adx > configuracion["adx_min"],

        "Breakdown < Lowest 5":
            precio < lowest_5
    }

    # ========================================================
    # MOSTRAR CONDICIONES
    # ========================================================

    print()
    print("🟢 CONDICIONES LONG")

    for nombre, resultado in condiciones_long.items():

        simbolo = "✅" if resultado else "❌"

        print(
            f"{simbolo} {nombre}"
        )

    print()

    print("🔴 CONDICIONES SHORT")

    for nombre, resultado in condiciones_short.items():

        simbolo = "✅" if resultado else "❌"

        print(
            f"{simbolo} {nombre}"
        )

    print()

    long_cumplidas = mostrar_resumen(
        "🟢 LONG",
        condiciones_long
    )

    short_cumplidas = mostrar_resumen(
        "🔴 SHORT",
        condiciones_short
    )

    # ========================================================
    # CONDICIONES FALTANTES
    # ========================================================

    faltan_long = [
        nombre
        for nombre, resultado
        in condiciones_long.items()
        if not resultado
    ]

    faltan_short = [
        nombre
        for nombre, resultado
        in condiciones_short.items()
        if not resultado
    ]

    print()

    print("🎯 Faltan para LONG:")

    if faltan_long:

        for condicion in faltan_long:

            print(
                f"   ❌ {condicion}"
            )

    else:

        print(
            "   ✅ Ninguna"
        )

    print()

    print("🎯 Faltan para SHORT:")

    if faltan_short:

        for condicion in faltan_short:

            print(
                f"   ❌ {condicion}"
            )

    else:

        print(
            "   ✅ Ninguna"
        )

    # ========================================================
    # SEÑAL LONG
    # ========================================================

    if long_cumplidas == 9:

        riesgo = (
            atr *
            configuracion["atr_mult"]
        )

        stop_loss = (
            precio -
            riesgo
        )

        tp1 = (
            precio +
            (riesgo * 2)
        )

        tp2 = (
            precio +
            (riesgo * 3.5)
        )

        mensaje = f"""
🚨 CRYPTO COPILOT — LONG

ORDER_SIGNAL
PAIR: {simbolo.replace("/", "")}
TYPE: LONG
ENTRY: {precio:.8f}
SL: {stop_loss:.8f}
TP1: {tp1:.8f}
TP2: {tp2:.8f}
END_SIGNAL

📈 Señal LONG detectada

🪙 Activo: {simbolo}
💰 Entrada: {precio:.8f}
🛑 SL: {stop_loss:.8f}
🎯 TP1: {tp1:.8f}
🎯 TP2: {tp2:.8f}

🕒 {obtener_hora_espana()}
"""

        enviado = enviar_telegram(
            mensaje
        )

        if enviado:

            cooldown[simbolo] = (
                time.time()
            )

            return {
                "tipo": "LONG",
                "entrada": precio,
                "sl": stop_loss,
                "tp1": tp1,
                "tp2": tp2
            }

        return None

    # ========================================================
    # SEÑAL SHORT
    # ========================================================

    if short_cumplidas == 9:

        riesgo = (
            atr *
            configuracion["atr_mult"]
        )

        stop_loss = (
            precio +
            riesgo
        )

        tp1 = (
            precio -
            (riesgo * 2)
        )

        tp2 = (
            precio -
            (riesgo * 3.5)
        )

        mensaje = f"""
🚨 CRYPTO COPILOT — SHORT

ORDER_SIGNAL
PAIR: {simbolo.replace("/", "")}
TYPE: SHORT
ENTRY: {precio:.8f}
SL: {stop_loss:.8f}
TP1: {tp1:.8f}
TP2: {tp2:.8f}
END_SIGNAL

📉 Señal SHORT detectada

🪙 Activo: {simbolo}
💰 Entrada: {precio:.8f}
🛑 SL: {stop_loss:.8f}
🎯 TP1: {tp1:.8f}
🎯 TP2: {tp2:.8f}

🕒 {obtener_hora_espana()}
"""

        enviado = enviar_telegram(
            mensaje
        )

        if enviado:

            cooldown[simbolo] = (
                time.time()
            )

            return {
                "tipo": "SHORT",
                "entrada": precio,
                "sl": stop_loss,
                "tp1": tp1,
                "tp2": tp2
            }

        return None

    print()
    print(
        "⛔ Sin confluencia suficiente."
    )

    return None


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print(
        "🚀 CRYPTO COPILOT - "
        "MODELO PRO V1.2"
    )
    print("=" * 70)

    print(
        f"🕒 Escaneo: "
        f"{obtener_hora_espana()}"
    )

    print(
        f"📈 Operativo: "
        f"{TIMEFRAME_OPERATIVO}"
    )

    print(
        f"📊 Macro: "
        f"{TIMEFRAME_MACRO}"
    )

    print(
        f"⏳ Cooldown: "
        f"{COOLDOWN_SEGUNDOS // 60} minutos"
    )

    print(
        f"🪙 Activos: "
        f"{len(CONFIG_ACTIVOS)}"
    )

    print("=" * 70)

    cooldown, sha = cargar_cooldown()

    hubo_cambio_cooldown = False

    for simbolo, configuracion in CONFIG_ACTIVOS.items():

        try:

            resultado = analizar_activo(
                simbolo,
                configuracion,
                cooldown
            )

            if resultado is not None:

                hubo_cambio_cooldown = True

                print()
                print(
                    f"🚨 SEÑAL GENERADA: "
                    f"{simbolo}"
                )

        except Exception as e:

            print()
            print(
                f"❌ Error analizando "
                f"{simbolo}: {e}"
            )

        # Pequeña pausa entre activos
        time.sleep(1)

    # ========================================================
    # GUARDAR COOLDOWN
    # ========================================================

    if hubo_cambio_cooldown:

        guardar_cooldown(
            cooldown,
            sha
        )

    print()
    print("=" * 70)
    print(
        "✅ ESCANEO FINALIZADO"
    )
    print("=" * 70)


if __name__ == "__main__":
    main()
