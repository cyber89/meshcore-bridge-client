"""Offline browser QA accepts only cancellations observed on application signals."""

from __future__ import annotations

from frontend_browser_resources import unexpected_request_failures


def test_observed_signal_abort_matches_one_request_only() -> None:
    url = "http://127.0.0.1:1234/api/analytics?range=24h"
    failures = [("net::ERR_ABORTED", url, "GET"), ("net::ERR_ABORTED", url, "GET")]
    assert unexpected_request_failures(failures, [{"url": url, "method": "GET"}]) == [
        f"net::ERR_ABORTED {url}",
    ]


def test_unobserved_cancellation_and_different_method_remain_failures() -> None:
    url = "http://127.0.0.1:1234/api/analytics?range=24h"
    other = "http://127.0.0.1:1234/api/airtime/stats"
    failures = [("net::ERR_ABORTED", url, "POST"), ("net::ERR_ABORTED", other, "GET")]
    assert unexpected_request_failures(failures, [{"url": url, "method": "GET"}]) == [
        f"net::ERR_ABORTED {url}", f"net::ERR_ABORTED {other}",
    ]


def test_network_failures_are_never_excused_by_signal_abort() -> None:
    url = "http://127.0.0.1:1234/api/analytics?range=24h"
    failures = [("net::ERR_FAILED", url, "GET"), ("net::ERR_CONNECTION_RESET", url, "GET")]
    assert unexpected_request_failures(failures, [{"url": url, "method": "GET"}]) == [
        f"net::ERR_FAILED {url}", f"net::ERR_CONNECTION_RESET {url}",
    ]


def test_observed_signal_abort_accepts_matching_cancelled_request() -> None:
    url = "http://127.0.0.1:1234/api/analytics?range=24h"
    assert unexpected_request_failures(
        [("net::ERR_ABORTED", url, "GET")], [{"url": url, "method": "GET"}],
    ) == []
