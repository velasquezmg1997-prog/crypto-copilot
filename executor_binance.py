import os
import time
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP

import requests
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException


# ============================================================
# CRYPTO COPILOT V1.3 - EJECUTOR BINANCE FUTURES DEMO
#
# Seguridad:
# - Solo funciona con BINANCE_TESTNET=true.
# - TRADING_ENABLED=false => DRY RUN: no crea/cancela/modifica órdenes.
# - No contiene claves dentro del código.
# ============================================================


BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "").strip()
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY", "").strip()

BINANCE_TESTNET = os.getenv("BINANCE_TESTNET", "true").strip().lower() in {
    "1", "true", "yes", "on"
}
TRADING_ENABLED = os.getenv("TRADING_ENABLED", "false").strip().lower() in {
    "1", "true", "yes", "on"
}

RISK_PCT = float(os.getenv("BINANCE_RISK_PCT", "0.01"))
LEVERAGE = int(os.getenv("BINANCE_LEVERAGE", "10"))
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "3"))
MAX_PRICE_DEVIATION_PCT = float(os.getenv("MAX_PRICE_DEVIATION_PCT", "0.50"))
MAX_MARGIN_PCT = float(os.getenv("MAX_MARGIN_PCT", "0.30"))
WORKING_TYPE = os.getenv("BINANCE_WORKING_TYPE", "MARK_PRICE").strip().upper()

WHITELIST = {
    x.strip().upper()
    for x in os.getenv(
        "BINANCE_SYMBOL_WHITELIST",
        "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT,ADAUSDT,"
        "AVAXUSDT,NEARUSDT,LINKUSDT,SUIUSDT",
    ).split(",")
    if x.strip()
}

TELEGRAM_NOTIFY_TOKEN = os.getenv(
    "TELEGRAM_NOTIFY_TOKEN",
    os.getenv("TELEGRAM_TOKEN", "")
).strip()

TELEGRAM_NOTIFY_CHAT_ID = os.getenv(
    "TELEGRAM_NOTIFY_CHAT_ID",
    os.getenv("TELEGRAM_CHAT_ID", "")
).strip()


_CLIENT = None
_EXCHANGE_INFO = None


def _bool_text(value):
    return "true" if value else "false"


def _crear_cliente():
    global _CLIENT

    if _CLIENT is not None:
        return _CLIENT

    if not BINANCE_TESTNET:
        raise RuntimeError(
            "Bloqueo de seguridad: BINANCE_TESTNET debe ser true. "
            "V1.3 no permite Binance producción."
        )

    if not BINANCE_API_KEY or not BINANCE_SECRET_KEY:
        raise RuntimeError(
            "Faltan BINANCE_API_KEY o BINANCE_SECRET_KEY en Render."
        )

    # python-binance >= 1.0.30 soporta Demo Trading con demo=True.
    _CLIENT = Client(
        BINANCE_API_KEY,
        BINANCE_SECRET_KEY,
        demo=True,
    )

    return _CLIENT


def _sincronizar_reloj(client):
    server_time = client.get_server_time()["serverTime"]
    local_time = int(time.time() * 1000)
    client.timestamp_offset = server_time - local_time


def _enviar_notificacion(mensaje):
    if not TELEGRAM_NOTIFY_TOKEN or not TELEGRAM_NOTIFY_CHAT_ID:
        print("ℹ️ Telegram notificador no configurado.")
        return False

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_NOTIFY_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_NOTIFY_CHAT_ID,
        "text": mensaje,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }

    try:
        response = requests.post(url, json=payload, timeout=15)

        if response.status_code != 200:
            print(
                "⚠ Telegram notificador respondió "
                f"{response.status_code}: {response.text[:250]}"
            )
            return False

        return bool(response.json().get("ok"))
    except Exception as exc:
        print(f"⚠ Error enviando notificación: {exc}")
        return False


