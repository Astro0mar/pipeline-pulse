FROM golang:1.23-alpine AS build
WORKDIR /src
COPY . .
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/site .

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /out/site /site
USER nonroot:nonroot
EXPOSE 8080
ENTRYPOINT ["/site"]
