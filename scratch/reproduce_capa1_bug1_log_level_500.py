import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import logging
from unittest.mock import MagicMock
from src.web.api_router import WebAPIRouter
from src.diagnostics import DiagnosticManager

async def test_invalid_log_level_reproduction():
    print("=== REPRODUCING BUG 1: POST /api/system/logs/level returns HTTP 500 on invalid client input ===")
    
    # Setup mock bridge with real DiagnosticManager
    mock_bridge = MagicMock()
    mock_bridge.node_registry = MagicMock()
    mock_bridge.node_registry.list_client_contacts.return_value = []
    mock_bridge.start_time = 1234567.0
    mock_bridge.packet_buffer = None
    mock_bridge.diagnostics = DiagnosticManager(bridge=mock_bridge, log_handler=None)
    
    router = WebAPIRouter(bridge=mock_bridge)
    
    # Send request with invalid log level
    invalid_level = "SUPER_CRITICAL_CUSTOM_LEVEL"
    status_code, response_body = await router.handle_request(
        method="POST",
        path="/api/system/logs/level",
        body={"level": invalid_level},
    )
    
    print(f"HTTP Status Code returned: {status_code}")
    print(f"Response Body: {response_body}")
    
    # Assert contract violation: Expected 400 (Bad Request), but received 500 (Internal Server Error)
    if status_code == 500:
        print("\n[REPRODUCTION CONFIRMED] BUG IDENTIFIED: The API returned HTTP 500 (Internal Server Error) instead of HTTP 400 Bad Request.")
        print(f"Detail: {response_body.get('detail')}")
        print(f"Title: {response_body.get('title')}")
        print("Violation: RFC 7807 and REST standards state invalid user input must return 400 or 422, never 500.")
    else:
        print(f"[UNEXPECTED] Returned status code: {status_code}")

if __name__ == "__main__":
    asyncio.run(test_invalid_log_level_reproduction())
