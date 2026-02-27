# Hacker News Discussion Scraper - Full Thread Extraction

**Source URL:** https://news.ycombinator.com/
**Project:** tmp
**Date:** 2026-02-26
**Task:** Extract full discussion threads from HN pages 1-2 with hierarchy

---

## Executive Summary

Complex HN scraper that:
1. Extracts posts from pages 1-2 (60 posts total)
2. Visits each discussion page
3. Extracts full comment threads with hierarchy
4. Captures all metadata for each comment
5. Preserves parent-child relationships

**Key Findings:**
- HN uses indent levels (`indent="N"`) instead of nested HTML
- Comments are in `<tr class="athing comtr">` rows
- Hierarchy must be reconstructed from indent levels
- Each comment has: author, time, text, points (votes), parent reference, reply count

---

## URL Structure

### Listing Pages
- Page 1: `https://news.ycombinator.com/`
- Page 2: `https://news.ycombinator.com/?p=2`
- ~30 posts per page

### Discussion Pages
- Pattern: `https://news.ycombinator.com/item?id=<ID>`
- Example: `https://news.ycombinator.com/item?id=47173121`

---

## Post (Story) Structure

**From listing pages:**
```html
<tr class="athing submission" id="47173121">
  <td class="title">
    <span class="titleline">
      <a href="URL">TITLE</a>
      <span class="sitestr">SOURCE</span>
    </span>
  </td>
</tr>
<tr>
  <td class="subtext">
    <span class="score">143 points</span>
    <a href="user?id=USER" class="hnuser">qwertox</a>
    <span class="age"><a href="item?id=47173121">36 minutes ago</a></span>
    <a href="item?id=47173121">61 comments</a>
  </td>
</tr>
```

**Fields to Extract (from listing):**
- `story_id`: `tr.athing::attr(id)`
- `title`: `span.titleline a::text`
- `url`: `span.titleline a::attr(href)`
- `source`: `span.sitestr::text`
- `points`: `span.score::text` → extract number
- `author`: `a.hnuser::text`
- `time_ago`: `span.age a::text`
- `num_comments`: Extract from comment link text
- `discussion_url`: `https://news.ycombinator.com/item?id={story_id}`

---

## Comment Structure

**HTML Structure:**
```html
<tr class="athing comtr" id="47173530">
  <td>
    <table>
      <tr>
        <td class="ind" indent="1">
          <img src="s.gif" width="40">  <!-- width = indent * 40 -->
        </td>
        <td class="votelinks">
          <a id='up_47173530' href='vote?...'>
            <div class='votearrow' title='upvote'></div>
          </a>
        </td>
        <td class="default">
          <div class="comhead">
            <a href="user?id=1024core" class="hnuser">1024core</a>
            <span class="age" title="2026-02-26T23:13:10">
              <a href="item?id=47173530">10 minutes ago</a>
            </span>
            <span class="navs">
              <a href="#47173414" class="clicky">parent</a>
              <a href="#47173670" class="clicky">prev</a>
              <a href="#47173539" class="clicky">next</a>
              <a class="togg" id="47173530" n="3">[–]</a>
            </span>
          </div>
          <div class="comment">
            <span class="comhead">
              <a href="user?id=USER" class="hnuser">username</a>
              <span class="age"><a href="item?id=ID">time</a></span>
            </span>
            <div class="commtext c5A">
              COMMENT TEXT HERE
            </div>
            <div class="reply">
              <p><font size="1">
                <u><a href="reply?id=ID" rel="nofollow">reply</a></u>
              </font></p>
            </div>
          </div>
        </td>
      </tr>
    </table>
  </td>
</tr>
```

**Fields to Extract:**

1. **comment_id**
   - Selector: `tr.athing.comtr::attr(id)`
   - Example: `47173530`

2. **author**
   - Selector: `a.hnuser::text`
   - Example: `1024core`

3. **time_text**
   - Selector: `span.age a::text`
   - Example: `10 minutes ago`

