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


class TaskLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "a" and attributes.get("data-site-task"):
            self.links.append(attributes)


@pytest.mark.parametrize("available, views", [
    ({"index.html"}, set()),
    ({"embedding-atlas.html"}, {"photos", "locations"}),
    ({"crownfirst-atlas.html"}, set()),
    (None, {"photos", "locations"}),
])
def test_task_links_keep_distinct_destinations_and_respect_built_pages(available, views):
    site = load("_site_navigation_tasks", DASHBOARD / "site_navigation.py")
    parser = TaskLinks()
    parser.feed(site.navigation("index.html", available=available))
    assert {link["data-atlas-view"] for link in parser.links} == views
    for link in parser.links:
        view = link["data-atlas-view"]
        assert link["data-site-task"] == view
        assert link["href"] == "embedding-atlas.html" + ("#view=locations" if view == "locations" else "")


@pytest.mark.parametrize("current, active", [
    ("embedding-atlas.html", "photos"),
    ("crownfirst-atlas.html", None),
    ("crownfirst-atlas.html#view=locations", None),
    ("embedding-atlas.html#view=locations", "locations"),
])
def test_initial_atlas_task_is_unique(current, active):
    site = load("_site_navigation_active_task", DASHBOARD / "site_navigation.py")
    parser = TaskLinks()
    parser.feed(site.navigation(current))
    assert [link["data-site-task"] for link in parser.links
            if link.get("aria-current") == "page"] == ([active] if active else [])


def test_experimental_comparison_is_not_a_primary_navigation_task():
    site = load("_site_navigation_experimental", DASHBOARD / "site_navigation.py")
    markup = site.navigation("index.html")
    assert "Compare models" not in markup
    assert "crownfirst-atlas.html" not in markup
