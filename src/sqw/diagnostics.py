"""Opt-in, local, privacy-minimised diagnostic bundle for SQE Studio.

No installation, privileged operations, uploads, or project data collection.
Uses only Python's standard library so it can run before the SQE environment is ready.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

SCHEMA = "sqe-diagnostics/1"
VERSION = "0.10.0"
MAX_LOG = 32000
CORE_MODULES = ("numpy", "scipy", "matplotlib", "shapely", "gmsh")
SAFE_FILE_NAMES = ("README-PRIVACY.txt", "environment.json", "checks.json", "test-results.txt", "SUMMARY.txt", "manifest.json")


def scrub(text: str, root: Path | None = None) -> str:
    """Defence in depth for known runtime logs; the user must still review the ZIP."""
    value = str(text)
    # Avoid including local user profiles, machine identity, addresses and emails.
    candidates = [str(root) if root else "", os.environ.get("USERPROFILE", ""),
                  os.environ.get("HOME", ""), os.environ.get("HOMEPATH", "")]
    for path in sorted({x for x in candidates if x and len(x) > 3}, key=len, reverse=True):
        value = re.sub(re.escape(path), "[LOCAL_PATH]", value, flags=re.I)
    for key in ("USERNAME", "USER", "COMPUTERNAME", "HOSTNAME"):
        secret = os.environ.get(key, "")
        if secret and len(secret) >= 3:
            value = re.sub(re.escape(secret), "[REDACTED]", value, flags=re.I)
    value = re.sub(r"(?i)[A-Z]:[\\/](?:Users|Documents and Settings)[\\/][^\\/\s:]+", "[USER_HOME]", value)
    value = re.sub(r"/home/[^/\s:]+", "[USER_HOME]", value)
    value = re.sub(r"(?i)\b[\w.+'-]+@[\w.-]+\.[a-z]{2,}\b", "[EMAIL]", value)
    value = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "[IPV4]", value)
    value = re.sub(r"(?i)(token|password|secret|api[_-]?key)\s*[=:]\s*[^\s,;]+", r"\1=[REDACTED]", value)
    # Don't include arbitrary environment or file paths; catch absolute traceback file paths.
    value = re.sub(r'File "[A-Za-z]:[\\/][^"]+"', 'File "[LOCAL_FILE]"', value)
    value = re.sub(r'File "/[^"]+"', 'File "[LOCAL_FILE]"', value)
    return value[:MAX_LOG]


def run(argv: list[str], *, root: Path, timeout: int = 15, env: dict | None = None):
    """Execute a fixed command, never through a shell; captured data is not logged by default."""
    try:
        r = subprocess.run(argv, cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=timeout, env=env, check=False)
        stdout = r.stdout.decode("utf-8", errors="replace")
        stderr = r.stderr.decode("utf-8", errors="replace")
        # WSL's --list output can contain interspersed NULs or UTF-16 LE.
        if r.stdout.count(b"\x00") > max(1, len(r.stdout) // 8):
            try:
                stdout = r.stdout.decode("utf-16-le", errors="replace")
            except UnicodeError:
                stdout = stdout.replace("\x00", "")
        return r.returncode, stdout, stderr, False
    except subprocess.TimeoutExpired:
        return None, "", "", True
    except (FileNotFoundError, PermissionError, OSError):
        return None, "", "", False


def run_regressions(root: Path, timeout: int = 35):
    """Run a curated, time-bounded smoke suite in isolated processes.

    The full CI suite starts background API/worker processes. Running that whole
    suite from a diagnostic collector can deadlock on inherited process handles.
    The workstation diagnostic instead runs a fixed set of scientific contracts;
    full CI remains `python -m unittest discover -s tests` in the repository.
    """
    test_env = os.environ.copy()
    test_env["PYTHONPATH"] = str(root / "src")
    test_env["PYTHONNOUSERSITE"] = "1"
    filenames = ("test_quantumlab.py", "test_physical_qpu.py", "test_parametric_qpu.py",
                 "test_palace_quality.py", "test_diagnostics.py")
    collected = []
    count = 0
    failed = False
    timed_out = False
    with tempfile.TemporaryDirectory(prefix="sqe-regressions-") as temporary:
        for filename in filenames:
            argv = [sys.executable, "-m", "unittest", "discover", "-s", "tests",
                    "-p", filename, "-q"]
            pathname = Path(temporary) / (filename + ".log")
            with pathname.open("wb") as log:
                try:
                    result = subprocess.run(argv, cwd=root, stdin=subprocess.DEVNULL,
                                            stdout=log, stderr=subprocess.STDOUT,
                                            timeout=timeout, env=test_env, check=False)
                    rc, timed = result.returncode, False
                except subprocess.TimeoutExpired:
                    rc, timed = None, True
                except (PermissionError, FileNotFoundError, OSError):
                    rc, timed = None, False
            with pathname.open("rb") as log:
                log.seek(0, os.SEEK_END)
                size = log.tell()
                log.seek(max(0, size - MAX_LOG // len(filenames)))
                message = scrub(log.read(MAX_LOG // len(filenames)).decode("utf-8", errors="replace"), root)
            match = re.search(r"Ran\s+(\d+)\s+tests?", message)
            if match:
                count += int(match.group(1))
            collected.append("=== " + filename + " (" + (str(rc) if rc is not None else "unavailable") + ") ===\n" + message)
            if rc != 0:
                failed = True
            timed_out = timed_out or timed
    return (None if timed_out else (1 if failed else 0)), "\n".join(collected), timed_out, count

def check(items: list, name: str, status: str, code: str, detail: str, suggestion: str = ""):
    assert status in ("PASS", "WARN", "FAIL", "SKIP")
    items.append({"id": name, "status": status, "code": code,
                  "detail": detail, "next_action": suggestion})


def versions():
    result = {}
    for module in CORE_MODULES:
        try:
            result[module] = importlib.metadata.version(module)
        except importlib.metadata.PackageNotFoundError:
            result[module] = None
    return result


def collect(root: Path, *, extended: bool = False, skip_tests: bool = False):
    items = []
    output = []
    win = os.name == "nt"
    fs = shutil.disk_usage(root)
    build = platform.win32_ver() if win else ("", "", "", "")
    env = {
        "schema": SCHEMA,
        "app_release": VERSION,
        "platform": "Windows" if win else platform.system(),
        "os_release": build[0] if win else platform.release(),
        "os_build": build[1] if win else None,
        "architecture": platform.machine(),
        "logical_cpu_count": os.cpu_count(),
        "free_disk_gib": round(fs.free / 1024**3, 1),
        "python_version": ".".join(map(str, sys.version_info[:3])),
        "python_venv": sys.prefix != sys.base_prefix,
        "package_versions": versions(),
        "mode": "extended" if extended else "standard",
        "data_collection": "allowlisted runtime metadata and application test output only",
    }
    if win:
        # Only selected non-personal CIM fields; deliberately exclude model serial,
        # user, host, BIOS ID, NICs, network configuration and installed apps.
        command = ("$p=Get-CimInstance Win32_Processor|Select-Object -First 1; "
                   "$s=Get-CimInstance Win32_ComputerSystem; "
                   "[pscustomobject]@{cpu_model=[string]$p.Name;"
                   "physical_memory_gib=[math]::Round($s.TotalPhysicalMemory/1GB,1);"
                   "virtualization_firmware_enabled=[bool]$p.VirtualizationFirmwareEnabled}" 
                   "|ConvertTo-Json -Compress")
        ps = shutil.which("powershell.exe")
        if ps:
            rc, out, _, _ = run([ps, "-NoProfile", "-NonInteractive", "-Command", command],
                                 root=root, timeout=12)
            if rc == 0:
                try:
                    hardware = json.loads(out.strip())
                    name = hardware.get("cpu_model")
                    if isinstance(name, str) and len(name) < 160:
                        env["cpu_model"] = scrub(name, root)
                    memory = hardware.get("physical_memory_gib")
                    if isinstance(memory, (float, int)) and 0 < memory < 8192:
                        env["physical_memory_gib"] = memory
                    virtual = hardware.get("virtualization_firmware_enabled")
                    if isinstance(virtual, bool):
                        env["virtualization_firmware_enabled"] = virtual
                except (ValueError, TypeError):
                    pass
    check(items, "runtime.python", "PASS" if (3, 11) <= sys.version_info[:2] < (3, 14) else "FAIL",
          "PYTHON_SUPPORTED" if (3, 11) <= sys.version_info[:2] < (3, 14) else "PYTHON_UNSUPPORTED",
          "Python 3.11-3.13" if (3, 11) <= sys.version_info[:2] < (3, 14) else "Python must be 3.11-3.13",
          "Use WINDOWS-FIRST-START.cmd for the isolated interpreter.")
    check(items, "resources.disk", "PASS" if fs.free >= 10 * 1024**3 else "WARN",
          "DISK_OK" if fs.free >= 10 * 1024**3 else "LOW_DISK_SPACE",
          "Free space (GiB): " + str(env["free_disk_gib"]),
          "Palace/Spack builds may require substantial additional free space.")
    installed = env["package_versions"]
    for module in CORE_MODULES:
        found = installed[module] is not None
        check(items, "python." + module, "PASS" if found else "WARN", "PACKAGE_PRESENT" if found else "PACKAGE_MISSING",
              (module + " " + str(installed[module])) if found else module + " not installed",
              "Run WINDOWS-FIRST-START.cmd to install/repair the Python environment." if not found else "")
    venv = root / ".venv" / ("Scripts/python.exe" if win else "bin/python")
    check(items, "app.virtualenv", "PASS" if venv.is_file() else "WARN",
          "VENV_FOUND" if venv.is_file() else "VENV_MISSING",
          "Isolated SQE interpreter exists" if venv.is_file() else "Isolated SQE interpreter not found",
          "Run WINDOWS-FIRST-START.cmd for initial setup." if not venv.is_file() else "")
    manifest_path = root / ".venv" / "sqw-environment.json"
    if manifest_path.is_file():
        # Explicitly allowlist two fields. The bootstrap state can contain command
        # paths and pip error strings, so never copy or print it wholesale.
        try:
            state = json.loads(manifest_path.read_text(encoding="utf-8"))
            status = state.get("status")
            profile = state.get("profile")
            env["bootstrap_status"] = status if status in {"ready", "failed", "installing"} else "unknown"
            env["bootstrap_profile"] = profile if profile in {"core", "full"} else "unknown"
            env["bootstrap_gmsh_registered"] = bool(state.get("optional_components", {}).get("gmsh", {}).get("native_api_initialized") is True)
            check(items, "app.bootstrap", "PASS" if status == "ready" else "WARN",
                  "BOOTSTRAP_READY" if status == "ready" else "BOOTSTRAP_INCOMPLETE",
                  "Bootstrap status: " + env["bootstrap_status"],
                  "Inspect the previous setup console output and rerun WINDOWS-FIRST-START.cmd" if status != "ready" else "")
        except (OSError, ValueError, TypeError, AttributeError):
            check(items, "app.bootstrap", "WARN", "BOOTSTRAP_MANIFEST_INVALID", "Local bootstrap record is unreadable")
    else:
        check(items, "app.bootstrap", "WARN", "BOOTSTRAP_MANIFEST_MISSING", "No installation state manifest found")

    if win:
        wsl = shutil.which("wsl.exe")
        if not wsl:
            check(items, "wsl.command", "WARN", "WSL_NOT_FOUND", "wsl.exe not available", "See WINDOWS-PALACE-SETUP.cmd")
        else:
            rc, out, _, timed = run([wsl, "--list", "--verbose"], root=root, timeout=18)
            if timed:
                check(items, "wsl.command", "WARN", "WSL_TIMEOUT", "wsl.exe --list --verbose exceeded 18 seconds")
            elif rc != 0:
                check(items, "wsl.command", "WARN", "WSL_NOT_INITIALIZED", "WSL list failed; no changes made",
                      "Open Ubuntu or use WINDOWS-PALACE-SETUP.cmd")
            else:
                norm = out.replace("\x00", "")
                lines = [x.strip().lstrip("*").strip() for x in norm.splitlines()]
                entries = [line for line in lines if re.search(r"\s[12]\s*$", line)]
                ubuntu_entry = next((e for e in entries if re.match(r"(?i)^Ubuntu(?:[-\w.]*)?\s+.*\s2\s*$", e)), None)
                ubuntu = bool(ubuntu_entry)
                ubuntu_name = ubuntu_entry.split()[0] if ubuntu_entry else None
                env["wsl_distro_count"] = len(entries)
                env["wsl_ubuntu2_detected"] = ubuntu
                check(items, "wsl.command", "PASS", "WSL_LIST_OK",
                      "WSL available; installed distributions: " + str(len(entries)) + "; Ubuntu WSL2: " + str(ubuntu),
                      "Install Ubuntu WSL2 if Palace is planned." if not ubuntu else "")
            if extended and rc == 0 and env.get("wsl_ubuntu2_detected"):
                # Read-only, bounded probe. Do not print whoami, paths, or package logs.
                script = ('echo SQE_WSL_READY=1; '
                          'if [ -x "$HOME/.sqe/palace/bin/palace" ]; then echo SQE_PALACE_BINARY=1; else echo SQE_PALACE_BINARY=0; fi; '
                          'if [ -f "$HOME/.sqe/spack/share/spack/setup-env.sh" ]; then '
                          'echo SQE_SPACK=1; '
                          'source "$HOME/.sqe/spack/share/spack/setup-env.sh" >/dev/null 2>&1; '
                          'if spack find --installed --format "{name}" palace 2>/dev/null | grep -qx palace; then echo SQE_PALACE_SPACK=1; else echo SQE_PALACE_SPACK=0; fi; '
                          'else echo SQE_SPACK=0; fi; '
                          'command -v python3 >/dev/null && echo SQE_PYTHON3=1 || echo SQE_PYTHON3=0')
                prc, pout, _, ptime = run([wsl, "-d", ubuntu_name, "--", "bash", "-lc", script], root=root, timeout=40)
                if not prc and "SQE_WSL_READY=1" in pout:
                    signals = {k: v for k, v in re.findall(r"(SQE_[A-Z0-9_]+)=(\d)", pout)}
                    env["wsl_probe"] = signals
                    check(items, "wsl.shell", "PASS", "WSL_BASH_OK", "Ubuntu bash responded; Spack: " + signals.get("SQE_SPACK", "?") + "; Palace via Spack: " + signals.get("SQE_PALACE_SPACK", "?") + "; local Palace binary: " + signals.get("SQE_PALACE_BINARY", "?"))
                else:
                    check(items, "wsl.shell", "WARN", "WSL_BASH_TIMEOUT" if ptime else "WSL_BASH_FAILED", "Ubuntu bash probe did not complete")
            elif extended:
                check(items, "wsl.shell", "SKIP", "WSL_NOT_READY", "Ubuntu WSL2 not detected")
    else:
        check(items, "wsl.command", "SKIP", "NOT_WINDOWS", "WSL checks apply only to Windows")

    # Julia check never loads packages or downloads anything unless extended was chosen.
    julia = shutil.which("julia")
    if julia:
        rc, out, _, timed = run([julia, "--startup-file=no", "--version"], root=root, timeout=12)
        v = re.search(r"julia version (\d+\.\d+\.\d+)", out, re.I)
        check(items, "julia.runtime", "PASS" if rc == 0 and v else "WARN",
              "JULIA_FOUND" if rc == 0 and v else "JULIA_UNRESPONSIVE",
              "Julia " + v.group(1) if v else "Julia version unavailable")
        if extended:
            project = root / ".julia-josephson" / "Project.toml"
            if project.exists():
                cmd = [julia, "--startup-file=no", "--project=" + str(project.parent),
                       "-e", 'using JosephsonCircuits; println("SQE_JC_READY=1")']
                jenv = os.environ.copy()
                jenv["JULIA_NUM_THREADS"] = "2"
                jenv["JULIA_PKG_PRECOMPILE_AUTO"] = "0"
                rc, out, _, timed = run(cmd, root=root, timeout=150, env=jenv)
                success = rc == 0 and "SQE_JC_READY=1" in out
                check(items, "julia.josephsoncircuits", "PASS" if success else "WARN",
                      "JC_IMPORT_OK" if success else "JC_TIMEOUT" if timed else "JC_IMPORT_FAILED",
                      "JosephsonCircuits import succeeded" if success else "Julia package import failed or timed out",
                      "Re-run WINDOWS-JOSEPHSONCIRCUITS-SETUP.cmd if needed.")
            else:
                check(items, "julia.josephsoncircuits", "SKIP", "JC_ENV_MISSING", "Dedicated Julia environment has not been installed")
    else:
        check(items, "julia.runtime", "WARN", "JULIA_NOT_ON_PATH", "Julia not on PATH (optional)",
              "Run WINDOWS-JOSEPHSONCIRCUITS-SETUP.cmd when nonlinear simulations are needed.")

    # Local Palace executable is optional; WSL Palace status is checked separately.
    palace = shutil.which("palace")
    check(items, "palace.native", "PASS" if palace else "SKIP", "PALACE_ON_PATH" if palace else "PALACE_NOT_ON_PATH",
          "Native Palace executable is available" if palace else "No native Palace on PATH; WSL Palace may still be installed")

    # Test suite runs under the selected interpreter; do not run user projects.
    if skip_tests:
        check(items, "app.regressions", "SKIP", "TESTS_DISABLED", "Application tests disabled by explicit option")
    else:
        rc, clean, timed, count = run_regressions(root, timeout=35)
        # Only the fixed project's unit tests are run. Their output is still reviewed before sharing.
        output.append("=== APPLICATION UNIT TESTS (REDACTED) ===\n" + clean)
        check(items, "app.regressions", "PASS" if rc == 0 else "FAIL", "TESTS_PASS" if rc == 0 else "TESTS_TIMEOUT" if timed else "TESTS_FAILED",
              "Focused smoke tests: " + str(count) + "; exit: " + str(rc),
              "Provide this diagnostic ZIP for regression failure analysis." if rc != 0 else "")
        if rc is None and not timed:
            check(items, "app.interpreter", "FAIL", "PYTHON_EXEC_FAILED", "Could not launch test Python")

    if extended:
        # Isolated native Gmsh mesh smoke test. Never touches a user's project or runs Palace.
        if installed["gmsh"] is not None:
            mesh_code = ("import gmsh,tempfile,os; gmsh.initialize(['-nopopup']); "
                         "gmsh.option.setNumber('General.Terminal',0); "
                         "gmsh.option.setNumber('Mesh.CharacteristicLengthMax',0.8); "
                         "gmsh.model.add('sqe_diagnostics_box'); "
                         "gmsh.model.occ.addBox(0,0,0,1,1,1); gmsh.model.occ.synchronize(); "
                         "gmsh.model.mesh.generate(3); "
                         "print('SQE_GMSH_3D_OK=1'); gmsh.finalize()")
            rc, out, _, timed = run([sys.executable, "-c", mesh_code], root=root, timeout=45)
            ok = rc == 0 and "SQE_GMSH_3D_OK=1" in out
            check(items, "gmsh.mesh_3d", "PASS" if ok else "FAIL", "GMSH_3D_OK" if ok else "GMSH_3D_TIMEOUT" if timed else "GMSH_3D_FAILED",
                  "Native Gmsh 3D unit-box meshing succeeded" if ok else "Gmsh could not generate a 3D unit-box mesh",
                  "Inspect Gmsh installation and native runtime libraries." if not ok else "")
        else:
            check(items, "gmsh.mesh_3d", "SKIP", "GMSH_NOT_INSTALLED", "Optional Gmsh 3D smoke test skipped")
    return env, items, "\n\n".join(output)


def bundle(root: Path, output_dir: Path, *, extended: bool = False, skip_tests: bool = False) -> tuple[Path, list]:
    root = root.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    # No network, no recursive project scan. Build a whitelist-only archive.
    with tempfile.TemporaryDirectory(prefix="sqe-diagnostics-") as tmp:
        stage = Path(tmp)
        env, checks, tests = collect(root, extended=extended, skip_tests=skip_tests)
        status = ("FAIL" if any(c["status"] == "FAIL" for c in checks)
                  else "WARN" if any(c["status"] == "WARN" for c in checks) else "PASS")
        totals = {s: sum(x["status"] == s for x in checks) for s in ("PASS", "WARN", "FAIL", "SKIP")}
        (stage / "environment.json").write_text(json.dumps(env, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (stage / "checks.json").write_text(json.dumps(checks, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (stage / "test-results.txt").write_text(tests if tests else "Regression tests skipped.\n", encoding="utf-8")
        lines = ["SQE Studio v0.10.0 - local diagnostic summary", "Overall: " + status,
                 "Checks: " + ", ".join(f"{s}={n}" for s, n in totals.items()), ""]
        for c in checks:
            lines.append("[" + c["status"] + "] " + c["id"] + " / " + c["code"] + " - " + c["detail"])
            if c["next_action"] and c["status"] != "PASS":
                lines.append("  Next: " + c["next_action"])
        (stage / "SUMMARY.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (stage / "README-PRIVACY.txt").write_text(
            "SQE LOCAL DIAGNOSTICS - REVIEW BEFORE SHARING\n\n"
            "The script does not upload data, install software, require administrator rights, "
            "read projects, list arbitrary user files, or collect environment variables.\n"
            "Collected: general OS/Python/tool versions, CPU count, free disk, WSL availability, "
            "fixed test names and sanitized errors.\n"
            "It does not collect system serial numbers, usernames, machine names, IP addresses, "
            "personal paths, passwords or design files by design.\n"
            "Redaction is best-effort, not a guarantee against all possible text generated by tests.\n"
            "ALWAYS OPEN SUMMARY.txt, environment.json, checks.json and test-results.txt "
            "and check their contents before sending the ZIP.\n"
            "Do not include studio-data, your QPU projects or any private files when sharing.\n",
            encoding="utf-8")
        manifest = {"schema": SCHEMA, "status": status, "release": VERSION,
                    "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "mode": "extended" if extended else "standard", "counts": totals,
                    "contents": list(SAFE_FILE_NAMES) + ["SHA256SUMS.txt"]}
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        checksums = []
        for name in SAFE_FILE_NAMES:
            checksums.append(hashlib.sha256((stage / name).read_bytes()).hexdigest() + "  " + name)
        (stage / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n", encoding="utf-8")
        timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%SZ")
        path = output_dir / ("SQE-DIAGNOSTICS-v0.10.0-" + timestamp + ".zip")
        if path.exists():
            raise FileExistsError("Diagnostic bundle with this timestamp already exists")
        with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_DEFLATED) as z:
            for name in list(SAFE_FILE_NAMES) + ["SHA256SUMS.txt"]:
                z.write(stage / name, arcname=name)
    return path, checks


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out-dir", type=Path, default=Path("diagnostics"))
    p.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    p.add_argument("--extended", action="store_true")
    p.add_argument("--skip-tests", action="store_true")
    args = p.parse_args(argv)
    try:
        path, checks = bundle(args.root, args.out_dir, extended=args.extended, skip_tests=args.skip_tests)
    except (OSError, ValueError) as exc:
        print("Diagnostics could not be created: " + scrub(str(exc)), file=sys.stderr)
        return 2
    for level in ("FAIL", "WARN"):
        for item in checks:
            if item["status"] == level:
                print("[" + level + "] " + item["id"] + ": " + item["code"])
    print("Diagnostics ZIP created: " + str(path))
    print("Open and review its contents before sharing. Nothing was uploaded.")
    # Diagnostic completeness, not tool availability, defines command success.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
