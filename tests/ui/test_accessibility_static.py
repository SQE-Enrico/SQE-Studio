"""Static semantic/accessibility checks; NOT substitutes for real-browser audits."""
from __future__ import annotations
import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / 'src' / 'sqe_studio' / 'web'

class Elements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.attrs = []
    def handle_starttag(self, tag, attrs):
        properties = dict(attrs)
        self.attrs.append((tag, properties))
        if 'id' in properties:
            self.ids.append(properties['id'])

def rgb(h):
    return [int(h[i:i+2], 16) / 255 for i in (1, 3, 5)]

def lum(h):
    v = [x / 12.92 if x <= .04045 else ((x+.055)/1.055)**2.4 for x in rgb(h)]
    return sum(a*b for a,b in zip(v, (.2126,.7152,.0722)))

def contrast(a,b):
    v, w = sorted((lum(a),lum(b)), reverse=True)
    return (v+.05)/(w+.05)

def test_semantic_shell_and_keyboard_intent():
    parsed = Elements()
    parsed.feed((WEB / 'index.html').read_text())
    assert len(parsed.ids) == len(set(parsed.ids)), 'Duplicate HTML IDs'
    roles = [v.get('role') for _, v in parsed.attrs]
    assert 'dialog' in roles and 'status' in roles and 'alert' in roles
    assert any(tag == 'main' for tag,_ in parsed.attrs)
    assert any(tag == 'form' for tag,_ in parsed.attrs)
    assert any(tag == 'nav' for tag,_ in parsed.attrs)
    assert any(tag == 'a' and v.get('href') == '#workspaceBody' for tag,v in parsed.attrs)
    assert any(v.get('aria-modal') == 'true' for _,v in parsed.attrs)
    js = (WEB/'app.js').read_text()
    for signature in ('dialogKeys(event)', "event.key==='Escape'", "event.key!=='Tab'", "'Enter'||e.key===' '", 'aria-current="step"', "setAttribute('aria-expanded'", "canRun('quantum_metal')", "data.source!=='scqubits.eigenvals'"):
        assert signature in js
    assert 'Math.random' not in js
    assert 'eval(' not in js

def test_wcag_static_palette_pairs():
    css = (WEB / 'style.css').read_text()
    pairs = [
        ('#edf5fc','#0a111d','body on background'),
        ('#afc0d3','#14243a','muted text on pane'),
        ('#98aec6','#14243a','subtle text on pane'),
        ('#d5e3f1','#0d1929','input labels on surface'),
        ('#b4c6d8','#0e1929','navigation on sidebar'),
        ('#f3f9ff','#1b3d51','diagram label on part'),
        ('#d3e4ef','#0a1829','canvas captions on dark grid'),
        ('#05242d','#6ee8d5','action text on primary button'),
        ('#f6e0b7','#332c27','blocked gate note'),
    ]
    for foreground, background, name in pairs:
        assert foreground in css or foreground == '#f3f9ff'
        value = contrast(foreground,background)
        assert value >= 4.5, (name, value)
        print(f'WCAG contrast {name}: {value:.2f}:1')
    assert 'focus-visible' in css
    assert 'prefers-reduced-motion' in css
    assert '@media(max-width:460px)' in css
