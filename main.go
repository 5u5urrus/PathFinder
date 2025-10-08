package main

import (
	"bufio"
	"fmt"
	jsoniter "github.com/json-iterator/go"
	"io"
	"net/url"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/sirupsen/logrus"
	"github.com/spf13/cobra"
)

const (
	CLIName = "pathfinder"
	AUTHOR  = "Vahe Demirkhanyan"
	VERSION = "v3.0"
)

var commands = &cobra.Command{
	Use:  CLIName,
	Long: fmt.Sprintf("Fast web spider written in Go - %v by %v", VERSION, AUTHOR),
	Run:  run,
}

func main() {
	commands.Flags().StringP("site", "s", "", "Site or bare domain to crawl (e.g., https://example.com or example.com)")
	commands.Flags().StringP("sites", "S", "", "File of sites/domains to crawl (one per line)")
	commands.Flags().StringP("proxy", "p", "", "Proxy (Ex: http://127.0.0.1:8080)")
	commands.Flags().StringP("output", "o", "", "Output folder")
	commands.Flags().StringP("user-agent", "u", "web", "User Agent to use\n\tweb: random web user-agent\n\tmobi: random mobile user-agent\n\tor set your own UA string")
	commands.Flags().StringP("cookie", "", "", "Cookie to use (testA=a; testB=b)")
	commands.Flags().StringArrayP("header", "H", []string{}, "Header to use (Use multiple -H to set multiple headers)")
	commands.Flags().StringP("burp", "", "", "Load headers and cookie from burp raw http request")
	commands.Flags().StringP("blacklist", "", "", "Blacklist URL Regex")
	commands.Flags().StringP("whitelist", "", "", "Whitelist URL Regex")
	commands.Flags().StringP("whitelist-domain", "", "", "Whitelist Domain (overrides auto-scope)")
	commands.Flags().StringP("filter-length", "L", "", "Ignore responses whose body length equals any of these CSV ints")

	commands.Flags().IntP("threads", "t", 1, "Number of targets to run in parallel")
	commands.Flags().IntP("concurrent", "c", 5, "Max concurrent requests per matching domain")
	commands.Flags().IntP("depth", "d", 1, "MaxDepth (0 = infinite)")
	commands.Flags().IntP("delay", "k", 0, "Fixed delay between requests (seconds)")
	commands.Flags().IntP("random-delay", "K", 0, "Extra randomized delay (seconds)")
	commands.Flags().IntP("timeout", "m", 10, "Request timeout (seconds)")

	commands.Flags().BoolP("base", "B", false, "Disable sitemap/robots/JS/3rd-party; use only HTML crawling")
	commands.Flags().BoolP("js", "", true, "Enable linkfinder for javascript files")
	commands.Flags().BoolP("sitemap", "", false, "Try to crawl sitemap.xml")
	commands.Flags().BoolP("robots", "", true, "Try to crawl robots.txt")
	commands.Flags().BoolP("other-source", "a", false, "Find URLs from 3rd party (Archive.org, CommonCrawl.org, VirusTotal.com, AlienVault.com)")
	commands.Flags().BoolP("include-subs", "w", false, "Include subdomains from 3rd party seeders (for --other-source)")
	commands.Flags().BoolP("include-other-source", "r", false, "Also print other-source URLs (still crawl them)")
	commands.Flags().BoolP("subs", "", false, "Include subdomains (for full-URL targets only; bare domains auto-enable subs)")

	commands.Flags().BoolP("debug", "", false, "Debug logging")
	commands.Flags().BoolP("json", "", false, "JSON output")
	commands.Flags().BoolP("verbose", "v", false, "Verbose logs")
	commands.Flags().BoolP("quiet", "q", false, "Only print URLs")
	commands.Flags().BoolP("no-redirect", "", false, "Disallow redirects off-scope")
	commands.Flags().BoolP("version", "", false, "Print version")
	commands.Flags().BoolP("length", "l", false, "Print response lengths")
	commands.Flags().BoolP("raw", "R", false, "Print raw bodies of visited responses")

	// render flags
	commands.Flags().Bool("render", false, "Enable selective headless render pass")
	commands.Flags().Int("render-budget", 6, "Max rendered pages per domain")
	commands.Flags().Int("render-timeout", 8, "Seconds per rendered page")

	// output-kind filtering
	commands.Flags().String("types", "", "Comma-separated allowlist of kinds to emit (href,url,javascript,linkfinder,form,upload-form,robots,sitemap,subdomains,aws,render,network). Empty = all.")
	commands.Flags().String("exclude-types", "", "Comma-separated denylist of kinds to suppress. Applied after --types if both are set.")

	commands.Flags().SortFlags = false
	if err := commands.Execute(); err != nil {
		Logger.Error(err)
		os.Exit(1)
	}
}

