"""Run repository commands inside a throwaway Docker container instead of on your machine.

With `--sandbox`, run_command executes in a fresh container per command:

- it sees only the repository (mounted at /work) and a per-repository home folder for package
  caches (~/.jarvis/sandbox-home/<repo>), never your home directory, SSH keys or environment
  variables, so GITHUB_TOKEN and ANTHROPIC_API_KEY stay out;
- it runs as your user ID (files it creates are yours), with every Linux capability dropped,
  no-new-privileges, and limits on memory, CPU and process count;
- networking is on by default so installs work; --sandbox-network none cuts it off entirely;
- on a timeout the container is killed, not just the client.

Jarvis's own git operations (commit, push) still run on the host, with the token only Jarvis holds.
"""

from __future__ import annotations

import os
import re
import subprocess
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_IMAGE = "node:22-bookworm"  # Node, Python 3, git, make and a C toolchain in one image
NETWORKS = ("bridge", "none")
CONTAINER_WORKDIR = "/work"
CONTAINER_HOME = "/home/jarvis"

Runner = Callable[..., Any]


class SandboxError(Exception):
    """Docker is missing, not running, or the image can't be pulled."""


@dataclass
class Sandbox:
    home_root: Path
    image: str = DEFAULT_IMAGE
    network: str = "bridge"
    memory: str = "4g"
    cpus: str = "2"
    pids: int = 512
    docker: str = "docker"
    runner: Runner = field(default=subprocess.run, repr=False)

    def __post_init__(self) -> None:
        if self.network not in NETWORKS:
            raise SandboxError(f"Unknown sandbox network '{self.network}'. Choose from: {', '.join(NETWORKS)}.")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/:@-]*", self.image):
            raise SandboxError(f"'{self.image}' is not a valid image name.")

    def home_for(self, repo: str) -> Path:
        home = self.home_root / re.sub(r"[^A-Za-z0-9._-]", "__", repo)
        home.mkdir(parents=True, exist_ok=True)
        return home

    def command_line(self, root: Path, repo: str, command: str, name: str) -> list[str]:
        args = [
            self.docker, "run", "--rm", "--name", name, "--init",
            "--network", self.network,
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--memory", self.memory, "--cpus", self.cpus, "--pids-limit", str(self.pids),
            "-v", f"{root.resolve()}:{CONTAINER_WORKDIR}",
            "-v", f"{self.home_for(repo).resolve()}:{CONTAINER_HOME}",
            "-w", CONTAINER_WORKDIR,
            "-e", f"HOME={CONTAINER_HOME}", "-e", "CI=1",
        ]
        if hasattr(os, "getuid"):  # Docker Desktop on Windows maps ownership itself
            args += ["--user", f"{os.getuid()}:{os.getgid()}"]
        return [*args, self.image, "sh", "-c", command]

    def run(self, root: Path, repo: str, command: str, timeout: int) -> subprocess.CompletedProcess[str]:
        """Run the command in a fresh container. Raises subprocess.TimeoutExpired after killing it."""
        name = f"jarvis-{uuid.uuid4().hex[:12]}"
        try:
            return self.runner(self.command_line(root, repo, command, name), capture_output=True, text=True,
                               timeout=timeout)
        except subprocess.TimeoutExpired:
            self.runner([self.docker, "kill", name], capture_output=True, text=True, timeout=30)
            raise

    def check(self, pull: bool = True) -> str:
        """Make sure Docker answers and the image is present (pulling it if allowed). Returns a status line."""
        try:
            info = self.runner([self.docker, "info", "--format", "{{.ServerVersion}}"], capture_output=True,
                               text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired) as err:
            raise SandboxError(f"Docker isn't available ({err}). Install Docker or drop --sandbox.") from err
        if info.returncode != 0:
            detail = (info.stderr or info.stdout).strip().splitlines()[-1:] or ["no output"]
            raise SandboxError(f"Docker isn't running: {detail[0]}")
        present = self.runner([self.docker, "image", "inspect", self.image], capture_output=True, text=True, timeout=30)
        if present.returncode != 0:
            if not pull:
                raise SandboxError(f"Image {self.image} isn't available locally.")
            pulled = self.runner([self.docker, "pull", "-q", self.image], capture_output=True, text=True, timeout=1800)
            if pulled.returncode != 0:
                raise SandboxError(f"Couldn't pull {self.image}: {(pulled.stderr or pulled.stdout).strip()[:300]}")
        return f"Sandbox: Docker {info.stdout.strip()}, image {self.image}, network {self.network}."
