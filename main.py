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
# 1. CONFIGURACIÓN DE ACTIVOS
# ============================================================

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

# Pedimos suficientes velas para calcular EMA200 y demás indicadores
LIMIT = 300

# Cooldown por activo
COOLDOWN_SEGUNDOS = 1800  # 30 minutos


# ============================================================
# 2. TELEGRAM / GITHUB
# ============================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = "velasquezmg1997-prog/crypto-copilot"
FILE_PATH = "cooldown.json"


# ============================================================
# 3. EXCHANGE
# ============================================================

exchange = ccxt.kucoin({
    "enableRateLimit": True
})


# ============================================================
# 4. HORA ESPAÑA
# ============================================================

def obtener_hora_espana():
    """
    Obtiene la hora real de España usando la zona horaria
    Europe/Madrid, incluyendo automáticamente horario de verano.
    """
    ahora = datetime.now(ZoneInfo("Europe/Madrid"))

    return (
        ahora.hour,
        ahora.strftime("%H:%M"),
        ahora.strftime("%d/%m/%Y %H:%M:%S")
    )


# ============================================================
# 5. COOLDOWN - GITHUB
# ============================================================

def cargar_cooldowns_github():
    """
    Recupera el estado de cooldown desde GitHub.
    """

    if not GITHUB_TOKEN:
        print("⚠️ GITHUB_TOKEN no configurado.")
        return {}

    url = (
        f"https://api.github.com/repos/"
        f"{GITHUB_REPO}/contents/{FILE_PATH}"
    )

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "Cache-Control": "no-cache"
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:

            data = response.json()

            content_encoded = data.get("content", "")

            if not content_encoded:
                return {}

            content_decoded = base64.b64decode(
                content_encoded
            ).decode("utf-8")

            datos = json.loads(content_decoded)

            if isinstance(datos, dict):
                return datos

    except Exception as e:

        print(
            f"⚠️ Error cargando cooldowns desde GitHub: {e}"
        )

    return {}


def guardar_cooldowns_github(ultimas_alertas):
    """
    Guarda el estado actualizado de cooldowns en GitHub.
    """

    if not GITHUB_TOKEN:
        print("⚠️ GITHUB_TOKEN no configurado.")
        return False

    url = (
        f"https://api.github.com/repos/"
        f"{GITHUB_REPO}/contents/{FILE_PATH}"
    )

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "Cache-Control": "no-cache"
    }

    sha = None

    # --------------------------------------------------------
    # Obtener SHA actual del archivo
    # --------------------------------------------------------

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:

            sha = response.json().get("sha")

    except Exception as e:

        print(
            f"⚠️ No se pudo obtener SHA de GitHub: {e}"
        )

    # --------------------------------------------------------
    # Preparar contenido
    # --------------------------------------------------------

    content_str = json.dumps(
        ultimas_alertas,
        indent=4
    )

    content_encoded = base64.b64encode(
        content_str.encode("utf-8")
    ).decode("utf-8")

    payload = {
        "message": (
            "Update cooldown state [skip ci]"
            if sha
            else
            "Create cooldown state [skip ci]"
        ),
        "content": content_encoded
    }

    if sha:
        payload["sha"] = sha

    # --------------------------------------------------------
    # Guardar
    # --------------------------------------------------------

    try:

        if sha:

            response = requests.put(
                url,
                headers=headers,
                json=payload,
                timeout=10
            )

        else:

            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=10
            )

        if response.status_code in (200, 201):

            return True

        print(
            f"⚠️ GitHub respondió "
            f"{response.status_code}: {response.text[:300]}"
        )

    except Exception as e:

        print(
            f"⚠️ Error guardando cooldowns en GitHub: {e}"
        )

    return False


# ============================================================
# 6. TELEGRAM
# ============================================================