4. **time_timestamp**
   - Selector: `span.age::attr(title)`
   - Example: `2026-02-26T23:13:10`

5. **indent_level**
   - Selector: `td.ind::attr(indent)`
   - Example: `1` (0 = top-level, 1 = first reply, 2 = nested reply, etc.)
   - **CRITICAL**: This determines parent-child hierarchy

6. **comment_text**
   - Selector: `div.commtext::text` or `div.commtext` (HTML)
   - Get all text content including formatted parts

7. **parent_id**
   - Selector: `a.clicky[href^="#"]::attr(href)` (first one with text "parent")
   - Example: `#47173414` → extract ID
   - OR derive from indent level (previous comment with indent_level - 1)

8. **reply_count**
   - Selector: `a.togg::attr(n)`
   - Example: `3` (number of direct + nested replies)

9. **vote_link**
   - Selector: `a[id^="up_"]::attr(href)`
   - Can extract voting status if needed

---

## Hierarchy Reconstruction Strategy

HN doesn't use nested HTML - it uses **indent levels**. To reconstruct the tree:

**Algorithm:**
1. Process comments in order
2. Track current path (stack of parent IDs at each level)
3. For each comment:
   - indent = 0 → top-level comment, parent = story
   - indent = N → child of most recent comment with indent = N-1
   - Update stack: keep only levels 0 to (N-1), add current ID at level N

**Example:**
```
Comment A (indent=0) → parent: story
Comment B (indent=1) → parent: A
Comment C (indent=2) → parent: B
Comment D (indent=1) → parent: A  (sibling of B)
Comment E (indent=2) → parent: D
```

**Storage Format:**
```json
{
  "comment_id": "47173530",
  "parent_id": "47173414",
  "indent_level": 1,
  "author": "1024core",
  "time": "10 minutes ago",
  "timestamp": "2026-02-26T23:13:10",
  "text": "Comment text here...",
  "reply_count": 3
}
```

---

## Spider Design

### Approach 1: Two-Spider Solution

**Spider 1: Extract Posts**
- Crawl pages 1-2
- Extract story metadata
- Generate list of discussion URLs

**Spider 2: Extract Comments**
- Input: List of discussion URLs
- For each URL: extract all comments
- Preserve indent levels for hierarchy

### Approach 2: Single Spider with Follow

**One spider that:**
- Start URLs: pages 1-2
- Rule 1: Extract posts from listing pages
- Rule 2: Follow `item?id=` links to discussions
- Rule 3: Extract comments from discussion pages

**Recommended: Approach 2** (single spider, cleaner)

---

## Spider Configuration

### Rules