// ScopeOverride tells the crawler to enforce a specific domain scope.
// When set (for bare domains), we allow subdomains by default.
type ScopeOverride struct {
	Domain    string
	AllowSubs bool
}

func run(cmd *cobra.Command, _ []string) {
	version, _ := cmd.Flags().GetBool("version")
	if version {
		fmt.Printf("Version: %s\n", VERSION)
		Examples()
		os.Exit(0)
	}

	isDebug, _ := cmd.Flags().GetBool("debug")
	if isDebug {
		Logger.SetLevel(logrus.DebugLevel)
	} else {
		Logger.SetLevel(logrus.InfoLevel)
	}

	verbose, _ := cmd.Flags().GetBool("verbose")
	if !verbose && !isDebug {
		Logger.SetOutput(io.Discard)
	}

	// Create output folder when save file option selected
	outputFolder, _ := cmd.Flags().GetString("output")
	if outputFolder != "" {
		if _, err := os.Stat(outputFolder); os.IsNotExist(err) {
			_ = os.Mkdir(outputFolder, os.ModePerm)
		}
	}

	// Parse sites input
	var siteList []string
	if siteInput, _ := cmd.Flags().GetString("site"); siteInput != "" {
		siteList = append(siteList, siteInput)
	}
	if sitesListInput, _ := cmd.Flags().GetString("sites"); sitesListInput != "" {
		sitesFile := ReadingLines(sitesListInput)
		if len(sitesFile) > 0 {
			siteList = append(siteList, sitesFile...)
		}
	}

	// read from stdin if piped
	if stat, _ := os.Stdin.Stat(); (stat.Mode() & os.ModeCharDevice) == 0 {
		sc := bufio.NewScanner(os.Stdin)
		for sc.Scan() {
			target := strings.TrimSpace(sc.Text())
			if err := sc.Err(); err == nil && target != "" {
				siteList = append(siteList, target)
			}
		}
	}

	if len(siteList) == 0 {
		Logger.Info("No site in list. Please check your site input again")
		os.Exit(1)
	}

	sitemap, _ := cmd.Flags().GetBool("sitemap")
	linkfinder, _ := cmd.Flags().GetBool("js")
	robots, _ := cmd.Flags().GetBool("robots")
	otherSource, _ := cmd.Flags().GetBool("other-source")
	includeSubs, _ := cmd.Flags().GetBool("include-subs")
	includeOtherSourceResult, _ := cmd.Flags().GetBool("include-other-source")
	base, _ := cmd.Flags().GetBool("base")
	threads, _ := cmd.Flags().GetInt("threads")

	if base {
		linkfinder = false
		robots = false
		otherSource = false
		includeSubs = false
		includeOtherSourceResult = false
	}

	// render flags (read in worker and applied per target)
	var wg sync.WaitGroup
	inputChan := make(chan string, threads)

	// worker
	for i := 0; i < threads; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for raw := range inputChan {
				// Normalize target: if no scheme, treat as bare domain (auto-scope + subs)
				siteURL, scope := normalizeTarget(raw)

				var siteWg sync.WaitGroup
				crawler := NewCrawler(siteURL, cmd, scope)

				// Attach headless renderer BEFORE starting the crawl
				renderEnabled, _ := cmd.Flags().GetBool("render")
				renderBudget, _ := cmd.Flags().GetInt("render-budget")
				renderTimeout, _ := cmd.Flags().GetInt("render-timeout")
				if renderEnabled {
					StartRenderManager(crawler, renderBudget, time.Duration(renderTimeout)*time.Second)
				}

				siteWg.Add(1)
				go func() {
					defer siteWg.Done()
					crawler.Start(linkfinder)
				}()

				if sitemap {
					siteWg.Add(1)
					go ParseSiteMap(siteURL, crawler, crawler.C, &siteWg)
				}

				if robots {
					siteWg.Add(1)
					go ParseRobots(siteURL, crawler, crawler.C, &siteWg)
				}

				if otherSource {
					siteWg.Add(1)
					go func() {
						defer siteWg.Done()
						urls := OtherSources(siteURL.Hostname(), includeSubs)
						for _, u := range urls {
							u = strings.TrimSpace(u)
							if u == "" {
								continue
							}
							outputFormat := fmt.Sprintf("[other-sources] - %s", u)
							if includeOtherSourceResult {
								if crawler.JsonOutput {
									sout := SpiderOutput{
										Input:      crawler.Input,
										Source:     "other-sources",
										OutputType: "url",
										Output:     u,
									}
									if data, err := jsoniter.MarshalToString(sout); err == nil {
										outputFormat = data
									}
								} else if crawler.Quiet {
									outputFormat = u
								}
								fmt.Println(outputFormat)
								if crawler.Output != nil {
									crawler.Output.WriteToFile(outputFormat)
								}
							}
							_ = crawler.C.Visit(u)
						}
					}()
				}

				siteWg.Wait()
				crawler.C.Wait()
				crawler.LinkFinderCollector.Wait()

				if crawler.Output != nil {
					crawler.Output.Close()
				}
			}
		}()
	}

	for _, s := range siteList {
		inputChan <- s
	}
	close(inputChan)
	wg.Wait()
	Logger.Info("Done.")
}

