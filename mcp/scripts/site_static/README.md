Search-engine verification assets copied into docs/ by build_site.py.

- verification.json: meta-tag tokens for the home page (google-site-verification, msvalidate.01 for Bing). Empty values are skipped.
- Any other file here (google<token>.html, BingSiteAuth.xml) is copied verbatim to the site root.
