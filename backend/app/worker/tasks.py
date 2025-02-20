"""
This module is maintained for backward compatibility.
All tasks have been moved to the tasks/ directory for better organization.
Please import tasks directly from their respective modules:

- WhatsApp tasks: from app.worker.tasks.whatsapp import send_whatsapp_message, send_bulk_whatsapp_messages
- Business tasks: from app.worker.tasks.business import process_business_search, cleanup_old_searches
"""

from app.worker.tasks.whatsapp import send_whatsapp_message, send_bulk_whatsapp_messages
from app.worker.tasks.business import process_business_search, cleanup_old_searches

__all__ = [
    'send_whatsapp_message',
    'send_bulk_whatsapp_messages',
    'process_business_search',
    'cleanup_old_searches',
]