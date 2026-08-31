// A minimal, dependency-free HTTP load generator.
//
// It lives in this repo on purpose: a benchmark whose measuring instrument is a
// third-party image nobody can pin is not evidence. Everything it reports —
// throughput, latency percentiles, error counts — comes from the code below.
//
//	loadgen -url http://rails:3000/api/posts?page=1 -c 8 -d 10s -warmup 3s
//
// Prints one JSON object on stdout. Everything else goes to stderr.
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"math/rand"
	"net"
	"net/http"
	"os"
	"sort"
	"sync"
	"sync/atomic"
	"time"
)

type result struct {
	URL          string  `json:"url"`
	Method       string  `json:"method"`
	Concurrency  int     `json:"concurrency"`
	DurationSec  float64 `json:"duration_s"`
	Completed    int64   `json:"completed"`
	Non2xx       int64   `json:"non_2xx"`
	Errors       int64   `json:"errors"`
	BytesOut     int64   `json:"bytes_read"`
	RPS          float64 `json:"rps"`
	MeanMs       float64 `json:"mean_ms"`
	P50Ms        float64 `json:"p50_ms"`
	P90Ms        float64 `json:"p90_ms"`
	P95Ms        float64 `json:"p95_ms"`
	P99Ms        float64 `json:"p99_ms"`
	MaxMs        float64 `json:"max_ms"`
	SampleBody   string  `json:"sample_body,omitempty"`
	SampleStatus int     `json:"sample_status,omitempty"`
}

func pct(sorted []float64, p float64) float64 {
	if len(sorted) == 0 {
		return 0
	}
	i := int(p * float64(len(sorted)))
	if i >= len(sorted) {
		i = len(sorted) - 1
	}
	return sorted[i]
}

func main() {
	url := flag.String("url", "", "target URL")
	method := flag.String("method", "GET", "HTTP method")
	body := flag.String("body", "", "request body template; %d is replaced by a per-request counter")
	ctype := flag.String("content-type", "application/json", "Content-Type for a body")
	conc := flag.Int("c", 8, "concurrent connections")
	dur := flag.Duration("d", 10*time.Second, "measurement window")
	warm := flag.Duration("warmup", 3*time.Second, "warm-up window, not measured")
	sample := flag.Bool("sample", false, "include one response body in the output")
	flag.Parse()
	if *url == "" {
		fmt.Fprintln(os.Stderr, "-url is required")
		os.Exit(2)
	}

	tr := &http.Transport{
		MaxIdleConns:        *conc * 2,
		MaxIdleConnsPerHost: *conc * 2,
		MaxConnsPerHost:     *conc * 2,
		IdleConnTimeout:     90 * time.Second,
		DisableCompression:  true,
		DialContext:         (&net.Dialer{Timeout: 5 * time.Second, KeepAlive: 30 * time.Second}).DialContext,
	}
	client := &http.Client{Transport: tr, Timeout: 30 * time.Second}

	var counter int64
	do := func(collect *[]float64, completed, non2xx, errs, nbytes *int64) {
		n := atomic.AddInt64(&counter, 1)
		var rdr io.Reader
		if *body != "" {
			rdr = bytes.NewReader([]byte(fmt.Sprintf(*body, n, rand.Int63())))
		}
		req, err := http.NewRequest(*method, *url, rdr)
		if err != nil {
			atomic.AddInt64(errs, 1)
			return
		}
		if *body != "" {
			req.Header.Set("Content-Type", *ctype)
		}
		t0 := time.Now()
		resp, err := client.Do(req)
		if err != nil {
			atomic.AddInt64(errs, 1)
			return
		}
		nb, _ := io.Copy(io.Discard, resp.Body)
		resp.Body.Close()
		el := float64(time.Since(t0).Microseconds()) / 1000.0
		if collect != nil {
			*collect = append(*collect, el)
		}
		atomic.AddInt64(completed, 1)
		atomic.AddInt64(nbytes, nb)
		if resp.StatusCode < 200 || resp.StatusCode >= 300 {
			atomic.AddInt64(non2xx, 1)
		}
	}

	// ---- warm-up: same code path, results thrown away
	if *warm > 0 {
		var c, n, e, b int64
		ctx, cancel := context.WithTimeout(context.Background(), *warm)
		var wg sync.WaitGroup
		for i := 0; i < *conc; i++ {
			wg.Add(1)
			go func() {
				defer wg.Done()
				for ctx.Err() == nil {
					do(nil, &c, &n, &e, &b)
				}
			}()
		}
		wg.Wait()
		cancel()
		fmt.Fprintf(os.Stderr, "warmup: %d requests, %d non-2xx, %d errors\n", c, n, e)
	}

	// ---- measurement window
	var completed, non2xx, errs, nbytes int64
	lat := make([][]float64, *conc)
	ctx, cancel := context.WithTimeout(context.Background(), *dur)
	defer cancel()
	start := time.Now()
	var wg sync.WaitGroup
	for i := 0; i < *conc; i++ {
		wg.Add(1)
		go func(slot int) {
			defer wg.Done()
			buf := make([]float64, 0, 4096)
			for ctx.Err() == nil {
				do(&buf, &completed, &non2xx, &errs, &nbytes)
			}
			lat[slot] = buf
		}(i)
	}
	wg.Wait()
	elapsed := time.Since(start).Seconds()

	all := make([]float64, 0, completed)
	for _, s := range lat {
		all = append(all, s...)
	}
	sort.Float64s(all)
	var sum float64
	for _, v := range all {
		sum += v
	}
	res := result{
		URL: *url, Method: *method, Concurrency: *conc, DurationSec: elapsed,
		Completed: completed, Non2xx: non2xx, Errors: errs, BytesOut: nbytes,
		RPS:   float64(completed) / elapsed,
		P50Ms: pct(all, 0.50), P90Ms: pct(all, 0.90), P95Ms: pct(all, 0.95),
		P99Ms: pct(all, 0.99),
	}
	if len(all) > 0 {
		res.MeanMs = sum / float64(len(all))
		res.MaxMs = all[len(all)-1]
	}
	if *sample {
		req, _ := http.NewRequest(*method, *url, nil)
		if r, err := client.Do(req); err == nil {
			b, _ := io.ReadAll(io.LimitReader(r.Body, 4096))
			r.Body.Close()
			res.SampleBody, res.SampleStatus = string(b), r.StatusCode
		}
	}
	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	enc.Encode(res)
}
