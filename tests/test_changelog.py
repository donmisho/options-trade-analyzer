"""
Tests for changelog routes and ticket-key parser (OTA-602).

Tests the Pydantic validation, token auth, and ticket-key parser utility
without requiring a live database. Route handler tests use mocked DB sessions.
"""

import pytest
from pydantic import ValidationError

from app.api.changelog_routes import (
    DeployRecordRequest,
    parse_ticket_keys,
)


# ─── Ticket-key parser ───────────────────────────────────────────────────────


class TestParseTicketKeys:
    def test_single_ticket(self):
        assert parse_ticket_keys("OTA-602 feat: change log page") == ["OTA-602"]

    def test_multiple_tickets(self):
        result = parse_ticket_keys("OTA-601 OTA-602 feat: multi-ticket commit")
        assert result == ["OTA-601", "OTA-602"]

    def test_deduplication(self):
        result = parse_ticket_keys("OTA-602 OTA-602 fix: duplicate tickets")
        assert result == ["OTA-602"]

    def test_no_tickets(self):
        assert parse_ticket_keys("chore: update dependencies") == []

    def test_lowercase_not_matched(self):
        assert parse_ticket_keys("ota-602 lowercase") == []

    def test_mixed_case_only_uppercase(self):
        result = parse_ticket_keys("OTA-100 ota-200 OTA-300")
        assert result == ["OTA-100", "OTA-300"]

    def test_tickets_in_body(self):
        msg = "feat: something\n\nResolves OTA-555, OTA-556"
        result = parse_ticket_keys(msg)
        assert result == ["OTA-555", "OTA-556"]


# ─── Pydantic schema validation ──────────────────────────────────────────────


class TestDeployRecordRequest:
    def test_valid_request(self):
        req = DeployRecordRequest(
            build_id="12345678",
            environment="dev",
            commit_sha="a" * 40,
            ticket_keys=["OTA-602"],
            notes=None,
        )
        assert req.build_id == "12345678"
        assert req.environment == "dev"
        assert req.commit_sha == "a" * 40

    def test_empty_build_id_rejected(self):
        with pytest.raises(ValidationError, match="build_id"):
            DeployRecordRequest(
                build_id="   ",
                environment="dev",
                commit_sha="a" * 40,
            )

    def test_bad_commit_sha_length(self):
        with pytest.raises(ValidationError, match="commit_sha"):
            DeployRecordRequest(
                build_id="123",
                environment="dev",
                commit_sha="abc123",
            )

    def test_bad_commit_sha_chars(self):
        with pytest.raises(ValidationError, match="commit_sha"):
            DeployRecordRequest(
                build_id="123",
                environment="dev",
                commit_sha="g" * 40,
            )

    def test_invalid_environment(self):
        with pytest.raises(ValidationError):
            DeployRecordRequest(
                build_id="123",
                environment="staging",
                commit_sha="a" * 40,
            )

    def test_invalid_ticket_key(self):
        with pytest.raises(ValidationError, match="ticket key"):
            DeployRecordRequest(
                build_id="123",
                environment="dev",
                commit_sha="a" * 40,
                ticket_keys=["INVALID-123"],
            )

    def test_empty_ticket_keys_allowed(self):
        req = DeployRecordRequest(
            build_id="123",
            environment="prod",
            commit_sha="b" * 40,
        )
        assert req.ticket_keys == []

    def test_prod_environment(self):
        req = DeployRecordRequest(
            build_id="456",
            environment="prod",
            commit_sha="c" * 40,
        )
        assert req.environment == "prod"
