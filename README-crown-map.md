# Crown map

`docs/crown-map.html` is a map of Barro Colorado Island (BCI), Panama. It shows every tree crown that a detection model found on one drone mosaic of the island. Each crown has a species guess from a classifier. The map lets you see where the classifier puts each species and how sure it is.

A guess is not a label. No botanist checked these crowns. Use a guess as a reason to go and look.

## What you need

- A browser.
- The data link. The page holds no crowns. The crowns are in a private file, and the link to that file comes from the team. Do not publish the link.

## Open the map

1. Open the crown map on the site, or run `python3 -m http.server 8000 -d docs` and open `http://localhost:8000/crown-map.html`.
2. Add `#data=` and the data link to the end of the address.
3. Press Enter. The map shows the whole island.

If the map says that the data link did not open, the link is out of date. Ask the team for a new link.

## Read the map

- **One shape is one crown.** A detection model drew the outline. A botanist did not.
- **The colour is the family** of the first guess. Families in the same order or clade have similar colours.
- **A fainter crown is a less sure guess.** Confidence is the score that the classifier gives to its first guess. It is not a measured accuracy.
- **Far out, crowns are filled. Close in, crowns are outlines**, so that you can see the canopy below them. Closer still, each crown shows the name of its first guess.

## Do a task

| You want to | Do this |
|---|---|
| See the first guess for a crown | Point at the crown. |
| See the five guesses for a crown | Click the crown. |
| Close the five guesses | Press Escape. |
| Read a crown without a mouse | Press Tab until the map has the focus. A white cross shows at the centre. Move the map with the arrow keys. Press Enter to read the crown under the cross. |
| Find more candidates for one species | Show only that species. Then select "Also where it is a lower guess". The map adds the crowns that have the species as guess two to five. |
| See where one species is | Type its name in **Show only one species**, or click a name in **Most common first guesses**, or click a crown and then **Show only this species**. |
| See all species again | Click **Show all** next to the species box. |
| Hide the unsure guesses | Move the slider below the chart. The grey bars are the crowns that you hide. |
| Hide or show a family, order or clade | Click its name in **Crowns in view**. |
| Send someone the same map | Copy the address. It keeps the view, the confidence level and the species. It also holds the data link, so send it only to the team. |

## Read the numbers

- The numbers below **Crowns in view** count **every crown in the file**.
- **Crowns in view** counts only the crowns on screen, after the confidence level and the species that you set.
- The chart counts crowns in each 10% step of confidence.
- **How this map was made** gives the accuracy on test crowns. These are crowns with a label that the classifier did not see in training.

## Do not conclude these things

- A common first guess does not show that a species is common.
- High confidence does not show that a guess is right.
- The accuracy on test crowns is not the accuracy of the whole map. Test crowns are easier than a typical crown outside the plots.
- One outline is not always one tree. Two crowns that touch can be one outline. One large tree can be two outlines. Trees below the canopy do not show.

## Change the page

The page is built. Do not edit `docs/crown-map.html` by hand.

1. Edit the template in `dashboard/crown_map_assets.py`.
2. Run `.venv/bin/python dashboard/build_crown_map.py`.
3. Run `.venv/bin/pytest -q tests/test_crown_map.py`.

The build makes no network call. It puts only the taxon tree and its colours in the page. The summary numbers come from the crown file when the page opens.

## Words

| Word | Meaning |
|---|---|
| crown | The top of one tree, seen from above. On this map, a detection model drew each crown. |
| mosaic | One image of the whole island, made from many drone photos. |
| classifier | The model that gives each crown five species guesses. |
| first guess | The guess with the highest confidence. |
| confidence | The score from 0% to 100% that the classifier gives to a guess. |
| test crowns | Crowns with a label that the classifier did not see in training. Accuracy is measured on them. |
| data link | The private address of the crown file. |
