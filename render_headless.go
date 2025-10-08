//go:build headless

package main

import (
	"context"
	"net/url"
	"regexp"
	"strings"
	"time"

	"github.com/chromedp/cdproto/fetch"
	"github.com/chromedp/cdproto/network"
	"github.com/chromedp/chromedp"
	"github.com/gocolly/colly/v2"
)

// StartRenderManager spins up a headless Chrome and selectively renders pages.
// Heuristics: small HTML responses likely to be SPAs, plus the start URL.
// We block heavy assets (images/css/media/fonts) to keep rendering light.
func StartRenderManager(c *Crawler, budget int, perPage time.Duration) {
	if budget <= 0 {
		budget = 6
	}
	if perPage <= 0 {
		perPage = 8 * time.Second
	}

	// queue of pages to render
	queue := make(chan string, 64)
	seenRender := NewStringFilter()

	// Seed with the start URL
	queue <- c.site.String()

	// Heuristic: enqueue HTML pages that look small (common for SPA shells)
	c.C.OnResponse(func(r *colly.Response) {
		if budget <= 0 {
			return
		}
		ct := strings.ToLower(r.Headers.Get("Content-Type"))
		if strings.Contains(ct, "text/html") && len(r.Body) < 60*1024 {
			select {
			case queue <- r.Request.URL.String():
			default:
				// queue full -> skip
			}
		}
	})

	go func() {
		// Build a browser context
		ctx, cancel := chromedp.NewContext(context.Background())
		defer cancel()

		// Enable Network & Fetch interception (to block heavy resources)
		if err := chromedp.Run(ctx,
			network.Enable(),
			fetch.Enable().WithPatterns([]*fetch.RequestPattern{
				{URLPattern: "*"}, // intercept everything; we’ll filter by resource type
			}),
		); err != nil {
			// If Chrome fails to start, just bail out silently
			return
		}

		// Listen for requests: block heavy types; forward XHR/Fetch URLs back to crawler
		chCtx, chCancel := context.WithCancel(ctx)
		defer chCancel()

		chromedp.ListenTarget(chCtx, func(ev interface{}) {
			switch e := ev.(type) {
			case *fetch.EventRequestPaused:
				// Block heavy resource types to keep the render lean
				switch e.ResourceType {
				case network.ResourceTypeImage,
					network.ResourceTypeStylesheet,
					network.ResourceTypeMedia,
					network.ResourceTypeFont:
					_ = fetch.FailRequest(e.RequestID, network.ErrorReasonBlockedByClient).Do(chCtx)
				default:
					_ = fetch.ContinueRequest(e.RequestID).Do(chCtx)
				}

			case *network.EventRequestWillBeSent:
				// Capture in-scope XHR/Fetch URLs (JS-driven endpoints)
				if e.Type == network.ResourceTypeXHR || e.Type == network.ResourceTypeFetch {
					reqURL := e.Request.URL
					if inScopeStr(reqURL, c.C.URLFilters) && !c.urlSet.Duplicate(reqURL) {
						// Feed back to the crawler
						_ = c.C.Visit(reqURL)
						// Emit via filter so --types works
						c.emitLine("network", "[network] - "+reqURL)
					}
				}
			}
		})

		for budget > 0 {
			select {
			case u := <-queue:
				if u == "" || seenRender.Duplicate(u) {
					continue
				}
				if !inScopeStr(u, c.C.URLFilters) {
					continue
				}

				// Emit a render marker (respects --types/--exclude-types)
				c.emitLine("render", "[render] - "+u)

				// Navigate and give the page a short window to load & fire its XHR
				pageCtx, cancelPage := context.WithTimeout(ctx, perPage)
				_ = chromedp.Run(pageCtx,
					chromedp.Navigate(u),
					chromedp.WaitReady("body", chromedp.ByQuery),
					chromedp.Sleep(1500*time.Millisecond), // simple "network idle" window
				)
				cancelPage()
				budget--

			case <-time.After(3 * time.Second):
				// idle tick; loop again until budget exhausted
			}
		}
	}()
}

// Helpers
func inScopeStr(raw string, filters []*regexp.Regexp) bool {
	u, err := url.Parse(raw)
	if err != nil {
		return false
	}
	return InScope(u, filters)
}
