"""Regression: distinct browser accounts must not share identity, workers or saves."""
import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from aiohttp import CookieJar
from aiohttp.test_utils import TestClient, TestServer

import render_server

ORIGIN = {"Origin": "http://127.0.0.1:10000"}
PASSWORD = "two-player-testing-password-12345"

async def browser(app):
    c = TestClient(TestServer(app), cookie_jar=CookieJar(unsafe=True))
    await c.start_server()
    return c

def service_of(app):
    for resource in app.router.resources():
        for route in resource:
            if getattr(route.handler, "__name__", "") == "register_submit":
                return route.handler.__self__
    raise AssertionError("Registration handler not found")

async def test_accounts():
    with tempfile.TemporaryDirectory() as data:
        cfg = dict(
            EXPANSE_PUBLIC_URL="http://127.0.0.1:10000", EXPANSE_DATA_DIR=data,
            EXPANSE_PUBLIC_PLAY="1", EXPANSE_ACCOUNT_REGISTRATION="1",
            EXPANSE_MAX_PUBLIC_PLAYERS="10", EXPANSE_MAX_ACTIVE_GAMES="2",
            EXPANSE_GUESTS_JSON="[]", EXPANSE_OWNER_NAME="ExpanseOwner",
            EXPANSE_OWNER_PASSWORD="owner-test-password-with-sufficient-length")
        with patch.dict(os.environ, cfg, clear=True):
            app = render_server.make_app()
            a, b, other = await browser(app), await browser(app), await browser(app)
            try:
                for c, name in ((a, "AlphaPlayer"), (b, "BetaPlayer")):
                    r = await c.post("/register", data={
                        "name":name, "password":PASSWORD, "confirm":PASSWORD}, headers=ORIGIN)
                    assert r.status == 200, (name, r.status, await r.text())
                svc = service_of(app)
                ta = a.session.cookie_jar.filter_cookies(a.make_url("/"))["expanse_local"].value
                tb = b.session.cookie_jar.filter_cookies(b.make_url("/"))["expanse_local"].value
                assert ta != tb
                assert svc.auth.lookup(ta) == "alphaplayer"
                assert svc.auth.lookup(tb) == "betaplayer"
                assert "Signed in as <strong>alphaplayer</strong>" in await (await a.get("/")).text()
                assert "Signed in as <strong>betaplayer</strong>" in await (await b.get("/")).text()
                world = "0" * 64
                assert svc.folder("alphaplayer", world) != svc.folder("betaplayer", world)
                for account in ("alphaplayer", "betaplayer"):
                    svc.workers[(account, world)] = render_server.PrivateWorker(account, world)
                    svc.selected_games[account] = world
                assert (await a.post("/logout", headers=ORIGIN, allow_redirects=False)).status == 303
                assert svc.auth.lookup(ta) is None
                assert svc.auth.lookup(tb) == "betaplayer"
                assert ("alphaplayer", world) not in svc.workers
                assert ("betaplayer", world) in svc.workers
                assert svc.selected_games["betaplayer"] == world
                assert "Signed in as <strong>betaplayer</strong>" in await (await b.get("/")).text()
                # The same username from a second browser deliberately rotates its session.
                assert (await other.post("/login", data={"name":"BetaPlayer","password":PASSWORD},
                    headers=ORIGIN, allow_redirects=False)).status == 303
                assert svc.auth.lookup(tb) is None
            finally:
                await a.close()
                await b.close()
                await other.close()
    print("PASS: unique accounts, separate browser cookies, private saves, isolated logout")

if __name__ == "__main__":
    asyncio.run(test_accounts())
