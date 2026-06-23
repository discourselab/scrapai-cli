# Proxy Support

scrapai has **SmartProxyMiddleware** that intelligently manages proxy usage to avoid blocks while minimizing costs.

## How It Works

**Auto Mode Strategy (default):**
1. **Start with direct connections** (fast, free)
2. **Detect blocking** (403/429/503 errors)
3. **Automatically retry with datacenter proxy** (cheap, fast)
4. **Learn which domains need proxies** (for the rest of the run)
5. **Use proxy proactively** for known-blocked domains
6. **Expert-in-the-loop** if datacenter fails → ask user before using expensive residential

All proxy URLs come from one place — `core/proxy.py`, driven entirely by `.env`.
Proxies are referenced **by name** (`datacenter`, `residential`, or any name you
define — `isp`, `mobile`, `residential_us`, …). Each spider picks its proxy with
the `PROXY_TYPE` setting (or `--proxy-type`), so different sites can use different
proxies.

**Smart cost control:**
- Direct connections are faster and free
- Proxies only used when necessary
- Datacenter proxies preferred (cheaper)
- Residential proxies require explicit user approval
- Learns per-domain blocking patterns
- Reduces proxy bandwidth costs by 80-90%
- **No surprise costs** - expensive proxies need human approval

## Setup

Add proxy config to `.env`. Each named proxy can be configured **two ways** — a
full URL (simplest, any provider) or component vars:

```bash
# Option 1: full URL (paste any provider's endpoint — encode country/session
# however your provider documents it)
# DATACENTER_PROXY_URL=http://user:pass@dc.decodo.com:10000

# Option 2: components
# DATACENTER_PROXY_USERNAME=your_username
# DATACENTER_PROXY_PASSWORD=your_password
# DATACENTER_PROXY_HOST=dc.decodo.com
# DATACENTER_PROXY_PORT=10000  # Port 10000 = rotating IPs (recommended)

# RESIDENTIAL_PROXY_URL=http://user:pass@gate.decodo.com:7000
```

`datacenter` and `residential` are the recognized defaults for `--proxy-type auto`
(auto tries datacenter, then residential).

### Named proxies (ISP, mobile, by country)

Define any proxy by name — the framework treats the URL as opaque, so **any
provider and any type works**. Name it `<NAME>` and set `<NAME>_PROXY_URL` (or the
`<NAME>_PROXY_*` components):

```bash
ISP_PROXY_URL=http://user:pass@isp-proxy.example.com:port
MOBILE_PROXY_URL=http://user:pass@mobile-proxy.example.com:port
# "by country" is just a named entry — encode the country in the URL per your provider
RESIDENTIAL_US_PROXY_URL=http://user-country-us:pass@gate.decodo.com:7000
```

Then select it per spider: `PROXY_TYPE: isp` (or `mobile`, `residential_us`, …).
Selecting a name that isn't configured **fails loudly** (logs which proxies *are*
configured) rather than silently using the wrong one.

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

### Auto Mode (Default) - Expert-in-the-Loop ⭐

**Smart escalation with cost control:**
```bash
# Auto mode (default) - smart escalation
./scrapai crawl spider_name --project proj --limit 10

# Explicit auto mode
./scrapai crawl spider_name --project proj --limit 10 --proxy-type auto
```

**How auto mode works:**
1. ✅ Start with direct connections (fast, free)
2. ✅ On block (403/429/503) → Try datacenter proxy (cheap, fast)
3. ⚠️ **Datacenter fails** → **Expert-in-the-loop prompt:**
   ```
   ⚠️  EXPERT-IN-THE-LOOP: Datacenter proxy failed for some domains
   🏠 Residential proxy is available but may incur HIGHER COSTS

   Blocked domains: example.com, site.org

   To proceed with residential proxy, run:
     ./scrapai crawl spider_name --project proj --proxy-type residential
   ```
4. 👤 **User decides** whether to use expensive residential proxies

**Cost protection:** Residential proxies require explicit user approval - no surprise costs!

