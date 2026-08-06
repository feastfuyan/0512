"""
Adversarial test suite — 50 Prompt Injection cases.

Goal: 100% capture rate on the patterns defined in
`safety/patterns/pi_patterns.yaml`. Any FAIL here blocks PR merge.

Layout (10 + 10 + 10 + 10 + 5 + 5 = 50):
  pi_chinese.py   — 10 cases, direct Chinese PI
  pi_english.py   — 10 cases, direct English PI
  pi_mixed.py     — 10 cases, mixed Zh/En
  pi_news.py      — 10 cases, indirect injection via news / research text
  pi_pdf.py       —  5 cases, PDF steganography surrogate inputs
  pi_social.py    —  5 cases, social-media adversarial templates

Run only this suite:
    pytest tests/adversarial/ -v --tb=short
"""
