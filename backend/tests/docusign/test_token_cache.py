"""In-process token cache + safety-margin re-mint (Task 9.3a).

Tokens are 1-hour with no refresh token, so the client caches in-process and
re-mints on demand with a safety margin. No persistence.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.docusign_client import DocuSignClient, MintedToken


class SpyProvider:
    """Counts mint() calls; hands out a distinct token each time."""

    def __init__(self, expires_in: int = 3600) -> None:
        self.calls = 0
        self.expires_in = expires_in

    def mint(self) -> MintedToken:
        self.calls += 1
        return MintedToken(access_token=f"token-{self.calls}", expires_in=self.expires_in)


@pytest.mark.asyncio
async def test_first_call_mints():
    provider = SpyProvider()
    client = DocuSignClient(provider=provider)
    token = await client.get_access_token()
    assert token == "token-1"
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_second_call_within_window_reuses_cache():
    provider = SpyProvider()
    client = DocuSignClient(provider=provider)
    first = await client.get_access_token()
    second = await client.get_access_token()
    assert first == second == "token-1"
    assert provider.calls == 1  # not re-minted


@pytest.mark.asyncio
async def test_expired_token_is_re_minted():
    provider = SpyProvider()
    client = DocuSignClient(provider=provider)
    await client.get_access_token()
    # Force expiry into the past.
    client._expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    token = await client.get_access_token()
    assert token == "token-2"
    assert provider.calls == 2


@pytest.mark.asyncio
async def test_safety_margin_triggers_re_mint():
    provider = SpyProvider()
    client = DocuSignClient(provider=provider, safety_margin_seconds=60)
    await client.get_access_token()
    # Token still technically valid (30s left) but inside the 60s margin.
    client._expires_at = datetime.now(timezone.utc) + timedelta(seconds=30)
    token = await client.get_access_token()
    assert token == "token-2"
    assert provider.calls == 2


@pytest.mark.asyncio
async def test_force_re_mints_even_when_cached():
    provider = SpyProvider()
    client = DocuSignClient(provider=provider)
    await client.get_access_token()
    token = await client.get_access_token(force=True)
    assert token == "token-2"
    assert provider.calls == 2
