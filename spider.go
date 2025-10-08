package main

import (
	"bufio"
	"crypto/tls"
	"encoding/json"
	"encoding/xml"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"path"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"time"

	jsoniter "github.com/json-iterator/go"
	"github.com/gocolly/colly/v2"
	"github.com/gocolly/colly/v2/extensions"
	"github.com/mitchellh/go-homedir"
	prefixed "github.com/x-cray/logrus-prefixed-formatter"
	"golang.org/x/net/publicsuffix"

	"github.com/sirupsen/logrus"
	"github.com/spf13/cobra"
)

/* ============================== Logger ============================== */

var Logger *logrus.Logger

func init() {
	logger := logrus.New()
	logger = &logrus.Logger{
		Out:   os.Stderr,
		Level: logrus.InfoLevel,
		Formatter: &prefixed.TextFormatter{
			ForceColors:     true,
			ForceFormatting: true,
		},
	}
	Logger = logger
}

/* ============================== Output ============================== */

type Output struct {
	mu     sync.Mutex
	f      *os.File
	writer *bufio.Writer
}

func NewOutput(folder, filename string) *Output {
	outFile := filepath.Join(folder, strings.ReplaceAll(filename, string(os.PathSeparator), "_"))
	f, err := os.OpenFile(outFile, os.O_APPEND|os.O_CREATE|os.O_WRONLY, os.ModePerm)
	if err != nil {
		Logger.Errorf("Failed to open file to write Output: %s", err)
		os.Exit(1)
	}
	writer := bufio.NewWriter(f)
	return &Output{f: f, writer: writer}
}
func (o *Output) WriteToFile(msg string) {
	o.mu.Lock()
	defer o.mu.Unlock()
	_, _ = o.writer.WriteString(msg + "\n")
}
func (o *Output) Flush() {
	o.mu.Lock()
	defer o.mu.Unlock()
	_ = o.writer.Flush()
}
func (o *Output) Close() {
	o.Flush()
	_ = o.f.Close()
}

/* ============================== Emit filter (optional) ============================== */

type EmitFilter struct {
	allowAll bool
	allow    map[string]struct{}
	deny     map[string]struct{}
}

func NewEmitFilter(includeCSV, excludeCSV string) *EmitFilter {
	f := &EmitFilter{allow: map[string]struct{}{}, deny: map[string]struct{}{}}
	trim := func(s string) string { return strings.TrimSpace(strings.ToLower(s)) }
	if strings.TrimSpace(includeCSV) == "" {
		f.allowAll = true
	} else {
		for _, k := range strings.Split(includeCSV, ",") {
			if k = trim(k); k != "" {
				f.allow[k] = struct{}{}
			}
		}
	}
	for _, k := range strings.Split(excludeCSV, ",") {
		if k = trim(k); k != "" {
			f.deny[k] = struct{}{}
		}
	}
	return f
}
func (f *EmitFilter) OK(kind string) bool {
	kind = strings.ToLower(kind)
	if _, bad := f.deny[kind]; bad {
		return false
	}
	if f.allowAll {
		return true
	}
	_, ok := f.allow[kind]
	return ok
}

/* ============================== Deduper ============================== */

type StringFilter struct{ filter sync.Map }

func NewStringFilter() *StringFilter { return &StringFilter{} }

func (sf *StringFilter) Duplicate(s string) bool {
	key := strings.ToLower(s)
	_, loaded := sf.filter.LoadOrStore(key, struct{}{})
	return loaded
}

/* ============================== Globals for perf/noise ============================== */

// Compile once, reuse both for DisallowedURLFilters and for local skip checks
var disallowedExtRE = regexp.MustCompile(`(?i)\.(png|apng|bmp|gif|ico|cur|jpg|jpeg|jfif|pjp|pjpeg|svg|tif|tiff|webp|xbm|3gp|aac|flac|mpg|mpeg|mp3|mp4|m4a|m4v|m4p|oga|ogg|ogv|mov|wav|webm|eot|woff|woff2|ttf|otf|css)(?:\?|#|$)`)

// Soft cap: skip heavy regex scans (subdomain/AWS/linkfinder/raw) for huge bodies
const maxGrepBody = 4 * 1024 * 1024 // 4MB

// Singletons for small hot paths
var newlineRE = regexp.MustCompile(`[\t\r\n]+`)
var allowDisallowStripRE = regexp.MustCompile(`(?i).*llow:\s*`)
var decodeReplacer = strings.NewReplacer(`\u002f`, "/", `\u0026`, "&")

/* ============================== Crawler ============================== */

var DefaultHTTPTransport = &http.Transport{
	DialContext: (&net.Dialer{
		Timeout:   10 * time.Second,
		KeepAlive: 30 * time.Second,
	}).DialContext,
	MaxIdleConns:    100,
	MaxConnsPerHost: 1000,
	IdleConnTimeout: 30 * time.Second,
	TLSClientConfig: &tls.Config{
		InsecureSkipVerify: false, // secure by default
		Renegotiation:      tls.RenegotiateOnceAsClient,
	},
}

type Crawler struct {
	cmd                 *cobra.Command
	C                   *colly.Collector
	LinkFinderCollector *colly.Collector
	Output              *Output

	subSet  *StringFilter
	awsSet  *StringFilter
	jsSet   *StringFilter
	urlSet  *StringFilter
	formSet *StringFilter

	site       *url.URL
	domain     string
	Input      string
	Quiet      bool
	JsonOutput bool
	length     bool
	raw        bool

	filterLengthSlice []int
	emit              *EmitFilter
}

type SpiderOutput struct {
	Input      string `json:"input"`
	Source     string `json:"source"`
	OutputType string `json:"type"`
	Output     string `json:"output"`
	StatusCode int    `json:"status"`
	Length     int    `json:"length"`
}

func (crawler *Crawler) emitLine(kind, line string) {
	if !crawler.emit.OK(kind) {
		return
	}
	fmt.Println(line)
	if crawler.Output != nil {
		crawler.Output.WriteToFile(line)
	}
}

// small helper to unify [url] emission logic
func (crawler *Crawler) emitURL(status, length int, u string) {
	out := fmt.Sprintf("[url] - [code-%d] - %s", status, u)
	if crawler.length {
		out = fmt.Sprintf("[url] - [code-%d] - [len_%d] - %s", status, length, u)
	}
	if crawler.JsonOutput {
		sout := SpiderOutput{
			Input:      crawler.Input,
			Source:     "body",
			OutputType: "url",
			StatusCode: status,
			Output:     u,
			Length:     length,
		}
		if data, err := jsoniter.MarshalToString(sout); err == nil {
			out = data
		}
	} else if crawler.Quiet {
		out = u
	}
	crawler.emitLine("url", out)
}

