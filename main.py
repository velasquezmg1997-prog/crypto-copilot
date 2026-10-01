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
# CRYPTO COPILOT - V1.2
# Scanner de señales 15m + filtro macro 1h
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
LIMIT = 300
COOLDOWN_SEGUNDOS = 1800
ZONA_HORARIA = ZoneInfo("Europe/Madrid")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GITHUB_REPO = os.getenv(
    "GITHUB_REPO",
    "velasquezmg1997-prog/crypto-copilot"
).strip()
FILE_PATH = os.getenv("COOLDOWN_FILE_PATH", "cooldown.json").strip()

exchange = ccxt.kucoin({"enableRateLimit": True})


def obtener_hora_espana():
    ahora = datetime.now(ZONA_HORARIA)
    return ahora.hour, ahora.strftime("%H:%M:%S")


def validar_configuracion():
    faltantes = []
    if not TELEGRAM_TOKEN:
        faltantes.append("TELEGRAM_TOKEN")
    if not TELEGRAM_CHAT_ID:
        faltantes.append("TELEGRAM_CHAT_ID")

    if faltantes:
        print("⚠ Variables no configuradas: " + ", ".join(faltantes))
        return False
    return True


def github_headers():
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "Cache-Control": "no-cache",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def cargar_cooldowns_github():
    if not GITHUB_TOKEN:
        return {}

    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{FILE_PATH}"

    try:
        response = requests.get(url, headers=github_headers(), timeout=15)

        if response.status_code == 404:
            return {}

        response.raise_for_status()
        data = response.json()
        content_encoded = data.get("content", "").replace("\n", "")

        if not content_encoded:
            return {}

        content_decoded = base64.b64decode(content_encoded).decode("utf-8")
        contenido = json.loads(content_decoded)

        return contenido if isinstance(contenido, dict) else {}

    except Exception as exc:
        print(f"⚠ Error cargando cooldowns desde GitHub: {exc}")
        return {}


def guardar_cooldowns_github(ultimas_alertas):
    if not GITHUB_TOKEN:
        print("ℹ️ GITHUB_TOKEN no configurado; cooldown persistente desactivado.")
        return False

    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{FILE_PATH}"
    headers = github_headers()
    sha = None

    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            sha = response.json().get("sha")
        elif response.status_code != 404:
            print(
                f"⚠ Error consultando cooldown.json: "
                f"{response.status_code} {response.text[:200]}"
            )
    except Exception as exc:
        print(f"⚠ Error consultando SHA: {exc}")

    contenido = json.dumps(ultimas_alertas, indent=4, ensure_ascii=False)
    contenido_encoded = base64.b64encode(
        contenido.encode("utf-8")
    ).decode("utf-8")

    payload = {
        "message": "Update cooldown state [skip ci]",
        "content": contenido_encoded,
    }

    if sha:
        payload["sha"] = sha

    try:
        response = requests.put(
            url,
            headers=headers,
            json=payload,
            timeout=15,
        )

        if response.status_code in (200, 201):
            print("💾 Cooldown guardado en GitHub.")
            return True

        print(
            f"⚠ No se pudo guardar cooldown: "
            f"{response.status_code} {response.text[:300]}"
        )
    except Exception as exc:
        print(f"⚠ Error guardando cooldowns: {exc}")

    return False


def enviar_telegram(mensaje, symbol):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"⚠ No se puede enviar {symbol}: faltan variables de Telegram.")
        return False

    ultimas_alertas = cargar_cooldowns_github()
    tiempo_actual = time.time()
    ultimo_envio = ultimas_alertas.get(symbol)

    if ultimo_envio is not None:
        try:
            transcurrido = tiempo_actual - float(ultimo_envio)
            if transcurrido < COOLDOWN_SEGUNDOS:
                minutos = max(
                    1,
                    int(np.ceil((COOLDOWN_SEGUNDOS - transcurrido) / 60))
                )
                print(f"⏳ Cooldown activo para {symbol}. Faltan ~{minutos} min.")
                return False
        except (TypeError, ValueError):
            print(f"⚠ Cooldown inválido para {symbol}; se ignorará.")

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensaje,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }

    try:
        response = requests.post(url, json=payload, timeout=15)

        if response.status_code != 200:
            print(
                f"❌ Telegram rechazó {symbol}: "
                f"{response.status_code} {response.text[:300]}"
            )
            return False

        data = response.json()
        if not data.get("ok", False):
            print(f"❌ Telegram indicó error para {symbol}: {data}")
            return False

        ultimas_alertas[symbol] = tiempo_actual
        guardar_cooldowns_github(ultimas_alertas)
        print(f"📲 Alerta enviada correctamente para {symbol}.")
        return True

    except Exception as exc:
        print(f"❌ Error enviando Telegram: {exc}")
        return False