def enviar_telegram(mensaje, symbol):
    """
    Envía una señal a Telegram respetando el cooldown.
    """

    ultimas_alertas = cargar_cooldowns_github()

    tiempo_actual = time.time()

    # --------------------------------------------------------
    # Comprobar cooldown
    # --------------------------------------------------------

    if symbol in ultimas_alertas:

        try:

            ultima_alerta = float(
                ultimas_alertas[symbol]
            )

            tiempo_transcurrido = (
                tiempo_actual - ultima_alerta
            )

            if tiempo_transcurrido < COOLDOWN_SEGUNDOS:

                minutos_restantes = max(
                    1,
                    int(
                        (
                            COOLDOWN_SEGUNDOS
                            - tiempo_transcurrido
                        ) / 60
                    )
                )

                print(
                    f"⏳ Cooldown activo para {symbol}. "
                    f"Faltan aproximadamente "
                    f"{minutos_restantes} min."
                )

                return False

        except (ValueError, TypeError):

            print(
                f"⚠️ Timestamp inválido en cooldown "
                f"para {symbol}. Se ignorará."
            )

    # --------------------------------------------------------
    # Comprobar configuración Telegram
    # --------------------------------------------------------

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:

        print(
            "⚠️ Variables TELEGRAM_TOKEN / "
            "TELEGRAM_CHAT_ID no configuradas."
        )

        return False

    # --------------------------------------------------------
    # Enviar
    # --------------------------------------------------------

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensaje,
        "parse_mode": "Markdown"
    }

    try:

        response = requests.post(
            url,
            json=payload,
            timeout=10
        )

        if response.status_code != 200:

            print(
                f"⚠️ Telegram respondió "
                f"{response.status_code}: "
                f"{response.text[:300]}"
            )

            return False

        # ----------------------------------------------------
        # Solo actualizar cooldown después de enviar
        # correctamente
        # ----------------------------------------------------

        ultimas_alertas[symbol] = tiempo_actual

        guardar_cooldowns_github(
            ultimas_alertas
        )

        print(
            f"📲 Alerta enviada correctamente "
            f"para {symbol}."
        )

        return True

    except Exception as e:

        print(
            f"⚠️ Error enviando mensaje a Telegram: {e}"
        )

        return False


# ============================================================
# 7. OBTENER DATOS
# ============================================================

