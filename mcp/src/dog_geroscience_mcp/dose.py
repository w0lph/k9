"""Allometric dose translation using the FDA body-surface-area (Km) method.

Source: FDA CDER, *Guidance for Industry: Estimating the Maximum Safe Starting Dose in
Initial Clinical Trials for Therapeutics in Adult Healthy Volunteers* (July 2005), Table 1.
HED (mg/kg) = animal dose (mg/kg) × (animal Km / human Km). The same ratio generalises to
any pair of species. This is a starting-point heuristic, not a substitute for
pharmacokinetic data.
"""

from __future__ import annotations

# species -> (reference body weight kg, Km factor)
KM_TABLE: dict[str, tuple[float, int]] = {
    "human": (60.0, 37),
    "child": (20.0, 25),
    "mouse": (0.02, 3),
    "hamster": (0.08, 5),
    "rat": (0.15, 6),
    "ferret": (0.30, 7),
    "guinea pig": (0.40, 8),
    "rabbit": (1.8, 12),
    "dog": (10.0, 20),
    "monkey": (3.0, 12),
    "marmoset": (0.35, 6),
    "squirrel monkey": (0.60, 7),
    "baboon": (12.0, 20),
    "micro-pig": (20.0, 27),
    "mini-pig": (40.0, 35),
}

ALIASES = {
    "humans": "human",
    "man": "human",
    "adult": "human",
    "mice": "mouse",
    "rats": "rat",
    "dogs": "dog",
    "canine": "dog",
    "canis lupus familiaris": "dog",
    "beagle": "dog",
    "rhesus": "monkey",
    "cynomolgus": "monkey",
    "macaque": "monkey",
    "minipig": "mini-pig",
    "micropig": "micro-pig",
    "guinea-pig": "guinea pig",
    "guineapig": "guinea pig",
}


def normalise_species(name: str) -> str:
    key = name.strip().lower()
    key = ALIASES.get(key, key)
    if key not in KM_TABLE:
        raise ValueError(f"unknown species {name!r}; known: {sorted(KM_TABLE)}")
    return key


def translate(dose_mg_per_kg: float, from_species: str, to_species: str = "dog") -> dict:
    src = normalise_species(from_species)
    dst = normalise_species(to_species)
    km_src = KM_TABLE[src][1]
    km_dst = KM_TABLE[dst][1]
    factor = km_src / km_dst
    return {
        "from_species": src,
        "to_species": dst,
        "dose_mg_per_kg_in": dose_mg_per_kg,
        "dose_mg_per_kg_out": round(dose_mg_per_kg * factor, 4),
        "km_from": km_src,
        "km_to": km_dst,
        "factor": round(factor, 4),
        "formula": f"dose_out = dose_in × (Km[{src}] / Km[{dst}]) = {dose_mg_per_kg} × ({km_src}/{km_dst})",
        "reference_weights_kg": {src: KM_TABLE[src][0], dst: KM_TABLE[dst][0]},
        "source": "FDA CDER guidance, July 2005, Table 1 (body-surface-area method)",
        "caveat": "Allometric starting-point estimate; confirm with species pharmacokinetics.",
    }
