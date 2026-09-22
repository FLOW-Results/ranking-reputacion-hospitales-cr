"""Ayudante mínimo para la API de Firecrawl (v2).

Uso desde otros scripts:
    from fc import scrape, search
La llave se lee de FIRECRAWL_API_KEY o, si no está en el entorno, de ~/.bash_profile.
"""
import json
import os
import re
import sys
import time
import requests

API = "https://api.firecrawl.dev/v2"


def api_key() -> str:
    key = os.environ.get("FIRECRAWL_API_KEY")
    if key:
        return key
    prof = os.path.expanduser("~/.bash_profile")
    if os.path.exists(prof):
        for line in open(prof, encoding="utf-8"):
            m = re.match(r'\s*(?:export\s+)?FIRECRAWL_API_KEY\s*=\s*"?([^"\s]+)"?', line)
            if m:
                return m.group(1)
    sys.exit("Falta FIRECRAWL_API_KEY (variable de entorno o ~/.bash_profile)")


import threading

_RPM = int(os.environ.get("FIRECRAWL_RPM", "10"))   # solicitudes por minuto (el plan actual corta cerca de 15)
_bloqueo = threading.Lock()
_ultimas = []


def _esperar_turno():
    """Regulador simple: no más de _RPM solicitudes en cualquier ventana de 60 s, compartido entre hilos."""
    while True:
        with _bloqueo:
            ahora = time.time()
            _ultimas[:] = [t for t in _ultimas if ahora - t < 60]
            if len(_ultimas) < _RPM:
                _ultimas.append(ahora)
                return
            espera = 60 - (ahora - _ultimas[0]) + 0.5
        time.sleep(max(espera, 0.5))


def _post(path: str, payload: dict, timeout: int = 180, retries: int = 4) -> dict:
    last = None
    for intento in range(retries):
        _esperar_turno()
        try:
            r = requests.post(
                API + path, json=payload, timeout=timeout,
                headers={"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"},
            )
            if r.status_code in (401, 402):
                return {"success": False, "error": f"HTTP {r.status_code}: {r.text[:300]}"}
            if r.status_code == 429:
                last = f"HTTP 429: {r.text[:200]}"
                time.sleep(20 * (intento + 1))
                continue
            if r.status_code >= 400:
                last = f"HTTP {r.status_code}: {r.text[:300]}"
            else:
                return r.json()
        except Exception as e:  # timeouts, red
            last = repr(e)
        time.sleep(3 * (intento + 1))
    return {"success": False, "error": last}


def scrape(url: str, formats=None, wait_for: int = 6000, country: str = "CR", timeout: int = 180) -> dict:
    """Devuelve el objeto `data` de Firecrawl (markdown/html/json según formats) o {"error": ...}."""
    payload = {
        "url": url,
        "formats": formats or ["markdown"],
        "waitFor": wait_for,
        "location": {"country": country, "languages": ["es"]},
    }
    res = _post("/scrape", payload, timeout=timeout)
    if not res.get("success"):
        return {"error": res.get("error", "sin detalle")}
    return res.get("data", {})


def search(query: str, limit: int = 8, country: str = "CR", scrape_content: bool = False) -> list:
    """Búsqueda web. Devuelve lista de {url, title, description[, markdown]}."""
    payload = {"query": query, "limit": limit, "location": country}
    if scrape_content:
        payload["scrapeOptions"] = {"formats": ["markdown"]}
    res = _post("/search", payload, timeout=120)
    if not res.get("success"):
        return [{"error": res.get("error", "sin detalle")}]
    data = res.get("data", [])
    if isinstance(data, dict):
        data = data.get("web", [])
    return data


if __name__ == "__main__":
    # CLI rápida: python3 fc.py search "consulta"  |  python3 fc.py scrape URL [markdown|html]
    if len(sys.argv) >= 3 and sys.argv[1] == "search":
        print(json.dumps(search(" ".join(sys.argv[2:])), ensure_ascii=False, indent=1))
    elif len(sys.argv) >= 3 and sys.argv[1] == "scrape":
        fmt = sys.argv[3] if len(sys.argv) > 3 else "markdown"
        d = scrape(sys.argv[2], formats=[fmt])
        print(d.get(fmt) or d.get("error"))
    else:
        print(__doc__)
