"""Server-rendered HTML for the *dynamic* parts of the web-login flow.

Static pages (index, login) live in ``site/`` and are served by Caddy + cached by
Cloudflare. Only these two pages are rendered here because they carry per-session
data (the JWT) and must not be cached. They link the shared static ``/style.css``.
"""
from __future__ import annotations

import html


def _shell(inner: str, *, err: bool = False) -> str:
    cls = "card err" if err else "card"
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="robots" content="noindex">'
        "<title>Emercoin Agent Gateway</title>"
        '<link rel="stylesheet" href="/style.css"></head><body>'
        f'<div class="{cls}"><div class="brand"><b>&#9679;</b> emer<span>coin</span></div>'
        f"{inner}</div></body></html>"
    )


def result_page(github_login: str, token: str, ttl_minutes: int, tariff: str) -> str:
    login = html.escape(github_login)
    tok = html.escape(token)
    inner = (
        '<div class="accent"></div>'
        f'<div class="badge">✓ Signed in as @{login}</div>'
        '<div class="tokbox"><label>Session token (Bearer)</label>'
        f'<textarea class="tok" id="tok" readonly>{tok}</textarea>'
        '<button class="copy" onclick="navigator.clipboard.writeText('
        "document.getElementById('tok').value).then(()=>{this.textContent='Copied ✓'})"
        '">Copy token</button></div>'
        f'<div class="meta">Expires in {ttl_minutes} min · {html.escape(tariff)} tier</div>'
        '<a class="back" href="/login">← back</a>'
    )
    return _shell(inner)


def error_page(message: str) -> str:
    inner = (
        "<h1>Sign-in failed</h1>"
        f'<p class="sub">{html.escape(message)}</p>'
        '<a class="back" href="/login">← try again</a>'
    )
    return _shell(inner, err=True)
