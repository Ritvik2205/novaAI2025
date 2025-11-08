from pathlib import Path

from app.ingest import chunk, label
from app.ingest.parse import parse_html


def test_html_parse_label_chunk(tmp_path):
    html_path = Path('web-sample/index.html')
    parsed = parse_html(html_path.read_text())
    assert 'Services' in parsed.text
    tags = label.fast_label(parsed.text)
    assert 'marketing' in tags or 'services' in tags
    chunks = chunk.chunk_text(parsed.text, url='https://demo')
    assert chunks, 'chunks should not be empty'
    first_meta = chunks[0]['meta']
    assert 'url' in first_meta