def _exchange_info(client):
    global _EXCHANGE_INFO

    if _EXCHANGE_INFO is None:
        _EXCHANGE_INFO = client.futures_exchange_info()

    return _EXCHANGE_INFO


def _symbol_info(client, symbol):
    info = _exchange_info(client)

    for item in info.get("symbols", []):
        if item.get("symbol") == symbol:
            return item

    raise ValueError(f"{symbol} no existe en Binance Futures Demo.")


def _filtro(symbol_info, filter_type):
    for item in symbol_info.get("filters", []):
        if item.get("filterType") == filter_type:
            return item
    return {}


def _decimal(value):
    return Decimal(str(value))


def _floor_step(value, step):
    value_d = _decimal(value)
    step_d = _decimal(step)

    if step_d <= 0:
        return float(value_d)

    units = (value_d / step_d).to_integral_value(rounding=ROUND_DOWN)
    return float(units * step_d)


def _round_step(value, step):
    value_d = _decimal(value)
    step_d = _decimal(step)

    if step_d <= 0:
        return float(value_d)

    units = (value_d / step_d).to_integral_value(rounding=ROUND_HALF_UP)
    return float(units * step_d)


def _fmt(value):
    s = format(Decimal(str(value)), "f")
    s = s.rstrip("0").rstrip(".")
    return s or "0"


def _obtener_reglas_symbol(client, symbol):
    info = _symbol_info(client, symbol)

    lot = _filtro(info, "LOT_SIZE")
    market_lot = _filtro(info, "MARKET_LOT_SIZE")
    price_filter = _filtro(info, "PRICE_FILTER")
    min_notional_filter = _filtro(info, "MIN_NOTIONAL")

    step_size = float(
        market_lot.get("stepSize")
        or lot.get("stepSize")
        or "1"
    )

    min_qty = float(
        market_lot.get("minQty")
        or lot.get("minQty")
        or "0"
    )

    max_qty = float(
        market_lot.get("maxQty")
        or lot.get("maxQty")
        or "1e50"
    )

    tick_size = float(price_filter.get("tickSize") or "0.01")

    min_notional = float(
        min_notional_filter.get("notional")
        or min_notional_filter.get("minNotional")
        or "0"
    )

    return {
        "step_size": step_size,
        "min_qty": min_qty,
        "max_qty": max_qty,
        "tick_size": tick_size,
        "min_notional": min_notional,
    }


def _obtener_balance(client):
    account = client.futures_account()

    wallet = float(account.get("totalWalletBalance", 0.0))
    available = float(account.get("availableBalance", 0.0))

    return wallet, available


def _posiciones_abiertas(client):
    positions = client.futures_position_information()
    return [
        p for p in positions
        if abs(float(p.get("positionAmt", 0.0))) > 0
    ]


def _posicion_symbol(client, symbol):
    positions = client.futures_position_information(symbol=symbol)

    for p in positions:
        if (
            p.get("symbol") == symbol
            and abs(float(p.get("positionAmt", 0.0))) > 0
        ):
            return p

    return None


def _validar_modo_posicion(client):
    try:
        mode = client.futures_get_position_mode()
        if bool(mode.get("dualSidePosition")):
            raise RuntimeError(
                "La cuenta está en Hedge Mode. "
                "V1.3 requiere One-way Mode para esta primera prueba."
            )
    except BinanceAPIException:
        raise
    except Exception as exc:
        raise RuntimeError(
            f"No se pudo verificar One-way/Hedge Mode: {exc}"
        ) from exc


def _hay_ordenes_previas(client, symbol):
    normales = client.futures_get_open_orders(symbol=symbol)

    try:
        algo = client.futures_get_open_algo_orders(symbol=symbol)
    except Exception:
        algo = []

    return normales, algo


