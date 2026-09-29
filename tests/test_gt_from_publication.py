"""The reviewed-label ground truth built from the publication workbook.

The workbook is built here as a minimal xlsx (the XML parts the reader opens),
so the tests pin the stdlib parser as well as the matching rules.
"""

import csv
import json
import zipfile
from xml.sax.saxutils import escape

import pytest
from conftest import REPO, load

HEADER = [
    "canopyrs_object_id",
    "site",
    "zoom link",
    "FINAL_SPECIES",
    "especie_1",
    "zoom_url_legacy",
]
LEGACY = "https://object-arbutus.cloud.computecanada.ca/m1/f1/"
CURRENT = "https://object-arbutus.alliancecan.ca/swift/v1/x/m1/f1/"


@pytest.fixture(scope="module")
def gfp():
    return load(
        "_gt_from_publication_under_test", REPO / "labelling" / "gt_from_publication.py"
    )


def col(i):
    return chr(ord("A") + i)


def write_xlsx(path, rows, sheet="master"):
    """A workbook whose ``sheet`` holds ``rows``; strings shared, like Excel's."""
    strings, xml_rows = [], []
    for r, row in enumerate(rows, 1):
        cells = []
        for c, value in enumerate(row):
            if value is None:
                continue
            strings.append(value)
            cells.append(f'<c r="{col(c)}{r}" t="s"><v>{len(strings) - 1}</v></c>')
        xml_rows.append(f'<row r="{r}">{"".join(cells)}</row>')
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(
            "xl/workbook.xml",
            f'<workbook {ns} xmlns:r="{rel_ns}"><sheets>'
            f'<sheet name="{sheet}" sheetId="1" r:id="rId5"/></sheets></workbook>',
        )
        z.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
            'relationships"><Relationship Id="rId5" Target="worksheets/sheet1.xml"/>'
            "</Relationships>",
        )
        z.writestr(
            "xl/sharedStrings.xml",
            f"<sst {ns}>"
            + "".join(f"<si><t>{escape(s)}</t></si>" for s in strings)
            + "</sst>",
        )
        z.writestr(
            "xl/worksheets/sheet1.xml",
            f"<worksheet {ns}><sheetData>{''.join(xml_rows)}</sheetData></worksheet>",
        )
    return path


def crown(cid, species, url, site="bci"):
    return [cid, site, "zoom", species, species, url]


def run(gfp, tmp_path, crowns, gt, inventory, header=HEADER):
    """Write the three inputs, run the builder, return its rows keyed by frame."""
    book = write_xlsx(tmp_path / "book.xlsx", [header, *crowns])
    gt_csv = tmp_path / "gt.csv"
    with open(gt_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["global_key", "wcvp_canonical_name"])
        w.writerows(gt.items())
    inv = tmp_path / "inventory.jsonl"
    inv.write_text(
        "".join(
            json.dumps({"global_key": k, "row_data": u}) + "\n"
            for k, u in inventory.items()
        ),
        encoding="utf-8",
    )
    out = tmp_path / "out.csv"
    gfp.main(
        [
            "--workbook",
            str(book),
            "--gt",
            str(gt_csv),
            "--inventory",
            str(inv),
            "--out",
            str(out),
        ]
    )
    with open(out, newline="", encoding="utf-8") as f:
        return {r["global_key"]: r for r in csv.DictReader(f)}


def test_exact_legacy_url_match_takes_the_reviewed_label(gfp, tmp_path):
    rows = run(
        gfp,
        tmp_path,
        [crown("1", "Ceiba pentandra [CEIBPE]", LEGACY + "A_zoom.JPG")],
        {"comb_A_zoom.JPG": "Pseudobombax septenatum"},
        {"comb_A_zoom.JPG": LEGACY + "A_zoom.JPG"},
    )
    r = rows["comb_A_zoom.JPG"]
    assert r["wcvp_canonical_name"] == "Ceiba pentandra"
    assert r["label_source"] == "publication_reviewed"
    assert r["labelbox_name"] == "Pseudobombax septenatum"
    assert r["canopyrs_object_id"] == "1"


def test_same_filename_under_another_url_is_not_a_match(gfp, tmp_path):
    rows = run(
        gfp,
        tmp_path,
        [crown("1", "Ceiba pentandra [CEIBPE]", CURRENT + "A_zoom.JPG")],
        {"comb_A_zoom.JPG": "Pseudobombax septenatum"},
        {"comb_A_zoom.JPG": LEGACY + "A_zoom.JPG"},
    )
    assert rows["comb_A_zoom.JPG"]["label_source"] == "labelbox_unreviewed"


def test_only_bci_crowns_are_used(gfp, tmp_path):
    rows = run(
        gfp,
        tmp_path,
        [
            crown(
                "357945", "Ceiba pentandra [CEIBPE]", LEGACY + "A_zoom.JPG", site="tbs"
            )
        ],
        {"comb_A_zoom.JPG": "Pseudobombax septenatum"},
        {"comb_A_zoom.JPG": LEGACY + "A_zoom.JPG"},
    )
    r = rows["comb_A_zoom.JPG"]
    assert r["label_source"] == "labelbox_unreviewed"
    assert r["wcvp_canonical_name"] == "Pseudobombax septenatum"


