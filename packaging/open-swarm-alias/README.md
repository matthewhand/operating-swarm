# `open-swarm` is a deprecated alias

**This package is not Operating Swarm.** It exists so `pip install open-swarm`
still resolves after the product moved.

- **Product:** Operating Swarm (OS)
- **Install:** `pip install os-core`
- **Source:** https://github.com/matthewhand/operating-swarm

`open-swarm` 0.5.4 and earlier were the full application. This 0.5.5+ stub
depends on `os-core` only. Console scripts (`os-cli`, `os-api`) ship with
`os-core`, not this alias. Do not yank 0.5.4.

Historical 0.5.4 wheels remain on PyPI for existing pins.