// New: third param scopeOverride enables "bare-domain => auto-scope + subs"
func NewCrawler(site *url.URL, cmd *cobra.Command, scopeOverride *ScopeOverride) *Crawler {
	domain := GetDomain(site)
	if domain == "" {
		Logger.Error("Failed to parse domain")
		os.Exit(1)
	}
	Logger.Infof("Start crawling: %s", site)

	quiet, _ := cmd.Flags().GetBool("quiet")
	jsonOutput, _ := cmd.Flags().GetBool("json")
	maxDepth, _ := cmd.Flags().GetInt("depth")
	concurrent, _ := cmd.Flags().GetInt("concurrent")
	delay, _ := cmd.Flags().GetInt("delay")
	randomDelay, _ := cmd.Flags().GetInt("random-delay")
	length, _ := cmd.Flags().GetBool("length")
	raw, _ := cmd.Flags().GetBool("raw")
	// note: subs flag is used only if scopeOverride == nil
	flagSubs, _ := cmd.Flags().GetBool("subs")
	filterLengthStr, _ := cmd.Flags().GetString("filter-length")

	// optional filter flags
	typesCSV, _ := cmd.Flags().GetString("types")
	excludeCSV, _ := cmd.Flags().GetString("exclude-types")
	emit := NewEmitFilter(typesCSV, excludeCSV)

	c := colly.NewCollector(
		colly.Async(true),
		colly.MaxDepth(maxDepth),
		colly.IgnoreRobotsTxt(),
	)

	client := &http.Client{}
	t := *DefaultHTTPTransport

	// Proxy
	if proxy, _ := cmd.Flags().GetString("proxy"); proxy != "" {
		Logger.Infof("Proxy: %s", proxy)
		if pU, err := url.Parse(proxy); err == nil {
			t.Proxy = http.ProxyURL(pU)
		} else {
			Logger.Error("Failed to set proxy")
		}
	}

	// Timeout
	if to, _ := cmd.Flags().GetInt("timeout"); to <= 0 {
		Logger.Info("Your input timeout is 0. pathfinder will set it to 10 seconds")
		client.Timeout = 10 * time.Second
	} else {
		client.Timeout = time.Duration(to) * time.Second
	}

	// Redirect policy
	noRedirect, _ := cmd.Flags().GetBool("no-redirect")
	client.Transport = &t
	if noRedirect {
		client.CheckRedirect = func(req *http.Request, via []*http.Request) error {
			tgt := req.URL.Hostname()
			base := site.Hostname()
			allowSubs := flagSubs
			if scopeOverride != nil {
				allowSubs = scopeOverride.AllowSubs
			}
			same := tgt == base || (allowSubs && strings.HasSuffix(tgt, "."+base))
			if same {
				return nil
			}
			return http.ErrUseLastResponse
		}
	}
	c.SetClient(client)

	// BURP raw
	if burpFile, _ := cmd.Flags().GetString("burp"); burpFile != "" {
		if bF, err := os.Open(burpFile); err == nil {
			rd := bufio.NewReader(bF)
			if req, err := http.ReadRequest(rd); err == nil {
				c.OnRequest(func(r *colly.Request) { r.Headers.Set("Cookie", GetRawCookie(req.Cookies())) })
				c.OnRequest(func(r *colly.Request) {
					for k, v := range req.Header {
						if len(v) > 0 {
							r.Headers.Set(strings.TrimSpace(k), strings.TrimSpace(v[0]))
						}
					}
				})
			} else {
				Logger.Errorf("Failed to Parse Raw Request in %s: %s", burpFile, err)
			}
		} else {
			Logger.Errorf("Failed to open Burp File: %s", err)
		}
	}

	// Cookie flag
	if cookie, _ := cmd.Flags().GetString("cookie"); cookie != "" {
		c.OnRequest(func(r *colly.Request) { r.Headers.Set("Cookie", cookie) })
	}

	// Custom headers
	if headers, _ := cmd.Flags().GetStringArray("header"); len(headers) > 0 {
		for _, h := range headers {
			parts := strings.SplitN(h, ":", 2)
			if len(parts) != 2 {
				continue
			}
			headerKey := strings.TrimSpace(parts[0])
			headerValue := strings.TrimSpace(parts[1])
			c.OnRequest(func(r *colly.Request) { r.Headers.Set(headerKey, headerValue) })
		}
	}

	// UA
	switch ua := strings.ToLower(getFlagString(cmd, "user-agent", "web")); {
	case ua == "mobi":
		extensions.RandomMobileUserAgent(c)
	case ua == "web":
		extensions.RandomUserAgent(c)
	default:
		c.UserAgent = ua
	}
	extensions.Referer(c)

	// EXTRA: add some browsery headers (helps with simple 403/WAFs)
	c.OnRequest(func(r *colly.Request) {
		if r.Headers.Get("Accept") == "" {
			r.Headers.Set("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8")
		}
		if r.Headers.Get("Accept-Language") == "" {
			r.Headers.Set("Accept-Language", "en-US,en;q=0.9")
		}
		if r.Headers.Get("Upgrade-Insecure-Requests") == "" {
			r.Headers.Set("Upgrade-Insecure-Requests", "1")
		}
	})

	// Output file
	var output *Output
	if outputFolder, _ := cmd.Flags().GetString("output"); outputFolder != "" {
		filename := strings.ReplaceAll(site.Hostname(), ".", "_")
		output = NewOutput(outputFolder, filename)
	}

	// Length filter list
	var filterLengthSlice []int
	if filterLengthStr != "" {
		for _, s := range strings.Split(filterLengthStr, ",") {
			if v, err := strconvAtoiSafe(s); err == nil {
				filterLengthSlice = append(filterLengthSlice, v)
			}
		}
	}

	// ----- Scope setup -----
	// If you seed the apex (e.g., neopets.com), automatically include subdomains.
	if scopeOverride != nil {
		host := regexp.QuoteMeta(scopeOverride.Domain)
		var scope *regexp.Regexp
		if scopeOverride.AllowSubs {
			scope = regexp.MustCompile("^https?://([^.]+\\.)*" + host + "(?::\\d+)?(?:/|$)")
		} else {
			scope = regexp.MustCompile("^https?://" + host + "(?::\\d+)?(?:/|$)")
		}
		c.URLFilters = append(c.URLFilters, scope)
	} else {
		// auto-enable subs if seed == apex
		if strings.EqualFold(site.Hostname(), domain) {
			flagSubs = true
		}
	}

	// Block heavy/static
	c.DisallowedURLFilters = append(c.DisallowedURLFilters, disallowedExtRE)

	// Optional explicit whitelist/blacklist (takes precedence if set)
	if blacklists, _ := cmd.Flags().GetString("blacklist"); blacklists != "" {
		c.DisallowedURLFilters = append(c.DisallowedURLFilters, regexp.MustCompile(blacklists))
	}
	if whiteLists, _ := cmd.Flags().GetString("whitelist"); whiteLists != "" {
		c.URLFilters = []*regexp.Regexp{regexp.MustCompile(whiteLists)}
	}
	if whiteListDomain, _ := cmd.Flags().GetString("whitelist-domain"); whiteListDomain != "" {
		d := regexp.QuoteMeta(whiteListDomain)
		c.URLFilters = []*regexp.Regexp{regexp.MustCompile("^https?://"+d+"(?::\\d+)?(?:/|$)")}
	}

	// If no filters were set at all, set default scope:
	if len(c.URLFilters) == 0 {
		var scope *regexp.Regexp
		if flagSubs {
			apex := regexp.QuoteMeta(domain) // e.g., "neopets.com"
			scope = regexp.MustCompile("^https?://([^.]+\\.)*" + apex + "(?::\\d+)?(?:/|$)")
		} else {
			host := regexp.QuoteMeta(site.Hostname())
			scope = regexp.MustCompile("^https?://" + host + "(?::\\d+)?(?:/|$)")
		}
		c.URLFilters = append(c.URLFilters, scope)
	}

	// Limits
	if err := c.Limit(&colly.LimitRule{
		DomainGlob:  "*",
		Parallelism: concurrent,
		Delay:       time.Duration(delay) * time.Second,
		RandomDelay: time.Duration(randomDelay) * time.Second,
	}); err != nil {
		Logger.Errorf("Failed to set Limit Rule: %s", err)
		os.Exit(1)
	}

	// LinkFinder collector
	linkFinderCollector := c.Clone()
	linkFinderCollector.URLFilters = nil
	// Respect explicit whitelist if provided for JS collector too
	if whiteLists, _ := cmd.Flags().GetString("whitelist"); whiteLists != "" {
		linkFinderCollector.URLFilters = append(linkFinderCollector.URLFilters, regexp.MustCompile(whiteLists))
	}
	if whiteListDomain, _ := cmd.Flags().GetString("whitelist-domain"); whiteListDomain != "" {
		d := regexp.QuoteMeta(whiteListDomain)
		linkFinderCollector.URLFilters = append(linkFinderCollector.URLFilters, regexp.MustCompile("^https?://"+d+"(?::\\d+)?(?:/|$)"))
	}
	// If auto-scope but no explicit whitelist is set, also scope JS collector
	if scopeOverride != nil && len(linkFinderCollector.URLFilters) == 0 {
		host := regexp.QuoteMeta(scopeOverride.Domain)
		if scopeOverride.AllowSubs {
			linkFinderCollector.URLFilters = append(linkFinderCollector.URLFilters, regexp.MustCompile("^https?://([^.]+\\.)*"+host+"(?::\\d+)?(?:/|$)"))
		} else {
			linkFinderCollector.URLFilters = append(linkFinderCollector.URLFilters, regexp.MustCompile("^https?://"+host+"(?::\\d+)?(?:/|$)"))
		}
	}
	// Mirror the main collector's scope if none set explicitly for linkFinderCollector
	if len(linkFinderCollector.URLFilters) == 0 {
		linkFinderCollector.URLFilters = append(linkFinderCollector.URLFilters, c.URLFilters...)
	}

	return &Crawler{
		cmd:                 cmd,
		C:                   c,
		LinkFinderCollector: linkFinderCollector,
		site:                site,
		Quiet:               quiet,
		Input:               site.String(),
		JsonOutput:          jsonOutput,
		length:              length,
		raw:                 raw,
		domain:              domain,
		Output:              output,
		urlSet:              NewStringFilter(),
		subSet:              NewStringFilter(),
		jsSet:               NewStringFilter(),
		formSet:             NewStringFilter(),
		awsSet:              NewStringFilter(),
		filterLengthSlice:   filterLengthSlice,
		emit:                emit,
	}
}

