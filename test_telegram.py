import os
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

ZONA_HORARIA = ZoneInfo("Europe/Madrid")


def main():
    print("=" * 60)
    print("🧪 TEST TELEGRAM - CRYPTO COPILOT")
    print("=" * 60)

    if not TELEGRAM_TOKEN:
        print("❌ Falta la variable de entorno TELEGRAM_TOKEN.")
        raise SystemExit(1)

    if not TELEGRAM_CHAT_ID:
        print("❌ Falta la variable de entorno TELEGRAM_CHAT_ID.")
        raise SystemExit(1)

    ahora = datetime.now(ZONA_HORARIA).strftime("%d/%m/%Y %H:%M:%S")

    mensaje = (
        "✅ *TEST CRYPTO COPILOT*\n\n"
        "Telegram está conectado correctamente con Render.\n\n"
        f"🕒 Hora España: `{ahora}`\n"
        "🤖 Bot: `Crypto Copilot V1.2`\n\n"
        "Si recibiste este mensaje, la conexión Telegram → Render funciona."
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensaje,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }

    print("📡 Enviando mensaje de prueba a Telegram...")

    try:
        response = requests.post(
            url,
            json=payload,
            timeout=15,
        )

        print(f"HTTP status: {response.status_code}")

        try:
            data = response.json()
        except Exception:
            data = None

        if response.status_code == 200 and data and data.get("ok"):
            print("✅ Telegram respondió correctamente.")
            print("📲 Mensaje enviado con éxito.")
            print("=" * 60)
            return

        print("❌ Telegram rechazó el mensaje.")

        if data:
            print("Respuesta de Telegram:")
            print(data)
        else:
            print(response.text[:1000])

        raise SystemExit(1)

    except requests.RequestException as exc:
        print(f"❌ Error de conexión con Telegram: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
