"""Offline fixtures: tiny HAGR/DAP raw files and a three-record corpus, built into SQLite."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dog_geroscience_mcp.build import build_db
from dog_geroscience_mcp.queries import connect

ANAGE = (
    "HAGRID\tKingdom\tPhylum\tClass\tOrder\tFamily\tGenus\tSpecies\tCommon name\tFemale maturity (days)\t"
    "Male maturity (days)\tGestation/Incubation (days)\tWeaning (days)\tLitter/Clutch size\tLitters/Clutches per year\t"
    "Inter-litter/Interbirth interval\tBirth weight (g)\tWeaning weight (g)\tAdult weight (g)\tGrowth rate (1/days)\t"
    "Maximum longevity (yrs)\tSource\tSpecimen origin\tSample size\tData quality\tIMR (per yr)\tMRDT (yrs)\t"
    "Metabolic rate (W)\tBody mass (g)\tTemperature (K)\tReferences\n"
    "00001\tAnimalia\tChordata\tMammalia\tCarnivora\tCanidae\tCanis\tfamiliaris\tDomestic dog\t\t\t63\t\t6\t\t\t\t\t40000\t\t27\t\tcaptivity\t\tacceptable\t0.02\t3\t\t\t\t1\n"
    "00004\tAnimalia\tChordata\tMammalia\tCarnivora\tCanidae\tCanis\tlupus\tGray wolf\t\t\t63\t\t6\t\t\t\t\t26625\t\t20.6\t\tcaptivity\t\thigh\t\t\t\t\t\t4\n"
    "00005\tAnimalia\tChordata\tMammalia\tCarnivora\tCanidae\tSpeothos\tvenaticus\tBush dog\t\t\t\t\t\t\t\t\t\t6000\t\t14.1\t\tcaptivity\t\tacceptable\t\t\t\t\t\t5\n"
    "00002\tAnimalia\tChordata\tMammalia\tPrimates\tHominidae\tHomo\tsapiens\tHuman\t\t\t270\t\t1\t\t\t\t\t62035\t\t122.5\t\twild\t\thigh\t0.0002\t8\t\t\t\t2\n"
    "00003\tAnimalia\tChordata\tMammalia\tRodentia\tMuridae\tMus\tmusculus\tHouse mouse\t\t\t19\t\t7\t\t\t\t\t20.5\t\t4\t\tcaptivity\t\thigh\t0.01\t0.3\t\t\t\t3\n"
)

DRUGAGE = (
    "compound_name,species,strain,dosage,age_at_initiation,treatment_duration,avg_lifespan_change_percent,"
    "avg_lifespan_significance,max_lifespan_change_percent,max_lifespan_significance,gender,weight_change_percent,"
    "weight_change_significance,ITP,pubmed_id\n"
    "Rapamycin,Mus musculus,UM-HET3,14 ppm,600 days,,9,S,13.6,S,Male,,NA,Yes,19587680\n"
    "Rapamycin,Mus musculus,UM-HET3,14 ppm,600 days,,14,S,9,S,Female,,NA,Yes,19587680\n"
    "Rapamycin,Rattus norvegicus,Wistar,2 mg/kg,12 months,,5,NS,,NA,Male,,NA,No,99999999\n"
    "L-deprenyl,Canis lupus familiaris,Beagle,1 mg/kg,,,,S,,NA,Both,,NA,No,9307048\n"
    "Acarbose,Mus musculus,UM-HET3,1000 ppm,4 months,,22,S,11,S,Male,,NA,Yes,24245565\n"
)

GENAGE_HUMAN = (
    "GenAge ID,symbol,name,entrez gene id,uniprot,why\n"
    "1,GHR,growth hormone receptor,2690,GHR_HUMAN,mammal\n"
    "2,IGF1R,insulin like growth factor 1 receptor,3480,IGF1R_HUMAN,mammal\n"
    "3,MTOR,mechanistic target of rapamycin kinase,2475,MTOR_HUMAN,\"mammal,model\"\n"
)

GENAGE_MODELS = (
    "GenAge ID,symbol,name,organism,entrez gene id,avg lifespan change (max obsv),lifespan effect,longevity influence\n"
    "1,Igf1r,insulin-like growth factor I receptor,Mus musculus,16001,33,Increase,Anti-Longevity\n"
    "2,mTor,mechanistic target of rapamycin,Mus musculus,56717,20,Increase,Anti-Longevity\n"
)

DAP_2025 = (
    "DataFile,Variable,SurveyText,Values,ValueLabels\n"
    "Dog_Overview,dog_id,Study ID,Numeric,NA\n"
    "HLES_health_conditions,hs_condition_type,Health condition category,\"1, 2, 3\",\"1, Eye; 2, Ear/Nose/Throat; 3, Oral/Dental\"\n"
    "HLES_dog_owner,mp_rapamycin,Is your dog currently taking rapamycin (sirolimus)?,\"0, 1\",\"0, No; 1, Yes\"\n"
    "EOLS,eol_cause_death,What was the cause of your dog's death?,\"1, 2, 98\",\"1, Illness/disease; 2, Injury/trauma; 98, Other\"\n"
)
DAP_2024 = "DataFile,Variable,SurveyText,Values,ValueLabels\nDog_Overview,dog_id,Study ID,Numeric,NA\n"

RECORDS = [
    {
        "key": "MED:38263575", "id": "38263575", "source": "MED", "pmid": "38263575", "pmcid": "PMC0000001",
        "doi": "10.1000/x", "title": "Weekly rapamycin in companion dogs: a test article",
        "abstract": "Dogs age faster than humans. In this randomized, placebo-controlled trial, rapamycin was well tolerated.", "journal": "GeroScience",
        "year": 2026, "first_publication_date": "2026-01-23", "pub_types": ["research-article"],
        "mesh": [{"descriptor": "Dogs", "major": True, "qualifiers": []}, {"descriptor": "Sirolimus", "major": False, "qualifiers": []}],
        "keywords": ["Aging", "Rapamycin"], "is_open_access": True, "license": "cc by", "cited_by_count": 4,
        "tiers": ["core", "extended"], "retrieved_at": "2026-09-28T00:00:00+00:00",
    },
    {
        "key": "MED:1", "id": "1", "source": "MED", "pmid": "1", "pmcid": None, "doi": None,
        "title": "Dental disease in senior dogs", "abstract": "Periodontal disease is common in geriatric dogs.",
        "journal": "JAVMA", "year": 2019, "pub_types": [], "mesh": [], "keywords": [], "is_open_access": False,
        "license": None, "cited_by_count": 0, "tiers": ["extended"], "retrieved_at": "t",
    },
    {
        "key": "PPR:PPR900001", "id": "PPR900001", "source": "PPR", "pmid": None, "pmcid": None,
        "doi": "10.1101/2026.06.03.729926", "title": "Dog breed inference with machine learning",
        "abstract": "Preprint on ancestry and lifespan in the Dog Aging Project.", "journal": None, "year": 2026,
        "pub_types": [], "mesh": [], "keywords": ["lifespan"], "is_open_access": False, "license": None,
        "cited_by_count": 0, "tiers": ["core", "extended"], "retrieved_at": "t",
    },
]


@pytest.fixture(scope="session")
def raw_dir(tmp_path_factory) -> Path:
    raw = tmp_path_factory.mktemp("raw")
    (raw / "anage_data.txt").write_text(ANAGE, encoding="utf-8")
    (raw / "drugage.csv").write_text(DRUGAGE, encoding="utf-8")
    (raw / "genage_human.csv").write_text(GENAGE_HUMAN, encoding="utf-8")
    (raw / "genage_models.csv").write_text(GENAGE_MODELS, encoding="utf-8")
    d = raw / "dap_codebooks"
    d.mkdir()
    (d / "DAP_2025_CODEBOOK_v1.0.csv").write_text(DAP_2025, encoding="utf-8")
    (d / "DAP_2024_CODEBOOK_v1.1.csv").write_text(DAP_2024, encoding="utf-8")
    (raw / "download_manifest.json").write_text(json.dumps({"anage": {"url": "fixture"}}), encoding="utf-8")
    return raw


@pytest.fixture(scope="session")
def corpus_dir(tmp_path_factory) -> Path:
    c = tmp_path_factory.mktemp("corpus")
    with (c / "records.jsonl").open("w", encoding="utf-8") as fh:
        for r in RECORDS:
            fh.write(json.dumps(r) + "\n")
    md = c / "fulltext" / "md"
    md.mkdir(parents=True)
    (md / "PMC0000001.md").write_text("---\npmcid: \"PMC0000001\"\n---\n\n# Weekly rapamycin\n\n## Methods\n\nWe enrolled 580 dogs.\n", encoding="utf-8")
    (c / "corpus_version.json").write_text(json.dumps({"corpus_version": "2026.09.28", "records_sha256": "abc"}), encoding="utf-8")
    return c


@pytest.fixture(scope="session")
def db_path(raw_dir, corpus_dir, tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("db") / "dog_geroscience.sqlite"
    build_db(raw_dir, corpus_dir, out)
    return out


@pytest.fixture()
def conn(db_path):
    c = connect(db_path)
    yield c
    c.close()