func getFlagString(cmd *cobra.Command, name, def string) string {
	v, _ := cmd.Flags().GetString(name)
	if v == "" {
		return def
	}
	return v
}

/* ============================== Canonicalization ============================== */

func canonicalizeURL(u *url.URL) string {
	u2 := *u
	u2.Fragment = ""
	// drop default ports
	if (u2.Scheme == "http" && u2.Port() == "80") || (u2.Scheme == "https" && u2.Port() == "443") {
		u2.Host = u2.Hostname()
	}
	if u2.Path == "" {
		u2.Path = "/"
	}
	return u2.String()
}

/* ============================== Fetch via Colly (for robots/sitemap) ============================== */

func fetchOnce(parent *colly.Collector, u string) (body []byte, status int, err error) {
	ch := make(chan struct{}, 1)
	var got []byte
	var code int
	child := parent.Clone()
	child.OnResponse(func(r *colly.Response) {
		got = append(got, r.Body...)
		code = r.StatusCode
		select { case ch <- struct{}{}: default: }
	})
	child.OnError(func(r *colly.Response, e error) {
		code = r.StatusCode
		err = e
		select { case ch <- struct{}{}: default: }
	})
	_ = child.Visit(u)
	child.Wait()
	<-ch
	return got, code, err
}

/* ============================== Emitting helpers ============================== */

