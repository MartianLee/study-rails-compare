FROM golang:1.25-bookworm AS build
WORKDIR /src
# go.mod and go.sum are committed, so the build is pinned and reproducible
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/server .

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*
COPY --from=build /out/server /usr/local/bin/server
EXPOSE 3000
CMD ["/usr/local/bin/server"]
