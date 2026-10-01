.PHONY: run test lint docker check
run:
	go run .
test:
	go test -race -cover ./...
lint:
	golangci-lint run
docker:
	docker build -t pipeline-pulse:dev .
check:
	python3 scripts/check-workflows.py
	python3 -m py_compile scripts/*.py
	shellcheck scripts/*.sh
