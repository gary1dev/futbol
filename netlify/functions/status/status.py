import json
from datetime import datetime, timezone


def handler(event, context):
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({
            "scraper": "ok",
            "datos_disponibles": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }),
    }