### Explicit Modes

**Datacenter only:**
```bash
# Force datacenter proxy only (even if residential configured)
./scrapai crawl spider_name --project proj --limit 10 --proxy-type datacenter
```

**Residential only:**
```bash
# Force residential proxy (explicit approval given)
./scrapai crawl spider_name --project proj --limit 10 --proxy-type residential
```

**Any named proxy:**
```bash
# Use a proxy you defined in .env by name
./scrapai crawl spider_name --project proj --limit 10 --proxy-type isp
```

**Per-spider (the usual way — the agent bakes it in):** set `PROXY_TYPE` in the
spider's `settings`, so each site uses its own proxy without a CLI flag:
```json
{ "settings": { "PROXY_TYPE": "isp" } }
```
The agent can also probe which proxy works during analysis:
`./scrapai inspect <url> --proxy-type residential` (inspect routes its fetch
through that proxy and reports whether it got through).

**All modes follow smart strategy:**
- ✅ Start with direct connections (fast, free)
- ✅ Only use proxy when blocked (403/429/503 errors)
- ✅ Learn which domains need proxies
- ✅ Use proxy proactively for blocked domains

The `--proxy-type` flag controls escalation behavior and cost limits.

## Configuration

**No spider configuration needed!** SmartProxyMiddleware works automatically for all spiders once configured in `.env`.

The middleware is enabled by default in `settings.py` with priority 350.

## Statistics Tracking

SmartProxyMiddleware tracks:
- **Direct requests** - Connections without proxy
- **Proxy attempts** - Requests sent through a proxy
- **Proxy successes** - Proxied requests that came back **200** (i.e. the proxy
  actually got through). Also emitted to Scrapy stats as `proxy/success`.
- **Blocked retries** - Requests that hit 403/429/503 and retried with proxy
- **Blocked domains** - Domains that consistently need proxies

Statistics are logged when the spider closes — the **success line tells you whether
the proxy is actually working**, not just that it was tried:
```
📊 Proxy Statistics for 'spider_name':
   Direct requests: 1847
   Proxy: 153 attempts, 146 unblocked (200) — 95% success
   Blocked & retried: 153
   Blocked domains: 2
   Domains that needed proxy: example.com, protected-site.com
```

## When to Mention to Users

Recommend proxy setup when:
- User asks about proxies or rate limiting
- Spider is getting blocked (403/429/503 errors in logs)
- User needs to scrape at scale (1000s of pages)
- User mentions proxy provider (Bright Data, Oxylabs, Smartproxy, etc.)
- Crawls are failing with "Access Denied" or "Too Many Requests"

## Proxy Providers

SmartProxyMiddleware works with any HTTP proxy provider:

**Datacenter Proxies** (recommended for most use cases):
- [Decodo](https://decodo.com/) ⭐ **(Recommended)** - Residential and datacenter proxies, good value
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
2. If response is 403/429/503 → mark domain as blocked, retry with proxy
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
1. Check `.env` has the proxy set — either `<NAME>_PROXY_URL`, or all 4 component vars (USERNAME, PASSWORD, HOST, PORT)
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

Already available:
- [x] **Per-spider proxy** — set `PROXY_TYPE` in the spider's settings
- [x] **Named proxy types** (ISP, mobile, …) and **geographic targeting** — define
      a named proxy URL (e.g. `RESIDENTIAL_US_PROXY_URL`) and select it by name
- [x] **Sticky sessions** — encode your provider's session params in the proxy URL

Planned:
- [ ] Persist learned blocked-domains across runs (currently in-memory per run)
- [ ] Proxy pool rotation (round-robin multiple URLs per name)
- [ ] Automatic datacenter→residential escalation in the crawl path (currently
      manual via the expert-in-the-loop prompt)

## See Also

- [Cloudflare Bypass](cloudflare.md) - For Cloudflare-protected sites
- [Analysis Workflow](analysis-workflow.md) - Spider building workflow
- [Queue Management](queue.md) - Batch processing multiple sites