def verificar_conexion_binance():
    """
    Comprueba credenciales y cuenta Demo.
    No crea ni cancela órdenes.
    """
    estado = {
        "ok": False,
        "mode": "DRY_RUN" if not TRADING_ENABLED else "TRADING",
        "wallet": None,
        "available": None,
        "message": "",
    }

    try:
        client = _crear_cliente()
        _sincronizar_reloj(client)
        wallet, available = _obtener_balance(client)
        _validar_modo_posicion(client)

        estado.update({
            "ok": True,
            "wallet": wallet,
            "available": available,
            "message": (
                "Conexión Binance Futures Demo correcta. "
                f"Wallet={wallet:.2f} USDT | "
                f"Disponible={available:.2f} USDT"
            ),
        })

        print("✅ " + estado["message"])
        print(
            "🛡️ Modo ejecución: "
            + ("ACTIVO (DEMO)" if TRADING_ENABLED else "DRY RUN")
        )

    except Exception as exc:
        estado["message"] = str(exc)
        print(f"❌ Binance Demo: {exc}")

    return estado


def _validar_senal(
    client,
    symbol,
    side_signal,
    entry_signal,
    stop_loss,
    tp1,
    tp2,
):
    symbol = symbol.upper().replace("/", "")
    side_signal = side_signal.upper()

    if symbol not in WHITELIST:
        raise ValueError(f"{symbol} no está en BINANCE_SYMBOL_WHITELIST.")

    if side_signal not in {"LONG", "SHORT"}:
        raise ValueError("TYPE debe ser LONG o SHORT.")

    entry_signal = float(entry_signal)
    stop_loss = float(stop_loss)
    tp1 = float(tp1) if tp1 is not None else None
    tp2 = float(tp2) if tp2 is not None else None

    if min(entry_signal, stop_loss) <= 0:
        raise ValueError("ENTRY y SL deben ser mayores que cero.")

    ticker = client.futures_symbol_ticker(symbol=symbol)
    current_price = float(ticker["price"])

    deviation_pct = (
        abs(current_price - entry_signal) / entry_signal
    ) * 100

    if deviation_pct > MAX_PRICE_DEVIATION_PCT:
        raise ValueError(
            f"Precio Binance se alejó {deviation_pct:.3f}% de la señal; "
            f"máximo permitido {MAX_PRICE_DEVIATION_PCT:.3f}%."
        )

    if side_signal == "LONG":
        if not stop_loss < current_price:
            raise ValueError("LONG inválido: SL debe estar debajo del precio.")
        if tp1 is not None and not tp1 > current_price:
            raise ValueError("LONG inválido: TP1 debe estar arriba del precio.")
        if tp2 is not None and not tp2 > current_price:
            raise ValueError("LONG inválido: TP2 debe estar arriba del precio.")
        if tp1 is not None and tp2 is not None and not tp2 > tp1:
            raise ValueError("LONG inválido: TP2 debe ser mayor que TP1.")
    else:
        if not stop_loss > current_price:
            raise ValueError("SHORT inválido: SL debe estar arriba del precio.")
        if tp1 is not None and not tp1 < current_price:
            raise ValueError("SHORT inválido: TP1 debe estar debajo del precio.")
        if tp2 is not None and not tp2 < current_price:
            raise ValueError("SHORT inválido: TP2 debe estar debajo del precio.")
        if tp1 is not None and tp2 is not None and not tp2 < tp1:
            raise ValueError("SHORT inválido: TP2 debe ser menor que TP1.")

    _validar_modo_posicion(client)

    existing_position = _posicion_symbol(client, symbol)
    if existing_position:
        raise ValueError(
            f"Ya existe una posición abierta en {symbol}; no se duplica."
        )

    open_positions = _posiciones_abiertas(client)
    if len(open_positions) >= MAX_OPEN_POSITIONS:
        raise ValueError(
            f"Hay {len(open_positions)} posiciones abiertas; "
            f"máximo configurado {MAX_OPEN_POSITIONS}."
        )

    normal_orders, algo_orders = _hay_ordenes_previas(client, symbol)
    if normal_orders or algo_orders:
        raise ValueError(
            f"Hay órdenes abiertas previas en {symbol}; "
            "V1.3 no las cancela automáticamente."
        )

    wallet, available = _obtener_balance(client)
    if wallet <= 0 or available <= 0:
        raise ValueError("Balance Demo disponible insuficiente.")

    rules = _obtener_reglas_symbol(client, symbol)

    risk_target = wallet * RISK_PCT
    risk_distance = abs(current_price - stop_loss)

    if risk_distance <= 0:
        raise ValueError("Distancia al Stop Loss inválida.")

    qty_by_risk = risk_target / risk_distance

    # Límite adicional de margen: por defecto máximo 30% del disponible.
    max_margin = available * MAX_MARGIN_PCT
    max_notional = max_margin * LEVERAGE
    qty_by_margin = max_notional / current_price

    qty_raw = min(qty_by_risk, qty_by_margin, rules["max_qty"])
    qty = _floor_step(qty_raw, rules["step_size"])

    if qty < rules["min_qty"] or qty <= 0:
        raise ValueError(
            f"Cantidad calculada {qty} menor que minQty "
            f"{rules['min_qty']}."
        )

    notional = qty * current_price

    if rules["min_notional"] and notional < rules["min_notional"]:
        raise ValueError(
            f"Notional {notional:.2f} menor que mínimo "
            f"{rules['min_notional']:.2f}."
        )

    qty_tp1 = 0.0
    if tp1 is not None and tp2 is not None:
        qty_tp1 = _floor_step(qty / 2.0, rules["step_size"])

        if qty_tp1 < rules["min_qty"]:
            raise ValueError(
                "La posición es demasiado pequeña para dividir TP1/TP2."
            )

        qty_remaining = _floor_step(
            qty - qty_tp1,
            rules["step_size"]
        )

        if qty_remaining < rules["min_qty"]:
            raise ValueError(
                "La cantidad restante después de TP1 sería menor a minQty."
            )

    sl_rounded = _round_step(stop_loss, rules["tick_size"])
    tp1_rounded = (
        _round_step(tp1, rules["tick_size"])
        if tp1 is not None else None
    )
    tp2_rounded = (
        _round_step(tp2, rules["tick_size"])
        if tp2 is not None else None
    )

    actual_risk = qty * risk_distance
    margin_estimated = notional / LEVERAGE

    return {
        "symbol": symbol,
        "direction": side_signal,
        "current_price": current_price,
        "signal_entry": entry_signal,
        "deviation_pct": deviation_pct,
        "stop_loss": sl_rounded,
        "tp1": tp1_rounded,
        "tp2": tp2_rounded,
        "qty": qty,
        "qty_tp1": qty_tp1,
        "wallet": wallet,
        "available": available,
        "risk_target": risk_target,
        "actual_risk": actual_risk,
        "notional": notional,
        "margin_estimated": margin_estimated,
        "rules": rules,
    }


