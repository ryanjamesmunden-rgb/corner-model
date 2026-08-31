"""Google sign-in and session tokens.

WHAT THIS IS NOT: a gate on the site. The app stays public — every screen that works
today keeps working signed out. Signing in adds two things and only two: games you have
starred, and prices you have entered yourself. So `optional_user` is the default
dependency and returns the shared guest when nobody is signed in; `require_user` is used
only on the handful of routes that genuinely need to know who you are.

FLOW. The browser gets an ID token from Google (Google Identity Services renders the
button and does the popup), and POSTs it here. We verify that token against Google's
public keys and then issue OUR OWN short session token. We never see a password, and
there is no client secret anywhere — the ID-token flow does not use one, which is one
fewer secret to leak.

WHY VERIFY RATHER THAN DECODE. A Google ID token is just a JWT, and anyone can mint one
that *looks* right. Only the signature check against Google's published keys makes it
proof of anything, so `verify=False` decoding is never acceptable here — it would let
anyone sign in as anyone by editing a payload.
"""
import os
import time
import threading
from typing import Optional

import jwt
import requests
from jwt import PyJWKClient

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"
# Google mints tokens with either of these two issuer spellings; both are legitimate.
GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")

# Signs OUR session tokens. Falls back to a random value per process, which is safe but
# means every restart logs everyone out — so it must be set in the environment for real.
SESSION_SECRET = os.environ.get("SESSION_SECRET") or os.urandom(32).hex()
SESSION_DAYS = 30

_jwk_client: Optional[PyJWKClient] = None
_jwk_lock = threading.Lock()


def _jwks() -> PyJWKClient:
    """Google's signing keys, fetched once and cached by PyJWKClient.

    It rotates keys, and the client refetches when it meets a key id it has not seen —
    so a rotation costs one extra request, not a wave of failed sign-ins."""
    global _jwk_client
    with _jwk_lock:
        if _jwk_client is None:
            _jwk_client = PyJWKClient(GOOGLE_CERTS_URL, cache_keys=True, lifespan=3600)
        return _jwk_client


class AuthError(Exception):
    """Sign-in failed. The message is safe to show a user."""


def verify_google_token(id_token: str, client_id: str = None) -> dict:
    """Google ID token -> {sub, email, name, picture}, or raise AuthError.

    Every check here matters:
      signature  proves Google issued it, not the caller
      audience   proves it was issued for THIS app — a token minted for some other site
                 is perfectly valid and must still be rejected, or anyone could sign in
                 with a token harvested elsewhere
      issuer     rejects a well-formed token from somewhere that is not Google
      expiry     enforced by pyjwt
    """
    aud = client_id or GOOGLE_CLIENT_ID
    if not aud:
        raise AuthError("Sign-in is not configured on the server (GOOGLE_CLIENT_ID unset)")
    try:
        key = _jwks().get_signing_key_from_jwt(id_token).key
        claims = jwt.decode(id_token, key, algorithms=["RS256"], audience=aud,
                            issuer=GOOGLE_ISSUERS, options={"require": ["exp", "sub"]})
    except jwt.ExpiredSignatureError:
        raise AuthError("That sign-in expired — please try again")
    except jwt.InvalidAudienceError:
        raise AuthError("That sign-in was issued for a different app")
    except Exception as e:                                        # noqa: BLE001
        raise AuthError(f"Could not verify that sign-in ({type(e).__name__})")
    if not claims.get("sub"):
        raise AuthError("Sign-in carried no account id")
    # email_verified can be absent on some account types; only treat an explicit false
    # as a rejection, since an unverified address must not become an identity.
    if claims.get("email") and claims.get("email_verified") is False:
        raise AuthError("That Google account's email is not verified")
    return {"sub": claims["sub"], "email": claims.get("email", ""),
            "name": claims.get("name") or (claims.get("email") or "").split("@")[0] or "Member",
            "picture": claims.get("picture", "")}


def issue_session(user_id: str) -> str:
    """Our own token. Short and boring on purpose: an id and an expiry, nothing else.

    Nothing here is trusted from the client — the row is always re-read from the database,
    so a stale token cannot carry stale name, email or permissions."""
    now = int(time.time())
    return jwt.encode({"sub": user_id, "iat": now, "exp": now + SESSION_DAYS * 86400},
                      SESSION_SECRET, algorithm="HS256")


def read_session(token: Optional[str]) -> Optional[str]:
    """Session token -> user_id, or None for anything that does not verify.

    Returns None rather than raising: a bad or expired token means "not signed in", which
    on a public site is an ordinary state and not an error."""
    if not token:
        return None
    try:
        return jwt.decode(token, SESSION_SECRET, algorithms=["HS256"]).get("sub")
    except Exception:                                             # noqa: BLE001
        return None


def bearer(header: Optional[str]) -> Optional[str]:
    """Pull the token out of an `Authorization: Bearer <token>` header."""
    if not header:
        return None
    parts = header.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip() or None
    return None
