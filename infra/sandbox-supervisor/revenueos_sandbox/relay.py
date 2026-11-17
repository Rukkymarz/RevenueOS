"""Runs INSIDE the sandbox (stdlib only, copied in read-only).

The sandbox has its own network namespace with only loopback, so this relay is the one way
out: it listens on 127.0.0.1:3128 (the HTTP_PROXY the agent sees) and pipes each connection
to the supervisor's per-session Unix socket, then execs the agent command.

usage: python3 relay.py <unix-socket> <command> [args...]
"""
import os
import socket
import sys
import threading

PORT = 3128


def _pipe(src: socket.socket, dst: socket.socket) -> None:
    try:
        while data := src.recv(65536):
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for s in (dst, src):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def _serve(listener: socket.socket, path: str) -> None:
    while True:
        client, _ = listener.accept()
        upstream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            upstream.connect(path)
        except OSError:
            client.close()
            continue
        threading.Thread(target=_pipe, args=(client, upstream), daemon=True).start()
        threading.Thread(target=_pipe, args=(upstream, client), daemon=True).start()


def main(argv: list[str]) -> None:
    path, command = argv[1], argv[2:]
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", PORT))
    listener.listen(64)
    if os.fork() == 0:          # child: serve until the sandbox's pid namespace ends
        os.setsid()
        _serve(listener, path)
        os._exit(0)
    listener.close()
    os.execvp(command[0], command)


if __name__ == "__main__":
    main(sys.argv)
