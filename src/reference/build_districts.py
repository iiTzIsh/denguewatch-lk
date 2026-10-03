"""Build reference/districts.csv from geoBoundaries gbOpen LKA ADM2 polygon centroids (OSM, ODbL 1.0).

A centroid outside its polygon is replaced by a representative interior point.
Run:  python -m src.reference.build_districts     (requires shapely)
"""

from __future__ import annotations

import json
import re

import pandas as pd
import requests

from src.config import REFERENCE_DIR

URL = (
    "https://media.githubusercontent.com/media/wmgeolab/geoBoundaries/main/"
    "releaseData/gbOpen/LKA/ADM2/geoBoundaries-LKA-ADM2_simplified.geojson"
)

PROVINCE = {
    "Colombo": "Western",
    "Gampaha": "Western",
    "Kalutara": "Western",
    "Kandy": "Central",
    "Matale": "Central",
    "Nuwara Eliya": "Central",
    "Galle": "Southern",
    "Matara": "Southern",
    "Hambantota": "Southern",
    "Jaffna": "Northern",
    "Kilinochchi": "Northern",
    "Mannar": "Northern",
    "Vavuniya": "Northern",
    "Mullaitivu": "Northern",
    "Batticaloa": "Eastern",
    "Ampara": "Eastern",
    "Trincomalee": "Eastern",
    "Kurunegala": "North Western",
    "Puttalam": "North Western",
    "Anuradhapura": "North Central",
    "Polonnaruwa": "North Central",
    "Badulla": "Uva",
    "Monaragala": "Uva",
    "Ratnapura": "Sabaragamuwa",
    "Kegalle": "Sabaragamuwa",
}


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def main() -> None:
    from shapely.geometry import shape  # optional dependency

    features = json.loads(requests.get(URL, timeout=60).text)["features"]
    rows = []
    for f in features:
        name = f["properties"]["shapeName"].replace(" District", "")
        geom = shape(f["geometry"])
        pt = geom.centroid if geom.contains(geom.centroid) else geom.representative_point()
        rows.append(
            {
                "district": slug(name),
                "district_name": name,
                "province": PROVINCE[name],
                "latitude": round(pt.y, 4),
                "longitude": round(pt.x, 4),
                "coord_source": "geoBoundaries gbOpen LKA ADM2 centroid (OSM, ODbL)",
            }
        )
    df = pd.DataFrame(rows).sort_values("district")
    assert len(df) == 25, f"expected 25 districts, got {len(df)}"
    out = REFERENCE_DIR / "districts.csv"
    df.to_csv(out, index=False)
    print(f"wrote {len(df)} districts -> {out}")


if __name__ == "__main__":
    main()
