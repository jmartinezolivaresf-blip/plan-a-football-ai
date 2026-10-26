"""The Azure scripts refuse corporate subscriptions/tenants and unapproved billable steps (D-046).

A fake `az` on PATH answers `account show` from the test's settings and records every other command, so these
tests never reach Azure; they assert that nothing but the local profile read happens when a guard refuses.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FAKE_AZ = """#!/usr/bin/env bash
echo "$*" >> "$FAKE_AZ_LOG"
if [[ "$1 $2" == "account show" ]]; then printf '%s\\n%s\\n' "$FAKE_SUB_NAME" "$FAKE_TENANT"; exit 0; fi
exit 0
"""

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


def run(tmp_path: Path, script: str, *args: str, name: str = "Plan A Hackathon", tenant: str = "1111-personal",
        sub: str | None = "00000000-aaaa-bbbb-cccc-000000000000", approved: bool = False):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    (bin_dir / "az").write_text(FAKE_AZ)
    (bin_dir / "az").chmod(0o755)
    log = tmp_path / "az.log"
    log.write_text("")
    env = {"PATH": f"{bin_dir}:{os.environ['PATH']}", "HOME": str(tmp_path), "FAKE_AZ_LOG": str(log),
           "PLAN_A_NO_DOTENV": "1",  # the repository's .env may hold real settings
           "FAKE_SUB_NAME": name, "FAKE_TENANT": tenant,
           **{k: v for k, v in os.environ.items() if k == "PLAN_A_DENY_SUBSCRIPTIONS"}}
    if sub:
        env["PLAN_A_SUBSCRIPTION_ID"] = sub
    if approved:
        env["PLAN_A_APPROVED"] = "yes"
    p = subprocess.run(["bash", str(ROOT / "infra" / script), *args], env=env, capture_output=True, text=True,
                       timeout=60)
    calls = [line for line in log.read_text().splitlines() if line]
    return p, calls


@pytest.mark.parametrize("script", ["foundry_provision.sh", "swa_deploy.sh", "teardown.sh"])
def test_subscription_must_be_explicit(tmp_path, script):
    p, calls = run(tmp_path, script, "--check", sub=None)
    assert p.returncode != 0 and "PLAN_A_SUBSCRIPTION_ID" in p.stderr and calls == []


@pytest.mark.parametrize("script", ["foundry_provision.sh", "swa_deploy.sh", "teardown.sh"])
def test_listed_subscriptions_are_refused_by_name_or_id(tmp_path, script, monkeypatch):
    monkeypatch.setenv("PLAN_A_DENY_SUBSCRIPTIONS", "Corp Sub One, Corp Sub Two ,00000000-aaaa-bbbb-cccc-000000000000")
    p, calls = run(tmp_path, script, name="Corp Sub Two", approved=True)
    assert p.returncode != 0 and "corporate subscription" in p.stderr
    p, calls = run(tmp_path, script, name="Looks Fine", approved=True)  # refused by its id
    assert p.returncode != 0 and "corporate subscription" in p.stderr
    assert all(c.startswith("account show") for c in calls)


def test_the_local_deny_file_is_git_ignored():
    out = subprocess.run(["git", "check-ignore", "infra/deny.local"], cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0


def test_corporate_tenant_is_refused(tmp_path):
    p, calls = run(tmp_path, "foundry_provision.sh", tenant="72F988BF-86F1-41AF-91AB-2D7CD011DB47", approved=True)
    assert p.returncode != 0 and "corporate tenant" in p.stderr
    assert all(c.startswith("account show") for c in calls)


def test_billable_steps_need_explicit_approval(tmp_path):
    p, calls = run(tmp_path, "foundry_provision.sh")
    assert p.returncode != 0 and "PLAN_A_APPROVED=yes" in p.stderr
    assert all(c.startswith("account show") for c in calls)


def test_check_mode_creates_nothing(tmp_path):
    p, calls = run(tmp_path, "foundry_provision.sh", "--check")
    assert p.returncode == 0 and "check only" in p.stdout
    assert all(c.startswith("account show") for c in calls)


def test_every_azure_command_names_the_subscription():
    for script in (ROOT / "infra").glob("*.sh"):
        for n, line in enumerate(script.read_text().splitlines(), 1):
            code = re.sub(r'"[^"]*"', '""', line.split("#", 1)[0])  # ignore messages in quotes
            if re.search(r"(^|[\s($])az\s", code) and "az_sub" not in code and "command -v az" not in code:
                assert "--subscription" in code or "az ad signed-in-user" in code, f"{script.name}:{n}: {line}"
