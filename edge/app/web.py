"""Lightweight, self-contained HTML for the browser web-login flow.

No template engine, no static mount: each page is one inline string with embedded
CSS and the logo as a data-URI (see assets.py). Styled to match emercoin.com —
purple #4A3777 with a gold #FFC033 accent on a light-purple field.
"""
from __future__ import annotations

import html

# emercoin.com brand palette
_PURPLE = "#4A3777"
_PURPLE_MID = "#7B6696"
_FIELD = "#f6f2fb"
_GOLD = "#FFC033"
_INK = "#404750"

_BASE_CSS = f"""
*{{box-sizing:border-box}}
html,body{{margin:0;height:100%}}
body{{
  font-family:system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  color:{_INK};background:{_FIELD};
  display:flex;align-items:center;justify-content:center;min-height:100vh;padding:24px;
}}
.card{{
  background:#fff;width:100%;max-width:420px;border-radius:16px;padding:40px 36px;
  box-shadow:0 10px 40px rgba(74,55,119,.14);border:1px solid #e4d6f5;text-align:center;
}}
.brand{{font-size:30px;font-weight:800;letter-spacing:-.5px;margin-bottom:18px;color:{_PURPLE}}}
.brand span{{color:{_PURPLE_MID}}}
.brand b{{color:{_GOLD};font-weight:800}}
h1{{font-size:22px;margin:0 0 8px;color:{_PURPLE}}}
p.sub{{margin:0 0 28px;color:{_PURPLE_MID};font-size:14px;line-height:1.5}}
.btn{{
  display:flex;align-items:center;justify-content:center;gap:10px;width:100%;
  padding:13px 18px;border-radius:10px;border:none;cursor:pointer;
  font-size:15px;font-weight:600;text-decoration:none;
  background:{_PURPLE};color:#fff;transition:background .15s;
}}
.btn:hover{{background:#3b2c61}}
.btn svg{{width:20px;height:20px;fill:#fff}}
.foot{{margin-top:22px;font-size:12px;color:#b09cc9;letter-spacing:.3px}}
.accent{{height:4px;width:54px;background:{_GOLD};border-radius:3px;margin:0 auto 24px}}
.badge{{
  display:inline-flex;align-items:center;gap:8px;background:{_FIELD};color:{_PURPLE};
  border-radius:999px;padding:6px 14px;font-size:14px;font-weight:600;margin-bottom:6px;
}}
.tokbox{{
  position:relative;margin:18px 0 6px;text-align:left;
}}
.tokbox label{{display:block;font-size:12px;color:{_PURPLE_MID};margin-bottom:6px}}
textarea.tok{{
  width:100%;height:84px;resize:none;border:1px solid #e4d6f5;border-radius:10px;
  padding:10px 12px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
  font-size:12px;color:{_INK};background:{_FIELD};word-break:break-all;
}}
.copy{{
  margin-top:8px;width:100%;padding:10px;border-radius:8px;border:1px solid {_PURPLE};
  background:#fff;color:{_PURPLE};font-weight:600;cursor:pointer;font-size:14px;
}}
.copy:hover{{background:{_FIELD}}}
.meta{{font-size:12px;color:{_PURPLE_MID};margin-top:14px}}
.err h1{{color:#b20f03}}
a.back{{display:inline-block;margin-top:18px;color:{_PURPLE_MID};font-size:13px;text-decoration:none}}
a.back:hover{{text-decoration:underline}}
"""

_GITHUB_SVG = (
    '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 0C3.58 0 0 3.58 0 8c0 '
    "3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-"
    ".49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23."
    "82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87."
    "31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 "
    "0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 "
    '2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.'
    '46.55.38A8.01 8.01 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>'
)


def _shell(inner: str, *, err: bool = False) -> str:
    cls = "card err" if err else "card"
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<meta name=\"robots\" content=\"noindex\">"
        "<title>Emercoin Agent Gateway</title>"
        f"<style>{_BASE_CSS}</style></head><body>"
        f'<div class="{cls}"><div class="brand"><b>&#9679;</b> emer<span>coin</span></div>'
        f"{inner}</div></body></html>"
    )


def login_page() -> str:
    inner = (
        '<div class="accent"></div>'
        "<h1>Agent Gateway</h1>"
        '<p class="sub">Sign in with GitHub to manage your agent identity and '
        "memory on the Emercoin blockchain.</p>"
        f'<a class="btn" href="/auth/github/start">{_GITHUB_SVG}Continue with GitHub</a>'
        '<div class="foot">ai.emercoin.com</div>'
    )
    return _shell(inner)


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