func normalizeTarget(raw string) (*url.URL, *ScopeOverride) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return &url.URL{}, nil
	}
	if strings.Contains(raw, "://") {
		u, err := url.Parse(raw)
		if err != nil {
			Logger.Errorf("Failed to parse %q: %v", raw, err)
			return &url.URL{}, nil
		}
		// Full URL input: keep legacy behavior; scope controlled by flags
		return u, nil
	}
	// Bare domain: start at https://<raw>, but scope by apex (eTLD+1) + subdomains
	u, err := url.Parse("https://" + raw)
	if err != nil {
		Logger.Errorf("Failed to parse domain %q: %v", raw, err)
		return &url.URL{}, nil
	}
	apex := GetDomain(u) // e.g., dzo.com.ua
	if apex == "" {
		apex = u.Host
	}
	return u, &ScopeOverride{Domain: apex, AllowSubs: true}
}

func Examples() {
	h := "\n\nExamples Command:\n"
	h += `pathfinder -q -s "https://target.com/"` + "\n"
	h += `pathfinder -s "https://target.com/" -o output -c 10 -d 1` + "\n"
	h += `pathfinder -s "target.com"                # auto-scope to apex + subdomains` + "\n"
	h += `pathfinder -s target.com --types href    # emit only [href]` + "\n"
	h += `pathfinder -s target.com --types url,render,network` + "\n"
	h += `echo 'target.com' | pathfinder -o output -c 10 -d 1 --other-source` + "\n"
	h += `pathfinder -s target.com --render        # enable headless pass (budget=6, timeout=8s)` + "\n"
	fmt.Println(h)
}
