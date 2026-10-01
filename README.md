# Pipeline Pulse

A small, good-looking static site (Go backend + htmx frontend) that doubles as a reference
**DevSecOps pipeline** on GitHub Actions: lint, test, SonarQube, build, Trivy, Red Hat ACS (RHACS),
deploy and Falco runtime security, with a rich summary on every run.

The page explains the pipeline itself: click a stage and htmx fetches its description from the Go server.

---

## 1. Project layout

| Path | What it is |
|---|---|
| `main.go` | Go server. Serves the embedded `static/` folder, `GET /stages/{id}` (HTML fragments for htmx), `GET /healthz`. Adds security headers and sane timeouts. |
| `main_test.go` | Unit tests for the routes and headers. |
| `static/index.html`, `static/style.css` | The page. htmx loads from unpkg (pinned to 2.0.4). No inline scripts or styles, so the CSP stays strict. |
| `Dockerfile` | Multi-stage build to a distroless, non-root image. |
| `k8s/deployment.yaml` | Namespace, Deployment (non-root, read-only filesystem, dropped capabilities, probes, limits) and Service. `IMAGE_PLACEHOLDER` is replaced with the verified image digest at deploy time. |
| `falco/custom-rules.yaml` | Two Falco rules for the app namespace: a shell inside a container, and unexpected outbound connections. |
| `sonar-project.properties` | SonarQube project config and coverage report path. |
| `.golangci.yml` | golangci-lint v2 config (defaults plus `gosec` and `revive`). |
| `.github/workflows/` | The pipeline, one file per stage (section 3). |
| `.github/dependabot.yml` | Weekly updates for Actions, Go modules and Docker base images. |
| `scripts/step-row.sh` | Prints one markdown table row with a status icon, used by every summary. |
| `scripts/summarize_tests.py` | Turns `go test -json` output into a summary table. |
| `scripts/trivy_report.py` | Counts Trivy findings (the gate) and renders the findings table. |
| `scripts/check-workflows.py` | Offline checker for the workflow files (section 8). |
| `Makefile` | Local shortcuts: `run`, `test`, `lint`, `docker`, `check`. |

## 2. The application

- **Backend:** standard-library `net/http` with Go 1.22+ routing patterns. `go:embed` bakes `static/` into the binary, so the container needs nothing else.
- **Frontend:** the stage buttons use `hx-get` and `hx-target="#detail"`; the server replies with a small HTML fragment and htmx swaps it in. The first stage loads on page load.
- **Security headers:** a Content-Security-Policy that only allows self, unpkg (htmx) and Google Fonts, plus `nosniff`, `no-referrer` and `frame-ancestors 'none'`.
- **Design:** sage background, deep teal ink, cobalt and amber accents, Bricolage Grotesque type. The one animated moment is the pipeline rail lighting up on load; reduced-motion is respected.

Run it: `go run .` then open http://localhost:8080 (set `PORT` to change the port).

or if you already use port 8080 

PORT=8090 go run . 


## 3. The pipeline

`pipeline.yml` is the only workflow with triggers. It calls the others as reusable workflows, so the
whole run appears as one graph in the Actions tab while each stage stays in its own small file.

```
lint ─┐
test ─┼─> build ─> trivy ─┐
test ─> sonarqube ────────┼─> publish ─> rhacs ─> deploy ─> falco
                          ┘
(summary job always runs last and writes the overview)
```

| File | Job | What it does | Fails when |
|---|---|---|---|
| `pipeline.yml` | orchestrator + `summary` | Triggers, concurrency, job order, final overview table. | Never fails by itself. |
| `lint.yml` | lint | golangci-lint, hadolint (Dockerfile), shellcheck (scripts). | Any linter reports an issue. |
| `test.yml` | test | `go test -race` with coverage, uploads `coverage.out`. | A test fails. |
| `sonarqube.yml` | sonarqube | Scans with the test coverage, then waits for the quality gate. | The quality gate fails. |
| `build.yml` | build | Builds the image with Buildx and layer caching, saves it as a tar. Nothing is pushed yet. | The image does not build. |
| `trivy.yml` | trivy | Scans source, secrets and IaC, and the image. Uploads SARIF to the Security tab. | Any fixable HIGH or CRITICAL finding. |
| `publish.yml` | publish | Pushes the already-scanned image to GHCR and outputs `repo@sha256:digest`. | Push fails. |
| `rhacs.yml` | rhacs | Installs `roxctl` from Central, then runs image scan, image policy check and deployment policy check. | An enforced RHACS policy is violated. |
| `deploy.yml` | deploy | Applies the manifest using the digest, waits for rollout, rolls back on failure. | Rollout does not become ready. |
| `falco.yml` | falco | Installs or upgrades Falco with the custom rules, then runs a self-test. | Helm install fails. The self-test is reported but does not fail the run. |

Design choices worth knowing:
- The image is scanned **before** it is pushed (build to tar, scan the tar, then publish). RHACS then checks the pushed image because Central pulls it from the registry.
- Deploy and RHACS use the **digest**, so what runs in the cluster is exactly what was scanned.
- Fork pull requests skip SonarQube because forks cannot read secrets.

## 4. Triggers

| Trigger | Stages that run |
|---|---|
| Pull request to `main` | lint, test, sonarqube, build, trivy. No publish and no deploy. |
| Push to `main` | Everything, including publish, rhacs, deploy, falco. |
| Tag `v*` | Everything up to rhacs. The image also gets the tag name. Deploy runs only from `main`. |
| Manual (`workflow_dispatch`) | Everything. Deploy runs only when started from `main`. |
| Monday 03:00 UTC (cron) | lint, test, sonarqube, build, trivy only, to catch newly published CVEs. |

