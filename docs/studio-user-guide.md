# Browser user guide

## Access and accounts

The server administrator opens the one-time setup link during installation and creates the first account. There is no anonymous registration. Administrators create one-use activation links in **People & access** and share them through the group's normal channel; the application does not send email.

Researchers can create projects and run jobs in projects they own or can edit. Viewers can inspect projects shared with them but cannot change drafts, launch jobs or consolidate results. Project owners and administrators manage project membership. Administrators can disable accounts and revoke their sessions. A minimum of one active administrator is retained.

## Drafts and revisions

A new project starts with the documented Al-on-Si transmon template. The device and process forms autosave changes. **Draft saved** indicates the server accepted them. An incomplete or invalid physical parameter is allowed in the draft, but the workflow map identifies what blocks execution.

If another editor saves a newer draft, an outdated save is rejected rather than silently replacing it. Reload the project and reconcile the changes. The current UI does not merge simultaneous edits automatically.

**Save revision** records an immutable snapshot and a note. Starting a job also snapshots the current saved draft. **History & sharing → Restore to draft** copies an old revision back into the editable draft; it does not delete later revisions or simulations. Continue editing and save another revision to create a new branch.

## Workflow map

Each phase has a description, current status, and specific blocking input/tool messages. Choose analytical preview or full FEM and configure CPU/memory reservations. The worker runs the required predecessor stages in dependency order, not every unrelated phase.

- **Ready:** the phase can be requested.
- **Queued/running:** remote work is pending or active.
- **Computed:** a compatible numerical result exists.
- **Consolidated:** a user recorded a review note for that result.
- **Stale:** older results exist, but their parameter signatures differ from the current draft.
- **Blocked:** required inputs or server tools are missing.

Consolidation records scientific review, not process sign-off or a fabrication certificate. An analytical surrogate can be reviewed as a software/model exercise while remaining a surrogate.

## Simulations and checkpoints

**Run to report** starts the integrated calculation through the report phase. Individual **Run** buttons stop at the chosen stage. The simulation table shows the immutable revision, target, resource request and job state. Open a job to follow its live log, view generated layout/measurement images, read the report or download numerical artifacts.

The progress percentage measures completed stages. It does not pretend to know how far a native eigensolver is through an iteration. Native solver logs/field outputs remain downloadable. Full 3D field inspection still uses a suitable viewer such as ParaView; a browser-based volume-field viewer is not included.

Closing the browser does not cancel a job. A web-service restart does not stop the separate worker service. **Cancel** requests process-group termination. A worker/host interruption is recorded as interrupted and can retain completed stages. A native solve cannot generally resume halfway through its internal iteration; the failed stage is rerun while compatible completed upstream stages are reused.

Select **Reuse** on a finalized job or choose an explicit checkpoint in execution settings. The latest finalized checkpoint is used by default. A change to intrinsic T1, for example, can reuse layout, EM inputs and the quantum model while recomputing expected measurements. A geometric change invalidates dependent stages. Reuse checks include source/dependency identity; it is deliberately conservative.

## Process, assets and code

Use **Process & junction** for die/wafer rules and generated mask candidates. Upload logos or laboratory GDS cells in **Assets**, then select them in the process editor. The declared process values are applied to the scientific configuration; conflicting duplicate chip/Jc inputs are not maintained independently in the basic device form.

Use **Code & macros** to inspect source and invoke reviewed extensions. The optional advanced project JSON editor exposes fields and macro parameters beyond the ordinary forms. Python macro activation is reserved for trusted administrators.

## Save or transfer the whole project

**Export project** creates a capsule containing the current draft, revisions, uploaded assets, job metadata, completed results and finalized workspaces. It works for projects stopped before the last phase. Active calculations continue on the server; their in-flight files are omitted to avoid pretending that a live solver workspace is a consistent snapshot.

**Import project capsule** creates a separate project. Historical results remain available, but imported consolidations need local review. Asset and job identities are remapped. Macros recorded in historical jobs are not automatically enabled as executable server extensions.

Default upload limits are 32 MiB per asset and 512 MiB per project capsule, with an 8 GiB expanded capsule limit. The server administrator can increase capsule limits. Large native field datasets may require an agreed server transfer or full-volume backup. The job view lists up to 2000 files; the project capsule retains the finalized workspace.