// Always emit JS/asset URLs; only visit when in-scope
func (crawler *Crawler) feedLinkfinder(jsFileUrl, OutputType, source string) {
	if crawler.jsSet.Duplicate(jsFileUrl) {
		return
	}
	abs, err := url.Parse(jsFileUrl)
	if err != nil {
		return
	}
	jsFileUrl = canonicalizeURL(abs)
	inScope := InScope(abs, crawler.C.URLFilters)

	// Emit the asset URL
	outputFormat := fmt.Sprintf("[%s] - %s", OutputType, jsFileUrl)
	if crawler.JsonOutput {
		sout := SpiderOutput{
			Input:      crawler.Input,
			Source:     source,
			OutputType: OutputType,
			Output:     jsFileUrl,
		}
		if data, err := jsoniter.MarshalToString(sout); err == nil {
			outputFormat = data
		}
	} else if crawler.Quiet {
		outputFormat = jsFileUrl
	}
	crawler.emitLine("javascript", outputFormat)

	// Only crawl / linkfind when in-scope
	if !inScope {
		return
	}
	if strings.Contains(jsFileUrl, ".min.js") {
		originalJS := strings.ReplaceAll(jsFileUrl, ".min.js", ".js")
		_ = crawler.LinkFinderCollector.Visit(originalJS)
	}
	_ = crawler.LinkFinderCollector.Visit(jsFileUrl)
}

/* ============================== Crawl Start ============================== */

func (crawler *Crawler) Start(linkfinder bool) {
	if linkfinder {
		crawler.setupLinkFinder()
	}

	uploadFormSet := NewStringFilter()

	crawler.C.OnHTML("a[href], link[href], script[src], form[action], input[type='file']", func(e *colly.HTMLElement) {
		switch e.Name {
		case "a", "link":
			urlString := e.Request.AbsoluteURL(e.Attr("href"))
			urlString = FixUrl(crawler.site, urlString)
			if urlString == "" {
				return
			}
			// Drop static noise early
			if disallowedExtRE.MatchString(urlString) {
				return
			}
			abs, err := url.Parse(urlString)
			if err != nil || !InScope(abs, crawler.C.URLFilters) {
				return // drop off-scope before printing
			}
			urlString = canonicalizeURL(abs)
			if !crawler.urlSet.Duplicate(urlString) {
				outputFormat := fmt.Sprintf("[href] - %s", urlString)
				if crawler.JsonOutput {
					sout := SpiderOutput{Input: crawler.Input, Source: "body", OutputType: "href", Output: urlString}
					if data, err := jsoniter.MarshalToString(sout); err == nil {
						outputFormat = data
					}
				} else if crawler.Quiet {
					outputFormat = urlString
				}
				crawler.emitLine("href", outputFormat)
				_ = e.Request.Visit(urlString)
			}

		case "form":
			formUrl := e.Request.URL.String()
			if !crawler.formSet.Duplicate(formUrl) {
				outputFormat := fmt.Sprintf("[form] - %s", formUrl)
				if crawler.JsonOutput {
					sout := SpiderOutput{Input: crawler.Input, Source: "body", OutputType: "form", Output: formUrl}
					if data, err := jsoniter.MarshalToString(sout); err == nil {
						outputFormat = data
					}
				} else if crawler.Quiet {
					outputFormat = formUrl
				}
				crawler.emitLine("form", outputFormat)
			}

		case "input":
			uploadUrl := e.Request.URL.String()
			if !uploadFormSet.Duplicate(uploadUrl) {
				outputFormat := fmt.Sprintf("[upload-form] - %s", uploadUrl)
				if crawler.JsonOutput {
					sout := SpiderOutput{Input: crawler.Input, Source: "body", OutputType: "upload-form", Output: uploadUrl}
					if data, err := jsoniter.MarshalToString(sout); err == nil {
						outputFormat = data
					}
				} else if crawler.Quiet {
					outputFormat = uploadUrl
				}
				crawler.emitLine("upload-form", outputFormat)
			}

		case "script":
			jsFileUrl := e.Request.AbsoluteURL(e.Attr("src"))
			jsFileUrl = FixUrl(crawler.site, jsFileUrl)
			if jsFileUrl == "" {
				return
			}
			fileExt := GetExtType(jsFileUrl)
			if fileExt == ".js" || fileExt == ".xml" || fileExt == ".json" {
				// do not gate on InScope here; feedLinkfinder emits always, visits only if in-scope
				crawler.feedLinkfinder(jsFileUrl, "javascript", "body")
			}
		}
	})

	crawler.C.OnResponse(func(response *colly.Response) {
		body := response.Body
		u := response.Request.URL.String()
		bodyLen := len(body)
		decoded := false
		var respStr string

		// Decide whether to decode+scan or skip heavy work
		if bodyLen <= maxGrepBody {
			respStr = DecodeChars(string(body))
			bodyLen = len(respStr)
			decoded = true
		}

		if len(crawler.filterLengthSlice) == 0 || !contains(crawler.filterLengthSlice, bodyLen) {
			crawler.emitURL(response.StatusCode, bodyLen, u)

			if decoded && InScope(response.Request.URL, crawler.C.URLFilters) {
				crawler.findSubdomains(respStr)
				crawler.findAWSS3(respStr)

				// NEW: run LinkFinder on HTML bodies too (catches //images.neopets.com/... from <script src>)
				ct := strings.ToLower(response.Headers.Get("Content-Type"))
				if strings.Contains(ct, "text/html") || strings.Contains(ct, "application/xhtml") || ct == "" {
					paths, err := LinkFinder(respStr)
					if err == nil && len(paths) > 0 {
						baseURL := response.Request.URL
						for _, relPath := range paths {
							if isNoiseToken(relPath) {
								continue
							}

							// Absolute?
							if isAbsoluteURL(relPath) {
								uAbs, _ := url.Parse(relPath)
								if !InScope(uAbs, crawler.C.URLFilters) {
									continue
								}
								absURL := canonicalizeURL(uAbs)
								if !crawler.urlSet.Duplicate(absURL) {
									var out string
									if crawler.JsonOutput {
										sout := SpiderOutput{Input: crawler.Input, Source: baseURL.String(), OutputType: "linkfinder", Output: absURL}
										if data, err := jsoniter.MarshalToString(sout); err == nil {
											out = data
										}
									} else if crawler.Quiet {
										out = absURL
									} else {
										out = fmt.Sprintf("[linkfinder] - %s", absURL)
									}
									if out != "" {
										crawler.emitLine("linkfinder", out)
									}
									_ = crawler.C.Visit(absURL)
								}
								continue
							}

							// Relative (includes scheme-relative //…)
							rebuildURL := FixUrl(baseURL, relPath)
							if rebuildURL == "" {
								continue
							}
							uReb, err := url.Parse(rebuildURL)
							if err != nil || !InScope(uReb, crawler.C.URLFilters) {
								continue
							}
							rebuildURL = canonicalizeURL(uReb)

							ext := GetExtType(rebuildURL)
							if ext == ".js" || ext == ".xml" || ext == ".json" || ext == ".map" {
								crawler.feedLinkfinder(rebuildURL, "linkfinder", "html")
								continue
							}

							if !crawler.urlSet.Duplicate(rebuildURL) {
								var out string
								if crawler.JsonOutput {
									sout := SpiderOutput{Input: crawler.Input, Source: baseURL.String(), OutputType: "linkfinder", Output: rebuildURL}
									if data, err := jsoniter.MarshalToString(sout); err == nil {
										out = data
									}
								} else if crawler.Quiet {
									out = rebuildURL
								} else {
									out = fmt.Sprintf("[linkfinder] - %s", rebuildURL)
								}
								if out != "" {
									crawler.emitLine("linkfinder", out)
								}
								_ = crawler.C.Visit(rebuildURL)
							}
						}
					}
				}

				if crawler.raw {
					rawLine := fmt.Sprintf("[Raw] - \n%s\n", respStr)
					if !crawler.Quiet {
						crawler.emitLine("raw", rawLine)
					} else if crawler.Output != nil {
						crawler.Output.WriteToFile(rawLine)
					}
				}
			}
		}
	})

	crawler.C.OnError(func(response *colly.Response, err error) {
		Logger.Debugf("Error request: %s - Status code: %v - Error: %s", response.Request.URL.String(), response.StatusCode, err)
		if response.StatusCode == 404 || response.StatusCode == 429 || response.StatusCode < 100 || response.StatusCode >= 500 {
			return
		}
		u := response.Request.URL.String()
		crawler.emitURL(response.StatusCode, len(response.Body), u)
	})

	if err := crawler.C.Visit(crawler.site.String()); err != nil {
		Logger.Errorf("Failed to start %s: %s", crawler.site.String(), err)
	}
}

