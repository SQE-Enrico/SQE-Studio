# Remote deployment and operation

SQE Studio v0.3 targets a **single Linux research server** with local persistent storage. Users connect through their browsers; the scientific packages and native solvers run on that server. A private institutional network/VPN plus HTTPS is the intended first deployment. The source repository can be public without exposing an anonymous public compute service.

## Services

The Compose deployment has three services:

- **proxy:** Caddy provides HTTPS for the configured hostname.
- **web:** Gunicorn serves the WSGI API and browser assets; it does not perform heavy numerical work in request handlers.
- **worker:** one scheduler admits queued jobs and starts independent scientific subprocesses.

Web and worker share the named `studio_data` volume. SQLite WAL, drafts, revisions, account/session records, assets and job workspaces live there. Keep it on a local filesystem. Do not put the SQLite database on NFS or serve this directory directly with a static web server.

## First installation

On the server, install Docker/Compose or use the site's approved equivalent. Copy `deploy/studio.env.example` to `deploy/studio.env`, set the real DNS hostname, and choose concurrency/CPU/memory capacity. The file is ignored by Git. Ensure the hostname resolves to the server and that the approved HTTPS route can reach it.

```bash
docker compose --env-file deploy/studio.env -f deploy/compose.yaml up --build -d
```

The default scientific image runs the analytical workflow and independent SciPy references. It intentionally has no fabricated native-solver result. The full optional image is selected by `SQE_DOCKERFILE=deploy/Dockerfile.palace`; it installs the candidate reference stack and builds Palace v0.18.1. That build can be substantial and has **not** been executed in this delivery environment. Preserve the resolved Python environment, source commit and built image digest after qualifying it on the host. The supplied image tags are convenient starting points, not a fully locked production supply chain.

The web and worker containers run as an unprivileged service user, with a read-only application filesystem and a writable data volume/tmp filesystem. Administrator-enabled macros still run under that trusted account and can access the shared data volume; these container settings are not per-project code isolation.

## First administrator

Retrieve the one-use setup URL from the web container:

```bash
docker compose --env-file deploy/studio.env -f deploy/compose.yaml exec web python scripts/studio_setup_link.py
```

Open it in the browser and create the first administrator. The secret is in the URL fragment, not a query parameter, and is removed from the browser address after loading. The token becomes unusable after setup. No default administrator password is shipped.

All later user invitations and project sharing are performed in the web UI. The application creates activation links but does not send email. Keep administrative accounts restricted to trusted maintainers; administrator-approved macros execute real Python on the server.

## Native tools and worker capacity

Configure `SQE_MAX_JOBS`, `SQE_TOTAL_CPUS` and `SQE_MEMORY_GB` for the compute service. For example, two jobs can each reserve four CPUs on an eight-CPU worker. Reservations prevent scheduler overbooking and set BLAS/OpenMP thread counts, but they do not enforce a per-job cgroup, aggregate MPI-memory cap or quota. Use host/container resource limits as appropriate for the institution.

The same code can be installed in a managed environment outside containers. Run `gunicorn 'sqw.studio.server:create_app()'` behind the site's approved HTTPS proxy and run `python -m sqw.studio.jobs` as a **separate supervised service**, with the same `SQE_DATA`, `SQE_ORIGIN`, capacity and solver settings. Production mode requires an HTTPS origin. Exactly one scheduler may own a data directory; multiple web workers are supported.

For an institution-managed Palace installation, set `SQE_PALACE` to its approved launcher path in both services. KLayout Python, Gmsh, scqubits and QuTiP must be installed in the worker's environment to use their corresponding routes. Installing only a GUI on an end user's laptop does not install a worker dependency.

Before interpreting a chip solve, run the [known reference problems](qualification.md), check solver/mesh/port conventions, and preserve qualification evidence. The capability page reports availability, not numerical or process qualification.

## File transfers and disk use

Assets are limited to 32 MiB each. Project imports default to 512 MiB compressed and 8192 MiB expanded, with at most 100000 archive entries and 32 MiB of metadata. Configure `SQE_MAX_CAPSULE_MB` and `SQE_MAX_EXPANDED_MB` in `deploy/studio.env`; the proxy and app share the compressed limit. Capsule uploads and unpacking use the data disk in bounded chunks. Invalid imports are rejected before a new project is published. Artifact hashes are streamed, so checking large solver fields does not read them into RAM all at once.

Exports are downloadable ZIP files built on the data disk; full native field folders can be large. The browser artifact list shows up to 2000 files per job. Keep disk capacity and export retention under the operator’s supervision: automated quotas, deduplication and export pruning are not implemented. For multi-gigabyte native archives, adjust limits/timeouts deliberately or use the site’s approved server backup/transfer tooling.

## Recovery, backups and upgrades

Browser closure and web-service restarts do not stop the compute service. A stopped/crashed worker leaves an interrupted or expired-heartbeat record; completed stage results can be selected as a checkpoint. Native iterations are rerun from their stage inputs rather than pretending to resume inside Palace's eigensolver.

Back up the **whole data volume**, not only SQLite. For a straightforward consistent full backup, stop web and worker services, back up the volume using the site's approved backup tooling, then restart services. Stopping an active worker interrupts its current native stage, while completed checkpoints and drafts remain. Test restoring to a separate instance before relying on backups. Project capsules are useful research transfers; they are not a backup of user accounts, sessions or the full server configuration.

Before upgrading, take a backup, qualify the new build in a separate instance, then restart both services with it. Engine source/dependency changes invalidate Studio reuse signatures conservatively. The current schema is version 1; future schema changes require explicit migrations. There is no automatic destructive migration.

Review `SECURITY.md`, keep OS/dependencies current, limit public exposure, and use the institution's authentication/network requirements. SSO/OIDC, multi-host scheduling, SLURM/PBS integration and untrusted tenant isolation are not implemented in v0.3. Docker/TLS deployment and real MPI cancellation remain host-qualification tasks.

## Local/tunnel use

`python scripts/start_studio.py` starts a loopback-only development server and a separate worker. It prints the one-use setup link. On a remote server it can be reached through an approved SSH tunnel to the loopback port. It should not be substituted for the provided production WSGI/proxy services on an exposed interface. The web/worker backend is intended for POSIX/Linux/WSL; the original scientific core retains its documented portability.
