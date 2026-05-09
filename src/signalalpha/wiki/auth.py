"""Invite-code authentication for the SignalAlpha dashboard.

Env vars:
  SESSION_SECRET  — secret used to sign session cookies (required in prod)
  INVITE_CODES    — comma-separated list of valid invite codes
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time

COOKIE_NAME    = "sa_session"
MAX_AGE_DAYS   = 30
_PUBLIC_PATHS  = {"/login", "/logout"}


def _secret() -> str:
    s = os.getenv("SESSION_SECRET", "")
    if not s:
        # Insecure fallback for local dev only — Railway must set SESSION_SECRET
        return "local-dev-secret-change-me"
    return s


def _invite_codes() -> set[str]:
    raw = os.getenv("INVITE_CODES", "")
    return {c.strip() for c in raw.split(",") if c.strip()}


def make_token() -> str:
    payload = str(int(time.time()))
    sig = hmac.new(_secret().encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{sig}.{payload}"


def verify_token(token: str) -> bool:
    try:
        sig, payload = token.split(".", 1)
        expected = hmac.new(_secret().encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return False
        return (time.time() - int(payload)) < MAX_AGE_DAYS * 86400
    except Exception:
        return False


def check_invite_code(code: str) -> bool:
    codes = _invite_codes()
    if not codes:
        return False
    return code.strip() in codes


def is_public(path: str) -> bool:
    return path in _PUBLIC_PATHS


LOGIN_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SignalAlpha — Access</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Segoe UI', system-ui, sans-serif;
    background: #1e1e1e; color: #f0f0f0;
    min-height: 100vh; display: flex; align-items: center; justify-content: center;
  }
  .box {
    background: #2a2a2a; border: 1px solid #3d3d3d; border-radius: 12px;
    padding: 2.5rem 2rem; width: 100%; max-width: 380px; text-align: center;
  }
  h1 { font-size: 1.4rem; font-weight: 700; letter-spacing: -.02em; margin-bottom: .35rem; }
  .sub { font-size: .82rem; color: #9e9e9e; margin-bottom: 2rem; }
  label { display: block; text-align: left; font-size: .78rem; color: #9e9e9e;
          margin-bottom: .4rem; }
  input {
    width: 100%; padding: .65rem .85rem; border-radius: 7px;
    background: #1e1e1e; border: 1px solid #3d3d3d; color: #f0f0f0;
    font-size: .95rem; outline: none; margin-bottom: 1.1rem;
    transition: border-color .15s;
  }
  input:focus { border-color: #6366f1; }
  button {
    width: 100%; padding: .7rem; border-radius: 7px; border: none;
    background: #6366f1; color: #fff; font-size: .95rem; font-weight: 600;
    cursor: pointer; transition: background .15s;
  }
  button:hover { background: #4f46e5; }
  .err {
    background: #2d0f0f; border: 1px solid #8b2020; color: #f85149;
    border-radius: 7px; padding: .55rem .85rem; font-size: .82rem;
    margin-bottom: 1rem; text-align: left;
  }
  .footer { margin-top: 1.5rem; font-size: .72rem; color: #555; }
</style>
</head>
<body>
<div class="box">
  <h1>SignalAlpha</h1>
  <p class="sub">Signal research &amp; ranking — invite only</p>
  {error}
  <form method="post" action="/login">
    <label for="code">Invite code</label>
    <input id="code" name="code" type="password" placeholder="Enter your invite code"
           autocomplete="current-password" autofocus required>
    <button type="submit">Enter</button>
  </form>
  <p class="footer">Don't have a code? Contact the admin.</p>
</div>
</body>
</html>"""
