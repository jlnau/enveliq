"""The formatted copy of an email (backend/mail/htmlview.py): what is kept, what is removed, and how the page is served."""
from backend.mail import htmlview
from backend.mail.parse import render_original


def html_mail() -> bytes:
    return (b"From: Carol <carol@example.invalid>\r\nTo: me@example.invalid\r\nSubject: Rich\r\nMIME-Version: 1.0\r\nContent-Type: text/html; charset=utf-8\r\n\r\n"
            b"<p>Hello <b>Dana</b></p><img src='http://tracker.invalid/p.gif'>\r\n")

TINY = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


def page(html: str, cids: dict | None = None, remote: bool = False) -> str:
    return htmlview.rebuild(html, cids or {}, remote).page


def body_of(html: str, **kw) -> str:
    out = page(html, **kw)
    return out[out.index("<body"):out.rindex("<script>")]


def test_the_sender_formatting_is_kept():
    out = body_of('<table width="300" bgcolor="#ffeeaa"><tr><td style="color:#c81e1e;font-size:20px">Hello <b>there</b></td></tr></table>'
                  '<p align="center"><font color="red" face="Arial">Hi</font></p>')
    assert '<table width="300" bgcolor="#ffeeaa">' in out and "color:#c81e1e" in out and "font-size:20px" in out
    assert "<b>there</b>" in out and 'align="center"' in out and '<font color="red" face="Arial">' in out


def test_style_blocks_are_kept_but_cannot_load_or_run_anything():
    out = page("<style>.a{color:red}@import url(https://x.invalid/a.css);.b{background:url(https://x.invalid/t.png)}.c{behavior:url(x.htc)}"
               "@font-face{font-family:f;src:url(https://x.invalid/f.woff)}.d{width:expression(alert(1))}</style><p class=a>x</p>")
    assert ".a{color:red}" in out
    for bad in ("@import", "x.invalid", "behavior", "@font-face", "expression"):
        assert bad not in out


def test_scripts_handlers_frames_forms_and_vectors_are_removed():
    html = ('<p onclick="x()" onmouseover="y()">Hi</p><script>alert(1)</script><iframe src="https://x.invalid"></iframe><object data="x"></object>'
            '<embed src="x"><svg onload="x()"><script>1</script></svg><math><mi>x</mi></math><form action="https://x.invalid"><input name="p"><button>Go</button></form>'
            '<video src="x"></video><meta http-equiv="refresh" content="0;url=https://x.invalid"><base href="https://x.invalid/"><link rel="stylesheet" href="https://x.invalid/s.css">')
    out = body_of(html)
    for bad in ("onclick", "onmouseover", "alert", "<iframe", "<object", "<embed", "<svg", "<math", "<form", "<input", "<button", "<video", "refresh", "<base", "<link", "x.invalid"):
        assert bad not in out, bad
    assert "<p>Hi</p>" in out


def test_links_keep_only_web_and_mail_addresses_and_open_nothing_by_themselves():
    out = body_of('<a href="https://example.com/a?b=1">ok</a><a href="javascript:alert(1)">bad</a><a href="data:text/html,x">bad2</a>'
                  '<a href="mailto:me@example.com">mail</a><a href="//evil.invalid/x">rel</a><a href="  JAVASCRIPT:alert(1)">spaced</a>')
    assert 'href="https://example.com/a?b=1" target="_blank" rel="noopener noreferrer nofollow"' in out
    assert 'href="mailto:me@example.com"' in out
    for bad in ("javascript", "data:text", "evil.invalid"):
        assert bad.lower() not in out.lower()


def test_pictures_inside_the_email_show_and_pictures_from_the_internet_wait():
    html = '<img src="cid:Logo@Example.com" alt="logo"><img src="https://t.invalid/p.gif" alt="p"><img src="http://t.invalid/q.gif"><img src="' + TINY + '">'
    held = htmlview.rebuild(html, {"logo@example.com": TINY})
    assert held.page.count(TINY) == 2 and "t.invalid" not in held.page and held.blocked == 2
    shown = htmlview.rebuild(html, {"logo@example.com": TINY}, remote_images=True)
    assert 'src="https://t.invalid/p.gif"' in shown.page and "http://t.invalid" not in shown.page and shown.blocked == 1   # plain http is never loaded


def test_style_pictures_follow_the_same_rule():
    held = htmlview.rebuild('<div style="background:url(https://t.invalid/b.png);color:red">x</div>')
    assert "t.invalid" not in held.page and "color:red" in held.page and held.blocked == 1
    assert "https://t.invalid/b.png" in htmlview.rebuild('<div style="background:url(https://t.invalid/b.png)">x</div>', remote_images=True).page


def test_a_style_cannot_cover_the_page():
    out = body_of('<div style="position:fixed;top:0;left:0;width:100%;height:100%;color:red">x</div>')
    assert "position" not in out and "color:red" in out


def test_unknown_tags_keep_their_text_and_a_self_closing_script_swallows_nothing():
    out = body_of("<o:p>kept</o:p><script/><p>after</p><custom-thing>also</custom-thing>")
    assert "kept" in out and "after" in out and "also" in out and "<o:p>" not in out


def test_deep_nesting_and_huge_input_are_cut_down():
    out = page("<div>" * 5000 + "x" + "</div>" * 5000)
    assert out.count("<div>") <= htmlview.MAX_DEPTH
    assert len(page("<p>" + "a" * 3_000_000 + "</p>")) < 2_500_000


def test_the_policy_allows_only_our_one_script_and_no_pictures_from_the_internet_by_default():
    csp = htmlview.policy_header(False)
    assert "sandbox allow-scripts" in csp and "default-src 'none'" in csp and "script-src '" + htmlview.SCRIPT_HASH + "'" in csp
    assert "img-src data:" in csp and "https:" not in csp and "'unsafe-eval'" not in csp and "form-action 'none'" in csp and "frame-ancestors 'self'" in csp
    assert "img-src data: https:" in htmlview.policy_header(True)
    assert htmlview.rebuild("<p>x</p>").page.count("<script>") == 1              # only ours


def test_has_html_is_reported_and_plain_emails_have_none():
    assert render_original(html_mail())["has_html"] is True
    plain = b"From: A <a@example.invalid>\r\nTo: b@example.invalid\r\nSubject: s\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nhello\r\n"
    assert render_original(plain)["has_html"] is False and htmlview.render(plain) is None


def test_inline_pictures_are_taken_from_the_email_by_content_id():
    raw = (b"From: A <a@example.invalid>\r\nTo: b@example.invalid\r\nSubject: s\r\nMIME-Version: 1.0\r\nContent-Type: multipart/related; boundary=R\r\n\r\n"
           b"--R\r\nContent-Type: text/html; charset=utf-8\r\n\r\n<p>Hi</p><img src=\"cid:pic1@x\" alt=\"p\">\r\n"
           b"--R\r\nContent-Type: image/png\r\nContent-ID: <pic1@x>\r\nContent-Transfer-Encoding: base64\r\n\r\n" + TINY.split(",")[1].encode() + b"\r\n--R--\r\n")
    built = htmlview.render(raw)
    assert built is not None and TINY in built.page and built.blocked == 0


def test_the_page_always_grows_with_the_email_and_never_gets_its_own_scrollbar():
    page = rebuild('<html><head><style>body{height:150px;overflow:auto}</style></head><body style="height:100px"><p>hi</p></body></html>').page
    assert "overflow:visible!important" in page and "height:auto!important" in page
    assert page.index("height:150px") < page.index("height:auto!important")        # ours comes last, so it wins
