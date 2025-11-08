from __future__ import annotations

from bs4 import BeautifulSoup


def extract_main_content(html: str) -> tuple[str, dict[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    meta = {"title": soup.title.string if soup.title else ""}
    text = "\n".join(part.get_text(" ", strip=True) for part in soup.find_all(["h1", "h2", "p", "li"]))
    return text.strip(), meta


def normalize_url(url: str) -> str:
    return url.rstrip("/")