def obtener_datos(symbol, timeframe):
    try:
        ohlcv = exchange.fetch_ohlcv(
            symbol,
            timeframe=timeframe,
            limit=LIMIT,
        )

        if not ohlcv or len(ohlcv) < 200:
            print(
                f"⚠ Datos insuficientes para {symbol} ({timeframe}): "
                f"{len(ohlcv) if ohlcv else 0}"
            )
            return None

        df = pd.DataFrame(
            ohlcv,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )

        cols = ["open", "high", "low", "close", "volume"]
        df[cols] = df[cols].astype(float)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)

        # Usamos únicamente velas cerradas.
        if len(df) > 1:
            df = df.iloc[:-1].copy()

        return df.reset_index(drop=True)

    except Exception as exc:
        print(f"❌ Error obteniendo {symbol} ({timeframe}): {exc}")
        return None


def calcular_vwap(df):
    typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
    tp_vol = typical_price * df["volume"]
    return tp_vol.cumsum() / (df["volume"].cumsum() + 1e-10)


def calcular_indicadores(df):
    if df is None or len(df) < 200:
        return None

    df = df.copy()

    df["ema9"] = df["close"].ewm(span=9, adjust=False).mean()
    df["ema21"] = df["close"].ewm(span=21, adjust=False).mean()
    df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()

    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
    rs = gain / (loss + 1e-10)
    df["rsi"] = 100 - (100 / (1 + rs))

    ema12 = df["close"].ewm(span=12, adjust=False).mean()
    ema26 = df["close"].ewm(span=26, adjust=False).mean()
    df["macd"] = ema12 - ema26
    df["signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["hist"] = df["macd"] - df["signal"]

    high_low = df["high"] - df["low"]
    high_close = np.abs(df["high"] - df["close"].shift())
    low_close = np.abs(df["low"] - df["close"].shift())

    tr = pd.concat(
        [high_low, high_close, low_close],
        axis=1,
    ).max(axis=1)

    df["atr"] = tr.rolling(14).mean()
    df["vol_sma"] = df["volume"].rolling(20).mean()
    df["vwap"] = calcular_vwap(df)

    # ADX corregido: el movimiento bajista se calcula como
    # low anterior - low actual.
    up_move = df["high"].diff()
    down_move = -df["low"].diff()

    plus_dm = np.where(
        (up_move > down_move) & (up_move > 0),
        up_move,
        0.0,
    )

    minus_dm = np.where(
        (down_move > up_move) & (down_move > 0),
        down_move,
        0.0,
    )

    plus_dm = pd.Series(plus_dm, index=df.index)
    minus_dm = pd.Series(minus_dm, index=df.index)

    tr14 = tr.rolling(14).sum()
    plus_di = 100 * plus_dm.rolling(14).sum() / (tr14 + 1e-10)
    minus_di = 100 * minus_dm.rolling(14).sum() / (tr14 + 1e-10)

    dx = (
        100
        * (plus_di - minus_di).abs()
        / (plus_di + minus_di + 1e-10)
    )

    df["adx"] = dx.rolling(14).mean()

    df["highest_5"] = df["high"].shift(1).rolling(5).max()
    df["lowest_5"] = df["low"].shift(1).rolling(5).min()

    return df


def construir_mensaje(
    symbol,
    tipo,
    precio,
    stop_loss,
    take_profit1,
    take_profit2,
    riesgo_pct,
    adx,
    vwap,
    config,
):
    symbol_clean = symbol.replace("/", "")

    if tipo == "LONG":
        emoji = "🟢"
        macro_texto = "Alcista 🟢"
    else:
        emoji = "🔴"
        macro_texto = "Bajista 🔴"

    return (
        "```ORDER_SIGNAL\n"
        f"PAIR: {symbol_clean}\n"
        f"TYPE: {tipo}\n"
        f"ENTRY: {precio:.8f}\n"
        f"SL: {stop_loss:.8f}\n"
        f"TP1: {take_profit1:.8f}\n"
        f"TP2: {take_profit2:.8f}\n"
        "END_SIGNAL```\n\n"
        f"🚨 *ALERTA PRO ({tipo} {emoji}) - "
        f"{symbol_clean} {TIMEFRAME_OPERATIVO}*\n\n"
        f"📊 *Filtro Macro (1h):* {macro_texto}\n"
        f"🔥 *ADX:* `{adx:.1f}` | *VWAP:* `${vwap:.8f}`\n\n"
        f"🎯 *Parámetros Adaptativos (R:B 1:{config['rr_tp1']}):*\n"
        f"• *Entrada:* `${precio:.8f}`\n"
        f"• *Stop Loss:* `${stop_loss:.8f}` (~`{riesgo_pct:.2f}%`)\n"
        f"• *Take Profit 1:* `${take_profit1:.8f}`\n"
        f"• *Take Profit 2:* `${take_profit2:.8f}`"
    )


def analizar_activo(symbol):
    config = CONFIG_ACTIVOS[symbol]

    print(f"\n🔎 Analizando {symbol}...")

    # Filtro macro 1h.
    df_macro = obtener_datos(symbol, TIMEFRAME_MACRO)
    if df_macro is None:
        return

    df_macro["ema200"] = df_macro["close"].ewm(
        span=200,
        adjust=False,
    ).mean()

    macro_close = float(df_macro["close"].iloc[-1])
    macro_ema200 = float(df_macro["ema200"].iloc[-1])

    tendencia_macro = (
        "BULLISH" if macro_close > macro_ema200 else "BEARISH"
    )

    # Operativa 15m.
    df = obtener_datos(symbol, TIMEFRAME_OPERATIVO)
    if df is None:
        return

    df = calcular_indicadores(df)
    if df is None:
        return

    last = df.iloc[-1]

    columnas = [
        "close", "ema200", "rsi", "hist", "atr", "volume",
        "vol_sma", "ema9", "ema21", "adx", "vwap",
        "highest_5", "lowest_5",
    ]

    if any(pd.isna(last[col]) for col in columnas):
        print(f"⚠ Indicadores incompletos para {symbol}.")
        return

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

    if precio <= 0 or atr <= 0:
        print(f"⚠ Precio/ATR inválido para {symbol}.")
        return

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
        distancia_sl = config["atr_sl"] * atr
        stop_loss = precio - distancia_sl
        take_profit1 = precio + distancia_sl * config["rr_tp1"]
        take_profit2 = precio + distancia_sl * config["rr_tp2"]
        riesgo_pct = ((precio - stop_loss) / precio) * 100

        mensaje = construir_mensaje(
            symbol,
            "LONG",
            precio,
            stop_loss,
            take_profit1,
            take_profit2,
            riesgo_pct,
            adx,
            vwap,
            config,
        )

        enviar_telegram(mensaje, symbol)
        return

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
        distancia_sl = config["atr_sl"] * atr
        stop_loss = precio + distancia_sl
        take_profit1 = precio - distancia_sl * config["rr_tp1"]
        take_profit2 = precio - distancia_sl * config["rr_tp2"]
        riesgo_pct = ((stop_loss - precio) / precio) * 100

        mensaje = construir_mensaje(
            symbol,
            "SHORT",
            precio,
            stop_loss,
            take_profit1,
            take_profit2,
            riesgo_pct,
            adx,
            vwap,
            config,
        )

        enviar_telegram(mensaje, symbol)
        return

    print(f"ℹ️ {symbol}: sin confluencia suficiente.")


def main():
    inicio = time.time()
    _, hora_str = obtener_hora_espana()

    print("=" * 60)
    print("🚀 CRYPTO COPILOT V1.2")
    print(f"🕒 Escaneo iniciado: {hora_str} (Europe/Madrid)")
    print(
        f"📈 Operativo: {TIMEFRAME_OPERATIVO} | "
        f"Macro: {TIMEFRAME_MACRO}"
    )
    print(f"💾 Cooldown: {COOLDOWN_SEGUNDOS // 60} minutos")
    print("=" * 60)

    validar_configuracion()

    for symbol in CONFIG_ACTIVOS:
        try:
            analizar_activo(symbol)
        except Exception as exc:
            # Un error en un activo no detiene todo el cron job.
            print(f"❌ Error no controlado analizando {symbol}: {exc}")

    duracion = time.time() - inicio

    print("=" * 60)
    print(f"✅ Escaneo finalizado en {duracion:.1f} segundos.")
    print("=" * 60)


if __name__ == "__main__":
    main()