def obtener_datos(symbol, timeframe):
    """
    Obtiene OHLCV desde KuCoin.
    """

    try:

        ohlcv = exchange.fetch_ohlcv(
            symbol,
            timeframe=timeframe,
            limit=LIMIT
        )

        if not ohlcv:

            print(
                f"⚠️ No se recibieron datos "
                f"para {symbol} ({timeframe})."
            )

            return None

        if len(ohlcv) < 200:

            print(
                f"⚠️ Datos insuficientes para "
                f"{symbol} ({timeframe}): "
                f"{len(ohlcv)} velas."
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

        columnas_numericas = [
            "open",
            "high",
            "low",
            "close",
            "volume"
        ]

        df[columnas_numericas] = (
            df[columnas_numericas]
            .astype(float)
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
            f"⚠️ Error obteniendo datos de "
            f"{symbol} ({timeframe}): {e}"
        )

        return None


# ============================================================
# 8. VWAP
# ============================================================

def calcular_vwap(df):
    """
    VWAP acumulado sobre las velas disponibles.

    IMPORTANTE:
    En esta V1 mantenemos el comportamiento de la estrategia
    original. No lo convertimos todavía en VWAP diario.
    """

    typical_price = (
        df["high"]
        + df["low"]
        + df["close"]
    ) / 3.0

    tp_vol = (
        typical_price
        * df["volume"]
    )

    cum_tp_vol = tp_vol.cumsum()

    cum_vol = df["volume"].cumsum()

    vwap = (
        cum_tp_vol
        / (cum_vol + 1e-10)
    )

    return vwap


# ============================================================
# 9. INDICADORES
# ============================================================

def calcular_indicadores(df):

    if df is None or len(df) < 200:
        return None

    df = df.copy()

    # --------------------------------------------------------
    # EMA
    # --------------------------------------------------------

    df["ema9"] = (
        df["close"]
        .ewm(
            span=9,
            adjust=False
        )
        .mean()
    )

    df["ema21"] = (
        df["close"]
        .ewm(
            span=21,
            adjust=False
        )
        .mean()
    )

    df["ema200"] = (
        df["close"]
        .ewm(
            span=200,
            adjust=False
        )
        .mean()
    )

    # --------------------------------------------------------
    # RSI
    # --------------------------------------------------------

    delta = df["close"].diff()

    gain = (
        delta.clip(lower=0)
        .rolling(14)
        .mean()
    )

    loss = (
        (-delta.clip(upper=0))
        .rolling(14)
        .mean()
    )

    rs = gain / (loss + 1e-10)

    df["rsi"] = (
        100
        - (
            100
            / (1 + rs)
        )
    )

    # --------------------------------------------------------
    # MACD
    # --------------------------------------------------------

    ema12 = (
        df["close"]
        .ewm(
            span=12,
            adjust=False
        )
        .mean()
    )

    ema26 = (
        df["close"]
        .ewm(
            span=26,
            adjust=False
        )
        .mean()
    )

    df["macd"] = ema12 - ema26

    df["signal"] = (
        df["macd"]
        .ewm(
            span=9,
            adjust=False
        )
        .mean()
    )

    df["hist"] = (
        df["macd"]
        - df["signal"]
    )

    # --------------------------------------------------------
    # ATR
    # --------------------------------------------------------

    high_low = (
        df["high"]
        - df["low"]
    )

    high_close = (
        df["high"]
        - df["close"].shift(1)
    ).abs()

    low_close = (
        df["low"]
        - df["close"].shift(1)
    ).abs()

    tr = pd.concat(
        [
            high_low,
            high_close,
            low_close
        ],
        axis=1
    ).max(axis=1)

    df["tr"] = tr

    df["atr"] = (
        tr
        .rolling(14)
        .mean()
    )

    # --------------------------------------------------------
    # Volumen
    # --------------------------------------------------------

    df["vol_sma"] = (
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
    #
    # Implementación corregida:
    # +DM y -DM se calculan independientemente.
    # --------------------------------------------------------

    up_move = (
        df["high"]
        .diff()
    )

    down_move = (
        df["low"].shift(1)
        - df["low"]
    )

    plus_dm = pd.Series(
        np.where(
            (up_move > down_move)
            & (up_move > 0),
            up_move,
            0.0
        ),
        index=df.index
    )

    minus_dm = pd.Series(
        np.where(
            (down_move > up_move)
            & (down_move > 0),
            down_move,
            0.0
        ),
        index=df.index
    )

    tr14 = (
        tr.rolling(14)
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
        100
        * plus_dm14
        / (tr14 + 1e-10)
    )

    minus_di = (
        100
        * minus_dm14
        / (tr14 + 1e-10)
    )

    dx = (
        100
        * (plus_di - minus_di).abs()
        / (
            plus_di
            + minus_di
            + 1e-10
        )
    )

    df["adx"] = (
        dx
        .rolling(14)
        .mean()
    )

    # --------------------------------------------------------
    # Estructura
    #
    # shift(1) evita utilizar la vela actual para determinar
    # el máximo/mínimo de referencia.
    # --------------------------------------------------------

    df["highest_5"] = (
        df["high"]
        .shift(1)
        .rolling(5)
        .max()
    )

    df["lowest_5"] = (
        df["low"]
        .shift(1)
        .rolling(5)
        .min()
    )

    return df


# ============================================================
# 10. VALIDACIÓN DE VELA CERRADA
# ============================================================

def obtener_ultima_vela_cerrada(df):
    """
    La última fila recibida por el exchange puede estar todavía
    en formación.

    Por seguridad utilizamos -2 como última vela cerrada.
    """

    if df is None or len(df) < 3:
        return None

    return df.iloc[-2]


# ============================================================
# 11. ANALIZAR ACTIVO
# ============================================================

def analizar_activo(symbol):

    config = CONFIG_ACTIVOS.get(
        symbol,
        {
            "atr_sl": 1.5,
            "rr_tp1": 2.0,
            "rr_tp2": 3.5,
            "adx_min": 25
        }
    )

    # ========================================================
    # 11.1 MACRO 1H
    # ========================================================

    df_macro = obtener_datos(
        symbol,
        TIMEFRAME_MACRO
    )

    if df_macro is None:
        return

    df_macro["ema200"] = (
        df_macro["close"]
        .ewm(
            span=200,
            adjust=False
        )
        .mean()
    )

    macro = obtener_ultima_vela_cerrada(
        df_macro
    )

    if macro is None:
        return

    macro_close = macro["close"]
    macro_ema200 = macro["ema200"]

    if pd.isna(macro_close) or pd.isna(macro_ema200):
        return

    tendencia_macro = (
        "BULLISH"
        if macro_close > macro_ema200
        else "BEARISH"
    )

    # ========================================================
    # 11.2 OPERATIVO 15M
    # ========================================================

    df = obtener_datos(
        symbol,
        TIMEFRAME_OPERATIVO
    )

    if df is None:
        return

    df = calcular_indicadores(df)

    if df is None:
        return

    last = obtener_ultima_vela_cerrada(df)

    if last is None:
        return

    # ========================================================
    # 11.3 VALIDAR INDICADORES
    # ========================================================

    columnas_requeridas = [
        "close",
        "ema200",
        "rsi",
        "hist",
        "atr",
        "volume",
        "vol_sma",
        "ema9",
        "ema21",
        "adx",
        "vwap",
        "highest_5",
        "lowest_5"
    ]

    for columna in columnas_requeridas:

        if pd.isna(last[columna]):

            print(
                f"⚠️ {symbol}: "
                f"Indicador {columna} no disponible."
            )

            return

    # ========================================================
    # 11.4 VALORES
    # ========================================================

    precio = float(last["close"])

    ema200 = float(last["ema200"])
    rsi = float(last["rsi"])
    macd_hist = float(last["hist"])
    atr = float(last["atr"])

    volume = float(last["volume"])
    vol_sma = float(last["vol_sma"])

    ema9 = float(last["ema9"])
    ema21 = float(last["ema21"])

    adx = float(last["adx"])
    vwap = float(last["vwap"])

    highest_5 = float(last["highest_5"])
    lowest_5 = float(last["lowest_5"])

    symbol_clean = symbol.replace(
        "/",
        ""
    )

    # ========================================================
    # 11.5 INFORMACIÓN DE DEBUG
    # ========================================================

    print(
        f"\n📊 {symbol_clean}"
    )

    print(
        f"   Cierre 15m: {precio:.6f}"
    )

    print(
        f"   Macro 1h: {tendencia_macro}"
    )

    print(
        f"   EMA9/EMA21: "
        f"{ema9:.6f} / {ema21:.6f}"
    )

    print(
        f"   RSI: {rsi:.2f}"
    )

    print(
        f"   ADX: {adx:.2f}"
    )

    print(
        f"   ATR: {atr:.6f}"
    )

    # ========================================================
    # 11.6 LONG
    # ========================================================

    cond_long = (
        tendencia_macro == "BULLISH"
        and precio > ema200
        and precio > vwap
        and ema9 > ema21
        and rsi > 52
        and macd_hist > 0
        and volume > vol_sma
        and adx > config["adx_min"]
        and precio > highest_5
    )

    if cond_long:

        distancia_sl = (
            config["atr_sl"]
            * atr
        )

        stop_loss = (
            precio
            - distancia_sl
        )

        take_profit1 = (
            precio
            + (
                distancia_sl
                * config["rr_tp1"]
            )
        )

        take_profit2 = (
            precio
            + (
                distancia_sl
                * config["rr_tp2"]
            )
        )

        riesgo_pct = (
            (
                precio
                - stop_loss
            )
            / precio
        ) * 100

        msg = (
            "```ORDER_SIGNAL\n"
            f"PAIR: {symbol_clean}\n"
            "TYPE: LONG\n"
            f"ENTRY: {precio:.8f}\n"
            f"SL: {stop_loss:.8f}\n"
            f"TP1: {take_profit1:.8f}\n"
            f"TP2: {take_profit2:.8f}\n"
            "END_SIGNAL```\n\n"

            f"🚨 *ALERTA PRO (LONG 🟢) - "
            f"{symbol_clean} {TIMEFRAME_OPERATIVO}*\n\n"

            f"📊 *Filtro Macro (1h):* "
            f"Alcista 🟢\n"

            f"🔥 *ADX:* `{adx:.1f}` | "
            f"*VWAP:* `${vwap:.8f}`\n\n"

            f"🎯 *Parámetros Adaptativos "
            f"(R:B 1:{config['rr_tp1']}):*\n"

            f"• *Entrada:* "
            f"`${precio:.8f}`\n"

            f"• *Stop Loss:* "
            f"`${stop_loss:.8f}` "
            f"(~`{riesgo_pct:.2f}%`)\n"

            f"• *Take Profit 1:* "
            f"`${take_profit1:.8f}`\n"

            f"• *Take Profit 2:* "
            f"`${take_profit2:.8f}`"
        )

        enviar_telegram(
            msg,
            symbol
        )

        return

    # ========================================================
    # 11.7 SHORT
    # ========================================================

    cond_short = (
        tendencia_macro == "BEARISH"
        and precio < ema200
        and precio < vwap
        and ema9 < ema21
        and rsi < 48
        and macd_hist < 0
        and volume > vol_sma
        and adx > config["adx_min"]
        and precio < lowest_5
    )

    if cond_short:

        distancia_sl = (
            config["atr_sl"]
            * atr
        )

        stop_loss = (
            precio
            + distancia_sl
        )

        take_profit1 = (
            precio
            - (
                distancia_sl
                * config["rr_tp1"]
            )
        )

        take_profit2 = (
            precio
            - (
                distancia_sl
                * config["rr_tp2"]
            )
        )

        riesgo_pct = (
            (
                stop_loss
                - precio
            )
            / precio
        ) * 100

        msg = (
            "```ORDER_SIGNAL\n"
            f"PAIR: {symbol_clean}\n"
            "TYPE: SHORT\n"
            f"ENTRY: {precio:.8f}\n"
            f"SL: {stop_loss:.8f}\n"
            f"TP1: {take_profit1:.8f}\n"
            f"TP2: {take_profit2:.8f}\n"
            "END_SIGNAL```\n\n"

            f"🚨 *ALERTA PRO (SHORT 🔴) - "
            f"{symbol_clean} {TIMEFRAME_OPERATIVO}*\n\n"

            f"📊 *Filtro Macro (1h):* "
            f"Bajista 🔴\n"

            f"🔥 *ADX:* `{adx:.1f}` | "
            f"*VWAP:* `${vwap:.8f}`\n\n"

            f"🎯 *Parámetros Adaptativos "
            f"(R:B 1:{config['rr_tp1']}):*\n"

            f"• *Entrada:* "
            f"`${precio:.8f}`\n"

            f"• *Stop Loss:* "
            f"`${stop_loss:.8f}` "
            f"(~`{riesgo_pct:.2f}%`)\n"

            f"• *Take Profit 1:* "
            f"`${take_profit1:.8f}`\n"

            f"• *Take Profit 2:* "
            f"`${take_profit2:.8f}`"
        )

        enviar_telegram(
            msg,
            symbol
        )

        return

    print(
        f"ℹ️ {symbol_clean}: "
        f"Sin confluencia suficiente."
    )


# ============================================================
# 12. MAIN
# ============================================================

def main():

    _, hora_str, fecha_hora = (
        obtener_hora_espana()
    )

    print(
        "\n"
        "==========================================\n"
        "🚀 CRYPTO COPILOT - MODELO PRO V1\n"
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
        "==========================================\n"
    )

    for symbol in CONFIG_ACTIVOS:

        try:

            analizar_activo(symbol)

        except Exception as e:

            print(
                f"❌ Error inesperado analizando "
                f"{symbol}: {e}"
            )

    print(
        "\n✅ Escaneo finalizado.\n"
    )


# ============================================================
# 13. EJECUCIÓN
# ============================================================

if __name__ == "__main__":
    main()
