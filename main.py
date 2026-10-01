```python
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
    "BTCUSDT": {
        "adx_min": 20,
        "sl_atr": 1.2,
    },
    "ETHUSDT": {
        "adx_min": 20,
        "sl_atr": 1.2,
    },
    "BNBUSDT": {
        "adx_min": 22,
        "sl_atr": 1.4,
    },
    "SOLUSDT": {
        "adx_min": 25,
        "sl_atr": 1.6,
    },
    "XRPUSDT": {
        "adx_min": 25,
        "sl_atr": 1.6,
    },
    "ADAUSDT": {
        "adx_min": 25,
        "sl_atr": 1.6,
    },
    "AVAXUSDT": {
        "adx_min": 25,
        "sl_atr": 1.6,
    },
    "NEARUSDT": {
        "adx_min": 25,
        "sl_atr": 1.6,
    },
    "LINKUSDT": {
        "adx_min": 25,
        "sl_atr": 1.6,
    },
    "SUIUSDT": {
        "adx_min": 28,
        "sl_atr": 2.0,
    },
}


TIMEFRAME_OPERATIVO = "15m"
TIMEFRAME_MACRO = "1h"

LIMIT = 300

COOLDOWN_SEGUNDOS = 1800


# ============================================================
# CREDENCIALES
# ============================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

GITHUB_REPO = "velasquezmg1997-prog/crypto-copilot"
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

    return ahora.strftime(
        "%d/%m/%Y %H:%M:%S"
    )


# ============================================================
# GITHUB - CARGAR COOLDOWNS
# ============================================================

def cargar_cooldowns_github():

    if not GITHUB_TOKEN:
        print("⚠️ GITHUB_TOKEN no configurado.")
        return {}

    url = (
        f"https://api.github.com/repos/"
        f"{GITHUB_REPO}/contents/{GITHUB_FILE}"
    )

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=15
        )

        if response.status_code == 200:

            data = response.json()

            contenido = base64.b64decode(
                data["content"]
            ).decode("utf-8")

            return json.loads(contenido)

        elif response.status_code == 404:

            return {}

        else:

            print(
                f"⚠️ Error GitHub cargando cooldowns: "
                f"{response.status_code}"
            )

            return {}

    except Exception as e:

        print(
            f"⚠️ Error leyendo cooldowns: {e}"
        )

        return {}


# ============================================================
# GITHUB - GUARDAR COOLDOWNS
# ============================================================

def guardar_cooldowns_github(cooldowns):

    if not GITHUB_TOKEN:
        print("⚠️ GITHUB_TOKEN no configurado.")
        return False

    url = (
        f"https://api.github.com/repos/"
        f"{GITHUB_REPO}/contents/{GITHUB_FILE}"
    )

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=15
        )

        sha = None

        if response.status_code == 200:

            sha = response.json().get("sha")

        contenido = json.dumps(
            cooldowns,
            indent=2
        )

        contenido_b64 = base64.b64encode(
            contenido.encode("utf-8")
        ).decode("utf-8")

        payload = {
            "message": "Actualizar cooldowns",
            "content": contenido_b64
        }

        if sha:
            payload["sha"] = sha

        response = requests.put(
            url,
            headers=headers,
            json=payload,
            timeout=15
        )

        if response.status_code in [200, 201]:

            return True

        print(
            f"⚠️ Error guardando cooldowns: "
            f"{response.status_code}"
        )

        return False

    except Exception as e:

        print(
            f"⚠️ Error guardando cooldowns: {e}"
        )

        return False


# ============================================================
# TELEGRAM
# ============================================================

def enviar_telegram(mensaje):

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:

        print("⚠️ Telegram no configurado.")

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
            timeout=15
        )

        if response.status_code == 200:

            return True

        print(
            f"⚠️ Error Telegram: "
            f"{response.status_code}"
        )

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

    simbolo_ccxt = simbolo.replace(
        "USDT",
        "/USDT"
    )

    try:

        ohlcv = exchange.fetch_ohlcv(
            simbolo_ccxt,
            timeframe=timeframe,
            limit=LIMIT
        )

        if len(ohlcv) < 200:

            print(
                f"⚠️ {simbolo}: Datos insuficientes."
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

        for columna in [
            "open",
            "high",
            "low",
            "close",
            "volume"
        ]:

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
        df["high"]
        + df["low"]
        + df["close"]
    ) / 3

    volumen = df["volume"]

    return (
        precio_tipico * volumen
    ).cumsum() / volumen.cumsum()


# ============================================================
# INDICADORES
# ============================================================

def calcular_indicadores(df):

    df = df.copy()

    # EMA
    df["ema9"] = df["close"].ewm(
        span=9,
        adjust=False
    ).mean()

    df["ema21"] = df["close"].ewm(
        span=21,
        adjust=False
    ).mean()

    df["ema200"] = df["close"].ewm(
        span=200,
        adjust=False
    ).mean()

    # RSI
    delta = df["close"].diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()

    rs = avg_gain / avg_loss.replace(
        0,
        np.nan
    )

    df["rsi"] = 100 - (
        100 / (1 + rs)
    )

    # MACD
    ema12 = df["close"].ewm(
        span=12,
        adjust=False
    ).mean()

    ema26 = df["close"].ewm(
        span=26,
        adjust=False
    ).mean()

    df["macd"] = ema12 - ema26

    df["macd_signal"] = df["macd"].ewm(
        span=9,
        adjust=False
    ).mean()

    df["macd_hist"] = (
        df["macd"]
        - df["macd_signal"]
    )

    # ATR
    high_low = (
        df["high"] - df["low"]
    )

    high_close = (
        df["high"]
        - df["close"].shift()
    ).abs()

    low_close = (
        df["low"]
        - df["close"].shift()
    ).abs()

    true_range = pd.concat(
        [
            high_low,
            high_close,
            low_close
        ],
        axis=1
    ).max(axis=1)

    df["atr"] = true_range.rolling(
        14
    ).mean()

    # Volumen
    df["volume_sma20"] = df[
        "volume"
    ].rolling(20).mean()

    # VWAP
    df["vwap"] = calcular_vwap(df)

    # ========================================================
    # ADX
    # ========================================================

    up_move = df["high"].diff()

    down_move = (
        df["low"].shift(1)
        - df["low"]
    )

    plus_dm = np.where(
        (up_move > down_move)
        & (up_move > 0),
        up_move,
        0.0
    )

    minus_dm = np.where(
        (down_move > up_move)
        & (down_move > 0),
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

    atr14 = true_range.rolling(
        14
    ).sum()

    plus_di = (
        100
        * plus_dm.rolling(14).sum()
        / atr14
    )

    minus_di = (
        100
        * minus_dm.rolling(14).sum()
        / atr14
    )

    denominator = (
        plus_di + minus_di
    )

    dx = (
        100
        * (plus_di - minus_di).abs()
        / denominator.replace(
            0,
            np.nan
        )
    )

    df["adx"] = dx.rolling(
        14
    ).mean()

    # ========================================================
    # ESTRUCTURA
    # ========================================================

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
# CONDICIÓN
# ============================================================

def mostrar_condicion(nombre, valor):

    if valor:
        print(f"   ✅ {nombre}")
    else:
        print(f"   ❌ {nombre}")


# ============================================================
# CONTADOR
# ============================================================

def mostrar_resumen(direccion, condiciones):

    total = len(condiciones)
    cumplidas = sum(condiciones)

    print(
        f"   {direccion}: "
        f"{cumplidas}/{total} condiciones"
    )

    return cumplidas


# ============================================================
# ANALIZAR ACTIVO
# ============================================================

def analizar_activo(
    simbolo,
    config,
    cooldowns
):

    print()
    print("=" * 60)
    print(f"📊 {simbolo}")

    # ========================================================
    # DATOS
    # ========================================================

    df_15m = obtener_datos(
        simbolo,
        TIMEFRAME_OPERATIVO
    )

    df_1h = obtener_datos(
        simbolo,
        TIMEFRAME_MACRO
    )

    if df_15m is None or df_1h is None:

        print(
            f"❌ {simbolo}: "
            f"No se pudieron obtener datos."
        )

        return

    # ========================================================
    # INDICADORES
    # ========================================================

    df_15m = calcular_indicadores(
        df_15m
    )

    df_1h = calcular_indicadores(
        df_1h
    )

    vela_15m = obtener_ultima_vela_cerrada(
        df_15m
    )

    vela_1h = obtener_ultima_vela_cerrada(
        df_1h
    )

    if vela_15m is None or vela_1h is None:

        print(
            f"❌ {simbolo}: "
            f"No hay velas suficientes."
        )

        return

    # ========================================================
    # HORA DE LA VELA
    # ========================================================

    hora_vela_15m = vela_15m["timestamp"]

    hora_vela_1h = vela_1h["timestamp"]

    print(
        f"🕯️ Vela 15m analizada: "
        f"{hora_vela_15m}"
    )

    print(
        f"🕯️ Vela 1h analizada: "
        f"{hora_vela_1h}"
    )

    # ========================================================
    # VALORES
    # ========================================================

    precio = vela_15m["close"]

    ema9 = vela_15m["ema9"]
    ema21 = vela_15m["ema21"]
    ema200 = vela_15m["ema200"]

    rsi = vela_15m["rsi"]

    macd_hist = vela_15m["macd_hist"]

    atr = vela_15m["atr"]

    volume = vela_15m["volume"]
    volume_sma20 = vela_15m["volume_sma20"]

    vwap = vela_15m["vwap"]

    adx = vela_15m["adx"]

    highest_5 = vela_15m["highest_5"]
    lowest_5 = vela_15m["lowest_5"]

    close_1h = vela_1h["close"]
    ema200_1h = vela_1h["ema200"]

    # ========================================================
    # MACRO
    # ========================================================

    macro_bullish = (
        close_1h > ema200_1h
    )

    macro_bearish = (
        close_1h < ema200_1h
    )

    macro_text = (
        "BULLISH"
        if macro_bullish
        else "BEARISH"
    )

    # ========================================================
    # INFORMACIÓN
    # ========================================================

    print(
        f"   Cierre 15m: {precio:.6f}"
    )

    print(
        f"   Macro 1h: {macro_text}"
    )

    print(
        f"   EMA9/EMA21: "
        f"{ema9:.6f} / {ema21:.6f}"
    )

    print(
        f"   EMA200: {ema200:.6f}"
    )

    print(
        f"   VWAP: {vwap:.6f}"
    )

    print(
        f"   RSI: {rsi:.2f}"
    )

    print(
        f"   MACD Hist: {macd_hist:.6f}"
    )

    print(
        f"   Volumen: {volume:.2f}"
    )

    print(
        f"   Vol SMA20: {volume_sma20:.2f}"
    )

    print(
        f"   ADX: {adx:.2f}"
    )

    print(
        f"   ATR: {atr:.6f}"
    )

    print(
        f"   Máximo 5 velas: {highest_5:.6f}"
    )

    print(
        f"   Mínimo 5 velas: {lowest_5:.6f}"
    )

    # ========================================================
    # LONG
    # ========================================================

    long_conditions = [
        macro_bullish,
        precio > ema200,
        precio > vwap,
        ema9 > ema21,
        rsi > 52,
        macd_hist > 0,
        volume > volume_sma20,
        adx > config["adx_min"],
        precio > highest_5
    ]

    long_names = [
        "Macro 1h BULLISH",
        "Precio > EMA200",
        "Precio > VWAP",
        "EMA9 > EMA21",
        "RSI > 52",
        "MACD Hist > 0",
        "Volumen > SMA20",
        f"ADX > {config['adx_min']}",
        "Precio > máximo 5 velas"
    ]

    # ========================================================
    # SHORT
    # ========================================================

    short_conditions = [
        macro_bearish,
        precio < ema200,
        precio < vwap,
        ema9 < ema21,
        rsi < 48,
        macd_hist < 0,
        volume > volume_sma20,
        adx > config["adx_min"],
        precio < lowest_5
    ]

    short_names = [
        "Macro 1h BEARISH",
        "Precio < EMA200",
        "Precio < VWAP",
        "EMA9 < EMA21",
        "RSI < 48",
        "MACD Hist < 0",
        "Volumen > SMA20",
        f"ADX > {config['adx_min']}",
        "Precio < mínimo 5 velas"
    ]

    # ========================================================
    # MOSTRAR LONG
    # ========================================================

    print()
    print("   🟢 CONDICIONES LONG")

    for nombre, condicion in zip(
        long_names,
        long_conditions
    ):

        mostrar_condicion(
            nombre,
            condicion
        )

    long_count = mostrar_resumen(
        "🟢 LONG",
        long_conditions
    )

    # ========================================================
    # MOSTRAR SHORT
    # ========================================================

    print()
    print("   🔴 CONDICIONES SHORT")

    for nombre, condicion in zip(
        short_names,
        short_conditions
    ):

        mostrar_condicion(
            nombre,
            condicion
        )

    short_count = mostrar_resumen(
        "🔴 SHORT",
        short_conditions
    )

    # ========================================================
    # CONDICIONES FALTANTES
    # ========================================================

    long_faltantes = [
        nombre
        for nombre, condicion
        in zip(
            long_names,
            long_conditions
        )
        if not condicion
    ]

    short_faltantes = [
        nombre
        for nombre, condicion
        in zip(
            short_names,
            short_conditions
        )
        if not condicion
    ]

    print()

    if long_faltantes:

        print(
            "   🎯 Faltan para LONG:"
        )

        for condicion in long_faltantes:

            print(
                f"      ❌ {condicion}"
            )

    else:

        print(
            "   🚨 LONG COMPLETO"
        )

    print()

    if short_faltantes:

        print(
            "   🎯 Faltan para SHORT:"
        )

        for condicion in short_faltantes:

            print(
                f"      ❌ {condicion}"
            )

    else:

        print(
            "   🚨 SHORT COMPLETO"
        )

    # ========================================================
    # SEÑAL FINAL
    # ========================================================

    señal_long = all(
        long_conditions
    )

    señal_short = all(
        short_conditions
    )

    print()

    if señal_long:

        print(
            "🚨🚨🚨 SEÑAL LONG DETECTADA 🚨🚨🚨"
        )

    elif señal_short:

        print(
            "🚨🚨🚨 SEÑAL SHORT DETECTADA 🚨🚨🚨"
        )

    else:

        print(
            "ℹ️ Sin confluencia suficiente."
        )


# ============================================================
# MAIN
# ============================================================

def main():

    fecha_hora = obtener_hora_espana()

    print()
    print(
        "🚀 CRYPTO COPILOT - MODELO PRO V1.2"
    )

    print(
        "=========================================="
    )

    print(
        f"🕒 Escaneo: {fecha_hora}"
    )

    print(
        f"📈 Operativo: {TIMEFRAME_OPERATIVO}"
    )

    print(
        f"📊 Macro: {TIMEFRAME_MACRO}"
    )

    print(
        f"⏳ Cooldown: "
        f"{COOLDOWN_SEGUNDOS // 60} minutos"
    )

    print(
        f"🪙 Activos: "
        f"{len(CONFIG_ACTIVOS)}"
    )

    print(
        "=========================================="
    )

    cooldowns = cargar_cooldowns_github()

    for simbolo, config in CONFIG_ACTIVOS.items():

        try:

            analizar_activo(
                simbolo,
                config,
                cooldowns
            )

        except Exception as e:

            print(
                f"❌ Error analizando "
                f"{simbolo}: {e}"
            )

        time.sleep(1)

    print()
    print(
        "=========================================="
    )

    print(
        "✅ Escaneo finalizado."
    )


# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":

    main()
```
