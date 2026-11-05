import logging

from procrastinate.contrib.django import app

from apps.ledger.services import generate_due

logger = logging.getLogger(__name__)


@app.periodic(cron="7 * * * *")  # hourly; pages also catch up on load
@app.task(lock="ledger_generate_recurring", name="ledger_generate_recurring")
def generate_recurring(timestamp=None):
    try:
        return f"Created {generate_due()} recurring entries"
    except Exception:
        logger.exception("Error in ledger_generate_recurring")
        raise