def _emergency_close(client, symbol):
    """
    Si la entrada fue creada pero falla la protección, intenta cerrar
    inmediatamente la posición completa a MARKET.
    """
    print(f"🚨 CIERRE DE EMERGENCIA solicitado para {symbol}.")

    try:
        try:
            client.futures_cancel_all_algo_open_orders(symbol=symbol)
        except Exception as exc:
            print(f"⚠ No se pudieron cancelar algo orders: {exc}")

        position = _posicion_symbol(client, symbol)

        if not position:
            print("ℹ️ No hay posición abierta que cerrar.")
            return True

        amount = float(position["positionAmt"])
        qty = abs(amount)

        if qty <= 0:
            return True

        side = "SELL" if amount > 0 else "BUY"

        client.futures_create_order(
            symbol=symbol,
            side=side,
            type="MARKET",
            quantity=_fmt(qty),
            reduceOnly="true",
            newOrderRespType="RESULT",
        )

        print("✅ Posición cerrada por emergencia.")
        return True

    except Exception as exc:
        print(f"❌ FALLÓ EL CIERRE DE EMERGENCIA: {exc}")
        _enviar_notificacion(
            f"🚨 *ALERTA CRÍTICA {symbol}*\n\n"
            f"Falló el cierre de emergencia.\n"
            f"Revisar Binance Demo manualmente.\n"
            f"`{str(exc)[:300]}`"
        )
        return False


