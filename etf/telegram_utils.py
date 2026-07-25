from io import BytesIO
import requests


def send_photo_bytes(token: str, chat_id: str, buf: BytesIO, caption: str | None = None) -> bool:
    """Sendet ein Bild (BytesIO) per Telegram sendPhoto API.

    Gibt True zurück bei Erfolg, False bei Fehler.
    """
    if buf is None:
        return False

    buf.seek(0)
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    data = {"chat_id": chat_id}
    if caption:
        data["caption"] = caption
        data["parse_mode"] = "Markdown"

    files = {"photo": ("chart.png", buf, "image/png")}
    try:
        resp = requests.post(url, data=data, files=files, timeout=20)
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        text = getattr(e.response, 'text', None)
        print(f"⚠️ Telegram-Fehler beim Senden des Bildes: {e}")
        if text:
            print(f"Telegram-Antwort: {text}")
        return False
