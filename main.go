// Package main serves the Pipeline Pulse site.
package main

import (
	"embed"
	"html/template"
	"io/fs"
	"log"
	"net/http"
	"os"
	"time"
)

//go:embed static
var assets embed.FS

// Stage describes one step of the DevSecOps pipeline.
type Stage struct {
	Name, Tool, Summary, Gate string
}

var stages = map[string]Stage{
	"lint":   {"Lint", "golangci-lint", "Catches bugs, unchecked errors and insecure patterns (gosec) before a human reviews the code.", "Blocks when any linter reports an issue."},
	"test":   {"Test", "go test -race", "Runs unit tests with the race detector and publishes coverage.", "Blocks when a test fails."},
	"sonar":  {"Code quality", "SonarQube", "Analyses bugs, vulnerabilities, code smells and coverage against a quality gate.", "Blocks when the quality gate fails."},
	"build":  {"Build", "Docker Buildx", "Builds a small, non-root, distroless image with layer caching.", "Blocks when the image does not build."},
	"trivy":  {"Vulnerability scan", "Trivy", "Scans source, secrets, config and the image for known CVEs, then uploads results to the Security tab.", "Blocks on a fixable HIGH or CRITICAL finding."},
	"rhacs":  {"Policy check", "Red Hat ACS (roxctl)", "Checks the pushed image and the Kubernetes manifest against cluster security policies.", "Blocks when an enforced policy is violated."},
	"deploy": {"Deploy", "kubectl on a self-hosted runner", "Rolls out the exact image digest that passed every earlier gate.", "Blocks when the rollout does not become ready."},
	"falco":  {"Runtime", "Falco", "Watches the running pod for surprises such as a shell or unexpected outbound traffic.", "Nothing blocks here; Falco raises an alert while the pod runs."},
}

var detail = template.Must(template.New("detail").Parse(
	`<h2>{{.Name}}</h2><p class="tool">{{.Tool}}</p><p>{{.Summary}}</p><p class="gate">{{.Gate}}</p>`))

func stageHandler(w http.ResponseWriter, r *http.Request) {
	s, ok := stages[r.PathValue("id")]
	if !ok {
		http.NotFound(w, r)
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	if err := detail.Execute(w, s); err != nil {
		log.Printf("render: %v", err)
	}
}

func newMux() *http.ServeMux {
	mux := http.NewServeMux()
	sub, err := fs.Sub(assets, "static")
	if err != nil {
		log.Fatal(err)
	}
	mux.Handle("GET /", http.FileServerFS(sub))
	mux.HandleFunc("GET /stages/{id}", stageHandler)
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte("ok"))
	})
	return mux
}

// secure adds baseline security headers to every response.
func secure(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		h := w.Header()
		h.Set("Content-Security-Policy", "default-src 'self'; script-src 'self' https://unpkg.com; style-src 'self' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; frame-ancestors 'none'")
		h.Set("X-Content-Type-Options", "nosniff")
		h.Set("Referrer-Policy", "no-referrer")
		next.ServeHTTP(w, r)
	})
}

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}
	srv := &http.Server{
		Addr:              ":" + port,
		Handler:           secure(newMux()),
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       10 * time.Second,
		WriteTimeout:      10 * time.Second,
		IdleTimeout:       60 * time.Second,
	}
	log.Printf("listening on %s", srv.Addr)
	log.Fatal(srv.ListenAndServe())
}
