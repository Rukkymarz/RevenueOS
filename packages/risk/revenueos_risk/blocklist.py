"""Destructive-pattern blocklist (INV-12), enforced by the supervisor before anything runs.

It applies in every mode, including YOLO: YOLO skips approval prompts, never this list. The
sandbox already makes these commands harmless to the host (no host mounts, COW workspace);
the blocklist is the second layer, so intent to destroy is refused and logged rather than
merely contained.
"""
import re
import shlex

SHELLS = {"sh", "bash", "dash", "zsh", "ksh", "ash", "busybox"}
SEPARATORS = re.compile(r"\|\||&&|[;|&\n]")
ROOTISH = re.compile(r"^(/|/\*|/\.|~|~/|\$HOME|\$\{HOME\}|/(bin|boot|dev|etc|home|lib\w*|opt|proc|root|sbin|srv|sys|usr|var)/?\*?)$")
FORK_BOMB = re.compile(r":\s*\(\s*\)\s*\{[^}]*:\s*\|\s*:")


def _base(word: str) -> str:
    return word.rsplit("/", 1)[-1]


def _split(command: str) -> list[list[str]]:
    out = []
    for segment in SEPARATORS.split(command):
        try:
            words = shlex.split(segment, posix=True)
        except ValueError:
            words = segment.split()
        if words:
            out.append(words)
    return out


def _check_words(words: list[str]) -> str | None:
    # Strip wrappers that run another command.
    while words and _base(words[0]) in {"sudo", "doas", "env", "nice", "nohup", "timeout", "command", "exec", "time", "xargs"}:
        wrapper, words = _base(words[0]), words[1:]
        while words and (words[0].startswith("-") or "=" in words[0]):   # the wrapper's own options
            words = words[1:]
        if wrapper == "timeout" and words and words[0].rstrip("smhd").replace(".", "", 1).isdigit():
            words = words[1:]
    if not words:
        return None
    cmd, args = _base(words[0]), words[1:]
    flags = "".join(a.lstrip("-") for a in args if a.startswith("-") and not a.startswith("--"))
    targets = [a for a in args if not a.startswith("-")]
    if cmd in SHELLS:   # sh -c, bash -lc, busybox sh -c ...: check the payload
        for i, a in enumerate(args):
            if a.startswith("-") and not a.startswith("--") and "c" in a:
                payload = next((p for p in args[i + 1:] if not p.startswith("-")), None)
                return check_command(payload) if payload else None
        if cmd == "busybox" and args:
            return _check_words(args)
    if cmd == "rm" and ("--no-preserve-root" in args or (("r" in flags or "R" in flags or "--recursive" in args)
                                                         and any(ROOTISH.match(t) for t in targets))):
        return "recursive delete of a system or home path"
    if cmd in {"chmod", "chown", "chgrp"} and ("R" in flags or "--recursive" in args) and any(ROOTISH.match(t) for t in targets):
        return f"recursive {cmd} of a system path"
    if cmd.startswith("mkfs") or cmd in {"wipefs", "fdisk", "sfdisk", "parted", "mkswap", "swapoff"}:
        return f"{cmd} rewrites disks"
    if cmd == "dd" and any(a.startswith("of=/dev/") for a in args):
        return "dd onto a device"
    if cmd == "shred" and any(t.startswith("/dev/") for t in targets):
        return "shred of a device"
    if cmd in {"shutdown", "reboot", "halt", "poweroff"} or (cmd == "init" and targets[:1] in (["0"], ["6"])):
        return f"{cmd} stops the host"
    if cmd == "systemctl" and any(t in {"poweroff", "reboot", "halt", "kexec"} for t in targets):
        return "systemctl power action"
    if cmd == "find" and targets[:1] and ROOTISH.match(targets[0]) and "-delete" in args:
        return "find -delete over a system path"
    if cmd == "mv" and targets and any(ROOTISH.match(t) for t in targets[:-1]):
        return "moving a system path"
    return None


def check_command(command: str) -> str | None:
    if FORK_BOMB.search(command):
        return "fork bomb"
    if re.search(r">\s*/dev/(sd|nvme|hd|vd|xvd|mmcblk)", command):
        return "redirect onto a block device"
    for words in _split(command):
        reason = _check_words(words)
        if reason:
            return reason
    return None


def check(argv: list[str]) -> str | None:
    """Reason the command is destructive, or None. Checks argv and any shell -c payload."""
    if not argv:
        return "empty command"
    return _check_words(list(argv))
