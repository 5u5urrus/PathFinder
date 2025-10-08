//go:build !headless

package main

import "time"

func StartRenderManager(_ *Crawler, _ int, _ time.Duration) {
	// no-op in non-headless builds
}
