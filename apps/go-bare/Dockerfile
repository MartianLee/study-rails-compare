FROM golang:1.25-bookworm AS build
WORKDIR /src
COPY go.mod ./
RUN go mod download 2>/dev/null || true
COPY . .
RUN go mod tidy && CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/server .

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*
COPY --from=build /out/server /usr/local/bin/server
EXPOSE 3000
CMD ["/usr/local/bin/server"]
