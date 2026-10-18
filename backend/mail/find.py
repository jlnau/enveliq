"""Find any email: search a person's whole mailbox on the mail service's side.

Nothing a search finds is stored. A search asks the person's own mail service
which emails match and keeps only folder and message numbers, in server memory,
for a few minutes. Headers are fetched for the page on screen and then dropped.
The search words are never logged.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .bridge import Bridge, Target
from .errors import BridgeError
from .parse import _addresses, clean, likely_has_files, parse_headers, received_at_of

log = logging.getLogger("enveliq.find")

MIN_QUERY = 2
MAX_QUERY = 200
MAX_TERMS = 12
JOB_LIFETIME = 15 * 60          # a search and its list of matches are forgotten after this
SEARCH_SECONDS = 180            # most time one mailbox gets
SOCKET_SECONDS = 200            # slow mail services (Proton Bridge: ~20 s) must not time out early
MAX_REFS = 5000                 # matches remembered per search (the count still shows the true total)
HEAD_PER_FOLDER = 100           # headers read up front per folder so the first pages are really newest-first
MAX_RUNNING = 4
PAGE = 25

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_QUOTED = re.compile(r'"([^"]*)"|([^\s",]+)')


class FindError(Exception):
    """A plain, kind message that is safe to show to the person."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass(frozen=True)
class Term:
    text: str
    phrase: bool


def parse_query(text: str) -> list[Term]:
    """Typed words are all required. "Quoted words" must appear together. Commas are ignored."""
    text = _CONTROL.sub(" ", str(text or "")).strip()
    if len(text) < MIN_QUERY:
        raise FindError("Type at least two letters to search.")
    if len(text) > MAX_QUERY:
        raise FindError("That search is too long. Try fewer words.")
    terms: list[Term] = []
    for match in _QUOTED.finditer(text):
        quoted, bare = match.group(1), match.group(2)
        value = " ".join((quoted if quoted is not None else bare).split())
        if value:
            terms.append(Term(value, quoted is not None))
    if not terms:
        raise FindError("Type at least two letters to search.")
    if len(terms) > MAX_TERMS:
        raise FindError("Please use fewer words in one search.")
    return terms


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def is_gmail(target: Target) -> bool:
    return target.kind == "imap" and (target.host or "").lower() in ("imap.gmail.com", "imap.googlemail.com")


def criteria(terms: list[Term], target: Target) -> tuple[list[str], bool]:
    """IMAP search criteria for these words, and whether they need UTF-8."""
    if is_gmail(target):
        # Gmail's own search language, so "from:bank" style words work too.
        raw = " ".join(('"' + t.text.replace('"', "") + '"') if t.phrase else t.text for t in terms)
        return ["X-GM-RAW", _quote(raw)], not raw.isascii()
    out: list[str] = []
    for term in terms:
        out += ["TEXT", _quote(term.text)]
    return out, not all(t.text.isascii() for t in terms)


def choose_folders(folders: list[tuple[set[str], str]], include_junk: bool) -> list[str]:
    """Which folders to search. One 'all mail' folder if the service has one,
    otherwise every normal folder. Spam and Bin only when asked."""
    def flagged(flag: str) -> list[str]:
        return [name for flags, name in folders if flag in flags]
    chosen = flagged("\\all")
    if not chosen:
        chosen = [name for _f, name in folders if name.lower() in ("all mail", "[gmail]/all mail", "[google mail]/all mail")][:1]
    if not chosen:
        skip = {"\\junk", "\\trash", "\\drafts"}
        chosen = [name for flags, name in folders if not (flags & skip) and name.lower() not in ("spam", "junk", "trash", "bin", "drafts", "deleted items")]
        if not any(n.upper() == "INBOX" for n in chosen):
            chosen.insert(0, "INBOX")
    if include_junk:
        for name in flagged("\\junk") + flagged("\\trash"):
            if name not in chosen:
                chosen.append(name)
        for name in ("Spam", "Trash"):           # Proton Bridge names them plainly
            if name in (n for _f, n in folders) and name not in chosen:
                chosen.append(name)
    return chosen


def nice_folder(name: str) -> str:
    last = name.replace("\\", "/").split("/")[-1].strip() or name
    return "Inbox" if last.upper() == "INBOX" else last


@dataclass
class Ref:
    account_id: str
    folder: str
    validity: int
    uid: int
    when: float = 0.0
    rid: int = 0


@dataclass
class Mailbox:
    account_id: str
    label: str
    state: str = "waiting"          # waiting | searching | done | failed | cancelled
    found: int = 0
    message: str = ""
    session: Any = None


