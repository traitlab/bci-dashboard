"""Atlas links retain the photo and active task across navigation."""

from test_atlas_mission_view import photo, run_atlas


def test_view_tabs_selection_and_model_links_keep_the_active_task():
    run_atlas([photo("query", "flight-a"), photo("next", "flight-b")], r"""
assert.equal(atlasView,'photos');
$('showLocationsView').onclick();
assert.equal(new URLSearchParams(location.hash.slice(1)).get('view'),'locations');
select(1);
assert.equal(location.hash,'#frame=next&view=locations');
assert.equal(navLinks[0].getAttribute('href'),'embedding-atlas.html#frame=next&view=locations');
assert.equal(navLinks[1].getAttribute('href'),'crownfirst-atlas.html#frame=next&view=locations');
assert.equal(navLinks[2].getAttribute('href'),'explorer.html#frame=next');
assert.equal(navLinks[3].getAttribute('href'),'embedding-atlas.html#frame=next');
assert.equal(navLinks[3].getAttribute('aria-current'),null);
assert.equal(navLinks[4].getAttribute('aria-current'),null);
assert.equal(navLinks[0].getAttribute('aria-current'),null);
assert.equal(navLinks[1].getAttribute('aria-current'),'page');
showAtlasView('models');
assert.equal(location.hash,'#frame=next&view=models');
assert.equal(navLinks[0].getAttribute('href'),'embedding-atlas.html#frame=next&view=models');
$('showPhotosView').onclick();assert.equal(location.hash,'#frame=next');
""")


def test_reload_and_hash_navigation_restore_photo_and_view_together():
    run_atlas([photo("query", "flight-a"), photo("next", "flight-b")], r"""
assert.equal(selected,1);assert.equal(atlasView,'models');
assert.equal($('modelComparisonView').hidden,false);
location.hash='#frame=query&view=locations';listeners.hashchange();
assert.equal(selected,0);assert.equal(atlasView,'locations');
assert.equal($('locationsView').hidden,false);assert.equal($('photosView').hidden,true);
location.hash='#frame=next';listeners.hashchange();
assert.equal(selected,1);assert.equal(atlasView,'photos');
assert.equal($('photosView').hidden,false);assert.equal($('locationsView').hidden,true);
location.hash='#frame=query&view=unavailable';listeners.hashchange();
assert.equal(atlasView,'photos');assert.equal(selected,0);
""", initial_hash="#frame=next&view=models")


def test_unavailable_photo_identity_survives_view_changes_and_model_switch():
    run_atlas([photo("query", "flight-a")], r"""
assert.equal(P[selected].key,'absent');assert.equal(requestedFrameKey,'absent');
assert.equal(atlasView,'locations');assert.match($('linkStatus').textContent,/not in the recorded photo inventory/);
showAtlasView('models');
assert.equal(location.hash,'#frame=absent&view=models');
assert.equal(navLinks[0].getAttribute('href'),'embedding-atlas.html#frame=absent&view=models');
assert.equal(navLinks[2].getAttribute('href'),'explorer.html#frame=absent');
select(0);assert.equal(requestedFrameKey,null);
assert.equal(location.hash,'#frame=query&view=models');assert.equal($('linkStatus').textContent,'');
""", initial_hash="#frame=absent&view=locations")