**Rule 1: List pages (don't follow)**
```json
{
  "allow": ["^/$", "^/\\?p=2$"],
  "callback": "parse_listing",
  "follow": true
}
```

**Rule 2: Discussion pages**
```json
{
  "allow": ["/item\\?id=\\d+"],
  "deny": ["/vote", "/reply", "/user"],
  "callback": "parse_discussion",
  "follow": false
}
```

### Callbacks

**parse_listing:**
- Extract: story metadata
- Output: Story items with discussion_url
- Follow: Links to `/item?id=...`

**parse_discussion:**
- Extract: All comments with hierarchy metadata
- Output: Comment items with parent relationships
- Follow: None (terminal page)

---

## Custom Fields

### Story Fields (from listing)
```json
{
  "story_id": {"css": "::attr(id)"},
  "title": {"css": "span.titleline a::text"},
  "url": {"css": "span.titleline a::attr(href)"},
  "source": {"css": "span.sitestr::text"},
  "points": {
    "xpath": "following-sibling::tr[1]//span[@class='score']/text()",
    "processors": [
      {"type": "regex", "pattern": "(\\d+)"},
      {"type": "cast", "to": "int"}
    ]
  },
  "author": {
    "xpath": "following-sibling::tr[1]//a[@class='hnuser']/text()"
  },
  "time_ago": {
    "xpath": "following-sibling::tr[1]//span[@class='age']/a/text()"
  },
  "num_comments": {
    "xpath": "following-sibling::tr[1]//a[contains(text(), 'comment')]/text()",
    "processors": [
      {"type": "regex", "pattern": "(\\d+)"},
      {"type": "default", "value": "0"},
      {"type": "cast", "to": "int"}
    ]
  }
}
```

### Comment Fields (from discussion page)
```json
{
  "comments": {
    "type": "nested_list",
    "selector": "tr.athing.comtr",
    "extract": {
      "comment_id": {
        "css": "::attr(id)"
      },
      "author": {
        "css": "a.hnuser::text"
      },
      "time_text": {
        "css": "span.age a::text"
      },
      "timestamp": {
        "css": "span.age::attr(title)"
      },
      "indent_level": {
        "css": "td.ind::attr(indent)",
        "processors": [
          {"type": "default", "value": "0"},
          {"type": "cast", "to": "int"}
        ]
      },
      "comment_html": {
        "css": "div.commtext"
      },
      "comment_text": {
        "css": "div.commtext::text",
        "get_all": true,
        "processors": [
          {"type": "join", "separator": " "}
        ]
      },
      "parent_link": {
        "css": "a.clicky[href^='#']::attr(href)"
      },
      "reply_count": {
        "css": "a.togg::attr(n)",
        "processors": [
          {"type": "default", "value": "0"},
          {"type": "cast", "to": "int"}
        ]
      }
    }
  }
}
```

---

## Technical Considerations

### Comment Threading
- HN uses flat HTML with indent levels
- Parent IDs can be extracted from `parent` links
- Some comments may not have parent links (use indent algorithm)
- Deleted/dead comments may appear as `[dead]` or `[deleted]`

### Rate Limiting
- HN has rate limiting (especially for logged-out users)
- Use DOWNLOAD_DELAY: 2-3 seconds
- CONCURRENT_REQUESTS: 2-4 (be conservative)

### Edge Cases
- `[dead]` comments (flagged/dead)
- `[deleted]` comments
- `[flagged]` comments
- Missing authors (deleted accounts)
- Comments without text (just links)
- Very long comment threads (100+ comments)

### Settings
```json
{
  "DOWNLOAD_DELAY": 2,
  "CONCURRENT_REQUESTS": 2,
  "ROBOTSTXT_OBEY": true,
  "DEPTH_LIMIT": 2
}
```

---

## Expected Output

### Story Item
```json
{
  "type": "story",
  "story_id": "47173121",
  "title": "Statement from Dario Amodei on Our Discussions with the Department of War",
  "url": "https://www.anthropic.com/news/statement-department-of-war",
  "source": "anthropic.com",
  "points": 143,
  "author": "qwertox",
  "time_ago": "36 minutes ago",
  "num_comments": 61,
  "scraped_at": "2026-02-26T23:30:00"
}
```

### Comment Item
```json
{
  "type": "comment",
  "story_id": "47173121",
  "comment_id": "47173530",
  "parent_id": "47173414",
  "indent_level": 1,
  "author": "1024core",
  "time_text": "10 minutes ago",
  "timestamp": "2026-02-26T23:13:10",
  "comment_text": "This isn't a one-election thing...",
  "comment_html": "<div>This isn't...</div>",
  "reply_count": 3,
  "scraped_at": "2026-02-26T23:30:00"
}
```

---

## Test Plan

1. **Phase 4A: Test with 1 discussion**
   - Single post URL as start_url
   - Verify all comments extracted
   - Verify hierarchy is correct
   - Check for missing fields

2. **Phase 4B: Test with page 1**
   - 30 posts
   - Follow to discussions
   - Verify no duplicates
   - Check rate limiting

3. **Phase 4C: Full run pages 1-2**
   - 60 posts
   - ~1000-2000 comments total
   - Monitor for errors
   - Validate output

---

**Status:** ✅ Phase 1-2 Complete
**Next:** Phase 3 - Create spider configs
