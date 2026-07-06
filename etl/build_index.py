# -*- coding: utf-8 -*-
"""Gera o index.json a partir dos anos processados na pasta dados/resultados/."""
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTADOS_DIR = PROJECT_ROOT / "dados" / "resultados"
OUT_FILE = PROJECT_ROOT / "dados" / "index.json"

def build_index():
    print("=== Generating index.json ===")
    if not RESULTADOS_DIR.exists():
        print("Erro: pasta dados/resultados não existe.")
        return
        
    jsons = sorted(RESULTADOS_DIR.glob("ar_*.json"))
    years = []
    
    for jp in jsons:
        # Pega o ano do nome do arquivo ar_{ano}.json
        name = jp.stem
        year_str = name.split("_")[1]
        years.append(year_str)
        
    # Ordena decrescentemente (mais recente primeiro)
    years = sorted(years, key=int, reverse=True)
    
    payload = {
        "years": years
    }
    
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        
    print(f"  -> index.json gerado com {len(years)} anos: {years}")

if __name__ == "__main__":
    build_index()