def _ejecutar_real_demo(client, plan):
    symbol = plan["symbol"]
    direction = plan["direction"]

    side = "BUY" if direction == "LONG" else "SELL"
    exit_side = "SELL" if side == "BUY" else "BUY"

    # No mutamos apalancamiento hasta el momento exacto de ejecutar.
    client.futures_change_leverage(
        symbol=symbol,
        leverage=LEVERAGE,
    )

    print(
        f"🚀 Enviando MARKET {side} {symbol} "
        f"qty={_fmt(plan['qty'])}"
    )

    entry_order = client.futures_create_order(
        symbol=symbol,
        side=side,
        type="MARKET",
        quantity=_fmt(plan["qty"]),
        newOrderRespType="RESULT",
    )

    # Leemos la posición real después del fill.
    position = _posicion_symbol(client, symbol)

    if not position:
        raise RuntimeError(
            "Binance respondió a la entrada pero no aparece posición abierta."
        )

    real_qty = abs(float(position["positionAmt"]))
    real_entry = float(position["entryPrice"])

    # Validación post-fill.
    if direction == "LONG":
        valid_post_fill = (
            plan["stop_loss"] < real_entry
            and (plan["tp1"] is None or plan["tp1"] > real_entry)
            and (plan["tp2"] is None or plan["tp2"] > real_entry)
        )
    else:
        valid_post_fill = (
            plan["stop_loss"] > real_entry
            and (plan["tp1"] is None or plan["tp1"] < real_entry)
            and (plan["tp2"] is None or plan["tp2"] < real_entry)
        )

    if not valid_post_fill:
        _emergency_close(client, symbol)
        raise RuntimeError(
            "El fill real dejó SL/TP del lado incorrecto; "
            "posición cerrada por seguridad."
        )

    try:
        # SL siempre cierra todo lo que quede de la posición.
        sl_order = client.futures_create_algo_order(
            symbol=symbol,
            side=exit_side,
            type="STOP_MARKET",
            triggerPrice=_fmt(plan["stop_loss"]),
            closePosition="true",
            workingType=WORKING_TYPE,
        )

        tp1_order = None
        if plan["tp1"] is not None and plan["tp2"] is not None:
            # Recalculamos la mitad con la cantidad real.
            rules = plan["rules"]
            real_tp1_qty = _floor_step(
                real_qty / 2.0,
                rules["step_size"],
            )

            if real_tp1_qty < rules["min_qty"]:
                raise RuntimeError(
                    "Fill real demasiado pequeño para TP1 parcial."
                )

            tp1_order = client.futures_create_algo_order(
                symbol=symbol,
                side=exit_side,
                type="TAKE_PROFIT_MARKET",
                triggerPrice=_fmt(plan["tp1"]),
                quantity=_fmt(real_tp1_qty),
                reduceOnly="true",
                workingType=WORKING_TYPE,
            )

        tp2_order = None
        final_tp = plan["tp2"] if plan["tp2"] is not None else plan["tp1"]

        if final_tp is not None:
            # TP final cierra todo lo que quede después de TP1.
            tp2_order = client.futures_create_algo_order(
                symbol=symbol,
                side=exit_side,
                type="TAKE_PROFIT_MARKET",
                triggerPrice=_fmt(final_tp),
                closePosition="true",
                workingType=WORKING_TYPE,
            )

        return {
            "entry_order": entry_order,
            "sl_order": sl_order,
            "tp1_order": tp1_order,
            "tp2_order": tp2_order,
            "real_entry": real_entry,
            "real_qty": real_qty,
        }

    except Exception:
        _emergency_close(client, symbol)
        raise


