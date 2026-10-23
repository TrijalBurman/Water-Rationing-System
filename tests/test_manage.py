"""Exercise native launchers without installing dependencies or starting Docker."""

import csv
import io
import os
import stat
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts import manage


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / "Water Wise, café"
    root.mkdir()
    monkeypatch.setattr(manage, "ROOT", root)
    # Allow the POSIX branch to be simulated on native Windows CI, too.
    monkeypatch.setattr(manage.os, "getuid", lambda: 1000, raising=False)
    monkeypatch.setattr(manage.os, "getgid", lambda: 1000, raising=False)
    identity = manage.windows_identity
    identity.cache_clear()
    yield root
    identity.cache_clear()


def environment_file(project):
    content = "# Café configuration\nMQTT_USERNAME=backend\nMQTT_PORT=1883\n"
    content += "\n".join(f"{key}=" for key in manage.SECRET_KEYS) + "\n"
    (project / ".env.example").write_text(content, encoding="utf-8")


def fake_docker(project, monkeypatch, *, fail_hash=False, daemon="linux"):
    commands = []

    def invoke(command, **kwargs):
        commands.append(command)
        if command[0] == "whoami":
            return subprocess.CompletedProcess(command, 0, '"LAB\\student","S-1-5-21-123-456"\n')
        if command[:2] == ["docker", "info"]:
            return subprocess.CompletedProcess(command, 0, daemon + "\n")
        if command[:2] == ["docker", "run"]:
            mount = command[command.index("--mount") + 1]
            assert next(csv.reader(io.StringIO(mount))) == [
                "type=bind",
                f"source={project / '.secrets'}",
                "target=/work",
            ]
            pending = project / ".secrets" / Path(command[-1]).name
            assert pending.read_text(encoding="utf-8").startswith("backend:")
            if fail_hash:
                raise subprocess.CalledProcessError(1, command)
            pending.write_text(
                "backend:$7$hashed-backend\ntank-01:$7$hashed-device\n", encoding="utf-8"
            )
        return subprocess.CompletedProcess(command, 0, "")

    monkeypatch.setattr(manage, "run", invoke)
    return commands


@pytest.mark.parametrize("on_windows", [False, True])
def test_setup_selects_native_environment_and_does_not_recreate_it(
    project, monkeypatch, on_windows
):
    monkeypatch.setattr(manage, "windows", lambda: on_windows)
    interpreter = manage.python_path(project / ".venv")
    interpreter.parent.mkdir(parents=True)
    interpreter.touch()
    invoke = Mock()
    monkeypatch.setattr(manage, "run", invoke)
    manage.setup()
    calls = [call.args[0] for call in invoke.call_args_list]
    assert all(command[0] == str(interpreter) for command in calls)
    assert not any(command[1:3] == ["-m", "venv"] for command in calls)
    assert calls[-1][-4:] == ["-c", "requirements.lock", "-e", ".[dev]"]
    env = invoke.call_args.kwargs["env"]
    assert env["TEMP"] == env["TMP"] == env["TMPDIR"] == str(project / ".runtime")


def test_run_passes_paths_as_arguments_and_uses_project_as_working_directory(project, monkeypatch):
    invoke = Mock()
    monkeypatch.setattr(manage.subprocess, "run", invoke)
    manage.run(["python", str(project / "script.py")], env={"PORT": "8010"}, quiet=True)
    assert invoke.call_args.args[0] == ["python", str(project / "script.py")]
    assert invoke.call_args.kwargs["cwd"] == project
    assert invoke.call_args.kwargs["env"] == {"PORT": "8010"}
    assert "shell" not in invoke.call_args.kwargs


def test_demo_clears_live_settings_and_uses_isolated_data(project, monkeypatch):
    interpreter = manage.python_path(project / ".venv")
    interpreter.parent.mkdir(parents=True)
    interpreter.touch()
    for key in ("API_KEY", "MQTT_HOST", "INFLUX_URL"):
        monkeypatch.setenv(key, "configured-live-value")
    invoke = Mock()
    monkeypatch.setattr(manage, "run", invoke)
    manage.demo(8123, Path(".runtime/test data"))
    command = invoke.call_args.args[0]
    assert command[-4:] == ["--host", "127.0.0.1", "--port", "8123"]
    env = invoke.call_args.kwargs["env"]
    assert env["APP_MODE"] == "demo"
    assert env["DEMO_AUTOSTART"] == "true"
    assert all(env[key] == "" for key in ("API_KEY", "MQTT_HOST", "INFLUX_URL"))
    assert Path(env["DATA_DIR"]) == project / ".runtime/test data"


