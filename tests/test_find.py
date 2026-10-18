"""Find any email: search the whole mailbox, open a result, keep one in Found emails."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import pytest

from helpers import create_user, sign_in
from test_llm import FakeModel
from test_summaries import account, messages, start
from backend.mail import find
from backend.mail.bridge import Target, locator, parse_folder_locator, parse_locator
from backend.mail.errors import BridgeError


def mail(subject, body, days_ago=1, sender="Dana <dana@example.invalid>"):
    when = format_datetime(datetime.now(timezone.utc) - timedelta(days=days_ago))
    return (f"From: {sender}\nTo: me@example.invalid\nSubject: {subject}\nDate: {when}\nMIME-Version: 1.0\nContent-Type: text/plain; charset=utf-8\nContent-Transfer-Encoding: 8bit\nMessage-ID: <{abs(hash(subject)) % 10**9}@example.invalid>\n\n{body}\n"
            ).replace("\n", "\r\n").encode("utf-8")


@pytest.fixture
def env(tmp_path):
    model = FakeModel()
    appm, client, bridge = start(tmp_path, model)
    bridge.add(701, mail("Canvas order", "Visual Art 2 canvases are on the way.", 3), "Archive")
    bridge.add(702, mail("Old project", "The 3D project and Visual Art 2 notes.", 400), "Archive")
    bridge.add(703, mail("Junk offer", "Cheap Visual Art 2 prints!", 2), "Trash")
    bridge.add(704, mail("Café menu", "Crème brûlée tonight.", 5), "Archive")
    yield appm, client, bridge, model
    bridge.close()
    model.close()


def run_search(client, query, include_junk=False, wait=10):
    r = client.post("/api/v1/find/searches", json={"query": query, "include_junk": include_junk})
    assert r.status_code == 201, r.text
    job = r.json()["id"]
    end = time.time() + wait
    while time.time() < end:
        p = client.get(f"/api/v1/find/searches/{job}")
        if p.json()["done"]:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("the search did not finish")
    page = client.get(f"/api/v1/find/searches/{job}/results").json()
    return job, page


# ---------- the words ----------

def test_typed_words_are_all_required_and_quotes_keep_a_phrase_together():
    terms = find.parse_query('canvas, "visual art 2" ,  order')
    assert [(t.text, t.phrase) for t in terms] == [("canvas", False), ("visual art 2", True), ("order", False)]


@pytest.mark.parametrize("bad", ["", "a", "   ", "x" * 201, " ".join(["word"] * 13)])
def test_unusable_searches_get_a_plain_answer(bad):
    with pytest.raises(find.FindError):
        find.parse_query(bad)


def test_search_words_are_quoted_for_the_mail_service():
    target = Target(host="mail.example.com", imap_port=993, username="u", password="p", smtp_port=None, kind="imap")
    crit, utf8 = find.criteria(find.parse_query('say "hi \\ there"'), target)
    assert crit[0] == "TEXT" and not utf8
    assert find._quote('a"b\\c') == '"a\\"b\\\\c"'
    gmail = Target(host="imap.gmail.com", imap_port=993, username="u", password="p", smtp_port=None, kind="imap")
    crit, _ = find.criteria(find.parse_query("from:bank invoice"), gmail)
    assert crit == ["X-GM-RAW", '"from:bank invoice"']
    assert find.criteria(find.parse_query("café"), target)[1] is True


def test_folder_choice():
    folders = [({"\\hasnochildren"}, "INBOX"), ({"\\all"}, "All Mail"), ({"\\junk"}, "Spam"), ({"\\trash"}, "Trash"), (set(), "Receipts")]
    assert find.choose_folders(folders, False) == ["All Mail"]
    assert find.choose_folders(folders, True) == ["All Mail", "Spam", "Trash"]
    plain = [(set(), "INBOX"), ({"\\sent"}, "Sent"), ({"\\junk"}, "Junk"), ({"\\trash"}, "Bin"), ({"\\drafts"}, "Drafts"), (set(), "Archive")]
    assert find.choose_folders(plain, False) == ["INBOX", "Sent", "Archive"]


def test_folder_locations_round_trip_and_old_inbox_ones_still_work():
    assert locator(7, 12) == "INBOX|7|12" and parse_locator("INBOX|7|12") == (7, 12)
    where = locator(7, 12, "Archive/Receipts 2026")
    assert parse_folder_locator(where) == ("Archive/Receipts 2026", 7, 12)
    with pytest.raises(BridgeError):
        parse_locator(where)                       # an old-style reader never mistakes a folder location for the Inbox


# ---------- searching ----------

def test_a_search_finds_mail_in_every_folder_but_not_bin_or_spam(env):
    _, client, bridge, _ = env
    account(client, bridge)
    _, page = run_search(client, "visual art 2")
    assert page["total"] == 2
    assert [r["subject"] for r in page["rows"]] == ["Canvas order", "Old project"]          # newest first
    assert {r["folder"] for r in page["rows"]} == {"Archive"}
    assert all("token" in r and "uid" not in r and "source_locator" not in r for r in page["rows"])
    _, page = run_search(client, "visual art 2", include_junk=True)
    assert page["total"] == 3 and "Junk offer" in [r["subject"] for r in page["rows"]]


def test_quoted_words_must_stay_together(env):
    _, client, bridge, _ = env
    account(client, bridge)
    assert run_search(client, '"art visual"')[1]["total"] == 0
    assert run_search(client, '"visual art 2" 3D')[1]["total"] == 1
    assert run_search(client, "visual 3D")[1]["total"] == 1


def test_non_english_words_are_found(env):
    _, client, bridge, _ = env
    account(client, bridge)
    assert [r["subject"] for r in run_search(client, "crème")[1]["rows"]] == ["Café menu"]


def test_a_search_changes_nothing_and_stores_nothing(env):
    appm, client, bridge, model = env
    aid = account(client, bridge)
    before = messages(client, aid)
    run_search(client, "visual art 2")
    assert messages(client, aid) == before
    assert model.requests == []
    assert not any("STORE" in line or "MOVE" in line for line in bridge.log)


def test_the_search_words_are_never_logged(env, caplog):
    _, client, bridge, _ = env
    account(client, bridge)
    with caplog.at_level("DEBUG"):
        run_search(client, "visual art 2")
    assert "visual art" not in caplog.text.lower()


def test_open_the_original_of_a_result(env):
    _, client, bridge, _ = env
    account(client, bridge)
    _, page = run_search(client, "canvases")
    r = client.get(f"/api/v1/find/results/{page['rows'][0]['token']}/original")
    assert r.status_code == 200 and "canvases are on the way" in r.text
    assert r.headers["cache-control"] == "no-store"


def test_no_mailbox_means_a_kind_message(tmp_path):
    appm, client, bridge = start(tmp_path, None)
    r = client.post("/api/v1/find/searches", json={"query": "anything"})
    assert r.status_code == 400 and "mailbox" in r.json()["detail"].lower()
    bridge.close()


def test_searches_are_limited_per_minute(env):
    _, client, bridge, _ = env
    account(client, bridge)
    codes = [client.post("/api/v1/find/searches", json={"query": "zzzz"}).status_code for _ in range(8)]
    assert 429 in codes


# ---------- whose search is it ----------

def test_nobody_else_can_use_my_search_or_my_results(env):
    appm, client, bridge, _ = env
    account(client, bridge)
    job, page = run_search(client, "visual art 2")
    token = page["rows"][0]["token"]
    create_user(client, "casey")
    other = sign_in(appm, "casey")
    assert other.get(f"/api/v1/find/searches/{job}").status_code == 404
    assert other.get(f"/api/v1/find/searches/{job}/results").status_code == 404
    assert other.delete(f"/api/v1/find/searches/{job}").status_code == 404
    assert other.get(f"/api/v1/find/results/{token}/original").status_code == 404
    assert other.post(f"/api/v1/find/results/{token}/keep").status_code == 404
    forged = token[:-4] + ("0000" if not token.endswith("0000") else "1111")
    assert client.get(f"/api/v1/find/results/{forged}/original").status_code == 404
    assert client.get("/api/v1/find/results/AAAAAAAAAAAA.0.000000000000000000000000/original").status_code == 404


def test_the_switch_turns_it_off(env):
    _, client, bridge, _ = env
    account(client, bridge)
    assert client.put("/api/v1/admin/features", json={"find_mail": False}).status_code == 200
    assert client.post("/api/v1/find/searches", json={"query": "visual"}).status_code == 403
    assert client.put("/api/v1/admin/features", json={"find_mail": True}).status_code == 200
    assert client.post("/api/v1/find/searches", json={"query": "visual"}).status_code == 201


# ---------- keeping one: Found emails ----------

def keep(client, token):
    r = client.post(f"/api/v1/find/results/{token}/keep")
    assert r.status_code == 200, r.text
    return r.json()


def test_keeping_a_result_lists_it_quietly_for_60_days(env):
    _, client, bridge, model = env
    aid = account(client, bridge)
    client.post(f"/api/v1/accounts/{aid}/sync", json={})
    _, page = run_search(client, "canvases")
    done = keep(client, page["rows"][0]["token"])
    assert done["already"] is False and done["summary_queued"] is True
    days = (done["found_until"] - time.time()) / 86400
    assert 59.9 < days < 60.1
    found = messages(client, aid)["Canvas order"]
    assert found["from_all_mail"] is True and found["found_until"] and "source_locator" not in found
    assert keep(client, page["rows"][0]["token"])["message_id"] == done["message_id"]        # pressing it twice keeps one


def test_summarising_several_found_emails_keeps_each_and_queues_them(env):
    _, client, bridge, _ = env
    aid = account(client, bridge)
    client.post(f"/api/v1/accounts/{aid}/sync", json={})
    _, page = run_search(client, "visual art 2")
    tokens = [row["token"] for row in page["rows"]]
    assert len(tokens) >= 2
    r = client.post("/api/v1/find/results/keep", json={"tokens": tokens + [tokens[0]]})      # a repeated one is only counted once
    assert r.status_code == 200, r.text
    results = r.json()["results"]
    assert set(results) == set(tokens)
    assert all(v["ok"] and v["already"] is False and v["summary_queued"] is True for v in results.values())
    again = client.post("/api/v1/find/results/keep", json={"tokens": tokens}).json()["results"]
    assert all(v["ok"] and v["already"] is True for v in again.values())          # pressing it twice keeps one each


def test_summarising_several_needs_a_sensible_list_and_only_opens_my_own_results(env):
    appm, client, bridge, _ = env
    account(client, bridge)
    _, page = run_search(client, "visual art 2")
    token = page["rows"][0]["token"]
    assert client.post("/api/v1/find/results/keep", json={"tokens": []}).status_code == 422
    assert client.post("/api/v1/find/results/keep", json={"tokens": [f"AAAAAAAAAAAA.{i}.000000000000000000000000" for i in range(101)]}).status_code == 422
    junk = client.post("/api/v1/find/results/keep", json={"tokens": ["not-a-token"]}).json()["results"]
    assert junk["not-a-token"]["ok"] is False
    create_user(client, "casey")
    other = sign_in(appm, "casey")
    theirs = other.post("/api/v1/find/results/keep", json={"tokens": [token]}).json()["results"]
    assert theirs[token]["ok"] is False


def test_a_kept_email_can_be_opened_and_summarised_from_its_own_folder(env):
    appm, client, bridge, model = env
    aid = account(client, bridge)
    _, page = run_search(client, "canvases")
    done = keep(client, page["rows"][0]["token"])
    end = time.time() + 10
    while time.time() < end and messages(client, aid)["Canvas order"]["summary"].startswith("Not summarised"):
        time.sleep(0.05)
    assert not messages(client, aid)["Canvas order"]["summary"].startswith("Not summarised")
    r = client.get(f"/api/v1/accounts/{aid}/messages/{done['message_id']}/original")
    assert r.status_code == 200 and "canvases" in r.text
    assert model.requests and "canvases" in str(model.requests[-1])


def test_a_kept_email_survives_sync_and_the_all_emails_clean_up(env):
    appm, client, bridge, _ = env
    aid = account(client, bridge)
    _, page = run_search(client, "visual art 2")
    for row in page["rows"]:                                    # one of them is 400 days old
        keep(client, row["token"])
    end = time.time() + 10                                      # let the summaries finish, so the mailbox is not busy
    while time.time() < end:
        q = client.get("/api/v1/me/summary-queue").json()
        if q["waiting"] == 0 and q["writing"] == 0:
            break
        time.sleep(0.05)
    client.post(f"/api/v1/accounts/{aid}/sync", json={})
    assert client.post(f"/api/v1/accounts/{aid}/inbox/recent").status_code == 200
    assert {"Canvas order", "Old project"} <= set(messages(client, aid))


def test_reviewed_removes_it_and_never_touches_the_mailbox(env):
    _, client, bridge, _ = env
    aid = account(client, bridge)
    _, page = run_search(client, "canvases")
    done = keep(client, page["rows"][0]["token"])
    log_before = len(bridge.log)
    assert client.post(f"/api/v1/accounts/{aid}/messages/{done['message_id']}/resolve", json={"outcome": "archived"}).status_code == 409
    assert client.post(f"/api/v1/accounts/{aid}/messages/{done['message_id']}/resolve", json={"outcome": "reviewed"}).status_code == 204
    assert "Canvas order" not in messages(client, aid)
    assert bridge.messages[701]["folder"] == "Archive" and "\\Seen" not in bridge.messages[701]["flags"]
    assert not any(" STORE " in f" {line} " or line.startswith("UID STORE") or line.startswith("UID MOVE") for line in bridge.log[log_before:])


def test_found_emails_expire_after_their_60_days(env):
    appm, client, bridge, _ = env
    aid = account(client, bridge)
    _, page = run_search(client, "canvases")
    done = keep(client, page["rows"][0]["token"])
    account_row = appm.vault.get_account(aid)
    stored = appm.vault.get_message(aid, done["message_id"])
    from backend.models import RetainedMessageCreate
    appm.vault.update_message(aid, done["message_id"], RetainedMessageCreate(**{**{k: v for k, v in stored.items() if k != "id"}, "found_until": time.time() - 5}).model_dump(mode="python"))
    assert appm.mail_service.drop_expired_found(appm.vault, account_row) == 1
    assert "Canvas order" not in messages(client, aid)


def test_switching_the_feature_off_forgets_what_was_kept(env):
    _, client, bridge, _ = env
    aid = account(client, bridge)
    _, page = run_search(client, "canvases")
    keep(client, page["rows"][0]["token"])
    client.put("/api/v1/me/features", json={"find_mail": False})
    assert "Canvas order" not in messages(client, aid)


# ---------- Fast search (the optional word list) ----------

from backend.mail import find_index as fi            # noqa: E402


def test_words_skip_long_numbers_and_long_words_and_ignore_accents():
    assert fi.words("Café 3D project, Visual-Art 2 1234567890 " + "x" * 31) == ["cafe", "3d", "project", "visual", "art", "2"]
    assert fi.words("card 4111111111111111 and 12345678") == ["card", "and", "12345678"]


def test_the_word_query_matches_word_starts_and_phrases_and_declines_what_it_cannot_answer():
    T = find.Term
    assert fi.match_query([T("crème", False)]) == '"creme"*'
    assert fi.match_query([T("visual art", True), T("3d", False)]) == '"visual art" AND "3d"*'
    assert fi.match_query([T("12345678901", False)]) is None          # such numbers are never kept, so live search must answer


def test_the_word_list_is_sealed_and_only_opens_for_the_right_key_and_person():
    import os
    idx = fi.UserIndex()
    idx.add("a", "INBOX", 7, 1, "Canvas order for a visual art project")
    sealed = fi.seal(idx.to_bytes(), b"k" * 32, b"person-1")
    assert b"canvas" not in sealed.lower()
    assert fi.unseal(sealed, b"k" * 32, b"person-1")
    for key, who in ((os.urandom(32), b"person-1"), (b"k" * 32, b"person-2")):
        with pytest.raises(Exception):
            fi.unseal(sealed, key, who)


def fast_on(client, appm, aid):
    index = appm.mail_ctx.find_index
    index.pause = 0
    assert client.put(f"/api/v1/find/fast/{aid}", json={"enabled": True}).status_code == 400            # the box must be ticked
    r = client.put(f"/api/v1/find/fast/{aid}", json={"enabled": True, "agree": True})
    assert r.status_code == 200, r.text
    end = time.time() + 15
    while time.time() < end:
        st = client.get("/api/v1/find/fast").json()["mailboxes"][0]
        if st["state"] == "ready":
            return index, st
        time.sleep(0.05)
    raise AssertionError("the word list was not built: " + str(st))


def test_fast_search_builds_answers_without_asking_the_mailbox_and_is_sealed(env):
    appm, client, bridge, _ = env
    aid = account(client, bridge)
    index, status = fast_on(client, appm, aid)
    assert status["total"] >= 3 and status["done"] == status["total"]
    mark = len(bridge.log)
    job, page = run_search(client, "visual art 2")
    assert [r["subject"] for r in page["rows"]] == ["Canvas order", "Old project"]
    assert page["mailboxes"][0]["fast"] is True
    assert not any("SEARCH" in line and "TEXT" in line for line in bridge.log[mark:])                    # the mailbox was not asked to search
    assert [r["subject"] for r in run_search(client, "crème")[1]["rows"]] == ["Café menu"]
    user = appm.vault.get_account(aid)["owner_user_id"]
    sealed = (appm.vault.db_path.parent / "find-index" / f"{user}.bin").read_bytes()
    assert b"canvas" not in sealed.lower() and b"SQLite" not in sealed


def test_fast_search_keeps_up_with_new_and_deleted_mail(env):
    appm, client, bridge, _ = env
    aid = account(client, bridge)
    index, _ = fast_on(client, appm, aid)
    user = appm.vault.get_account(aid)["owner_user_id"]
    bridge.add(705, mail("Fresh news", "A brand new zeppelin arrived.", 0), "Archive")
    del bridge.messages[702]
    index.pass_once(user, aid)
    assert [r["subject"] for r in run_search(client, "zeppelin")[1]["rows"]] == ["Fresh news"]
    assert run_search(client, "3D project")[1]["total"] == 0


def test_a_long_number_falls_back_to_the_live_search_and_spam_is_never_in_the_word_list(env):
    appm, client, bridge, _ = env
    aid = account(client, bridge)
    fast_on(client, appm, aid)
    _, page = run_search(client, "visual art 2", include_junk=True)
    assert page["mailboxes"][0]["fast"] is False and page["total"] == 3 and "Junk offer" in [r["subject"] for r in page["rows"]]
    _, page = run_search(client, "98765432101")
    assert page["mailboxes"][0]["fast"] is False


def test_turning_fast_search_off_deletes_the_word_list(env):
    appm, client, bridge, _ = env
    aid = account(client, bridge)
    fast_on(client, appm, aid)
    user = appm.vault.get_account(aid)["owner_user_id"]
    path = appm.vault.db_path.parent / "find-index" / f"{user}.bin"
    assert path.exists()
    assert client.put(f"/api/v1/find/fast/{aid}", json={"enabled": False}).status_code == 200
    assert not path.exists()
    assert run_search(client, "visual art 2")[1]["mailboxes"][0]["fast"] is False
    assert client.get("/api/v1/find/fast").json()["mailboxes"][0]["state"] == "off"


def test_the_word_list_goes_when_the_person_does_and_is_never_shared(env):
    appm, client, bridge, _ = env
    aid = account(client, bridge)
    fast_on(client, appm, aid)
    user = appm.vault.get_account(aid)["owner_user_id"]
    create_user(client, "casey")
    other = sign_in(appm, "casey")
    assert other.get("/api/v1/find/fast").json()["mailboxes"] == []                                     # nothing of mine is listed
    assert other.put(f"/api/v1/find/fast/{aid}", json={"enabled": True, "agree": True}).status_code == 404
    assert other.post(f"/api/v1/find/fast/{aid}/rebuild").status_code == 404
    path = appm.vault.db_path.parent / "find-index" / f"{user}.bin"
    appm.delete_user_data(user)
    assert not path.exists() and appm.mail_ctx.find_index.enabled(user) == {}


def test_the_word_list_is_not_in_a_backup(env):
    appm, client, bridge, _ = env
    aid = account(client, bridge)
    fast_on(client, appm, aid)
    import sqlite3
    copy = appm.vault.db_path.parent / "copy.sqlite3"
    with sqlite3.connect(appm.vault.db_path) as src, sqlite3.connect(copy) as dst:
        src.backup(dst)
    assert b"canvas" not in copy.read_bytes().lower() and b"ENVFIDX1" not in copy.read_bytes()


def test_switching_find_any_email_off_deletes_the_word_list_too(env):
    appm, client, bridge, _ = env
    aid = account(client, bridge)
    fast_on(client, appm, aid)
    user = appm.vault.get_account(aid)["owner_user_id"]
    path = appm.vault.db_path.parent / "find-index" / f"{user}.bin"
    assert path.exists()
    client.put("/api/v1/me/features", json={"find_mail": False})
    assert not path.exists() and appm.mail_ctx.find_index.enabled(user) == {}