/* ============================== Helpers for Start() ============================== */

func (crawler *Crawler) findSubdomains(resp string) {
	subs := GetSubdomains(resp, crawler.domain)
	for _, sub := range subs {
		if !crawler.subSet.Duplicate(sub) {
			if crawler.JsonOutput {
				sout := SpiderOutput{Input: crawler.Input, Source: "body", OutputType: "subdomain", Output: sub}
				if data, err := jsoniter.MarshalToString(sout); err == nil {
					crawler.emitLine("subdomains", data)
				}
			} else if !crawler.Quiet {
				crawler.emitLine("subdomains", fmt.Sprintf("[subdomains] - http://%s", sub))
				crawler.emitLine("subdomains", fmt.Sprintf("[subdomains] - https://%s", sub))
			} else {
				crawler.emitLine("subdomains", sub)
			}
		}
	}
}

func (crawler *Crawler) findAWSS3(resp string) {
	aws := GetAWSS3(resp)
	for _, e := range aws {
		if !crawler.awsSet.Duplicate(e) {
			outputFormat := fmt.Sprintf("[aws-s3] - %s", e)
			if crawler.JsonOutput {
				sout := SpiderOutput{Input: crawler.Input, Source: "body", OutputType: "aws", Output: e}
				if data, err := jsoniter.MarshalToString(sout); err == nil {
					outputFormat = data
				}
			} else if crawler.Quiet {
				outputFormat = e
			}
			crawler.emitLine("aws", outputFormat)
		}
	}
}

/* ============================== LinkFinder ============================== */

var linkFinderRegex = regexp.MustCompile(`(?:"|')(((?:[a-zA-Z]{1,10}://|//)[^"'/]{1,}\.[a-zA-Z]{2,}[^"']{0,})|((?:/|\.\./|\./)[^"'><,;| *()(%%$^/\\\[\]][^"'><,;|()]{1,})|([a-zA-Z0-9_\-/]{1,}/[a-zA-Z0-9_\-/]{1,}\.(?:[a-zA-Z]{1,4}|action)(?:[\?|#][^"|']{0,}|))|([a-zA-Z0-9_\-/]{1,}/[a-zA-Z0-9_\-/]{3,}(?:[\?|#][^"|']{0,}|))|([a-zA-Z0-9_\-]{1,}\.(?:php|asp|aspx|jsp|json|action|html|js|txt|xml)(?:[\?|#][^"|']{0,}|)))(?:"|')`)

var mimeRE = regexp.MustCompile(`^[a-zA-Z][a-zA-Z0-9.+-]*/[a-zA-Z0-9.+-]+$`)
var dateRE = regexp.MustCompile(`^\d{1,2}/\d{1,2}/\d{2,4}$`)

func isNoiseToken(s string) bool {
	s = strings.TrimSpace(s)
	if s == "" {
		return true
	}
	if mimeRE.MatchString(s) {
		return true // application/json, text/plain, etc.
	}
	if dateRE.MatchString(s) {
		return true // 12/31/2025, MM/DD/YYYY, etc.
	}
	if strings.Contains(s, "{{") || strings.Contains(s, "}}") {
		return true // templated tokens
	}
	if strings.Contains(s, "/:") {
		return true // route templates like /tenders/:id
	}
	return false
}
func isAbsoluteURL(s string) bool {
	u, err := url.Parse(s)
	return err == nil && u.Scheme != "" && u.Host != ""
}

func LinkFinder(source string) ([]string, error) {
	var links []string
	if len(source) > 1_000_000 {
		source = strings.ReplaceAll(source, ";", ";\r\n")
		source = strings.ReplaceAll(source, ",", ",\r\n")
	}
	source = DecodeChars(source)

	match := linkFinderRegex.FindAllStringSubmatch(source, -1)
	for _, m := range match {
		matchGroup1 := FilterNewLines(m[1])
		if matchGroup1 == "" {
			continue
		}
		links = append(links, matchGroup1)
	}
	links = Unique(links)
	return links, nil
}