def procesar_senal(
    simbolo,
    tipo_orden,
    precio_entrada,
    stop_loss,
    tp1=None,
    tp2=None,
):
    """
    Valida una señal y:
    - con TRADING_ENABLED=false: solo DRY RUN.
    - con TRADING_ENABLED=true: ejecuta únicamente en Binance Demo.
    """
    result = {
        "ok": False,
        "mode": "DRY_RUN" if not TRADING_ENABLED else "TRADING",
        "message": "",
        "plan": None,
    }

    try:
        client = _crear_cliente()
        _sincronizar_reloj(client)

        plan = _validar_senal(
            client=client,
            symbol=simbolo,
            side_signal=tipo_orden,
            entry_signal=precio_entrada,
            stop_loss=stop_loss,
            tp1=tp1,
            tp2=tp2,
        )

        result["plan"] = plan

        resumen = (
            f"{plan['symbol']} {plan['direction']} | "
            f"Binance={plan['current_price']:.8f} | "
            f"qty={_fmt(plan['qty'])} | "
            f"riesgo≈{plan['actual_risk']:.2f} USDT | "
            f"margen≈{plan['margin_estimated']:.2f} USDT"
        )

        if not TRADING_ENABLED:
            result.update({
                "ok": True,
                "message": "DRY RUN validado: " + resumen,
            })

            print("🧪 " + result["message"])

            _enviar_notificacion(
                "🧪 *CRYPTO COPILOT V1.3 — DRY RUN*\n\n"
                f"✅ Señal validada en Binance Futures Demo\n"
                f"📌 `{plan['symbol']} {plan['direction']}`\n"
                f"💵 Precio Binance: `{plan['current_price']:.8f}`\n"
                f"📏 Desvío vs señal: `{plan['deviation_pct']:.3f}%`\n"
                f"📦 Cantidad prevista: `{_fmt(plan['qty'])}`\n"
                f"🛡 Riesgo estimado: `{plan['actual_risk']:.2f} USDT`\n"
                f"💰 Wallet Demo: `{plan['wallet']:.2f} USDT`\n\n"
                "🚫 *No se envió ninguna orden* porque "
                "`TRADING_ENABLED=false`."
            )

            return result

        execution = _ejecutar_real_demo(client, plan)

        result.update({
            "ok": True,
            "message": (
                "Orden Demo ejecutada: "
                f"{plan['symbol']} {plan['direction']} | "
                f"entry={execution['real_entry']:.8f} | "
                f"qty={_fmt(execution['real_qty'])}"
            ),
            "execution": execution,
        })

        print("✅ " + result["message"])

        _enviar_notificacion(
            "✅ *CRYPTO COPILOT V1.3 — ORDEN DEMO*\n\n"
            f"📌 `{plan['symbol']} {plan['direction']}`\n"
            f"💵 Entry real: `{execution['real_entry']:.8f}`\n"
            f"📦 Cantidad: `{_fmt(execution['real_qty'])}`\n"
            f"🛑 SL: `{plan['stop_loss']:.8f}`\n"
            f"🎯 TP1: `{plan['tp1'] if plan['tp1'] is not None else '-'} `\n"
            f"🎯 TP2: `{plan['tp2'] if plan['tp2'] is not None else '-'} `\n"
            f"🛡 Riesgo estimado: `{plan['actual_risk']:.2f} USDT`\n\n"
            "Entorno: *Binance Futures Demo*."
        )

        return result

    except (BinanceAPIException, BinanceRequestException) as exc:
        message = f"Binance API: {exc}"
        result["message"] = message
        print(f"❌ {message}")

        _enviar_notificacion(
            "❌ *CRYPTO COPILOT V1.3 — BINANCE*\n\n"
            f"`{str(exc)[:700]}`"
        )

        return result

    except Exception as exc:
        result["message"] = str(exc)
        print(f"❌ Ejecutor: {exc}")

        _enviar_notificacion(
            "⚠️ *CRYPTO COPILOT V1.3 — SEÑAL RECHAZADA*\n\n"
            f"`{str(exc)[:700]}`"
        )

        return result
