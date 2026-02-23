# Proxy Support

ScrapAI has **SmartProxyMiddleware** that intelligently manages proxy usage to avoid blocks while minimizing costs.

## How It Works

**Strategy:**
1. **Start with direct connections** (fast, free)
2. **Detect blocking** (403/429 errors)
3. **Automatically retry with proxy**
4. **Learn which domains need proxies**
5. **Use proxy proactively** for known-blocked domains

This is smarter than always-on proxy rotation because:
- Direct connections are faster and free
- Proxies only used when necessary
- Learns per-domain blocking patterns
- Reduces proxy bandwidth costs by 80-90%

## Setup

Add proxy credentials to `.env`:

```bash
# Datacenter Proxy (default - used with --proxy-type datacenter or no flag)
# DATACENTER_PROXY_USERNAME=your_username
# DATACENTER_PROXY_PASSWORD=your_password
# DATACENTER_PROXY_HOST=dc.decodo.com
# DATACENTER_PROXY_PORT=10000  # Port 10000 = rotating IPs (recommended)

# Residential Proxy (used with --proxy-type residential flag)
# RESIDENTIAL_PROXY_USERNAME=your_username
# RESIDENTIAL_PROXY_PASSWORD=your_password
# RESIDENTIAL_PROXY_HOST=gate.decodo.com
# RESIDENTIAL_PROXY_PORT=7000  # Port 7000 = rotating residential IPs
```

Uncomment the lines and fill in your proxy provider credentials.

**Important:** For Decodo, use port 10000 for rotating IPs (recommended). Ports 10001-63000 provide sticky IPs (same IP per port).

### Example: Decodo Configuration ⭐ (Recommended)

**Datacenter Proxies (default):**
```bash
# Get credentials from Decodo dashboard
DATACENTER_PROXY_USERNAME=your_decodo_username
DATACENTER_PROXY_PASSWORD=your_decodo_password
DATACENTER_PROXY_HOST=dc.decodo.com
DATACENTER_PROXY_PORT=10000  # Rotating datacenter IPs
```

**Residential Proxies (for sites blocking datacenter IPs):**
```bash
# Get credentials from Decodo dashboard
RESIDENTIAL_PROXY_USERNAME=your_decodo_username
RESIDENTIAL_PROXY_PASSWORD=your_decodo_password
RESIDENTIAL_PROXY_HOST=gate.decodo.com
RESIDENTIAL_PROXY_PORT=7000  # Rotating residential IPs
```

**Decodo Port Options:**

*Datacenter (dc.decodo.com):*
- **Port 10000**: Rotating IPs (recommended) - Each request gets a different IP automatically
- **Ports 10001-63000**: Sticky IPs - Same port = same IP address

*Residential (gate.decodo.com):*
- **Port 7000**: Rotating residential IPs (recommended)

Since our SmartProxyMiddleware uses a single proxy connection, **use rotating ports (10000 for datacenter, 7000 for residential)**.

## Usage

**Datacenter Proxy (default):**
```bash
# Uses datacenter proxy when blocked (if configured)
./scrapai crawl spider_name --project proj --limit 10

# Explicit datacenter
./scrapai crawl spider_name --project proj --limit 10 --proxy-type datacenter
```

**Residential Proxy (explicit):**
```bash
# Uses residential proxy when blocked (must be configured in .env)
./scrapai crawl spider_name --project proj --limit 10 --proxy-type residential
```

**Testing both:**
```bash
# Test with datacenter proxies
./scrapai crawl myspider --project proj --limit 5 --proxy-type datacenter

# Test with residential proxies
./scrapai crawl myspider --project proj --limit 5 --proxy-type residential

# Compare which works better for your use case
```

**Important:** Both proxy types follow the same smart strategy:
- ✅ Start with direct connections (fast, free)
- ✅ Only use proxy when blocked (403/429 errors)
- ✅ Learn which domains need proxies
- ✅ Use proxy proactively for blocked domains

