# Source inspection and trusted Python macros

The browser exposes selected scientific engine modules as read-only source. Ordinary physical parameters remain in forms, and advanced users can edit the complete project JSON, including `macro_parameters`.

Administrators can save a named Python macro version, inspect its source and explicitly enable that exact version. Versions are immutable rows with source hashes and an audit trail. Researchers can inspect and invoke enabled versions, but cannot install or approve executable source. Invocation records the exact code in the job input and workspace.

A macro defines:

```python
def apply(project):
    parameters = project.get("macro_parameters", {})
    project["config"]["targets"]["f01_GHz"] = float(parameters.get("target_GHz", 5.2))
    return project
```

It runs in a worker subprocess on a saved project revision and returns a proposed project document. The proposal is validated and written to `macro_result.json`; the live draft is not changed automatically. The user can review the result and choose **Apply proposed document to draft**, then save a revision. This avoids racing a calculation against another editor's draft changes.

Enabled Python is trusted server code with the worker account's filesystem and library access. It is not a sandbox, a restricted expression interpreter or an isolation boundary. Imports and custom calculations are available, so administrators must review code and treat enabled authors as trusted operators. The application does not expose an unrestricted Python console to every user.

Macros currently propose configuration/process changes and can perform arbitrary trusted calculations. They do not automatically replace the scientific stage dependency graph or turn an arbitrary GDS into a supported physical topology. To add a device family, implement a reviewed geometry/provider module and its contracts/tests in the repository, then expose its parameters. This preserves full Python access without claiming unsupported automatic simulation of all layouts.

## Custom analysis artifacts

Each macro receives the immutable project document as `project` and an absolute `ARTIFACTS_DIR` global pointing inside its own job workspace. Save extra CSV, JSON or PNG outputs there; the simulation artifact list exposes them through project authorization. For example:

```python
def apply(project):
    import json
    from pathlib import Path
    from sqw import circuit, geometry
    from sqw.studio.process import resolve

    cfg, _ = resolve(project)
    model = circuit.surrogate(cfg, geometry.build(cfg))
    parameters = circuit.parameters(cfg, model)
    (Path(ARTIFACTS_DIR) / "custom_parameters.json").write_text(
        json.dumps(parameters, indent=2)
    )
    return project
```

This supports project-specific analysis and parameter scans with ordinary open Python libraries on the remote worker. A macro shares the job's resource reservation and cancellation mechanism. Its source and generated artifacts stay with the historical job. The returned document must pass the process/configuration contract before it becomes an applicable proposal.
