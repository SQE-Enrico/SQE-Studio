# Current architecture

| Concern | Owner | Typical entry |
|---|---|---|
| Local HTTP service | server.py + http_api/ | make_server / handler.call |
| Authentication and request bounds | http_api/handler.py | security / json_body |
| HTTP routing | http_api/router.py | public_route / authenticated_route |
| Project revisions | contracts.py + store.py | fresh_project / Store.commit |
| Quantum research endpoints | http_api/quantum.py, extraction.py | declare_independent / extract |
| Verified results and comparisons | http_api/results.py, comparisons.py, fields.py | inspect / compare |
| Native jobs | jobs.py + worker.py | Jobs.start / worker.run |
| Artifact, sweep and optimization policy | orchestration/ | verify_manifest / sweep/optimization |
| Native integrations | adapters/ | registry.REGISTRY |
| Scientific provenance and reduction | interop/ | extracted_transmon / transmon_reduction |
| UI state and shared helpers | web/app.js | api / activeModel |
| UI concerns | web/modules/ | workspace, fields, extraction, editors, results |
| UI delivery | web_assets.py + web/modules.json | javascript_bundle |
| Automatic Test | testing/ | catalog / runner / task_worker |
| Current source integrity | governance.py + tools/verify_release_source.py | check / verify |

The HTTP request passes loopback/Host/Origin validation, bounded parsing,
session authentication, and CSRF before any private resource handler executes.
Resource modules receive an immutable Request description and the handler;
they use the same authenticated Store and Jobs objects. Native computation
remains in isolated worker processes. Results are revision/hash checked before
scientific readers consume them.

The UI modules are plain classic-script source parts with explicit shared state
in app.js. They retain the exact dev78 source order and function bodies.
web_assets.py concatenates the manifest order into the existing /app.js response;
there is no eval, framework, network dependency or checked-in generated copy.
Each file owns a feature group. These are source boundaries sharing the existing
controller scope, not a claim that all UI state has become isolated ES modules.
Further state isolation can be done feature by feature with the same tests.

PROJECT_MAP.json maps work to code/tests. tools/context.py indexes declarations
without importing the native toolchain and emits bounded excerpts. Large stable
scientific adapters remain intact; inspect the needed symbol instead of loading
the entire file. The current core hash map and frozen contracts protect them.

Historical dispatch/delivery/review trees and obsolete agent-delta CLI tooling
are removed. The active scientific case matrix lives in config/. Scientific
fixtures remain because regression tests use them, not as product history.
