#!/usr/bin/env python3
"""Unit tests for pin cross-check (no network)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ingest_lib import is_domain_only_source_url  # noqa: E402
from park_geo import (  # noqa: E402
    HUMAN_DROPS,
    HUMAN_RENAMES,
    MANUAL_OVERRIDES,
    GeoHit,
    apply_human_edits,
    apply_to_parks,
    decide,
    geo_names_ok,
    in_mn_polygon,
    looks_swapped,
    query_strings,
    score_hit,
)


NESSEL = {
    "name": "Nessel Campground / Rush Creek",
    "park_type": "county",
    "latitude": 45.627,
    "longitude": -93.137,
    "managing_agency": "Chisago County Parks",
    "source": "curated_greater_mn_county",
    "source_id": "county:nessel-campground-rush-creek",
}

OJIKETA = {
    "name": "Ojiketa Regional Park",
    "park_type": "county",
    "latitude": 45.4195,
    "longitude": -92.6478,
    "managing_agency": "Chisago County Parks",
    "source": "curated_greater_mn_county",
    "source_id": "county:ojiketa-regional-park",
}

SACN = {
    "name": "Saint Croix National Scenic Riverway",
    "park_type": "national",
    "latitude": 45.700192,
    "longitude": -92.361267,
    "managing_agency": "National Park Service",
    "source": "nps_api",
    "source_id": "sacn",
}

VOYA = {
    "name": "Voyageurs National Park",
    "park_type": "national",
    "latitude": 48.483706,
    "longitude": -92.838291,
    "managing_agency": "National Park Service",
    "source": "nps_api",
    "source_id": "voya",
}

ITASCA = {
    "name": "Itasca State Park",
    "park_type": "state",
    "latitude": 47.243,
    "longitude": -95.208,
    "managing_agency": "Minnesota DNR Parks & Trails",
    "source": "mn_dnr_state_parks",
    "source_id": "spk00228",
}


class MnPolygonTests(unittest.TestCase):
    def test_rush_lake_in_mn(self):
        self.assertTrue(in_mn_polygon(45.689118, -93.054827))

    def test_nessel_farmland_still_in_mn(self):
        # The bad pin is inside the state — just not on the unit.
        self.assertTrue(in_mn_polygon(45.627, -93.137))

    def test_st_croix_nps_pin_is_wisconsin(self):
        self.assertFalse(in_mn_polygon(45.700192, -92.361267))

    def test_superior_wi_out(self):
        self.assertFalse(in_mn_polygon(46.72, -92.10))

    def test_voyageurs_in(self):
        self.assertTrue(in_mn_polygon(48.483706, -92.838291))


class SwapTests(unittest.TestCase):
    def test_detects_swapped_pair(self):
        self.assertTrue(looks_swapped(-93.137, 45.627))

    def test_normal_mn_not_swapped(self):
        self.assertFalse(looks_swapped(45.627, -93.137))


class QueryAndScoreTests(unittest.TestCase):
    def test_slash_name_splits(self):
        qs = query_strings(NESSEL)
        blob = " | ".join(qs).lower()
        self.assertIn("nessel campground", blob)
        self.assertIn("rush creek", blob)
        self.assertIn("rush lake", blob)

    def test_admin_score_is_zero(self):
        hit = GeoHit(
            lat=45.686,
            lon=-93.067,
            name="Nessel Township",
            display_name="Nessel Township, Chisago County, Minnesota",
            osm_class="boundary",
            osm_type="administrative",
            source="nominatim",
        )
        self.assertEqual(score_hit(hit, NESSEL), 0)
        self.assertTrue(hit.in_admin())

    def test_rejects_substring_lake_name(self):
        self.assertFalse(
            geo_names_ok("Bald Eagle-Otter Lakes - Bald Eagle Lake", "Bald Eagle Lake")
        )
        self.assertFalse(geo_names_ok("Locke Park", "Locke Circle Park"))
        self.assertTrue(geo_names_ok("Ojiketa Regional Park", "Ojiketa Regional Park"))
        self.assertTrue(geo_names_ok("Shager Park", "Shager County Park"))
        self.assertFalse(geo_names_ok("Gull Lake Recreation Area (county/federal mix)", "County Forest"))

    def test_camp_site_scores_high(self):
        hit = GeoHit(
            lat=45.346,
            lon=-92.888,
            name="Ojiketa Regional Park",
            display_name="Ojiketa Regional Park, Camp Ojiketa, Chisago City, Minnesota",
            osm_class="tourism",
            osm_type="camp_site",
            source="nominatim",
        )
        self.assertGreaterEqual(score_hit(hit, OJIKETA), 8)


class DecideTests(unittest.TestCase):
    def test_nessel_override_moves_to_rush_lake(self):
        d = decide(NESSEL, [])
        self.assertEqual(d.action, "corrected")
        self.assertAlmostEqual(d.latitude, 45.689118, places=5)
        self.assertAlmostEqual(d.longitude, -93.054827, places=5)
        self.assertGreater(d.miles, 4)
        self.assertIn((NESSEL["source"], NESSEL["source_id"]), MANUAL_OVERRIDES)

    def test_ojiketa_moves_to_camp_site(self):
        hit = GeoHit(
            lat=45.3460011,
            lon=-92.8876549,
            name="Ojiketa Regional Park",
            display_name="Ojiketa Regional Park, Camp Ojiketa, Chisago City, Minnesota",
            osm_class="tourism",
            osm_type="camp_site",
            source="nominatim",
            quality=15,
        )
        d = decide(OJIKETA, [hit])
        self.assertEqual(d.action, "corrected")
        self.assertAlmostEqual(d.latitude, 45.346001, places=5)
        self.assertGreater(d.miles, 10)

    def test_does_not_snap_to_township(self):
        hit = GeoHit(
            lat=45.686,
            lon=-93.067,
            name="Nessel Township",
            display_name="Nessel Township, Chisago County, Minnesota",
            osm_class="boundary",
            osm_type="administrative",
            source="nominatim",
            quality=0,
        )
        park = dict(NESSEL, source_id="county:some-other-nessel")
        d = decide(park, [hit], overrides={})
        self.assertNotEqual(d.action, "corrected")
        self.assertEqual(d.latitude, park["latitude"])

    def test_st_croix_outside_mn_snaps_or_uses_vc(self):
        vc = GeoHit(
            lat=45.416155,
            lon=-92.646482,
            name="St. Croix River Visitor Center",
            display_name="St. Croix River Visitor Center",
            osm_class="tourism",
            osm_type="information",
            source="nps_visitorcenter",
            quality=4,  # in Wisconsin
        )
        d = decide(SACN, [], nps_vcs=[vc], overrides={})
        self.assertEqual(d.action, "corrected")
        self.assertTrue(in_mn_polygon(d.latitude, d.longitude))
        self.assertFalse(in_mn_polygon(SACN["latitude"], SACN["longitude"]))

    def test_voyageurs_in_mn_kept(self):
        vc = GeoHit(
            lat=48.584709,
            lon=-93.161146,
            name="Rainy Lake Visitor Center",
            display_name="Rainy Lake Visitor Center",
            osm_class="tourism",
            osm_type="information",
            source="nps_visitorcenter",
            quality=12,
        )
        d = decide(VOYA, [], nps_vcs=[vc], overrides={})
        self.assertEqual(d.action, "keep")
        self.assertEqual(d.latitude, VOYA["latitude"])

    def test_state_park_kept(self):
        d = decide(ITASCA, [], overrides={})
        self.assertEqual(d.action, "keep")

    def test_bald_eagle_does_not_jump_to_boundary_waters(self):
        park = {
            "name": "Bald Eagle-Otter Lakes - Bald Eagle Lake",
            "park_type": "county",
            "latitude": 45.116993,
            "longitude": -93.00599,
            "managing_agency": "Ramsey County Parks",
            "source": "metrogis_collaborative_parks",
            "source_id": "123",
        }
        hit = GeoHit(
            lat=47.824289,
            lon=-91.564864,
            name="Bald Eagle Lake",
            display_name="Bald Eagle Lake, St. Louis County, Minnesota",
            osm_class="natural",
            osm_type="water",
            source="nominatim",
            quality=12,
        )
        d = decide(park, [hit], overrides={})
        self.assertEqual(d.latitude, park["latitude"])
        self.assertNotEqual(d.action, "corrected")

    def test_apply_to_parks_only_corrections(self):
        parks = [dict(NESSEL), dict(VOYA)]
        decisions = [decide(NESSEL, []), decide(VOYA, [], overrides={})]
        changed = apply_to_parks(parks, decisions)
        self.assertGreaterEqual(changed, 1)
        self.assertAlmostEqual(parks[0]["latitude"], 45.689118, places=5)
        self.assertEqual(parks[1]["latitude"], VOYA["latitude"])
        self.assertTrue(parks[0]["source_url_hub"])
        self.assertTrue(parks[1]["source_url_hub"])

    def test_arrowhead_override_uses_maps_point(self):
        park = {
            "name": "Arrowhead Point County Park",
            "park_type": "county",
            "latitude": 43.652,
            "longitude": -93.368,
            "managing_agency": "Freeborn County Parks",
            "source": "curated_greater_mn_county",
            "source_id": "county:arrowhead-point-county-park",
            "source_url": "https://www.co.freeborn.mn.us/",
        }
        d = decide(park, [])
        self.assertEqual(d.action, "corrected")
        self.assertAlmostEqual(d.latitude, 43.739915, places=5)
        self.assertAlmostEqual(d.longitude, -93.553606, places=5)
        self.assertTrue(d.source_url_hub)

    def test_human_edits_drop_and_rename(self):
        parks = [
            {
                "name": "Ortonville / Big Stone County Park",
                "park_type": "county",
                "latitude": 45.305,
                "longitude": -96.445,
                "source": "curated_greater_mn_county",
                "source_id": "county:ortonville-big-stone-county-park",
                "source_url": "https://www.bigstonecounty.org/",
            },
            {
                "name": "Dalles / Snake River County Park",
                "park_type": "county",
                "latitude": 45.826,
                "longitude": -93.010,
                "source": "curated_greater_mn_county",
                "source_id": "county:dalles-snake-river-county-park",
                "source_url": "https://www.co.pine.mn.us/",
            },
            dict(VOYA, source_url="https://www.nps.gov/voya/"),
        ]
        kept, dropped = apply_human_edits(parks)
        self.assertEqual(len(dropped), 1)
        self.assertEqual(dropped[0].action, "dropped")
        self.assertEqual(kept[0]["name"], "Snake River Landing (Pine City)")
        self.assertEqual(kept[0]["source_id"], "county:snake-river-landing-pine-city")
        self.assertIn(
            ("curated_greater_mn_county", "county:ortonville-big-stone-county-park"),
            HUMAN_DROPS,
        )
        self.assertIn(
            ("curated_greater_mn_county", "county:dalles-snake-river-county-park"),
            HUMAN_RENAMES,
        )
        d = decide(kept[0], [])
        self.assertEqual(d.action, "corrected")
        self.assertAlmostEqual(d.latitude, 45.840293, places=5)


class DomainOnlySourceUrlTests(unittest.TestCase):
    def test_flags_missing_slash_and_query_homepage(self):
        self.assertTrue(is_domain_only_source_url(""))
        self.assertTrue(is_domain_only_source_url(None))
        self.assertTrue(is_domain_only_source_url("https://www.chisagocountymn.gov/"))
        self.assertTrue(is_domain_only_source_url("https://www.chisagocountymn.gov"))
        self.assertTrue(is_domain_only_source_url("https://www.chisagocounty.us/"))
        self.assertTrue(is_domain_only_source_url("https://www.example.com/?utm=1"))
        self.assertTrue(is_domain_only_source_url("/"))

    def test_does_not_flag_park_or_department_path(self):
        self.assertFalse(
            is_domain_only_source_url("https://www.chisagocountymn.gov/456/Parks")
        )
        self.assertFalse(
            is_domain_only_source_url("https://www.blueearthcountymn.gov/181/Parks")
        )
        self.assertFalse(
            is_domain_only_source_url(
                "https://www.dnr.state.mn.us/state_parks/park.html?id=spk00115"
            )
        )
        self.assertIn(
            ("curated_greater_mn_county", "county:arrowhead-point-county-park"),
            MANUAL_OVERRIDES,
        )


if __name__ == "__main__":
    unittest.main()