func (crawler *Crawler) setupLinkFinder() {
	crawler.LinkFinderCollector.OnResponse(func(response *colly.Response) {
		if response.StatusCode == 404 || response.StatusCode == 429 || response.StatusCode < 100 {
			return
		}

		body := response.Body
		u := response.Request.URL.String()
		bodyLen := len(body)

		// Soft cap: still emit [url], but skip deep scans for huge bodies
		if bodyLen > maxGrepBody {
			crawler.emitURL(response.StatusCode, bodyLen, u)
			return
		}

		respStr := DecodeChars(string(body))
		bodyLen = len(respStr)

		if len(crawler.filterLengthSlice) == 0 || !contains(crawler.filterLengthSlice, bodyLen) {
			crawler.emitURL(response.StatusCode, bodyLen, u)

			if InScope(response.Request.URL, crawler.C.URLFilters) {
				crawler.findSubdomains(respStr)
				crawler.findAWSS3(respStr)

				paths, err := LinkFinder(respStr)
				if err != nil {
					Logger.Error(err)
					return
				}

				currentPathURL, err := url.Parse(u)
				currentPathURLerr := err != nil

				for _, relPath := range paths {
					if isNoiseToken(relPath) {
						continue
					}

					// Absolute link in JS: enforce scope, print only if in-scope
					if isAbsoluteURL(relPath) {
						uAbs, _ := url.Parse(relPath)
						if !InScope(uAbs, crawler.C.URLFilters) {
							continue
						}
						relPath = canonicalizeURL(uAbs)
						if !crawler.urlSet.Duplicate(relPath) {
							var out string
							if crawler.JsonOutput {
								sout := SpiderOutput{Input: crawler.Input, Source: response.Request.URL.String(), OutputType: "linkfinder", Output: relPath}
								if data, err := jsoniter.MarshalToString(sout); err == nil {
									out = data
								}
							} else if crawler.Quiet {
								out = relPath
							} else {
								out = fmt.Sprintf("[linkfinder] - %s", relPath)
							}
							if out != "" {
								crawler.emitLine("linkfinder", out)
							}
							_ = crawler.C.Visit(relPath)
						}
						continue
					}

					// Rebuild relative -> absolute against the JS file URL (or root)
					var rebuildURL string
					if !currentPathURLerr {
						rebuildURL = FixUrl(currentPathURL, relPath)
					} else {
						rebuildURL = FixUrl(crawler.site, relPath)
					}
					if rebuildURL == "" {
						continue
					}

					uReb, err := url.Parse(rebuildURL)
					if err != nil || !InScope(uReb, crawler.C.URLFilters) {
						continue // drop off-scope before printing
					}
					rebuildURL = canonicalizeURL(uReb)

					ext := GetExtType(rebuildURL)
					if ext == ".js" || ext == ".xml" || ext == ".json" || ext == ".map" {
						crawler.feedLinkfinder(rebuildURL, "linkfinder", "javascript")
						continue
					}

					if !crawler.urlSet.Duplicate(rebuildURL) {
						var out string
						if crawler.JsonOutput {
							sout := SpiderOutput{Input: crawler.Input, Source: response.Request.URL.String(), OutputType: "linkfinder", Output: rebuildURL}
							if data, err := jsoniter.MarshalToString(sout); err == nil {
								out = data
							}
						} else if crawler.Quiet {
							out = rebuildURL
						} else {
							out = fmt.Sprintf("[linkfinder] - %s", rebuildURL)
						}
						if out != "" {
							crawler.emitLine("linkfinder", out)
						}
						_ = crawler.C.Visit(rebuildURL)
					}
				}

				if crawler.raw {
					rawLine := fmt.Sprintf("[Raw] - \n%s\n", respStr)
					if !crawler.Quiet {
						crawler.emitLine("raw", rawLine)
					} else if crawler.Output != nil {
						crawler.Output.WriteToFile(rawLine)
					}
				}
			}
		}
	})
}

/* ============================== Robots & Sitemap ============================== */

func ParseRobots(site *url.URL, crawler *Crawler, c *colly.Collector, wg *sync.WaitGroup) {
	defer wg.Done()
	robotsURL := site.String() + "/robots.txt"

	body, status, err := fetchOnce(c, robotsURL)
	if err != nil || status != 200 || len(body) == 0 {
		return
	}

	Logger.Infof("Found robots.txt: %s", robotsURL)
	lines := strings.Split(string(body), "\n")

	for _, line := range lines {
		if strings.Contains(strings.ToLower(line), "llow:") {
			u := allowDisallowStripRE.ReplaceAllString(line, "")
			u = FixUrl(site, strings.TrimSpace(u))
			if u == "" {
				continue
			}
			outputFormat := fmt.Sprintf("[robots] - %s", u)
			if crawler.JsonOutput {
				sout := SpiderOutput{Input: crawler.Input, Source: "robots", OutputType: "url", Output: u}
				if data, err := jsoniter.MarshalToString(sout); err == nil {
					outputFormat = data
				}
			} else if crawler.Quiet {
				outputFormat = u
			}
			crawler.emitLine("robots", outputFormat)
			_ = c.Visit(u)
		}
	}
}

type locOnly struct {
	Loc string `xml:"loc"`
}
type urlset struct {
	URLs []locOnly `xml:"url"`
}
type sitemapIndex struct {
	Maps []locOnly `xml:"sitemap"`
}

func ParseSiteMap(site *url.URL, crawler *Crawler, c *colly.Collector, wg *sync.WaitGroup) {
	defer wg.Done()
	sitemapUrls := []string{
		"/sitemap.xml", "/sitemap_news.xml", "/sitemap_index.xml", "/sitemap-index.xml", "/sitemapindex.xml",
		"/sitemap-news.xml", "/post-sitemap.xml", "/page-sitemap.xml", "/portfolio-sitemap.xml", "/home_slider-sitemap.xml",
		"/category-sitemap.xml", "/author-sitemap.xml",
	}

	for _, p := range sitemapUrls {
		target := site.String() + p
		Logger.Infof("Trying to find %s", target)

		body, status, err := fetchOnce(c, target)
		if err != nil || status != 200 || len(body) == 0 {
			continue
		}

		// Try <urlset>
		var us urlset
		if xml.Unmarshal(body, &us) == nil && len(us.URLs) > 0 {
			for _, e := range us.URLs {
				loc := strings.TrimSpace(e.Loc)
				if loc == "" {
					continue
				}
				out := loc
				if crawler.JsonOutput {
					sout := SpiderOutput{Input: crawler.Input, Source: "sitemap", OutputType: "url", Output: loc}
					if data, err := jsoniter.MarshalToString(sout); err == nil {
						out = data
					}
				} else if !crawler.Quiet {
					out = fmt.Sprintf("[sitemap] - %s", loc)
				}
				crawler.emitLine("sitemap", out)
				_ = c.Visit(loc)
			}
			continue
		}

		// Or <sitemapindex> containing nested sitemaps
		var si sitemapIndex
		if xml.Unmarshal(body, &si) == nil && len(si.Maps) > 0 {
			for _, e := range si.Maps {
				loc := strings.TrimSpace(e.Loc)
				if loc == "" {
					continue
				}
				nb, nstatus, nerr := fetchOnce(c, loc)
				if nerr != nil || nstatus != 200 || len(nb) == 0 {
					continue
				}
				var nus urlset
				if xml.Unmarshal(nb, &nus) == nil && len(nus.URLs) > 0 {
					for _, ue := range nus.URLs {
						u := strings.TrimSpace(ue.Loc)
						if u == "" {
							continue
						}
						out := u
						if crawler.JsonOutput {
							sout := SpiderOutput{Input: crawler.Input, Source: "sitemap", OutputType: "url", Output: u}
							if data, err := jsoniter.MarshalToString(sout); err == nil {
								out = data
							}
						} else if !crawler.Quiet {
							out = fmt.Sprintf("[sitemap] - %s", u)
						}
						crawler.emitLine("sitemap", out)
						_ = c.Visit(u)
					}
				}
			}
		}
	}
}

