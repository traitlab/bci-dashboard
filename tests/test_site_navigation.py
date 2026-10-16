"""Keyboard skip navigation must not replace hash-based photo state."""

import json
import subprocess
from html.parser import HTMLParser

import pytest
from conftest import DASHBOARD, load


class SkipLink(HTMLParser):
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("class") == "site-skip":
            self.attributes = attrs


@pytest.mark.parametrize("fragment", [
    "#source=recorded&status=compare&frame=photo%20one.JPG",
    "#frame=photo.JPG&view=locations",
    "#frame=photo.JPG&view=models",
])
def test_keyboard_skip_preserves_photo_task_and_filters(fragment):
    site = load("_site_navigation_under_test", DASHBOARD / "site_navigation.py")
    link = SkipLink()
    link.feed(site.navigation("explorer.html"))
    attributes = link.attributes
    script = """
const assert=require('node:assert/strict');
const original=__FRAGMENT__,location={hash:original};let prevented=false,focused=null;
const event={preventDefault(){prevented=true}};
const document={getElementById(id){return {focus(){focused=id}}}};
new Function('event','document',__HANDLER__)(event,document);
if(!prevented)location.hash=__DESTINATION__;
assert.equal(location.hash,original,'skip navigation discarded the saved photo state');
assert.equal(focused,'main-content','skip navigation did not focus the main content');
"""
    script = (script.replace("__FRAGMENT__", json.dumps(fragment))
              .replace("__HANDLER__", json.dumps(attributes.get("onclick", "")))
              .replace("__DESTINATION__", json.dumps(attributes["href"])))
    subprocess.run(["node", "-e", script], check=True)