The `--proxy-type` flag only changes **which proxy** to use, not **when** to use it.

## Configuration

**No spider configuration needed!** SmartProxyMiddleware works automatically for all spiders once configured in `.env`.

The middleware is enabled by default in `settings.py` with priority 350.

## Statistics Tracking

SmartProxyMiddleware tracks:
- **Direct requests** - Connections without proxy
- **Proxy requests** - Connections using proxy
- **Blocked retries** - Requests that hit 403/429 and retried with proxy
- **Blocked domains** - Domains that consistently need proxies

Statistics are logged when spider closes:
```
📊 Proxy Statistics for 'spider_name':
   Direct requests: 1847
   Proxy requests: 153
   Blocked & retried: 153
   Blocked domains: 2
   Domains that needed proxy: example.com, protected-site.com
```

## When to Mention to Users

Recommend proxy setup when:
- User asks about proxies or rate limiting
- Spider is getting blocked (403/429 errors in logs)
- User needs to scrape at scale (1000s of pages)
- User mentions proxy provider (Bright Data, Oxylabs, Smartproxy, etc.)
- Crawls are failing with "Access Denied" or "Too Many Requests"

## Proxy Providers

SmartProxyMiddleware works with any HTTP proxy provider:

**Datacenter Proxies** (recommended for most use cases):
- [Decodo](https://decodo.com/) ⭐ **(We use this)** - Residential and datacenter proxies, good value
- [Bright Data](https://brightdata.com/) - Industry leader
- [Oxylabs](https://oxylabs.io/) - High quality
- [IPRoyal](https://iproyal.com/) - Budget friendly

**Residential Proxies** (for sites that block datacenter IPs):
- Use with `--proxy-type residential` flag on crawl command
- Same smart strategy (direct first, proxy only when blocked)
- **Note:** Decodo offers residential proxies - configure RESIDENTIAL_PROXY_* vars in .env

## Technical Details

**Middleware Logic:**
1. On first request to domain → try direct connection
2. If response is 403/429 → mark domain as blocked, retry with proxy
3. On subsequent requests to blocked domain → use proxy immediately
4. Blocked domains remembered for spider lifetime

**Proxy URL Format:**
```
http://username:password@proxy.example.com:8080
```

**Implementation:**
- Located in `middlewares.py`
- Class: `SmartProxyMiddleware`
- Priority: 350 (in `settings.py`)
- Scrapy downloader middleware

## Troubleshooting

### Proxy not being used
1. Check `.env` has all 4 variables set (USERNAME, PASSWORD, HOST, PORT)
2. Verify proxy credentials are correct
3. Test proxy manually: `curl -x http://user:pass@host:port https://httpbin.org/ip`
4. Check logs for "Datacenter proxy available" message on spider start

### Still getting blocked with proxy
1. Check if proxy IP is already blocked by target site
2. Try different proxy provider
3. Add delays between requests (`DOWNLOAD_DELAY` in spider config)
4. Reduce concurrency (`CONCURRENT_REQUESTS` in spider config)

### Proxy costs too high
SmartProxyMiddleware should already minimize costs by using direct connections first. If costs are still high:
1. Check which domains are marked as blocked (in stats at spider close)
2. Verify those domains actually need proxies
3. Consider if site has changed and unblocking is possible
4. Some sites may require proxies for all requests - this is expected

## Future Enhancements

Planned features:
- [ ] Residential proxy support
- [ ] Per-spider proxy configuration (override .env)
- [ ] Proxy pool rotation (multiple proxies)
- [ ] Automatic proxy health checks
- [ ] Sticky sessions (same proxy per domain)
- [ ] Geographic targeting (use proxies from specific countries)

## See Also

- [Cloudflare Bypass](cloudflare.md) - For Cloudflare-protected sites
- [Analysis Workflow](analysis-workflow.md) - Spider building workflow
- [Queue Management](queue.md) - Batch processing multiple sites
