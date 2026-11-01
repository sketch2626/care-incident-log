"""The resident's own email (M15d): SMTP to Gmail or Yahoo, and the one-time tickets a skill needs to use it.

Nothing goes out without a ticket. The core mints one (M15c: send_gate.py and SkillContext.send_now), one per try, only
after the resident's own "send it" and a five-second Undo. The only send without a ticket is send_test: fixed words, to the
resident's own address. TLS runs from the first byte and there's no plain-text path. Stdlib only.
"""

import email.policy
import email.utils
import hashlib
import html
import json
import re
import secrets
import smtplib
import socket
import ssl
import threading
import time
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

PROVIDERS = {"gmail": ("smtp.gmail.com", 465), "yahoo": ("smtp.mail.yahoo.com", 465)}
ACCOUNT_SECRET = "mail_account"

# One send must end well inside skills_core.GUARD_SLOW_TIMEOUT (18 s). A skill call past that limit is reported as
# failed but its daemon thread keeps running, so a slower send could go out after the resident was told it hadn't. smtplib's
# timeout is per network step, so it can't bound a whole send: SEND_DEADLINE does that, by cutting the connection.
SMTP_TIMEOUT = 4.0  # each of the three steps of connecting: the connection, TLS, the server's hello
SEND_DEADLINE = 12.0  # the whole send, start to finish (3 x SMTP_TIMEOUT, so connecting can't outlive it)
TICKET_TTL = 120

ADDRESS_MAX = 254
SUBJECT_MAX = 200
BODY_MAX = 100_000
PICTURES_MAX = 4  # front, inside, both side by side
PICTURES_BYTES_MAX = 15_000_000
PASSWORD_MIN = 8
PASSWORD_MAX = 64

TEST_SUBJECT = "Test email"
TEST_BODY = "This is a test. Your email is working."

MESSAGES = {
    "no_email": "Your email isn't set up yet, and a helper can set it up in My info.",
    "wrong_password": "Your email account didn't accept the password, and a helper can put in a new one in My info.",
    "offline": "The email couldn't get through because the internet isn't working right now.",
    "refused": "Your email account wouldn't send that message.",
    "no_ticket": "That message wasn't sent because you hadn't said to send it.",
    "bad_message": "Something is wrong with that message, so it wasn't sent.",
    "unsure": "I'm not sure that went.",  # M15c: it started going and we never heard back, so nobody retries by themselves
}

