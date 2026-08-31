FROM golang:1.25-bookworm AS build
WORKDIR /src
COPY go.mod ./
COPY main.go ./
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/loadgen .

FROM debian:bookworm-slim
COPY --from=build /out/loadgen /usr/local/bin/loadgen
ENTRYPOINT ["/usr/local/bin/loadgen"]
