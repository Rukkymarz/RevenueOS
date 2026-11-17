"""HTML extraction with the standard library only: title, description, text, links, contacts, and a
small selector subset (tag, tag.class, #id, .class)."""
import re
from html.parser import HTMLParser
from urllib.parse import urljoin

SKIP = {"script", "style", "noscript", "template", "svg"}
VOID = {"br", "img", "hr", "meta", "link", "input", "area", "base", "col", "embed", "source", "track", "wbr"}
EMAIL = re.compile(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", re.I)
PHONE = re.compile(r"(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}")


class _Page(HTMLParser):
    def __init__(self, base: str):
        super().__init__(convert_charrefs=True)
        self.base, self.title, self.desc = base, "", ""
        self.text: list[str] = []
        self.links: list[dict] = []
        self._skip = 0
        self._in_title = False
        self._a: dict | None = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in SKIP:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "meta" and (a.get("name") or "").lower() == "description":
            self.desc = (a.get("content") or "").strip()
        elif tag == "a" and a.get("href"):
            self._a = {"href": urljoin(self.base, a["href"]), "text": ""}
            self.links.append(self._a)

    def handle_endtag(self, tag):
        if tag in SKIP and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False
        elif tag == "a":
            self._a = None

    def handle_data(self, data):
        if self._in_title:
            self.title += data
            return
        if self._skip:
            return
        if self._a is not None:
            self._a["text"] += data
        if data.strip():
            self.text.append(data.strip())


def page(html: str, base: str = "") -> dict:
    p = _Page(base)
    p.feed(html)
    text = " ".join(p.text)
    seen, links = set(), []
    for l in p.links:
        if l["href"] not in seen and l["href"].startswith(("http://", "https://", "mailto:", "tel:")):
            seen.add(l["href"])
            links.append({"href": l["href"], "text": " ".join(l["text"].split())[:120]})
    mails = sorted({m.lower() for m in EMAIL.findall(text)} |
                   {l["href"][7:].split("?")[0].lower() for l in links if l["href"].startswith("mailto:")})
    return {"title": " ".join(p.title.split()), "description": p.desc, "text": text[:200_000], "links": links[:300],
            "contacts": {"emails": mails[:50], "phones": sorted(set(PHONE.findall(text)))[:20]}}


class _Sel(HTMLParser):
    def __init__(self, tag, cls, ident):
        super().__init__(convert_charrefs=True)
        self.tag, self.cls, self.ident = tag, cls, ident
        self.stack: list[tuple[str, bool]] = []
        self.depth = 0
        self.cur: list[str] | None = None
        self.out: list[str] = []

    def _match(self, tag, a):
        classes = (a.get("class") or "").split()
        return ((not self.tag or tag == self.tag) and (not self.cls or self.cls in classes)
                and (not self.ident or a.get("id") == self.ident))

    def handle_starttag(self, tag, attrs):
        if tag in VOID:
            return
        if self.cur is None and self._match(tag, dict(attrs)):
            self.cur, self.depth = [], 1
        elif self.cur is not None:
            self.depth += 1

    def handle_endtag(self, tag):
        if self.cur is not None and tag not in VOID:
            self.depth -= 1
            if self.depth == 0:
                self.out.append(" ".join(" ".join(self.cur).split()))
                self.cur = None

    def handle_data(self, data):
        if self.cur is not None:
            self.cur.append(data)


def select(html: str, selector: str) -> list[str]:
    m = re.fullmatch(r"([a-zA-Z][a-zA-Z0-9]*)?(?:#([\w-]+))?(?:\.([\w-]+))?", selector.strip())
    if not m or not any(m.groups()):
        raise ValueError("selector must be tag, tag.class, #id, or .class")
    s = _Sel(m.group(1), m.group(3), m.group(2))
    s.feed(html)
    return s.out
