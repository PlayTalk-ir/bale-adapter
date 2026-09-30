"""HTML login for Swagger docs (panel password only)."""

from __future__ import annotations

DOCS_LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Bale API docs — sign in</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 22rem; margin: 4rem auto; padding: 0 1rem; }
    label { display: block; margin: 1rem 0 0.25rem; font-weight: 600; }
    input[type=password] { width: 100%; padding: 0.5rem; box-sizing: border-box; }
    button { margin-top: 1rem; padding: 0.5rem 1rem; cursor: pointer; }
    .err { color: #b00020; margin-top: 1rem; }
    .hint { color: #555; font-size: 0.9rem; margin-top: 1.5rem; }
  </style>
</head>
<body>
  <h1>API documentation</h1>
  <p>Enter the same operator password as the Bale admin panel.</p>
  <form method="post" action="/v1/docs/login">
    <label for="password">Password</label>
    <input id="password" name="password" type="password" autocomplete="current-password" required autofocus/>
    <button type="submit">Continue to Swagger</button>
  </form>
  {error}
  <p class="hint">Already signed in at <a href="/login">/login</a>? Open this page again after panel login.</p>
</body>
</html>
"""


def login_page(error: str = "") -> str:
    block = f'<p class="err">{error}</p>' if error else ""
    return DOCS_LOGIN_HTML.replace("{error}", block)
