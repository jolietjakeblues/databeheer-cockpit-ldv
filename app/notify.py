import os

import requests


def send_ntfy(title: str, message: str, priority: str = "default", tags: str = "") -> bool:
    """Stuurt een push-notificatie via ntfy.sh. Doet niets (en geeft False
    terug) als NTFY_TOPIC niet gezet is (bv. lokaal draaien zonder alerting)."""
    topic = os.getenv("NTFY_TOPIC")
    if not topic:
        return False
    try:
        requests.post(
            f"https://ntfy.sh/{topic}",
            data=message.encode("utf-8"),
            headers={"Title": title, "Priority": priority, "Tags": tags},
            timeout=10,
        )
        return True
    except Exception as exc:
        print(f"[notify] kon ntfy-melding niet versturen: {exc}")
        return False