_ATOM = r"[A-Za-z0-9_%+-]+"
_ADDRESS_RE = re.compile(rf"{_ATOM}(?:\.{_ATOM})*@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
_SUBJECT_BREAKS_RE = re.compile("[\x00-\x1f\x7f\x85  ]")  # every character Python treats as a line break, too
_PICTURE_KINDS = ((b"\x89PNG\r\n\x1a\n", ("png", "png")), (b"\xff\xd8\xff", ("jpeg", "jpg")))
_POLICY = email.policy.default.clone(cte_type="7bit")  # long lines and accents are safe on any mail server


def address_mark(address):  # M18
    """A short mark for mail.log: two sends to one address match, and the address can't be read back out of it."""
    return hashlib.sha256(("mail.log " + str(address).strip().lower()).encode("utf-8")).hexdigest()[:10]


def _address_ok(address):
    return isinstance(address, str) and len(address) <= ADDRESS_MAX and _ADDRESS_RE.fullmatch(address) is not None


def _clean_password(password):
    """The password without its spaces (Google shows it in groups of four), or None when it can't be one."""
    if not isinstance(password, str):
        return None
    cleaned = "".join(password.split())
    usable = PASSWORD_MIN <= len(cleaned) <= PASSWORD_MAX and all(33 <= ord(ch) <= 126 for ch in cleaned)
    return cleaned if usable else None


def _plain(value):
    """value as an exact str or bytes, else None. A subclass could read differently the second time it's asked."""
    if type(value) in (str, bytes):
        return value
    return bytes(value) if type(value) is bytearray else None


def _freeze(to, subject, body, pictures):
    """Plain copies, made once, so what the ticket checks is what goes out. Anything odd becomes None and fails
    the checks in _message_ok."""
    if type(pictures) not in (list, tuple):
        pictures = (None,)
    frozen = tuple((_plain(p.get("name")), _plain(p.get("data"))) if type(p) is dict else (None, None)
                   for p in pictures)
    return _plain(to), _plain(subject), _plain(body), frozen


def _digest(to, subject, body, pictures):
    """sha256 of the exact content, each piece prefixed with its type and length. to is compared lower-case."""
    digest = hashlib.sha256()
    for piece in (to.lower() if to else to, subject, body, *(part for picture in pictures for part in picture)):
        raw = piece.encode("utf-8", "surrogatepass") if isinstance(piece, str) else piece or b""
        digest.update(b"%s %d:" % (type(piece).__name__.encode("ascii"), len(raw)))
        digest.update(raw)
    return digest.hexdigest()


def _token_key(ticket):
    return hashlib.sha256(ticket.encode("utf-8", "surrogatepass")).hexdigest()


def _picture_kind(data):
    """(mime subtype, file ending) from the file's first bytes, or None when it isn't a PNG or JPEG."""
    for magic, kind in _PICTURE_KINDS:
        if isinstance(data, bytes) and data.startswith(magic):
            return kind
    return None


def _filename(name, number, ending):
    """A safe file name: letters, digits and dashes from the name, and the ending the picture's content shows."""
    stem = re.sub(r"[^A-Za-z0-9]+", "-", name.rsplit(".", 1)[0]).strip("-")[:40]
    return f"{stem or 'picture-' + str(number)}.{ending}"


def _message_ok(to, subject, body, pictures):
    if not (_address_ok(to) and isinstance(subject, str) and isinstance(body, str)):
        return False
    if len(subject) > SUBJECT_MAX or len(body) > BODY_MAX or _SUBJECT_BREAKS_RE.search(subject):
        return False
    if len(pictures) > PICTURES_MAX:
        return False
    if not all(isinstance(name, str) and _picture_kind(data) for name, data in pictures):
        return False
    return sum(len(data) for _, data in pictures) <= PICTURES_BYTES_MAX


def _build(sender, to, subject, body, pictures, when):
    """The message: the resident's words as plain text, and with pictures also a page showing them in the message itself.
    No tag or footer: it's the resident's message. Date in GMT, and no laptop name in the Message-ID."""
    subject.encode("utf-8")  # text that can't be sent stops here, before any connection
    body.encode("utf-8")
    domain = sender.rsplit("@", 1)[1]
    message = EmailMessage(policy=_POLICY)
    message["From"] = sender
    message["To"] = to
    message["Subject"] = subject
    message["Date"] = email.utils.formatdate(when, usegmt=True)
    message["Message-ID"] = email.utils.make_msgid(domain=domain)
    message.set_content(body)
    if pictures:
        cids = [email.utils.make_msgid(domain=domain) for _ in pictures]
        shown = "".join(f'<div><img src="cid:{cid[1:-1]}" style="max-width:100%"></div>' for cid in cids)
        message.add_alternative(f'<html><body><div style="white-space:pre-wrap">{html.escape(body)}</div>{shown}'
                                "</body></html>", subtype="html")
        page = message.get_payload()[1]
        for number, ((name, data), cid) in enumerate(zip(pictures, cids), 1):
            subtype, ending = _picture_kind(data)
            page.add_related(data, "image", subtype, cid=cid, disposition="inline",
                             filename=_filename(name, number, ending))
    return message


def _cut_off(smtp):
    """Ends a send that has run past SEND_DEADLINE. It's the raw socket's shutdown on purpose: SSLSocket.shutdown drops
    TLS first, and the sending thread could then write in plain text."""
    try:
        socket.socket.shutdown(smtp.sock, socket.SHUT_RDWR)
    except (OSError, AttributeError, TypeError):
        pass


class Mailer:
    """The resident's one email account, in the secret store. servers and tls_context are for tests, which pass a
    loopback server and a context trusting a test certificate, so they use real TLS too."""

    def __init__(self, secrets, log_path, servers=PROVIDERS, tls_context=None, clock=time.time):
        self._secrets = secrets
        self._log_path = Path(log_path)
        self._servers = servers
        self._tls_context = tls_context
        self._clock = clock
        self._lock = threading.Lock()
        self._log_lock = threading.Lock()
        self._tickets = {}  # sha256 of the token -> (skill, content digest, expiry)

    # ----- the account -----

    def connect_account(self, address, provider, password):
        """Saves the resident's account. Plain ValueError on bad input; its words never hold the password."""
        address = address.strip() if isinstance(address, str) else address
        if not _address_ok(address):
            raise ValueError("That email address doesn't look right.")
        if not isinstance(provider, str) or provider not in self._servers:
            raise ValueError("Please choose Gmail or Yahoo.")
        password = _clean_password(password)
        if password is None:
            raise ValueError("That password doesn't look right. It's the app password your email account gave you.")
        account = {"address": address, "provider": provider, "password": password}
        try:
            self._secrets.put(ACCOUNT_SECRET, json.dumps(account))
        except Exception:  # noqa: BLE001 (whatever the store says, the resident hears this and nothing else)
            raise ValueError("This computer couldn't keep your email password safe, so it wasn't saved.") from None

    def _account(self):
        """The saved account, or None when there's none or it can't be read."""
        try:
            account = json.loads(self._secrets.get(ACCOUNT_SECRET) or "")
            usable = (isinstance(account, dict) and _address_ok(account.get("address"))
                      and account.get("provider") in self._servers and _clean_password(account.get("password")))
        except Exception:  # noqa: BLE001 (unreadable or corrupt counts as not connected)
            return None
        return account if usable else None

    def status(self):
        """For the page: never the password."""
        try:
            available = bool(self._secrets.available())
        except Exception:  # noqa: BLE001
            available = False
        account = self._account() or {}
        return {"available": available, "connected": bool(account), "address": account.get("address", ""),
                "provider": account.get("provider", "")}

    def disconnect(self):
        try:
            self._secrets.delete(ACCOUNT_SECRET)
        except Exception:  # noqa: BLE001 (status then still says connected, which is the truth)
            pass

    # ----- tickets -----

    def mint_ticket(self, skill, to, subject, body, pictures=(), ttl=TICKET_TTL):
        """Only the core calls this (SkillContext.send_now), after the resident's own "send it" and the count. The ticket
        is good for one try, by this skill, with exactly this content."""
        digest = _digest(*_freeze(to, subject, body, pictures))
        token = secrets.token_urlsafe(32)
        now = self._clock()
        with self._lock:
            for key in [key for key, held in self._tickets.items() if held[2] <= now]:
                del self._tickets[key]
            self._tickets[_token_key(token)] = (skill, digest, now + ttl)
        return token

    def _redeem(self, skill, ticket, content):
        """True when the ticket fits this skill and this content. A known ticket is used up whatever the answer."""
        if type(ticket) is not str:
            return False
        with self._lock:
            held = self._tickets.pop(_token_key(ticket), None)
        if held is None:
            return False
        return held[0] == skill and held[1] == _digest(*content) and self._clock() < held[2]

    # ----- sending -----

    def send_for_skill(self, skill, ticket, to, subject, body, pictures=()):
        """Sends with a ticket from mint_ticket; a retry needs a new one. {"ok": True} or {"ok": False, "code", "message"}.
        Never raises."""
        try:
            content = _freeze(to, subject, body, pictures)
            if not self._redeem(skill, ticket, content):
                return self._done(skill, content[0], "no_ticket")
            return self._deliver(skill, *content)
        except Exception:  # noqa: BLE001 (never raises, and no error text leaves here)
            return self._done(skill, None, "refused")

    def send_test(self):
        """Shows the account works: fixed words, only to the account's own address. The one send with no ticket."""
        try:
            account = self._account()
            if account is None:
                return self._done("test", None, "no_email")
            return self._deliver("test", account["address"], TEST_SUBJECT, TEST_BODY, ())
        except Exception:  # noqa: BLE001 (never raises, and no error text leaves here)
            return self._done("test", None, "refused")

    def _deliver(self, skill, to, subject, body, pictures):
        """Checks and sends one message. Private: every public way in has a ticket, or is send_test."""
        if not _message_ok(to, subject, body, pictures):
            return self._done(skill, to, "bad_message")
        account = self._account()
        if account is None:
            return self._done(skill, to, "no_email")
        started = time.monotonic()  # building a big message takes a second or so, and SEND_DEADLINE counts that too
        try:
            message = _build(account["address"], to, subject, body, pictures, self._clock())
        except Exception:  # noqa: BLE001 (text that can't be encoded, say)
            return self._done(skill, to, "bad_message")
        return self._done(skill, to, self._hand_over(account, message, to, started))

    def _hand_over(self, account, message, to, started):
        """None when the server took the message, else the code. The order matters: SMTPException and ssl.SSLError are
        both OSErrors. The exceptions' text is never kept. M15c: once the message has started going, only a clear no from
        the server is refused. Any other failure is unsure, because it may have arrived."""
        going = []  # M15c: not empty once the message has started up to the server
        try:
            self._smtp_send(account, message, to, started, going)
        except smtplib.SMTPAuthenticationError:
            return "wrong_password"
        except (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected):
            return "unsure" if going else "offline"
        except (smtplib.SMTPResponseException, smtplib.SMTPRecipientsRefused):  # M15c: a clear no from the server
            return "refused"
        except smtplib.SMTPException:
            return "unsure" if going else "refused"
        except OSError:  # sockets, timeouts, gaierror and ssl.SSLError: a wifi sign-in page fails the certificate
            return "unsure" if going else "offline"
        except Exception:  # noqa: BLE001
            return "unsure" if going else "refused"
        return None

    def _smtp_send(self, account, message, to, started, going):
        """TLS from the first byte, and local_hostname so the laptop's name isn't sent. No `with` block: its exit raises
        on a bad reply to QUIT, which would report a delivered message as failed, and a retry would send it twice."""
        host, port = self._servers[account["provider"]]
        context = self._tls_context or ssl.create_default_context()
        smtp = smtplib.SMTP_SSL(host, port, timeout=SMTP_TIMEOUT, context=context, local_hostname="localhost")
        watchdog = threading.Timer(max(0.0, started + SEND_DEADLINE - time.monotonic()), _cut_off, (smtp,))
        watchdog.daemon = True
        watchdog.start()
        try:
            smtp.login(account["address"], account["password"])
            # Every step from here gets what's left of the deadline: a slow upload or a slow "OK" isn't a failure, and a
            # write stuck on a full connection ends in time even if the watchdog can't wake it.
            smtp.sock.settimeout(max(0.1, started + SEND_DEADLINE - time.monotonic()))
            going.append(True)  # M15c: from here on a failure can't say whether it arrived
            smtp.send_message(message, from_addr=account["address"], to_addrs=[to])
            try:
                smtp.quit()
            except Exception:  # noqa: BLE001 (the server already has the message)
                pass
        finally:
            watchdog.cancel()
            smtp.close()

    # ----- the log -----

    def _done(self, skill, to, code=None):
        """Writes the one log line for an attempt and gives back its result."""
        self._log(skill, to, code)
        if code is None:
            return {"ok": True}
        return {"ok": False, "code": code, "message": MESSAGES[code]}

    def _log(self, skill, to, code):
        """One JSON line per attempt: never the address (M18: only its mark), subject, body, pictures or password. A
        failed write stops nothing."""
        try:
            line = json.dumps({"when": datetime.fromtimestamp(self._clock()).isoformat(timespec="seconds"),
                               "skill": str(skill)[:64], "to": address_mark(to) if _address_ok(to) else "",
                               "ok": code is None, "code": code or ""})
            with self._log_lock:
                self._log_path.parent.mkdir(parents=True, exist_ok=True)
                with self._log_path.open("a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
        except Exception:  # noqa: BLE001
            pass

    def hide_old_addresses(self):  # M18
        """Lines from before M18 held the address: they get its mark, and a torn line that shows one goes. Never raises."""
        temp = self._log_path.with_name(self._log_path.name + ".tmp")
        try:
            with self._log_lock:
                if not self._log_path.is_file():
                    return
                before = self._log_path.read_text(encoding="utf-8")
                if "@" not in before:
                    return
                kept = []
                for line in before.splitlines():
                    try:
                        row = json.loads(line)
                    except ValueError:
                        row = None
                    if isinstance(row, dict) and "@" in str(row.get("to")):
                        line = json.dumps(dict(row, to=address_mark(row["to"])))
                    if "@" not in line:
                        kept.append(line)
                temp.write_text("".join(line + "\n" for line in kept), encoding="utf-8")
                temp.replace(self._log_path)
        except Exception:  # noqa: BLE001
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass

    def scrub_log(self, addresses=None):  # M15c
        """Blanks "to" on the lines with these addresses, in any case, or on every line with None. The swap is atomic, so
        a crash leaves the old log or the new one. Never raises, and no log file is fine."""
        temp = self._log_path.with_name(self._log_path.name + ".tmp")
        try:
            wanted = None if addresses is None else {str(address).strip().lower() for address in addresses}
            marks = None if wanted is None else {address_mark(address) for address in wanted}  # M18
            with self._log_lock:
                if not self._log_path.is_file():
                    return
                kept = []
                for line in self._log_path.read_text(encoding="utf-8").splitlines():
                    try:
                        row = json.loads(line)
                    except ValueError:
                        row = None
                    if not isinstance(row, dict):  # a torn line: keep it only if it can't hold the address
                        if wanted is not None and not any(address in line.lower() for address in wanted):
                            kept.append(line)
                        continue
                    if row.get("to") and (wanted is None or str(row["to"]).lower() in wanted or row["to"] in marks):
                        row["to"] = ""
                        line = json.dumps(row)
                    kept.append(line)
                temp.write_text("".join(line + "\n" for line in kept), encoding="utf-8")
                temp.replace(self._log_path)
        except Exception:  # noqa: BLE001
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