def test_unmatched_frames_are_kept_and_flagged(gfp, tmp_path):
    rows = run(
        gfp,
        tmp_path,
        [crown("1", "Ceiba pentandra [CEIBPE]", LEGACY + "A_zoom.JPG")],
        {
            "comb_A_zoom.JPG": "Ceiba pentandra",
            "comb_B_zoom.JPG": "Inga",
            "comb_C_zoom.JPG": "Hura crepitans",
        },
        {
            "comb_A_zoom.JPG": LEGACY + "A_zoom.JPG",
            "comb_B_zoom.JPG": LEGACY + "B_zoom.JPG",
        },
    )
    assert list(rows) == ["comb_A_zoom.JPG", "comb_B_zoom.JPG", "comb_C_zoom.JPG"]
    for key, name in [
        ("comb_B_zoom.JPG", "Inga"),
        ("comb_C_zoom.JPG", "Hura crepitans"),
    ]:
        assert rows[key]["label_source"] == "labelbox_unreviewed"
        assert rows[key]["wcvp_canonical_name"] == name
        assert rows[key]["canopyrs_object_id"] == ""
    sidecar = (tmp_path / "out.provenance.txt").read_text(encoding="utf-8")
    assert "on 1 of 3 labelled frames" in sidecar and "other 2" in sidecar


def test_a_url_two_crowns_share_is_not_used(gfp, tmp_path):
    rows = run(
        gfp,
        tmp_path,
        [
            crown("1", "Ceiba pentandra [CEIBPE]", LEGACY + "A_zoom.JPG"),
            crown("2", "Hura crepitans [HURACR]", LEGACY + "A_zoom.JPG"),
        ],
        {"comb_A_zoom.JPG": "Ceiba pentandra"},
        {"comb_A_zoom.JPG": LEGACY + "A_zoom.JPG"},
    )
    assert rows["comb_A_zoom.JPG"]["label_source"] == "labelbox_unreviewed"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Hieronyma alchorneoides [HYERAL]", "Hieronyma alchorneoides"),
        ("Coussapoa villosa", "Coussapoa villosa"),
        ("  Alseis   blackiana [ALSEBL] ", "Alseis blackiana"),
        ("Terminalia amazonica [TER1AM]", "Terminalia amazonia"),
    ],
)
def test_reviewed_names_are_cleaned_to_the_labelbox_vocabulary(
    gfp, core, raw, expected
):
    assert gfp.reviewed_name(raw) == expected
    canon = core.canonicaliser({})
    assert canon(gfp.reviewed_name(raw)) == canon(expected)


def test_missing_column_fails_naming_it(gfp, tmp_path):
    header = [h for h in HEADER if h != "zoom_url_legacy"]
    book = write_xlsx(
        tmp_path / "b.xlsx", [header, ["1", "bci", "z", "Ceiba", "Ceiba"]]
    )
    with pytest.raises(SystemExit, match="zoom_url_legacy"):
        gfp.read_sheet(book)


def test_empty_sheet_and_header_only_fail(gfp, tmp_path):
    with pytest.raises(SystemExit, match="is empty"):
        gfp.read_sheet(write_xlsx(tmp_path / "e.xlsx", []))
    with pytest.raises(SystemExit, match="no rows"):
        gfp.read_sheet(write_xlsx(tmp_path / "h.xlsx", [HEADER]))


def test_absent_sheet_fails(gfp, tmp_path):
    book = write_xlsx(tmp_path / "s.xlsx", [HEADER], sheet="other")
    with pytest.raises(SystemExit, match="no sheet named 'master'"):
        gfp.read_sheet(book)


def test_blank_reviewed_species_fails(gfp, tmp_path):
    with pytest.raises(SystemExit, match="empty FINAL_SPECIES"):
        run(
            gfp,
            tmp_path,
            [crown("7", None, LEGACY + "A_zoom.JPG")],
            {"comb_A_zoom.JPG": "Ceiba pentandra"},
            {"comb_A_zoom.JPG": LEGACY + "A_zoom.JPG"},
        )


def test_measure_filter_refuses_a_gt_without_label_source(health):
    with pytest.raises(SystemExit, match="no label_source column"):
        health.only_label_source(
            [{"global_key": "k", "wcvp_canonical_name": "x"}],
            "publication_reviewed",
            "gt.csv",
        )
    rows = [
        {
            "global_key": "k",
            "wcvp_canonical_name": "x",
            "label_source": "labelbox_unreviewed",
        }
    ]
    with pytest.raises(SystemExit, match="found: labelbox_unreviewed"):
        health.only_label_source(rows, "publication_reviewed", "gt.csv")
    assert health.only_label_source(rows, "labelbox_unreviewed", "gt.csv") == rows


def test_the_workbook_default_is_the_core_constant(gfp, core):
    assert gfp.parse_args([]).workbook == core.PUBLICATION_WORKBOOK


def test_a_missing_workbook_fails_and_never_falls_back(gfp, tmp_path):
    out = tmp_path / "out.csv"
    with pytest.raises(SystemExit) as e:
        gfp.main(["--workbook", str(tmp_path / "absent.xlsx"), "--out", str(out)])
    msg = str(e.value)
    assert "absent.xlsx" in msg
    assert "no fallback to the Labelbox labels" in msg
    assert not out.exists()


def test_check_reads_the_sheet_and_writes_nothing(gfp, tmp_path, capsys):
    book = write_xlsx(tmp_path / "b.xlsx", [HEADER, crown("1", "Ceiba", LEGACY + "A.JPG")])
    out = tmp_path / "out.csv"
    gfp.main(["--workbook", str(book), "--out", str(out), "--check"])
    assert "workbook ok" in capsys.readouterr().out
    assert not out.exists()
    with pytest.raises(SystemExit, match="zoom_url_legacy"):
        gfp.main(["--workbook", str(write_xlsx(tmp_path / "c.xlsx", [HEADER[:-1], ["1"]])),
                  "--check"])
