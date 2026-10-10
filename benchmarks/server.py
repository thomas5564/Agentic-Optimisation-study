"""Trusted subprocess launcher. Local process separation is NOT an agent sandbox."""
from __future__ import annotations

import argparse
import cProfile
from functools import wraps
import inspect
from pathlib import Path
import pstats
import socket
import sys

import uvicorn


def instrument(app, active: Path, profiles: list):
    def wrap(call):
        def measure():
            profile = cProfile.Profile() if active.exists() else None
            if profile:
                profile.enable()
            return profile

        def finish(profile):
            if profile:
                profile.disable()
                profiles.append(profile)

        if inspect.iscoroutinefunction(call):
            @wraps(call)
            async def asynchronous(*args, **kwargs):
                profile = measure()
                try:
                    return await call(*args, **kwargs)
                finally:
                    finish(profile)
            return asynchronous

        @wraps(call)
        def synchronous(*args, **kwargs):
            profile = measure()
            try:
                return call(*args, **kwargs)
            finally:
                finish(profile)
        return synchronous

    for route in app.routes:
        if getattr(route, "dependant", None) and route.dependant.call:
            route.dependant.call = wrap(route.dependant.call)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-root", type=Path, required=True)
    parser.add_argument("--ready", type=Path, required=True)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--profile-active", type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.app_root.resolve()))
    from app.main import app

    profiles = []

    def save_profiles():
        if profiles:
            stats = pstats.Stats(profiles[0])
            for profile in profiles[1:]:
                stats.add(profile)
            stats.dump_stats(str(args.profile))

    if args.profile:
        instrument(app, args.profile_active, profiles)
        # Uvicorn may re-raise SIGTERM after graceful shutdown, before finally.
        app.router.add_event_handler("shutdown", save_profiles)
    with socket.socket() as sock:
        # The harness supplies the listening socket to Uvicorn. Disable Nagle
        # explicitly so small split HTTP writes do not wait for delayed ACKs.
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.bind(("127.0.0.1", 0))
        sock.listen(128)
        args.ready.write_text(str(sock.getsockname()[1]))
        try:
            server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False, workers=1))
            server.run(sockets=[sock])
        finally:
            save_profiles()


if __name__ == "__main__":
    main()
