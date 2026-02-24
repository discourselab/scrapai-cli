import click


@click.command()
@click.argument("html_file")
@click.option("--test", default=None, help="Test a specific CSS selector")
@click.option("--find", default=None, help="Find elements by keyword")
def analyze(html_file, test, find):
    """Analyze HTML for CSS selector discovery"""
    if test:
        _test_selector(html_file, test)
    elif find:
        _find_by_keyword(html_file, find)
    else:
        _analyze_html(html_file)


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
