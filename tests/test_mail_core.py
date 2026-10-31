"""M15d: the resident's email. A fake SMTP server on loopback speaks real TLS; no real mail, accounts or keys."""
from tests import helpers  # first: scratch folders and an in-memory secret backend

import base64
import email
import email.policy
import itertools
import json
import socket
import ssl
import threading
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

import mail_core
import secret_store
import server
import skills_core
from tests import test_skills_core as tsc

# A throwaway loopback test certificate and key (CN 127.0.0.1, subjectAltName 127.0.0.1, valid 100 years).
# It protects nothing and is used only by the fake server below.
CERT_PEM = """-----BEGIN CERTIFICATE-----
MIIDHDCCAgSgAwIBAgIUQc8YZ2/fNRHm6tT3mPio6R0snXMwDQYJKoZIhvcNAQEL
BQAwFDESMBAGA1UEAwwJMTI3LjAuMC4xMCAXDTI2MTAzMTE4NTkyOFoYDzIxMjYx
MDA3MTg1OTI4WjAUMRIwEAYDVQQDDAkxMjcuMC4wLjEwggEiMA0GCSqGSIb3DQEB
AQUAA4IBDwAwggEKAoIBAQDV64OZxKjC18HUEpfiyAM7WOSW/8CbUYHLsKqMPGHI
40dIlnpsNDhFo9J3wBv1kxzZFk2QLAHqpQ6URZsA4+CgN1gxQwNVn0SiKGDFcytR
iuiWzTeBH5VNv8msbE71CmFI6H5t4vWFhve/JWg1sc2xSREX+2A/scZCfuLcvYRG
DrSBJtajBb1o3vD+mldgHoA64dAvdMtvy1uVlQSlBEIXG9KUTl+7eyXEwVpFvplp
D75bidFx6PB4x/CMDGUbXPRp9rSSq6NLjga1itvTVMQsC6v1F2tI4OymnPi+JJKN
EP3wrVrkjp4G6rofj6BMikNYhFU3b3t0gXaXcZVqpq3TAgMBAAGjZDBiMB0GA1Ud
DgQWBBTeT9Umub10wtkxj7bEBWUhInATfzAfBgNVHSMEGDAWgBTeT9Umub10wtkx
j7bEBWUhInATfzAPBgNVHRMBAf8EBTADAQH/MA8GA1UdEQQIMAaHBH8AAAEwDQYJ
KoZIhvcNAQELBQADggEBAG2Y6Yf1lG/CITQJGBrTbQPFXyW+j/5NNJ6mTSzAHp7k
sJpN1lw0JtmP22+5dK8sHM5w0aqgvyog3xqLXyLe1VG+0zZnDYIcNBB6Tst118fs
OgIbnvci7eJR7ZeGO+nj6AzugcW/Liyx4rkSekIwPDpqaCW7sYhJrJWuX1/idFO3
huQjOdTVO4MD5+eNBEUNHxjO455a36kP86ql91n5O8vua/AYbwLwvsLn/15kjUlf
pZ0wHik934id7jaIDmsxXN3i29kueZ7AUmUw8mE8l03mHjxef4kTChLmBnXZTB7v
HbKMIkY/40Tu1B2tKo0xwMW4dLmCRYg+r+ReEHRN24k=
-----END CERTIFICATE-----
"""
KEY_PEM = """-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQDV64OZxKjC18HU
EpfiyAM7WOSW/8CbUYHLsKqMPGHI40dIlnpsNDhFo9J3wBv1kxzZFk2QLAHqpQ6U
RZsA4+CgN1gxQwNVn0SiKGDFcytRiuiWzTeBH5VNv8msbE71CmFI6H5t4vWFhve/
JWg1sc2xSREX+2A/scZCfuLcvYRGDrSBJtajBb1o3vD+mldgHoA64dAvdMtvy1uV
lQSlBEIXG9KUTl+7eyXEwVpFvplpD75bidFx6PB4x/CMDGUbXPRp9rSSq6NLjga1
itvTVMQsC6v1F2tI4OymnPi+JJKNEP3wrVrkjp4G6rofj6BMikNYhFU3b3t0gXaX
cZVqpq3TAgMBAAECggEABkAO2h/OWdRe/pjFJPmjaoj9iNHpKUCXkmwo14HDePtM
WmPB05vaUbfoeYTnQY9uUNjKJF5nd0PM/2ph4y6aog5r6RM5q4yZ6e5UbCsiHAxQ
dmjW6H1pPy/NhIMCSD4+Oxib6mRZYxuJ7TpPvKiOHNId3z2s1r+VeNznOPw1O1dl
+YN03QtnourJP/lexL2voigzLHY/WX9ZYvcZyfO9CXumwYoYcxpE7lN6J0f+DTAn
gEkijs6nvm0juVHP4fAM5Zwsl2/OXtENxF56oVWH4E6RlBO8IfXNx5sGvnU62Gc/
kG22B2mRWGk7NElKdC4hZy5k1kHA6cGxuttJJmIpfQKBgQDrzD7PovWnm15qOCCt
RpFHjuhUzbPdyKw9wePPLjKIMGeOCoCB2gBfhF1M35J+f57xY6MMPL9ev7duk0c6
cmhpWwZ3xmRlCHoC+cIFKVq67jsWZWMJnp1x2DAP3m3E5BKzCCNG5oAPXbkuFy2i
tLkyQUlog3TRshLTJEANNM5pzQKBgQDoP2vumeKsE0cmWQgJlh14gkjZ+Gn8dcMg
/leOUYPlXcyt6FKgHEDE9/xrr18+KRLETwGvlFLI0Nrr1wIDuM6NSZNcVa8U6YOR
/klF6+7HG3w9PNFMSu03MSlTXM9LpefnQtWkhTrdRnklgpQ0bvCbcZbbxU12mSa2
oM2SxZFWHwKBgQDEqNUeEbi2cFOfXW6LddaHCv5kdCd2av6Uh1g7nDkS8uP7SHED
W9GB2ICEM9cXX9MtWj9LXoLxQA55z6XRbkf8zqknTjS/OwGf57RU37fHPhfTxv2B
sWN45qi3I3kDhIDABqJ9aJMXvcBLW5N5JydqbZ8O5syQc+dVZ99v5EHfZQKBgDjU
1C+F3o7nBMEghjP6VOnZT8Ru4liR5JbdRkWgMttcsapYsGdXoo3QdSdQuci3Ok1p
W+tAK2XSnc+aRHbusTSnrXSpzvcaEUUXaYy/qCV211cQ29KEfznDQO6SRnOnfHD9
zNO+emINTbXdFzEheKVBDX5n8IW2AmAsR0HEMMVXAoGBAIMTPdmSDNuGLyHEXxzq
ukDaTzuKmS+1tEUpg5PIapciWq5BMHnf5wXOJDs/8Shd/5MP1lZ3RJVrad2hzX2c
yApdnCgoxr2F9QpfC6JQDwLW/6Y5bl95nNB4XTmg9HBGP4EfFMFbkx5ebQpfCh9t
ipDjbFyX1w3+oLfsX98JCrnc
-----END PRIVATE KEY-----
"""