/* ============================== Other sources ============================== */

type wurl struct {
	date string
	url  string
}
type fetchFn func(string, bool) ([]wurl, error)

func OtherSources(domain string, includeSubs bool) []string {
	noSubs := !includeSubs
	var urls []string

	fetchFns := []fetchFn{
		getWaybackURLs,
		getCommonCrawlURLs,
		getVirusTotalURLs,
		getOtxUrls,
	}

	out := make(chan wurl, 256)
	var wg sync.WaitGroup

	for _, fn := range fetchFns {
		wg.Add(1)
		go func(fetch fetchFn) {
			defer wg.Done()
			resp, err := fetch(domain, noSubs)
			if err != nil {
				Logger.Debugf("Error fetching from source: %v", err)
				return
			}
			for _, r := range resp {
				if r.url != "" {
					out <- r
				}
			}
		}(fn)
	}

	go func() {
		wg.Wait()
		close(out)
	}()

	for w := range out {
		urls = append(urls, w.url)
	}
	return Unique(urls)
}

func getWaybackURLs(domain string, noSubs bool) ([]wurl, error) {
	subsWildcard := "*."
	matchType := "domain"
	if noSubs {
		subsWildcard = ""
		matchType = "host"
	}
	res, err := http.Get(
		fmt.Sprintf("https://web.archive.org/cdx/search/cdx?url=%s%s/*&output=json&fl=timestamp,original&collapse=urlkey&matchType=%s", subsWildcard, domain, matchType),
	)
	if err != nil {
		return []wurl{}, err
	}
	defer res.Body.Close()

	raw, err := io.ReadAll(res.Body)
	if err != nil {
		return []wurl{}, err
	}

	var wrapper [][]string
	if err := json.Unmarshal(raw, &wrapper); err != nil {
		return []wurl{}, err
	}

	out := make([]wurl, 0, len(wrapper))
	skip := true
	for _, cols := range wrapper {
		if skip {
			// first row is a header when output=json (["timestamp","original"])
			skip = false
			continue
		}
		// Ensure we have at least 2 columns (timestamp, original)
		if len(cols) < 2 {
			continue
		}
		out = append(out, wurl{date: cols[0], url: cols[1]})
	}
	return out, nil
}

func getCommonCrawlURLs(domain string, noSubs bool) ([]wurl, error) {
	subsWildcard := "*."
	if noSubs {
		subsWildcard = ""
	}

	// First, get the list of available indices
	indexURL := "https://index.commoncrawl.org/collinfo.json"
	resp, err := http.Get(indexURL)
	if err != nil {
		Logger.Debugf("Failed to fetch CommonCrawl index list: %v", err)
		return []wurl{}, err
	}
	defer resp.Body.Close()

	var indices []struct {
		ID     string `json:"id"`
		Name   string `json:"name"`
		CDXAPI string `json:"cdx-api"`
	}
	
	if err := json.NewDecoder(resp.Body).Decode(&indices); err != nil {
		Logger.Debugf("Failed to parse CommonCrawl index list: %v", err)
		return []wurl{}, err
	}

	if len(indices) == 0 {
		return []wurl{}, fmt.Errorf("no CommonCrawl indices available")
	}

	// Use the most recent index (first in the list)
	latestIndex := indices[0].ID
	Logger.Debugf("Using CommonCrawl index: %s", latestIndex)

	// Query the latest index
	queryURL := fmt.Sprintf("https://index.commoncrawl.org/%s?url=%s%s/*&output=json", 
		latestIndex, subsWildcard, domain)
	
	res, err := http.Get(queryURL)
	if err != nil {
		return []wurl{}, err
	}
	defer res.Body.Close()

	sc := bufio.NewScanner(res.Body)
	// allow longer lines
	buf := make([]byte, 1024*1024)
	sc.Buffer(buf, 10*1024*1024)

	out := make([]wurl, 0)

	for sc.Scan() {
		wrapper := struct {
			URL       string `json:"url"`
			Timestamp string `json:"timestamp"`
		}{}
		if err := json.Unmarshal([]byte(sc.Text()), &wrapper); err != nil {
			Logger.Debugf("Failed to parse CommonCrawl result: %v", err)
			continue
		}
		if wrapper.URL != "" {
			out = append(out, wurl{date: wrapper.Timestamp, url: wrapper.URL})
		}
	}

	if err := sc.Err(); err != nil {
		Logger.Debugf("Scanner error reading CommonCrawl results: %v", err)
	}

	return out, nil
}

func getVirusTotalURLs(domain string, _ bool) ([]wurl, error) {
	out := make([]wurl, 0)

	apiKey := os.Getenv("VT_API_KEY")
	if apiKey == "" {
		Logger.Warnf("You are not set VirusTotal API Key yet.")
		return out, nil
	}

	fetchURL := fmt.Sprintf("https://www.virustotal.com/vtapi/v2/domain/report?apikey=%s&domain=%s", apiKey, domain)
	resp, err := http.Get(fetchURL)
	if err != nil {
		return out, err
	}
	defer resp.Body.Close()

	wrapper := struct {
		URLs []struct {
			URL string `json:"url"`
		} `json:"detected_urls"`
	}{}

	dec := json.NewDecoder(resp.Body)
	if err := dec.Decode(&wrapper); err != nil {
		Logger.Debugf("Failed to parse VirusTotal response: %v", err)
		return out, nil
	}
	for _, u := range wrapper.URLs {
		if u.URL != "" {
			out = append(out, wurl{url: u.URL})
		}
	}
	return out, nil
}

