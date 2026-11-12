from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

import finn_api.api.auth as auth


def test_access_token_validation_requires_issuer_audience_and_signature(monkeypatch):
    subject = uuid4()
    observed = {}

    class FakeJwkClient:
        def get_signing_key_from_jwt(self, token):
            assert token == "signed-token"
            return SimpleNamespace(key="verified-public-key")

    def decode(token, key, **kwargs):
        observed.update(kwargs)
        assert token == "signed-token"
        assert key == "verified-public-key"
        return {"sub": str(subject)}

    monkeypatch.setattr(
        auth,
        "get_settings",
        lambda: SimpleNamespace(
            auth_jwks_url="https://auth.example.test/jwks",
            auth_issuer="https://auth.example.test",
            auth_audience="authenticated",
        ),
    )
    monkeypatch.setattr(auth, "_jwk_client", lambda url: FakeJwkClient())
    monkeypatch.setattr(auth.jwt, "decode", decode)

    assert auth._decode_subject("signed-token") == subject
    assert observed["issuer"] == "https://auth.example.test"
    assert observed["audience"] == "authenticated"
    assert observed["algorithms"] == ["ES256", "RS256", "EdDSA"]
    assert observed["options"]["require"] == ["exp", "sub"]


def test_access_token_fails_closed_when_authentication_is_not_configured(monkeypatch):
    monkeypatch.setattr(
        auth,
        "get_settings",
        lambda: SimpleNamespace(auth_jwks_url=None, auth_issuer=None),
    )
    with pytest.raises(HTTPException) as error:
        auth._decode_subject("any-token")
    assert error.value.status_code == 503
    assert error.value.detail["code"] == "authentication_not_configured"


def test_access_token_rejects_bad_signature_or_claims(monkeypatch):
    class FakeJwkClient:
        def get_signing_key_from_jwt(self, token):
            return SimpleNamespace(key="verification-key")

    monkeypatch.setattr(
        auth,
        "get_settings",
        lambda: SimpleNamespace(
            auth_jwks_url="https://auth.example.test/jwks",
            auth_issuer="https://auth.example.test",
            auth_audience="authenticated",
        ),
    )
    monkeypatch.setattr(auth, "_jwk_client", lambda url: FakeJwkClient())
    monkeypatch.setattr(
        auth.jwt,
        "decode",
        lambda *args, **kwargs: (_ for _ in ()).throw(auth.jwt.InvalidTokenError("bad signature")),
    )

    with pytest.raises(HTTPException) as error:
        auth._decode_subject("tampered-token")
    assert error.value.status_code == 401
    assert error.value.detail["code"] == "invalid_access_token"
