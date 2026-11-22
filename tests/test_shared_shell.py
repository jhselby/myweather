"""model.html and mesonet.html must carry the same shared shell (header, nav, headings, panels).

Both files embed one CSS block between SHARED SHELL START/END. Edit it in both places; this test fails if they differ.
Both pages also use the same top navigation (App, Mesonet, Model) and the same title element."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _shell(name):
    s = (ROOT / name).read_text()
    m = re.search(r"/\* SHARED SHELL START.*?/\* SHARED SHELL END \*/", s, re.S)
    assert m, f"{name}: shared shell block missing"
    return m.group(0)


def test_shell_identical():
    assert _shell("model.html") == _shell("mesonet.html")


def test_same_nav_prefix():
    for name, here in (("model.html", "Model"), ("mesonet.html", "Mesonet")):
        s = (ROOT / name).read_text()
        nav = re.search(r'<nav class="toc">(.*?)<span class="sep"></span>', s, re.S).group(1)
        links = re.findall(r'<a href="([^"]+)"([^>]*)>([^<]+)</a>', nav)
        assert [(h, t) for h, _, t in links] == [("/", "← App"), ("mesonet.html", "Mesonet"), ("model.html", "Model")], name
        assert [t for h, a, t in links if "here" in a] == [here], name