func getOtxUrls(domain string, _ bool) ([]wurl, error) {
	var urls []wurl
	page := 0
	maxPages := 10 // Safety limit to prevent infinite loops

	for page < maxPages {
		r, err := http.Get(fmt.Sprintf("https://otx.alienvault.com/api/v1/indicators/hostname/%s/url_list?limit=50&page=%d", domain, page))
		if err != nil {
			return []wurl{}, err
		}
		bytes, err := io.ReadAll(r.Body)
		r.Body.Close()
		if err != nil {
			return []wurl{}, err
		}
		wrapper := struct {
			HasNext bool `json:"has_next"`
			URLList []struct{ URL string `json:"url"` } `json:"url_list"`
		}{}
		if err := json.Unmarshal(bytes, &wrapper); err != nil {
			Logger.Debugf("Failed to parse AlienVault response: %v", err)
			return []wurl{}, err
		}
		for _, u := range wrapper.URLList {
			if u.URL != "" {
				urls = append(urls, wurl{url: u.URL})
			}
		}
		if !wrapper.HasNext {
			break
		}
		page++
	}
	return urls, nil
}

/* ============================== Grep ============================== */

const SUBRE = `(?i)(([a-zA-Z0-9]{1}|[_a-zA-Z0-9]{1}[_a-zA-Z0-9-]{0,61}[a-zA-Z0-9]{1})[.]{1})+`

var AWSS3 = regexp.MustCompile(`(?i)[a-z0-9.-]+\.s3\.amazonaws\.com|[a-z0-9.-]+\.s3-[a-z0-9-]\.amazonaws\.com|[a-z0-9.-]+\.s3-website[.-](eu|ap|us|ca|sa|cn)|//s3\.amazonaws\.com/[a-z0-9._-]+|//s3-[a-z0-9-]+\.amazonaws\.com/[a-z0-9._-]+`)

func subdomainRegex(domain string) *regexp.Regexp {
	d := strings.Replace(domain, ".", "[.]", -1)
	return regexp.MustCompile(SUBRE + d)
}

func GetSubdomains(source, domain string) []string {
	re := subdomainRegex(domain)
	ms := re.FindAllString(source, -1)
	subs := make([]string, 0, len(ms))
	for _, m := range ms {
		subs = append(subs, CleanSubdomain(m))
	}
	return subs
}

func GetAWSS3(source string) []string {
	ms := AWSS3.FindAllString(source, -1)
	aws := make([]string, 0, len(ms))
	for _, m := range ms {
		aws = append(aws, DecodeChars(m))
	}
	return aws
}

/* ============================== Utils ============================== */

func GetRawCookie(cookies []*http.Cookie) string {
	var rawCookies []string
	for _, c := range cookies {
		rawCookies = append(rawCookies, fmt.Sprintf("%s=%s", c.Name, c.Value))
	}
	return strings.Join(rawCookies, "; ")
}

func GetDomain(site *url.URL) string {
	domain, err := publicsuffix.EffectiveTLDPlusOne(site.Hostname())
	if err != nil {
		return ""
	}
	return domain
}

func FixUrl(mainSite *url.URL, nextLoc string) string {
	nextLocUrl, err := url.Parse(nextLoc)
	if err != nil {
		return ""
	}
	return mainSite.ResolveReference(nextLocUrl).String()
}

func Unique(in []string) []string {
	keys := make(map[string]struct{}, len(in))
	out := make([]string, 0, len(in))
	for _, s := range in {
		if _, ok := keys[s]; !ok {
			keys[s] = struct{}{}
			out = append(out, s)
		}
	}
	return out
}

func GetExtType(rawUrl string) string {
	u, err := url.Parse(rawUrl)
	if err != nil {
		return ""
	}
	return path.Ext(u.Path)
}

var nameStripRE = regexp.MustCompile("(?i)^((20)|(25)|(2b)|(2f)|(3d)|(3a)|(40))+")
func CleanSubdomain(s string) string {
	s = strings.TrimSpace(strings.ToLower(s))
	s = strings.TrimPrefix(s, "*.")
	return cleanName(s)
}
func cleanName(name string) string {
	for {
		if i := nameStripRE.FindStringIndex(name); i != nil {
			name = name[i[1]:]
		} else {
			break
		}
	}
	name = strings.Trim(name, "-")
	if len(name) > 1 && name[0] == '.' {
		name = name[1:]
	}
	return name
}

func FilterNewLines(s string) string {
	return newlineRE.ReplaceAllString(strings.TrimSpace(s), " ")
}

func DecodeChars(s string) string {
	if source, err := url.QueryUnescape(s); err == nil {
		s = source
	}
	return decodeReplacer.Replace(s)
}

func InScope(u *url.URL, regexps []*regexp.Regexp) bool {
	for _, r := range regexps {
		if r.MatchString(u.String()) {
			return true
		}
	}
	return false
}

func ReadingLines(filename string) []string {
	var result []string
	if strings.HasPrefix(filename, "~") {
		filename, _ = homedir.Expand(filename)
	}
	file, err := os.Open(filename)
	if err != nil {
		return result
	}
	defer file.Close()

	scanner := bufio.NewScanner(file)
	// allow big lines (e.g., very long URLs)
	buf := make([]byte, 1024*1024)
	scanner.Buffer(buf, 10*1024*1024)

	for scanner.Scan() {
		val := strings.TrimSpace(scanner.Text())
		if val == "" {
			continue
		}
		result = append(result, val)
	}
	return result
}

func contains(ii []int, j int) bool {
	for _, v := range ii {
		if v == j {
			return true
		}
	}
	return false
}

func strconvAtoiSafe(s string) (int, error) {
	s = strings.TrimSpace(s)
	var n int
	for _, ch := range s {
		if ch == '+' || ch == '-' {
			continue
		}
		if ch < '0' || ch > '9' {
			return 0, fmt.Errorf("not int")
		}
	}
	_, err := fmt.Sscanf(s, "%d", &n)
	return n, err
}