@dataclass
class Job:
    id: str
    user_id: str
    include_junk: bool
    created: float
    terms: list[Term]
    mailboxes: dict[str, Mailbox]
    refs: list[Ref] = field(default_factory=list)
    total: int = 0
    cancelled: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)
    ordered: bool = False
    by_id: dict[int, Ref] = field(default_factory=dict)

    @property
    def done(self) -> bool:
        return all(m.state in ("done", "failed", "cancelled") for m in self.mailboxes.values())


class FindJobs:
    def __init__(self, bridge: Bridge, load_account: Callable[[str], dict[str, Any]], target_for: Callable[[dict[str, Any]], Target]):
        self.bridge = bridge
        self._load = load_account
        self._target = target_for
        self._secret = secrets.token_bytes(32)
        self._jobs: dict[str, Job] = {}
        self._guard = threading.Lock()
        self._busy: dict[str, threading.Lock] = {}
        self._slots = threading.BoundedSemaphore(MAX_RUNNING)

    # ---------- references the page can hold ----------

    def token(self, job: Job, index: int) -> str:
        mac = hmac.new(self._secret, f"{job.user_id}|{job.id}|{index}".encode(), hashlib.sha256).hexdigest()[:24]
        return f"{job.id}.{index}.{mac}"

    def resolve(self, user_id: str, token: str) -> tuple[Job, Ref]:
        """The search and the one email a token points at. Anything wrong is plainly 'not found'."""
        try:
            job_id, index, mac = str(token).split(".")
            n = int(index)
        except ValueError:
            raise FindError("Not found.", 404) from None
        job = self.job(user_id, job_id)
        good = hmac.new(self._secret, f"{job.user_id}|{job.id}|{n}".encode(), hashlib.sha256).hexdigest()[:24]
        ref = job.by_id.get(n)
        if not hmac.compare_digest(good, mac) or ref is None:
            raise FindError("Not found.", 404)
        return job, ref

    def job(self, user_id: str, job_id: str) -> Job:
        self._forget_old()
        job = self._jobs.get(str(job_id))
        if job is None or job.user_id != user_id:
            raise FindError("Not found.", 404)
        return job

    def _forget_old(self) -> None:
        cutoff = time.time() - JOB_LIFETIME
        with self._guard:
            for key in [k for k, j in self._jobs.items() if j.created < cutoff and j.done]:
                del self._jobs[key]

    # ---------- start / cancel ----------

    def running_for(self, user_id: str) -> int:
        return sum(1 for j in self._jobs.values() if j.user_id == user_id and not j.done)

    def start(self, user_id: str, accounts: list[tuple[str, str]], terms: list[Term], include_junk: bool) -> Job:
        """accounts: (account_id, label) for every mailbox of this person that can be searched."""
        if not accounts:
            raise FindError("Connect a mailbox first, then you can search it.")
        if self.running_for(user_id) >= 2:
            raise FindError("Two searches are already running. Wait for one to finish or cancel it.", 429)
        job = Job(id=secrets.token_urlsafe(9), user_id=user_id, include_junk=include_junk, created=time.time(), terms=terms,
                  mailboxes={a: Mailbox(a, label) for a, label in accounts})
        self._forget_old()
        with self._guard:
            self._jobs[job.id] = job
        for account_id in job.mailboxes:
            threading.Thread(target=self._run_mailbox, args=(job, account_id), name="enveliq-find", daemon=True).start()
        return job

    def cancel(self, job: Job) -> None:
        job.cancelled = True
        for mb in job.mailboxes.values():
            session = mb.session
            if session is not None:
                session.abort()

    # ---------- the search itself ----------

    def _mailbox_lock(self, account_id: str) -> threading.Lock:
        with self._guard:
            return self._busy.setdefault(account_id, threading.Lock())

    def _run_mailbox(self, job: Job, account_id: str) -> None:
        mb = job.mailboxes[account_id]
        lock = self._mailbox_lock(account_id)
        if not lock.acquire(blocking=False):
            mb.state, mb.message = "failed", "This mailbox is already being searched."
            return
        try:
            with self._slots:
                if job.cancelled:
                    mb.state = "cancelled"
                    return
                mb.state = "searching"
                self._search_account(job, mb)
        except BridgeError as err:
            mb.state = "cancelled" if job.cancelled else "failed"
            mb.message = "" if job.cancelled else err.message
        except Exception:
            log.warning("find: search failed for one mailbox")     # never log the words
            mb.state = "cancelled" if job.cancelled else "failed"
            mb.message = "" if job.cancelled else "This mailbox could not be searched just now."
        finally:
            mb.session = None
            lock.release()

    def _search_account(self, job: Job, mb: Mailbox) -> None:
        account = self._load(mb.account_id)
        target = self._target(account)
        started = time.time()
        crit, utf8 = criteria(job.terms, target)
        with self.bridge.session(target) as s:
            mb.session = s
            s.set_timeout(SOCKET_SECONDS)
            folders = choose_folders(s.list_folders(), job.include_junk)
            for folder in folders:
                if job.cancelled:
                    mb.state = "cancelled"
                    return
                if time.time() - started > SEARCH_SECONDS:
                    mb.state, mb.message = "done", "Stopped early because this mailbox took too long. Try more specific words."
                    return
                validity = s.select_folder(folder, True)
                uids = s.search(crit, utf8)
                head = uids[:HEAD_PER_FOLDER]
                dates: dict[int, float] = {}
                if head:
                    for uid, raw in s.header_blocks(head, "Date"):
                        dates[uid] = received_at_of(raw) or 0.0
                with job.lock:
                    job.total += len(uids)
                    mb.found += len(uids)
                    room = max(0, MAX_REFS - len(job.refs))
                    for uid in uids[:room]:
                        ref = Ref(mb.account_id, folder, validity, uid, dates.get(uid, 0.0), len(job.by_id))
                        job.by_id[ref.rid] = ref
                        job.refs.append(ref)
                    job.ordered = False
        mb.state = "done"

    # ---------- a page of results ----------

    def _order(self, job: Job) -> None:
        with job.lock:
            if not job.ordered:
                job.refs.sort(key=lambda r: (r.when, r.uid), reverse=True)
                job.ordered = True

    def progress(self, job: Job) -> dict[str, Any]:
        return {
            "id": job.id, "done": job.done, "cancelled": job.cancelled, "total": job.total,
            "include_junk": job.include_junk,
            "mailboxes": [{"account_id": m.account_id, "label": m.label, "state": m.state, "found": m.found, "message": m.message} for m in job.mailboxes.values()],
        }

    def page(self, job: Job, offset: int, limit: int = PAGE) -> list[dict[str, Any]]:
        """Header rows for one page. Sorting happens first; tokens are issued after it, so they are stable for this list."""
        self._order(job)
        offset = max(0, int(offset))
        with job.lock:
            chunk = [(ref.rid, ref) for ref in job.refs[offset:offset + limit]]
        groups: dict[tuple[str, str, int], list[int]] = {}
        for index, ref in chunk:
            groups.setdefault((ref.account_id, ref.folder, ref.validity), []).append(ref.uid)
        headers: dict[tuple[str, str, int], bytes] = {}
        for (account_id, folder, validity), uids in groups.items():
            try:
                account = self._load(account_id)
                with self.bridge.session(self._target(account)) as s:
                    s.set_timeout(60)
                    if s.select_folder(folder, True) != validity:
                        continue
                    for uid, raw in s.header_blocks(uids):
                        headers[(account_id, folder, uid)] = raw
            except BridgeError:
                continue
        rows = []
        for index, ref in chunk:
            raw = headers.get((ref.account_id, ref.folder, ref.uid))
            if raw is None:
                continue
            msg = parse_headers(raw)
            name, address = (_addresses(msg, "From") or [("", "")])[0]
            rows.append({
                "token": self.token(job, index),
                "account_id": ref.account_id,
                "account": job.mailboxes[ref.account_id].label,
                "from_name": clean(name, 200), "from_address": clean(address, 320),
                "subject": clean(msg.get("Subject"), 300) or "(no subject)",
                "date": received_at_of(raw) or ref.when or None,
                "folder": nice_folder(ref.folder),
                "has_files": likely_has_files(msg),
            })
        return rows

    def original(self, user_id: str, token: str) -> tuple[bytes, Ref]:
        job, ref = self.resolve(user_id, token)
        account = self._load(ref.account_id)
        with self.bridge.session(self._target(account)) as s:
            s.set_timeout(60)
            if s.select_folder(ref.folder, True) != ref.validity:
                raise BridgeError("not_found", "The mailbox was reset on the server. Search again.")
            return s.original(ref.uid), ref

    def headers_of(self, user_id: str, token: str) -> tuple[bytes, Ref]:
        job, ref = self.resolve(user_id, token)
        account = self._load(ref.account_id)
        with self.bridge.session(self._target(account)) as s:
            s.set_timeout(60)
            if s.select_folder(ref.folder, True) != ref.validity:
                raise BridgeError("not_found", "The mailbox was reset on the server. Search again.")
            for _uid, raw in s.header_blocks([ref.uid]):
                return raw, ref
        raise BridgeError("not_found", "This email can no longer be found in the mailbox.")
