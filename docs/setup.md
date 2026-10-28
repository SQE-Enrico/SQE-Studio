# Development environment

## Python isolation

Use Python 3.12 and run `python scripts/bootstrap.py` from the repository root. The script is idempotent: it creates/reuses `.venv`, installs the editable project, runs `pip check`, executes tests and creates the first report. It does not modify system Python. Re-running a completed first example does not overwrite its output.

`--profile core` is the default. `--profile full` adds the project's proposed scqubits/QPDK/Gmsh chain and QuTiP. Direct reference dependencies are pinned, but their transitive resolution is a **qualification candidate**, not an already verified lock. The generated `.sqw/full-resolved.txt` records all resolved Python dependencies. Copy it into a reviewed `requirements/full-qualified-PYTHON-OS.txt` after reference tests pass. Restore with:

```bash
python scripts/bootstrap.py --profile full --lock requirements/full-qualified-3.12-linux.txt
```

Before installing anything into an already recorded environment, bootstrap compares its current freeze with the last successful record. Unexplained drift stops setup before package changes. It also rejects venvs that inherit system packages, preventing an accidental dependence on the host runtime. Use `--venv .venv-clean` for a separate environment; no old environment is deleted. Upgrading the same managed core environment to the full profile is supported, and full dependencies are constrained by `core.lock`. Incompatible candidate requirements fail explicitly.

Freeze files are platform-specific and do not lock the MPI/compiler/BLAS stack or downloaded wheel hashes. For long-term experiments also archive wheels and the native solver build/container digest. A failed setup records `status=failed` in the target environment's `sqw-environment.json`; it does not print a successful setup message.

Inspect a plan without creating files or making network calls:

```bash
python scripts/bootstrap.py --profile full --venv .venv-reference --plan
```

For a laboratory wheelhouse prepared on an approved connected workstation:

```bash
python scripts/bootstrap.py --offline --wheelhouse /approved/wheels --venv .venv-offline
```

The wheelhouse must contain setuptools/wheel, the core lock and all relevant dependencies for the selected Python/OS. For the full profile it must additionally contain the reference dependencies and their transitives. Every pip install receives `--no-index`; this is an offline installation mode, not a claim that the delivery includes those wheels. With a custom venv path the resolved freeze uses a unique suffix under `.sqw/`, and the script prints the exact interpreter to use.

The core requirements pin every dependency in the tested scientific stack. The checked-in `.github/workflows/ci.yml` is intended to test additional Python versions; it has not been run on GitHub as part of this delivery.

## Native tools

Linux or WSL2 is the recommended full-solver host. Core Python examples are portable to macOS and Windows. For Ubuntu, an administrator can install the native build prerequisites:

```bash
sudo apt-get update
sudo apt-get install -y build-essential cmake gfortran git pkg-config \
  libopenblas-dev liblapack-dev libopenmpi-dev openmpi-bin \
  libglu1-mesa libgl1 libegl1 zlib1g-dev
```

Check the installed CMake/compiler against the requirements of the Palace version you select. The helper targets Palace **v0.18.1** and needs a suitable C++20 compiler and CMake 3.27+. It builds in `.sqw/` without sudo:

```bash
bash scripts/build_palace.sh
sqw doctor
```

After the OS prerequisites are present, `bash scripts/setup_full.sh` performs both the Python reference setup and the native Palace build in one invocation.

The helper records the source commit. Supply the resulting full launcher path through `--palace .sqw/palace-v0.18.1/build/bin/palace`, or add its directory to `PATH`. A full source build downloads dependencies and may take substantial time and memory. It has not been executed in the delivery sandbox. The default SuperLU and SLEPc build matches the generated eigenmode solver configuration. A lab installation with another direct solver must adjust that configuration deliberately.

[Palace's official Spack instructions](https://awslabs.github.io/palace/stable/install/) are an alternative; concretize and preserve `spack.lock` and `spack find --long` output. No opaque, unverified container image is required by this repository.

Install the **KLayout desktop application** separately from [klayout.de](https://www.klayout.de/). The Python `klayout` package installed through GDSFactory is not a substitute for the desktop executable. Open GDS with the supplied `technology/sqw.lyp`; the repository's explicit layer map takes precedence over generic QPDK technology colors. `python -m qpdk.install_tech` is optional for exploring the upstream PDK and writes to the user's KLayout configuration.

## Diagnostics

`sqw doctor` prints Python package versions and executable locations. It does not imply that a solver has passed numerical validation. `python -m unittest discover -s tests -v` explicitly skips unavailable external libraries. Run the manual `reference-adapters` CI job, or the same full-profile commands locally, to cross-check QPDK geometry, scqubits spectra and QuTiP dynamics.

Run `sqw qualify --out build/references` to prepare independent reference problems, and `sqw qualify --solve --out build/references-palace` when Palace is installed. See [qualification](qualification.md). For actual chip runs, `sqw verify --run RUN_DIRECTORY` checks stored artifacts and their dependency history.

If PyPI is blocked, install from an institution-managed wheel mirror or a pre-approved wheelhouse. Do not treat an offline failed install as a successful setup. The included `examples/results/` artifacts remain inspectable without any installation.