A new push cancels an older run on the same branch only for pull requests, so deploys are never cancelled halfway.

## 5. Runners

| Stages | Runner | Why |
|---|---|---|
| lint, test, sonarqube, build, trivy, publish, rhacs, summary | `ubuntu-latest` (GitHub-hosted) | No cluster access needed. |
| deploy, falco | Self-hosted, labels `self-hosted, linux, x64, k8s` | Needs `kubectl` and `helm` with access to the cluster. |

Set up the self-hosted runner: Settings, Actions, Runners, New self-hosted runner, add the label `k8s`,
install `kubectl` and `helm`, and give it a kubeconfig for a service account allowed to manage the
`pipeline-pulse` and `falco` namespaces. To use different labels, create a repository variable
`DEPLOY_RUNNER_LABELS` with a JSON array such as `["self-hosted","linux","arm64","prod"]`.

If your SonarQube is only reachable inside your network, change `runs-on` in `sonarqube.yml` to the same self-hosted labels.

## 6. Secrets, variables and settings

| Name | Where | Used by |
|---|---|---|
| `SONAR_TOKEN` | Secret | sonarqube |
| `SONAR_HOST_URL` | Secret | sonarqube (for example `https://sonar.example.com`) |
| `ROX_API_TOKEN` | Secret | rhacs (an RHACS API token with permission to run image and deployment checks) |
| `ROX_CENTRAL_ADDRESS` | Secret | rhacs (`host:port`, for example `central.example.com:443`) |
| `DEPLOY_RUNNER_LABELS` | Variable (optional) | deploy, falco |
| `production` environment | Settings, Environments | deploy. Add required reviewers for a manual approval gate. |
| Workflow permissions | Settings, Actions | Packages write is requested per job; nothing else to change. |

`GITHUB_TOKEN` is automatic. Security-tab upload needs code scanning, which is free on public repos and
part of GitHub Advanced Security on private ones; the upload step is allowed to fail so the pipeline still works without it.

## 7. Tool setup notes

**SonarQube.** Create a project with key `pipeline-pulse` (or change `sonar-project.properties`), generate a token, and use the server URL as `SONAR_HOST_URL`.

**RHACS.** In Central, create an API token with the `Admin` or a suitably scoped role. Add GHCR as an image integration (a GitHub PAT with `read:packages`) so Central can pull and scan the pushed image. Enable "build" stage enforcement on the policies that should block the pipeline. For a self-signed Central certificate, set `ROX_INSECURE_CLIENT_SKIP_TLS_VERIFY=true` in the rhacs job environment (not for production).

**Falco.** The workflow installs the official Helm chart with the `modern_ebpf` driver, which needs a reasonably recent Linux kernel on the nodes. Alerts go to the Falco pod logs; view them with `kubectl -n falco logs -l app.kubernetes.io/name=falco -c falco`. Forward them with Falcosidekick if you want Slack or a SIEM.

## 8. Step summaries

Every job writes markdown to `$GITHUB_STEP_SUMMARY`, shown on the run page:

- **Lint:** a pass/fail row per linter.
- **Test:** passed, failed, skipped counts, total coverage and the names of failed tests.
- **SonarQube:** analysis and quality gate result.
- **Build:** image name, archive size and checksum.
- **Trivy:** a findings table (severity, CVE or rule, package, fixed version) for source and image, and the gate rule.
- **Publish:** the immutable image reference.
- **RHACS:** a row per check plus the full `roxctl` output in collapsible blocks.
- **Deploy:** rollout result and `kubectl get deploy,pods,svc`.
- **Falco:** install result, self-test result and pod list.
- **Pipeline overview:** one table of every stage with a status icon (✅ passed, ❌ failed, ⏭️ skipped).

## 9. Verify everything locally

```
make test      # go test -race -cover ./...
make lint      # needs golangci-lint v2
make check     # offline workflow checks and script compile (needs PyYAML and shellcheck)
make docker    # builds the image
make run       # starts the site on :8080
```

`scripts/check-workflows.py` confirms that every workflow parses, every `needs` target exists, every
reusable workflow is called with exactly the inputs it declares, required inputs and secrets are passed,
and every `scripts/` file referenced by a workflow exists.

## 10. Hardening before production

- Pin every action to a full commit SHA (Dependabot will keep the SHAs fresh) and pin the base images by digest.
- Vendor htmx into `static/` and drop unpkg from the CSP in `main.go`.
- Add branch protection on `main` requiring the `pipeline` checks.
- Add a registry-side image signing step (cosign) if you need provenance.

## 11. Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| sonarqube fails immediately | `SONAR_TOKEN` or `SONAR_HOST_URL` missing, or the server is not reachable from GitHub-hosted runners. |
| trivy fails on a finding you cannot fix | Add a reviewed `.trivyignore` entry, or update the base image. |
| Upload SARIF step is red but the job continues | Code scanning is not enabled for the repo. |
| rhacs cannot pull the image | GHCR integration missing in Central, or the package is private without credentials. |
| deploy job queued forever | No online self-hosted runner has all of the configured labels. |
| Falco self-test says failed | The test pod was blocked by pod security, or the driver is not loaded. Check `kubectl -n falco logs`. |
