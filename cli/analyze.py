import click


@click.command()
@click.argument("html_file")
@click.option("--test", default=None, help="Test a specific CSS selector")
@click.option("--find", default=None, help="Find elements by class/id keyword")
@click.option(
    "--find-text",
    default=None,
    help="Find the element holding a VALUE you saw in the screenshot "
    "(author name, date, title) and get its selector",
)
def analyze(html_file, test, find, find_text):
    """Analyze HTML for CSS selector discovery"""
    if test:
        _test_selector(html_file, test)
    elif find:
        _find_by_keyword(html_file, find)
    elif find_text:
        _find_by_text_cmd(html_file, find_text)
    else:
        _analyze_html(html_file)


def _selector_for(el):
    """Build a usable CSS selector for a BeautifulSoup element."""
    el_id = el.get("id")
    if el_id:
        return f"{el.name}#{el_id}"
    classes = el.get("class") or []
    if classes:
        return f"{el.name}." + ".".join(classes)
    return el.name


def find_by_text(html, value, limit=8):
    """Elements whose visible text contains ``value``, tightest container first.

    Lets you go from a value you SAW in the screenshot to the selector that
    holds it — even when the class name is obfuscated. Returns a list of
    {selector, tag, text}, deduped by selector. Long containers (>200 chars of
    text) are skipped so you get the tight field element, not the whole article.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    needle = value.strip().lower()
    candidates = []
    for el in soup.find_all():
        text = el.get_text(strip=True)
        if text and len(text) < 200 and needle in text.lower():
            candidates.append((len(text), el, text))
    candidates.sort(key=lambda c: c[0])

    results, seen = [], set()
    for _, el, text in candidates:
        sel = _selector_for(el)
        if sel in seen:
            continue
        seen.add(sel)
        results.append({"selector": sel, "tag": el.name, "text": text[:120]})
        if len(results) >= limit:
            break
    return results


def _find_by_text_cmd(html_path, value):
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    matches = find_by_text(html, value)
    click.echo(f"\nElements holding the value '{value}' (tightest first):")
    click.echo("=" * 60)
    if not matches:
        click.echo(f"\nNo element found containing '{value}'.")
        click.echo(
            "Check the value matches the screenshot exactly (spacing; case is OK)."
        )
        return
    for m in matches:
        click.echo(f"\n  {m['selector']}")
        click.echo(f"    Text: {m['text']}")


def _analyze_html(html_path):
    from bs4 import BeautifulSoup

    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    soup = BeautifulSoup(html, "lxml")

    click.echo(f"📄 Analyzing: {html_path}")
    click.echo(f"📊 HTML size: {len(html)} bytes")
    click.echo("\n💡 TIP: Use --find 'keyword' to search for specific elements\n")

    click.echo("=" * 60)
    click.echo("🏷️  HEADERS (h1, h2)")
    click.echo("=" * 60)
    for tag in ["h1", "h2"]:
        elements = soup.find_all(tag)
        if elements:
            click.echo(f"\n{tag.upper()} - Found {len(elements)}:")
            for i, el in enumerate(elements[:5], 1):
                classes = el.get("class", [])
                class_str = "." + ".".join(classes) if classes else ""
                text = el.get_text(strip=True)[:80]
                click.echo(f"  [{i}] {tag}{class_str}")
                click.echo(f"      Text: {text}")

    click.echo("\n" + "=" * 60)
    click.echo("📝 CONTENT CONTAINERS")
    click.echo("=" * 60)
    content_keywords = ["article", "content", "body", "text", "post", "entry"]
    found_containers = []

    for el in soup.find_all(["article", "div", "section", "main"]):
        classes = el.get("class", [])
        class_str = " ".join(classes) if classes else ""
        if el.name == "article" or any(
            kw in class_str.lower() for kw in content_keywords
        ):
            text_len = len(el.get_text(strip=True))
            if text_len > 200:
                found_containers.append((el, text_len))

    found_containers.sort(key=lambda x: x[1], reverse=True)

    for i, (el, text_len) in enumerate(found_containers[:5], 1):
        classes = el.get("class", [])
        class_str = "." + ".".join(classes) if classes else ""
        click.echo(f"\n  [{i}] {el.name}{class_str}")
        click.echo(f"      Size: {text_len} chars")
        click.echo(f"      Preview: {el.get_text(strip=True)[:80]}...")

    click.echo("\n" + "=" * 60)
    click.echo("📅 DATES")
    click.echo("=" * 60)
    date_keywords = ["date", "time", "published", "posted", "updated"]
    found = 0
    for el in soup.find_all(["time", "span", "div", "p"]):
        classes = el.get("class", [])
        class_str = " ".join(classes) if classes else ""
        if el.name == "time" or any(kw in class_str.lower() for kw in date_keywords):
            text = el.get_text(strip=True)
            if text and len(text) < 50:
                classes_list = el.get("class", [])
                selector = "." + ".".join(classes_list) if classes_list else ""
                click.echo(f"  {el.name}{selector}: {text}")
                found += 1
                if found >= 5:
                    break

    click.echo("\n" + "=" * 60)
    click.echo("✍️  AUTHORS")
    click.echo("=" * 60)
    author_keywords = ["author", "byline", "writer", "by"]
    found = 0
    for el in soup.find_all(["span", "div", "a", "p"]):
        classes = el.get("class", [])
        class_str = " ".join(classes) if classes else ""
        if any(kw in class_str.lower() for kw in author_keywords):
            text = el.get_text(strip=True)
            if text and len(text) < 100:
                classes_list = el.get("class", [])
                selector = "." + ".".join(classes_list) if classes_list else ""
                click.echo(f"  {el.name}{selector}: {text}")
                found += 1
                if found >= 5:
                    break

    click.echo("\n" + "=" * 60)


def _test_selector(html_path, selector):
    from bs4 import BeautifulSoup

    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    soup = BeautifulSoup(html, "lxml")

    click.echo(f"\n🔍 Testing selector: {selector}")
    click.echo("=" * 60)

    elements = soup.select(selector)
    if not elements:
        click.echo("❌ No elements found!")
        return

    click.echo(f"✓ Found {len(elements)} element(s)\n")
    for i, el in enumerate(elements[:3], 1):
        text = el.get_text(strip=True)
        click.echo(f"[{i}] {el.name}")
        click.echo(f"    Classes: {el.get('class', [])}")
        click.echo(f"    Text ({len(text)} chars): {text[:150]}...")
        click.echo()


def _find_by_keyword(html_path, keyword):
    from bs4 import BeautifulSoup

    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    soup = BeautifulSoup(html, "lxml")

    click.echo(f"\n🔎 Finding elements with keyword: '{keyword}'")
    click.echo("=" * 60)

    found = 0
    for el in soup.find_all():
        classes = el.get("class", [])
        class_str = " ".join(classes) if classes else ""
        el_id = el.get("id", "")

        if keyword.lower() in class_str.lower() or keyword.lower() in el_id.lower():
            text = el.get_text(strip=True)
            if text and len(text) < 200:
                classes_list = el.get("class", [])
                selector = "." + ".".join(classes_list) if classes_list else ""
                if el_id:
                    selector = f"#{el_id}"
                click.echo(f"\n  {el.name}{selector}")
                click.echo(f"    Text: {text[:100]}")
                found += 1
                if found >= 10:
                    break

    if found == 0:
        click.echo(f"\n❌ No elements found with keyword '{keyword}'")
        click.echo("\n💡 Try: 'price', 'rating', 'author', 'date', 'title'")