@pytest.mark.parametrize("on_windows", [False, True])
def test_bootstrap_preserves_credentials_and_device_host(project, monkeypatch, capsys, on_windows):
    monkeypatch.setattr(manage, "windows", lambda: on_windows)
    environment_file(project)
    commands = fake_docker(project, monkeypatch)
    manage.bootstrap()
    first = (project / ".env").read_bytes()
    values = manage.env_values(first.decode("utf-8").splitlines())
    assert all(values[key] for key in manage.SECRET_KEYS)
    assert b"\r" not in first
    assert "Café" in first.decode("utf-8")
    device = project / ".secrets/tank-01.env"
    device.write_text(
        device.read_text(encoding="utf-8").replace("YOUR_COMPUTER_LAN_IP", "192.168.1.42"),
        encoding="utf-8",
    )
    manage.bootstrap()
    assert (project / ".env").read_bytes() == first
    assert "MQTT_HOST=192.168.1.42\n" in device.read_text(encoding="utf-8")
    assert (
        (project / ".secrets/mosquitto.passwd")
        .read_text(encoding="utf-8")
        .startswith("backend:$7$")
    )
    assert not list((project / ".secrets").glob("*.pending"))
    output = capsys.readouterr().out
    assert all(values[key] not in output for key in manage.SECRET_KEYS)
    hash_commands = [command for command in commands if command[:2] == ["docker", "run"]]
    assert all(("--user" in command) != on_windows for command in hash_commands)
    assert all(
        values[key] not in " ".join(command) for command in commands for key in manage.SECRET_KEYS
    )
    if on_windows:
        assert any(command[0] == "icacls" and "/inheritance:r" in command for command in commands)
    elif os.name == "posix":
        assert stat.S_IMODE((project / ".env").stat().st_mode) == 0o600
        assert stat.S_IMODE((project / ".secrets").stat().st_mode) == 0o700
        assert stat.S_IMODE((project / ".secrets/mosquitto.passwd").stat().st_mode) == 0o644


def test_failed_password_hash_keeps_existing_credentials_and_cleans_plaintext(project, monkeypatch):
    environment_file(project)
    original_env = (
        (project / ".env.example").read_bytes().replace(b"API_KEY=", b"API_KEY=existing-key")
    )
    (project / ".env").write_bytes(original_env)
    directory = project / ".secrets"
    directory.mkdir()
    original_password = b"backend:$7$existing-hash\n"
    (directory / "mosquitto.passwd").write_bytes(original_password)
    fake_docker(project, monkeypatch, fail_hash=True)
    with pytest.raises(subprocess.CalledProcessError):
        manage.bootstrap()
    assert (project / ".env").read_bytes() == original_env
    assert (directory / "mosquitto.passwd").read_bytes() == original_password
    assert not list(directory.glob("*.pending"))
    assert not (directory / "tank-01.env").exists()


def test_wrong_docker_mode_fails_before_creating_credentials(project, monkeypatch):
    environment_file(project)
    fake_docker(project, monkeypatch, daemon="windows")
    with pytest.raises(RuntimeError, match="Linux containers"):
        manage.bootstrap()
    assert not (project / ".env").exists()
    assert not (project / ".secrets").exists()


def test_windows_acl_failures_include_permission_diagnostic(project, monkeypatch):
    monkeypatch.setattr(manage, "windows", lambda: True)
    monkeypatch.setattr(manage, "windows_identity", lambda: "*S-1-5-21-123-456")
    diagnostic = "Set-Acl: Access to this path is denied by the filesystem policy."
    invoke = Mock(
        side_effect=subprocess.CalledProcessError(1, ["powershell.exe"], stderr=diagnostic)
    )
    monkeypatch.setattr(manage, "run", invoke)
    with pytest.raises(RuntimeError, match="Access to this path is denied"):
        manage.restrict(project, directory=True)


def test_demo_cli_uses_port_environment_and_validates_range(monkeypatch):
    launcher = Mock()
    monkeypatch.setattr(manage, "demo", launcher)
    monkeypatch.setenv("PORT", "8017")
    assert manage.main(["demo"]) == 0
    launcher.assert_called_once_with(8017, None)
    with pytest.raises(SystemExit):
        manage.main(["demo", "--port", "65536"])


@pytest.mark.skipif(os.name != "nt", reason="requires native Windows NTFS ACLs")
def test_windows_private_files_remove_broad_permissions(project, monkeypatch):
    """Run the real Windows ACL utilities, including an existing explicit grant."""
    # PowerShell 7 hosts can pass incompatible module paths to Windows PowerShell
    # 5.1. The permission implementation must work without module loading.
    monkeypatch.setenv("PSModulePath", str(project / "no PowerShell modules"))
    directory = project / ".secrets"
    directory.mkdir()
    manage.run(["icacls", str(directory), "/grant", "*S-1-1-0:(OI)(CI)R"], quiet=True)
    manage.restrict(directory, directory=True)
    private = project / ".env"
    private.write_text("old value", encoding="utf-8")
    manage.run(["icacls", str(private), "/grant", "*S-1-1-0:R"], quiet=True)
    manage.write_private(private, "# Café\nAPI_KEY=local-test-value\n")
    assert private.read_bytes() == "# Café\nAPI_KEY=local-test-value\n".encode()
    script = (
        "$ErrorActionPreference = 'Stop'; "
        "if ([System.IO.Directory]::Exists($env:WATERWISE_ACL_PATH)) { "
        "$acl = [System.IO.Directory]::GetAccessControl($env:WATERWISE_ACL_PATH) "
        "} else { $acl = [System.IO.File]::GetAccessControl($env:WATERWISE_ACL_PATH) }; "
        "if (-not $acl.AreAccessRulesProtected) { exit 1 }; "
        "$rules = @($acl.GetAccessRules($true, $true, "
        "[System.Security.Principal.SecurityIdentifier])); "
        "if ($rules.Count -ne 1 -or $rules[0].IdentityReference.Value -ne "
        "$env:WATERWISE_ACL_SID -or $rules[0].AccessControlType -ne 'Allow') { exit 2 }"
    )
    for path in (directory, private):
        env = manage.project_environment()
        env.update(WATERWISE_ACL_PATH=str(path), WATERWISE_ACL_SID=manage.windows_identity()[1:])
        manage.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            env=env,
            quiet=True,
        )