CERT_DIR = helpers.TMP / "loopback-cert"
CERT_DIR.mkdir(exist_ok=True)
CERT, KEY = CERT_DIR / "cert.pem", CERT_DIR / "key.pem"
CERT.write_text(CERT_PEM, encoding="ascii")
KEY.write_text(KEY_PEM, encoding="ascii")

PNG = b"\x89PNG\r\n\x1a\n" + b"PICMARK-png-" * 20
JPG = b"\xff\xd8\xff\xe0" + b"PICMARK-jpg-" * 20
PASSWORD = "abcd efgh ijkl mnop"
CLEAN = "abcdefghijklmnop"
ORIG_DEADLINE, ORIG_TIMEOUT = mail_core.SEND_DEADLINE, mail_core.SMTP_TIMEOUT
COUNTER = itertools.count()


class FakeSMTP:
    """Real TLS from the first byte. Modes: ok, badauth (535), reject (550 on the recipient), stall_greeting,
    stall_auth, stall_final (never answers the end of the message), stall_body (stops reading the message)."""

    def __init__(self, mode="ok", tls=True):
        self.mode, self.tls = mode, tls
        self.ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.ctx.load_cert_chain(str(CERT), str(KEY))
        self.sock = socket.create_server(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.messages, self.ehlo, self.auth, self.rcpt = [], [], [], []
        threading.Thread(target=self.loop, daemon=True).start()

    def close(self):
        self.sock.close()

    def loop(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self.one, args=(conn,), daemon=True).start()

    def one(self, conn):
        try:
            sock = self.ctx.wrap_socket(conn, server_side=True) if self.tls else conn
            if self.mode == "stall_greeting":
                time.sleep(6)
                return
            sock.sendall(b"220 hi\r\n")
            reader = sock.makefile("rb")
            while True:
                line = reader.readline()
                if not line:
                    return
                word = line.split()[0].upper() if line.split() else b""
                if word == b"EHLO":
                    self.ehlo.append(line.split()[1].decode())
                    sock.sendall(b"250-fake\r\n250 AUTH PLAIN\r\n")
                elif word == b"AUTH":
                    self.auth.append(base64.b64decode(line.split()[2]).decode())
                    if self.mode == "stall_auth":
                        time.sleep(6)
                        return
                    sock.sendall(b"535 no\r\n" if self.mode == "badauth" else b"235 ok\r\n")
                elif word == b"MAIL":
                    sock.sendall(b"250 ok\r\n")
                elif word == b"RCPT":
                    self.rcpt.append(line.decode())
                    sock.sendall(b"550 secret smtp words\r\n" if self.mode == "reject" else b"250 ok\r\n")
                elif word == b"DATA":
                    sock.sendall(b"354 go\r\n")
                    if self.mode == "stall_body":
                        time.sleep(6)
                        return
                    data = []
                    while True:
                        row = reader.readline()
                        if row == b".\r\n" or not row:
                            break
                        data.append(row[1:] if row.startswith(b"..") else row)
                    self.messages.append(b"".join(data))
                    if self.mode == "stall_final":
                        time.sleep(6)
                        return
                    sock.sendall(b"250 taken\r\n")
                elif word == b"QUIT":
                    sock.sendall(b"221 bye\r\n")
                    return
                else:
                    sock.sendall(b"500 what\r\n")
        except OSError:
            pass
        finally:
            conn.close()


def dead_port():
    with closing(socket.socket()) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def parse(raw):
    return email.message_from_bytes(raw, policy=email.policy.default)


class MailTestCase(unittest.TestCase):

    def setUp(self):
        helpers.reset_db()
        self.tmp = Path(__import__("tempfile").mkdtemp(dir=helpers.TMP))
        self.log_path = None

    def fake(self, mode="ok", tls=True):
        fake = FakeSMTP(mode, tls)
        self.addCleanup(fake.close)
        return fake

    def mailer(self, fake=None, connect=True, trust=True, clock=time.time, port=None):
        n = next(COUNTER)
        store = secret_store.SecretStore(self.tmp / f"data{n}")
        port = port or (fake.port if fake else dead_port())
        servers = {"gmail": ("127.0.0.1", port), "yahoo": ("127.0.0.1", port)}
        self.log_path = self.tmp / f"log{n}" / "mail.log"
        context = ssl.create_default_context(cafile=str(CERT)) if trust else None
        made = mail_core.Mailer(store, self.log_path, servers=servers, tls_context=context, clock=clock)
        if connect:
            made.connect_account(" me@example.com ", "gmail", PASSWORD)
        return made

    def send(self, made, skill="s", to="Pal@Example.org", subject="Hi there", body="Hello", pictures=()):
        ticket = made.mint_ticket(skill, to, subject, body, pictures)
        return made.send_for_skill(skill, ticket, to, subject, body, pictures)

    def log_entries(self):
        return [json.loads(x) for x in self.log_path.read_text(encoding="utf-8").splitlines()]


class SendTest(MailTestCase):

    def test_send_with_pictures(self):
        fake = self.fake()
        made = self.mailer(fake)
        pics = [{"name": "..\\..\\front card.exe.png", "data": PNG}, {"name": "", "data": JPG},
                {"name": "third.PNG", "data": PNG}]
        out = self.send(made, subject="Happy birthday — Ruth", body="a <b> & c\nsecond line", pictures=pics)
        self.assertEqual(out, {"ok": True})
        raw = fake.messages[-1]
        msg = parse(raw)
        self.assertEqual((msg["To"], msg["From"], msg["Subject"]), ("Pal@Example.org", "me@example.com",
                                                                    "Happy birthday — Ruth"))
        self.assertEqual(msg.get_body(("plain",)).get_content().strip().replace("\r\n", "\n"),
                         "a <b> & c\nsecond line")
        page = msg.get_body(("html",)).get_content()
        self.assertIn("a &lt;b&gt; &amp; c", page)
        self.assertNotIn("a <b> & c", page)
        images = [p for p in msg.walk() if p.get_content_maintype() == "image"]
        self.assertEqual(len(images), 3)
        self.assertEqual([p.get_content() for p in images], [PNG, JPG, PNG])
        self.assertTrue(all(p.get_content_disposition() == "inline" for p in images))
        self.assertEqual([p.get_filename() for p in images], ["front-card-exe.png", "picture-2.jpg", "third.png"])
        for part in images:
            self.assertIn(f'src="cid:{part["Content-ID"][1:-1]}"', page)
        self.assertEqual(fake.ehlo and set(fake.ehlo), {"localhost"})
        host = socket.gethostname()
        if host.lower() != "localhost":
            self.assertNotIn(host.lower().encode(), raw.lower())
        self.assertTrue(msg["Message-ID"].endswith("@example.com>"), msg["Message-ID"])
        self.assertNotIn(b"Mary", raw)
        self.assertEqual(fake.auth[-1], f"\0me@example.com\0{CLEAN}")

    def test_no_account(self):
        made = self.mailer(self.fake(), connect=False)
        self.assertEqual(self.send(made)["code"], "no_email")
        self.assertEqual(made.send_test()["code"], "no_email")


class FailureTest(MailTestCase):

    def test_wrong_password(self):
        fake = self.fake("badauth")
        out = self.send(self.mailer(fake))
        self.assertEqual(out["code"], "wrong_password")
        self.assertEqual(fake.messages, [])

    def test_offline_cases(self):
        self.assertEqual(self.send(self.mailer(None))["code"], "offline")  # nothing listening
        self.assertEqual(self.send(self.mailer(self.fake(tls=False)))["code"], "offline")  # TLS fails

    def test_certificate_check_is_on(self):
        fake = self.fake()
        out = self.send(self.mailer(fake, trust=False))  # a default context doesn't trust the test certificate
        self.assertEqual(out["code"], "offline")
        self.assertEqual((fake.messages, fake.auth, fake.ehlo), ([], [], []))

    def test_recipient_refused(self):
        fake = self.fake("reject")
        out = self.send(self.mailer(fake))
        self.assertEqual(out["code"], "refused")
        self.assertNotIn("secret", json.dumps(out))
        self.assertEqual(fake.messages, [])

    def test_deadline_is_inside_the_guard(self):
        self.assertLess(ORIG_DEADLINE, skills_core.GUARD_SLOW_TIMEOUT)
        self.assertLess(mail_core.SEND_DEADLINE, skills_core.GUARD_SLOW_TIMEOUT)

    def _stall(self, mode, pictures=()):
        with mock.patch.object(mail_core, "SMTP_TIMEOUT", 0.5), mock.patch.object(mail_core, "SEND_DEADLINE", 1.2):
            made = self.mailer(self.fake(mode))
            started = time.monotonic()
            out = self.send(made, pictures=pictures)
            took = time.monotonic() - started
        self.assertEqual(out.get("code"), "offline", out)
        self.assertLess(took, 1.2 + 2.0, took)

    def test_stalled_reads(self):
        for mode in ("stall_greeting", "stall_auth", "stall_final"):
            self._stall(mode)

    def test_stalled_write(self):
        self._stall("stall_body", [{"name": "x", "data": PNG + b"z" * 14_000_000}])


class TicketTest(MailTestCase):
    ARGS = ("Pal@Example.org", "Hi", "Hello")

    def setUp(self):
        super().setUp()
        self.fake_ = self.fake()
        self.made = self.mailer(self.fake_)

    def nothing_sent(self):
        self.assertEqual((self.fake_.messages, self.fake_.ehlo), ([], []))

    def test_no_ticket_cases(self):
        made = self.made
        valid_shape = "A" * 43
        for ticket in (None, "", "made-up", valid_shape, 5, b"x", ["x"], "\ud800"):
            self.assertEqual(made.send_for_skill("s", ticket, *self.ARGS)["code"], "no_ticket", repr(ticket))
        self.nothing_sent()

    def test_reuse_is_refused(self):
        ticket = self.made.mint_ticket("s", *self.ARGS)
        self.assertEqual(self.made.send_for_skill("s", ticket, *self.ARGS), {"ok": True})
        self.assertEqual(self.made.send_for_skill("s", ticket, *self.ARGS)["code"], "no_ticket")
        self.assertEqual(len(self.fake_.messages), 1)

    def test_a_failed_send_uses_it_up(self):
        fake = self.fake("badauth")
        made = self.mailer(fake)
        ticket = made.mint_ticket("s", *self.ARGS)
        self.assertEqual(made.send_for_skill("s", ticket, *self.ARGS)["code"], "wrong_password")
        self.assertEqual(made.send_for_skill("s", ticket, *self.ARGS)["code"], "no_ticket")
        self.assertEqual(len(fake.auth), 1)

    def test_expired(self):
        now = [1_000_000.0]
        fake = self.fake()
        made = self.mailer(fake, clock=lambda: now[0])
        ticket = made.mint_ticket("s", *self.ARGS)
        now[0] += mail_core.TICKET_TTL + 1
        self.assertEqual(made.send_for_skill("s", ticket, *self.ARGS)["code"], "no_ticket")
        self.assertEqual(fake.messages, [])
        ticket = made.mint_ticket("s", *self.ARGS)  # still good a moment before it runs out
        now[0] += mail_core.TICKET_TTL - 1
        self.assertEqual(made.send_for_skill("s", ticket, *self.ARGS), {"ok": True})

    def test_mismatches_are_refused_and_use_the_ticket_up(self):
        pic = [{"name": "a", "data": PNG}]
        base = ("s", self.ARGS, pic)
        cases = {
            "skill": ("other", self.ARGS, pic),
            "to": ("s", ("Other@Example.org", "Hi", "Hello"), pic),
            "subject": ("s", ("Pal@Example.org", "Hi!", "Hello"), pic),
            "body": ("s", ("Pal@Example.org", "Hi", "Hello!"), pic),
            "picture data": ("s", self.ARGS, [{"name": "a", "data": JPG}]),
            "picture name": ("s", self.ARGS, [{"name": "b", "data": PNG}]),
            "picture added": ("s", self.ARGS, pic + pic),
            "picture dropped": ("s", self.ARGS, ()),
        }
        for label, (skill, args, pictures) in cases.items():
            ticket = self.made.mint_ticket("s", *self.ARGS, pic)
            self.assertEqual(self.made.send_for_skill(skill, ticket, *args, pictures)["code"], "no_ticket", label)
            self.assertEqual(self.made.send_for_skill(*base[:1], ticket, *self.ARGS, pic)["code"], "no_ticket",
                             label + " burned")
        self.nothing_sent()

    def test_a_str_subclass_that_lies_gives_no_ticket(self):
        class Liar(str):
            reads = 0

            def encode(self, *a, **k):
                Liar.reads += 1
                return super().encode(*a, **k) if Liar.reads == 1 else b"something else"

            def lower(self):
                Liar.reads += 1
                return super().lower() if Liar.reads == 1 else "other@example.org"

        token = self.made.mint_ticket("s", *self.ARGS)
        self.assertEqual(self.made.send_for_skill("s", Liar(token), *self.ARGS)["code"], "no_ticket")
        token = self.made.mint_ticket("s", *self.ARGS)
        self.assertEqual(self.made.send_for_skill("s", token, Liar(self.ARGS[0]), *self.ARGS[1:])["code"], "no_ticket")
        token = self.made.mint_ticket("s", *self.ARGS)
        self.assertEqual(self.made.send_for_skill("s", token, self.ARGS[0], Liar("Hi"), "Hello")["code"], "no_ticket")
        self.nothing_sent()


class SkillCannotGetOneTest(tsc.SkillsTestCase):

    SEND = ("def go(ctx):\n    return ctx.send_mail('', 'pal@example.org', 'Hi', 'Hello')\n\n\n"
            "def fake(ctx):\n    return ctx.send_mail('A' * 43, 'pal@example.org', 'Hi', 'Hello')\n")

    def setUp(self):
        super().setUp()
        helpers.reset_db()
        self.fake = FakeSMTP()
        self.addCleanup(self.fake.close)
        n = next(COUNTER)
        servers = {"gmail": ("127.0.0.1", self.fake.port)}
        self.mailer = mail_core.Mailer(secret_store.SecretStore(self.dir / "mailer-data"), self.dir / "mail.log",
                                       servers=servers, tls_context=ssl.create_default_context(cafile=str(CERT)))
        self.mailer.connect_account("me@example.com", "gmail", PASSWORD)

    def test_no_ticket_and_not_on_card(self):
        card = {"needs": {"internet_hosts": [], "send_mail": True}, "slow": True}
        self.write_skill("mailer", self.SEND, [tsc.action("go"), tsc.action("fake")], **card)
        self.write_skill("plain", self.SEND, [tsc.action("go")])
        host = self.host()
        host.mailer = self.mailer.send_for_skill
        for name in ("mailer__go", "mailer__fake"):
            self.assertEqual(host.call(name)["response"]["code"], "no_ticket", name)
        self.assertEqual(host.call("plain__go")["response"]["code"], "not_on_card")
        self.assertEqual((self.fake.messages, self.fake.ehlo), ([], []))
        text = (self.dir / "skills.log").read_text(encoding="utf-8")
        self.assertNotIn("pal@example.org", text)
        self.assertNotIn("Hello", text)

    def test_cards_that_cant_load(self):
        self.write_skill("notslow", "def go(ctx):\n    return {}\n", [tsc.action("go")],
                         needs={"internet_hosts": [], "send_mail": True})
        self.write_skill("nonbool", "def go(ctx):\n    return {}\n", [tsc.action("go")],
                         needs={"internet_hosts": [], "send_mail": "yes"}, slow=True)
        host = self.host()
        self.assertNotIn("notslow", host.skills)
        self.assertNotIn("nonbool", host.skills)
        self.assertIn("notslow", host.load_errors)
        self.assertIn("nonbool", host.load_errors)
        manifest = dict(tsc.BASE, name="good_card", title="X", actions=[], needs={"internet_hosts": [], "send_mail": True})
        self.assertTrue(skills_core.manifest_problems(manifest, "good_card"))
        manifest.update(slow=True)
        self.assertEqual(skills_core.manifest_problems(manifest, "good_card"), [])

    def test_source_problems(self):
        sources = {
            "import mail_core": "import mail_core\n",
            "import secret_store": "import secret_store\n",
            "import sys": "import sys\n",
            "import builtins": "import builtins\n",
            "import gc": "import gc\n",
            "import inspect": "import inspect\n",
            "ctx._host": "def f(ctx):\n    return ctx._host\n",
            "mint_ticket": "def f(m):\n    return m.mint_ticket('a')\n",
            "vars(ctx)": "def f(ctx):\n    return vars(ctx)\n",
            "ctx.__dict__": "def f(ctx):\n    return ctx.__dict__\n",
            "x.__self__": "def f(x):\n    return x.__self__\n",
            "__globals__": "def f():\n    return f.__globals__\n",
            "__getattribute__": "def f(c):\n    return c.__getattribute__('_host')\n",
        }
        for label, source in sources.items():
            path = self.dir / "src.py"
            path.write_text(source, encoding="utf-8")
            self.assertTrue(skills_core.source_problems(path), label)
        path.write_text("def f(ctx):\n    return ctx.send_mail('t', 'a@b.co', 's', 'b')\n", encoding="utf-8")
        self.assertEqual(skills_core.source_problems(path), [])

    def test_nothing_called_mint_is_reachable(self):
        self.write_skill("one", "def go(ctx):\n    return {}\n", [tsc.action("go")])
        host = self.host()
        ctx = host.context("one")
        for thing in (skills_core.SkillContext, skills_core.SkillHost, ctx, host):
            self.assertEqual([n for n in dir(thing) if "mint" in n.lower()], [], thing)


class RepoRulesTest(unittest.TestCase):

    def test_only_mail_core_defines_mint_ticket_and_nobody_calls_it(self):
        root, found = helpers.ROOT, []
        skip = {"tests", "__pycache__", "node_modules", "dist", "build"}
        for path in root.rglob("*"):
            parts = path.relative_to(root).parts
            if any(p in skip or p.startswith(".") or p == ".venv" for p in parts[:-1]) or not path.is_file():
                continue
            in_skills = parts[0] == "skills"
            if path.suffix != ".py" and not in_skills:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for number, line in enumerate(text.splitlines(), 1):
                if "mint_ticket(" in line and not (path.name == "mail_core.py" and line.strip().startswith("def mint_ticket(")):
                    found.append(f"{path.relative_to(root)}:{number}")
        self.assertEqual(found, [])

    def test_shipped_skills_that_send_mail_are_slow(self):
        folders = [p for p in (helpers.ROOT / "skills").iterdir() if (p / "manifest.json").exists()]
        self.assertTrue(folders)
        for folder in folders:
            manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
            if (manifest.get("needs") or {}).get("send_mail"):
                self.assertIs(manifest.get("slow"), True, folder.name)
            self.assertFalse((manifest.get("needs") or {}).get("send_mail") is True and manifest.get("slow") is not True)


class LogTest(MailTestCase):

    def test_log_has_no_content(self):
        pics = [{"name": "SECRETNAME.png", "data": PNG}]
        subject, body = "SUBJECT-MARKER-xyz", "BODY-MARKER-xyz"
        good, bad, refuse = self.fake(), self.fake("badauth"), self.fake("reject")
        made = self.mailer(good)
        self.send(made, subject=subject, body=body, pictures=pics)
        self.send(made, subject=subject, body=body * 100_000)  # bad message
        made.send_for_skill("s", "A" * 43, "Pal@Example.org", subject, body, pics)  # no ticket
        made.send_test()
        for fake in (bad, refuse, None):
            other = mail_core.Mailer(made._secrets, self.log_path, servers={"gmail": ("127.0.0.1", fake.port if fake else dead_port())},
                                     tls_context=ssl.create_default_context(cafile=str(CERT)))
            self.send(other, subject=subject, body=body, pictures=pics)
        self.log_path = made._log_path
        text = self.log_path.read_text(encoding="utf-8")
        entries = self.log_entries()
        self.assertGreaterEqual(len(entries), 6)
        self.assertTrue(all(set(e) == {"when", "skill", "to", "ok", "code"} for e in entries), entries)
        for secret in (subject, "BODY-MARKER", "PICMARK", base64.b64encode(b"PICMARK").decode(), "SECRETNAME",
                       CLEAN, PASSWORD):
            self.assertNotIn(secret, text)
        self.assertEqual({e["code"] for e in entries},
                         {"", "bad_message", "no_ticket", "wrong_password", "refused", "offline"})


class RouteTest(MailTestCase):

    def setUp(self):
        super().setUp()
        self.fake_ = self.fake()
        for name, value in (("_servers", {"gmail": ("127.0.0.1", self.fake_.port),
                                          "yahoo": ("127.0.0.1", self.fake_.port)}),
                            ("_tls_context", ssl.create_default_context(cafile=str(CERT)))):
            patcher = mock.patch.object(server.MAIL, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        (server.DATA / "mail.log").unlink(missing_ok=True)

    def connect(self, **over):
        body = {"address": "me@example.com", "provider": "gmail", "password": PASSWORD}
        body.update(over)
        return helpers.api("POST", "/api/mail/connect", body)

    def test_connect_strips_spaces_and_the_password_goes_nowhere(self):
        replies = [helpers.api("GET", "/api/mail")]
        code, reply, _ = self.connect()
        self.assertEqual((code, reply["connected"], reply["address"]), (200, True, "me@example.com"))
        replies += [(code, reply, None), helpers.api("GET", "/api/mail"), helpers.api("POST", "/api/mail/test", {})]
        self.assertEqual(replies[-1][1], {"ok": True})
        self.assertEqual(self.fake_.auth[-1], f"\0me@example.com\0{CLEAN}")
        replies.append(helpers.api("GET", "/api/settings"))
        for _, reply, _ in replies:
            self.assertNotIn(CLEAN, json.dumps(reply))
            self.assertNotIn("abcd", json.dumps(reply))
        self.assertIn(CLEAN, server.SECRETS.get("mail_account"))  # it is in the store, and only there
        self.assertNotIn(CLEAN, (server.DATA / "mail.log").read_text(encoding="utf-8"))
        with closing(server.connect()) as conn:
            table = json.dumps([tuple(r) for r in conn.execute("SELECT * FROM settings")])
        self.assertNotIn(CLEAN, table)
        raw = server.DB_PATH.read_bytes()
        wal = Path(str(server.DB_PATH) + "-wal")
        raw += wal.read_bytes() if wal.exists() else b""
        self.assertNotIn(CLEAN.encode(), raw)
        self.assertNotIn(PASSWORD.encode(), raw)
        code, reply, _ = helpers.api("POST", "/api/mail/disconnect", {})
        self.assertEqual((code, reply["connected"]), (200, False))
        self.assertNotIn(CLEAN, json.dumps(reply))
        self.assertIsNone(server.SECRETS.get("mail_account"))
        self.assertFalse(helpers.api("GET", "/api/mail")[1]["connected"])

    def test_bad_input_is_plain_and_never_echoes_the_password(self):
        for over in ({"address": "nope"}, {"provider": "hotmail"}, {"password": "short1"},
                     {"password": "pässwörd-secret"}, {"password": None}, {"password": "x" * 65}):
            code, reply, _ = self.connect(**over)
            self.assertEqual(code, 400, over)
            text = reply["error"]
            for leaked in ("short1", "pässwörd", "xxxxxxxx", CLEAN):
                self.assertNotIn(leaked, text)
            self.assertNotIn("Traceback", text)
        self.assertFalse(helpers.api("GET", "/api/mail")[1]["connected"])

    def test_post_routes_need_the_tracker_header(self):
        body = {"address": "me@example.com", "provider": "gmail", "password": PASSWORD}
        for path in ("connect", "test", "disconnect"):
            code, _, _ = helpers.api("POST", f"/api/mail/{path}", body, tracker=False)
            self.assertEqual(code, 403, path)
        self.assertIsNone(server.SECRETS.get("mail_account"))
        self.assertEqual(self.fake_.messages, [])

    def test_test_without_an_account(self):
        code, reply, _ = helpers.api("POST", "/api/mail/test", {})
        self.assertEqual((code, reply["code"]), (200, "no_email"))

    def test_send_test_goes_only_to_the_accounts_own_address(self):
        self.connect()
        code, reply, _ = helpers.api("POST", "/api/mail/test", {"to": "evil@example.org", "address": "evil@example.org",
                                                                  "subject": "x", "body": "x"})
        self.assertEqual((code, reply), (200, {"ok": True}))
        msg = parse(self.fake_.messages[-1])
        self.assertEqual(msg["To"], "me@example.com")
        self.assertEqual(len(self.fake_.rcpt), 1)
        self.assertIn("me@example.com", self.fake_.rcpt[0])
        self.assertNotIn(b"evil@example.org", self.fake_.messages[-1])


if __name__ == "__main__":
    unittest.main()
