# -*- coding: utf-8 -*-
"""Shapefile -> GeoJSON (WGS84, simplificado) para o visualizador.

Uso:
    python etl/build_maps.py 2025 2022
    python etl/build_maps.py --all

Saída: dados/mapas/freguesias_{ano}.geojson, concelhos_{ano}.geojson, distritos_{ano}.geojson
"""
import json
import sys

import numpy as np
import pandas as pd
import geopandas as gpd
import shapely
from shapely.geometry import mapping

from common import (MAPAS_DIR, OUT_DIR, YEARS, norm_dicofre, circulo_from_dicofre,
                    has_mojibake, BBOX_CONTINENTE, BBOX_MADEIRA, BBOX_ACORES)

KEY_CANDIDATES = ["DICOFRE", "dicofre", "Dicofre", "dtmnfr", "DTMNFR"]
NAME_CANDIDATES = ["Freguesia", "FREGUESIA", "freguesia", "Nome", "NOME", "nome",
                   "designacao", "Des_Simpli"]
CONCELHO_CANDIDATES = ["Municipio", "MUNICIPIO", "municipio", "Concelho", "CONCELHO",
                       "concelho"]
SMALL_WORDS = {"de", "da", "do", "das", "dos", "e", "a", "o", "à", "d'"}


def smart_title(s):
    """CALHETA DE NESQUIM -> Calheta de Nesquim (só quando está todo em maiúsculas)."""
    if not isinstance(s, str) or s != s.upper():
        return s
    words = s.lower().split()
    out = []
    for i, w in enumerate(words):
        out.append(w if (i > 0 and w in SMALL_WORDS) else w.capitalize())
    return " ".join(out)


def find_col(df, candidates):
    for c in candidates:
        if c in df.columns:
            return c
    return None


def read_shapefile(path):
    """Lê um shapefile corrigindo mojibake (cpg errado) se necessário."""
    try:
        gdf = gpd.read_file(path)
        text_cols = [c for c in gdf.columns if gdf[c].dtype == object]
        sample = " ".join(str(v) for c in text_cols for v in gdf[c].head(200).tolist())
        if not has_mojibake(sample):
            return gdf, None
    except Exception as e:
        pass

    for enc in ("cp1252", "latin1"):
        try:
            gdf2 = gpd.read_file(path, encoding=enc)
            text_cols = [c for c in gdf2.columns if gdf2[c].dtype == object]
            sample2 = " ".join(str(v) for c in text_cols for v in gdf2[c].head(200).tolist())
            if not has_mojibake(sample2):
                return gdf2, enc
        except Exception:
            pass
    print(f"  AVISO: mojibake persistente ou erro de encoding em {path.name}")
    try:
        return gpd.read_file(path, encoding="cp1252"), "cp1252"
    except Exception:
        return gpd.read_file(path), None


def find_year_shapefile(root, year):
    """Encontra o .shp de um ano; prefere o que tem o ano no nome."""
    folder = root / str(year)
    if not folder.exists():
        return None
    shps = sorted(folder.rglob("*.shp"))
    if not shps:
        return None
    
    # Se estamos na pasta continente freguesias, tentamos excluir ficheiros de ilhas
    if "continente" in str(root).lower():
        non_ilhas = [s for s in shps if "ilha" not in s.name.lower() and "ilha" not in s.parent.name.lower()]
        if non_ilhas:
            shps = non_ilhas

    for s in shps:
        if str(year) in s.stem:
            return s
    return shps[0]


def normalize_layer(gdf, src_name):
    key = find_col(gdf, KEY_CANDIDATES)
    if key is None:
        raise ValueError(f"{src_name}: sem coluna DICOFRE/dtmnfr ({list(gdf.columns)})")
    name = find_col(gdf, NAME_CANDIDATES)
    conc = find_col(gdf, CONCELHO_CANDIDATES)
    ilha = find_col(gdf, ["Ilha", "ILHA", "ilha"])
    taa = find_col(gdf, ["TAA", "Taa", "taa"])

    out = gpd.GeoDataFrame({
        "dicofre": gdf[key].map(norm_dicofre),
        "nome": gdf[name].map(smart_title) if name else None,
        "concelho": gdf[conc].map(smart_title) if conc else None,
        # 'ilha' é usada só internamente (agrupamento p/ reposicionar as ilhas);
        # não é exportada para o GeoJSON.
        "ilha": gdf[ilha].astype(str) if ilha else None,
        "_taa": gdf[taa].astype(str) if taa else None,
    }, geometry=gdf.geometry, crs=gdf.crs)
    out = out[out["dicofre"].notna() & out.geometry.notna()]
    out["circulo"] = out["dicofre"].map(circulo_from_dicofre)
    out = out[out["circulo"].notna()]

    # Filtro TAA "Área Principal" APENAS nas ilhas (círculo >= 30), onde evita a
    # duplicação inset/real. No CONTINENTE mantemos TODAS as partes — as linhas
    # "Área Secundária" são os EXCLAVES das freguesias; descartá-las abria buracos
    # (ex.: 2009/2011). O dissolve por dicofre une parte principal + exclaves.
    if out["_taa"].notna().any():
        is_princ = out["_taa"].astype(str).str.upper().str.contains("PRINCIPAL", na=False)
        is_island = out["circulo"] >= "30"
        keep = (~is_island) | is_princ
        # só aplica se de facto há linhas Principal nas ilhas (evita esvaziar)
        if (is_island & is_princ).any():
            out = out[keep]

    return out.drop(columns=["_taa"])


# ---- Reposicionamento das ilhas para POSIÇÃO GEOGRÁFICA REAL ----
# Os ficheiros de ilhas de cada ano colocam as ilhas em posições inconsistentes
# (inset moderno, ou amontoadas junto ao continente nos anos antigos). Para exibir
# todas na posição real do Atlântico, MANTEMOS a geometria própria de cada ano
# (que encaixa/tiling perfeitamente, sem buracos) e apenas a DESLOCAMOS por ilha.
# A biblioteca abaixo (posição real) serve de referência de centróide por DICOFRE
# para calcular o deslocamento. Duas fontes cobrem 100% dos códigos de ilha:
#   - madeira e açores 2002 (205 freg, DICOFRE pré-2013)
#   - continente 2025      (210 freg, DICOFRE pós-2013)
_ISLAND_LIB = None       # {'old': {dicofre: geom(3763)}, 'new': {dicofre: geom(3763)}}
_ISLAND_CENTROIDS = None  # {'old': {dicofre: (x,y)}, 'new': {dicofre: (x,y)}}


def load_true_island_library():
    global _ISLAND_LIB, _ISLAND_CENTROIDS
    if _ISLAND_LIB is not None:
        return _ISLAND_LIB

    def geom_dict(shp):
        gdf, _ = read_shapefile(shp)
        norm = normalize_layer(gdf, shp.name)
        norm = norm[norm["circulo"] >= "30"].to_crs(3763)
        norm["geometry"] = norm.geometry.make_valid()
        norm = norm.dissolve(by="dicofre", as_index=False, aggfunc="first")
        return dict(zip(norm["dicofre"], norm.geometry))

    old_shp = find_year_shapefile(MAPAS_DIR / "madeira e açores freguesias", 2002)
    new_shp = find_year_shapefile(MAPAS_DIR / "continente freguesias", 2025)
    _ISLAND_LIB = {"old": geom_dict(old_shp), "new": geom_dict(new_shp)}
    _ISLAND_CENTROIDS = {
        k: {d: (g.representative_point().x, g.representative_point().y)
            for d, g in dd.items()}
        for k, dd in _ISLAND_LIB.items()
    }
    print(f"  ref. ilhas (posição real): old={len(_ISLAND_LIB['old'])}, new={len(_ISLAND_LIB['new'])}")
    return _ISLAND_LIB


def true_island_geom(dicofre, year):
    """Geometria da ilha em posição real (EPSG:3763). Escolhe por era com fallback:
    <=2011 preferem 2002 (pré-2013); >=2015 preferem 2025 (pós-2013)."""
    load_true_island_library()
    if year <= 2011:
        return _ISLAND_LIB["old"].get(dicofre) or _ISLAND_LIB["new"].get(dicofre)
    return _ISLAND_LIB["new"].get(dicofre) or _ISLAND_LIB["old"].get(dicofre)


def true_island_centroid(dicofre, year):
    """Centróide da ilha em posição real (EPSG:3763)."""
    load_true_island_library()
    if year <= 2011:
        return _ISLAND_CENTROIDS["old"].get(dicofre) or _ISLAND_CENTROIDS["new"].get(dicofre)
    return _ISLAND_CENTROIDS["new"].get(dicofre) or _ISLAND_CENTROIDS["old"].get(dicofre)


def reposition_islands(ilhas, year):
    """Desloca a geometria PRÓPRIA das ilhas do ano para a posição real, com uma
    TRANSLAÇÃO uniforme por ilha (preserva o encaixe -> sem buracos). Deslocamento de
    cada ilha = mediana de (centróide real por DICOFRE − centróide do ano) sobre as
    freguesias do grupo. Usado apenas para anos <=2011 (os modernos usam a geometria
    de referência diretamente). Agrupa pela coluna 'ilha'; se em falta, por componente
    conexa da união."""
    if len(ilhas) == 0:
        return ilhas
    ilhas = ilhas.copy()
    reps = ilhas.geometry.representative_point()
    ilhas["_cx"] = reps.x.values
    ilhas["_cy"] = reps.y.values
    ref = ilhas["dicofre"].map(lambda d: true_island_centroid(d, year))
    ilhas["_tx"] = [(p[0] if p else np.nan) for p in ref]
    ilhas["_ty"] = [(p[1] if p else np.nan) for p in ref]

    if ilhas["ilha"].notna().any():
        groups = ilhas["ilha"].fillna("?").tolist()
    else:
        merged = shapely.unary_union(ilhas.geometry.values)
        polys = list(getattr(merged, "geoms", [merged]))
        groups = [next((i for i, poly in enumerate(polys) if poly.intersects(p)), -1)
                  for p in reps]
    ilhas["_grp"] = groups

    out = []
    for _, sub in ilhas.groupby("_grp"):
        dx = np.nanmedian(sub["_tx"] - sub["_cx"])
        dy = np.nanmedian(sub["_ty"] - sub["_cy"])
        dx = dx if np.isfinite(dx) else 0.0
        dy = dy if np.isfinite(dy) else 0.0
        moved = sub.copy()
        moved["geometry"] = sub.geometry.apply(
            lambda g: shapely.transform(g, lambda a: a + np.array([dx, dy])))
        out.append(moved)
    res = gpd.GeoDataFrame(pd.concat(out, ignore_index=True), crs=ilhas.crs)
    return res.drop(columns=["_cx", "_cy", "_tx", "_ty", "_grp"])


_CONCELHOS_LIB = None


def load_concelhos_library():
    global _CONCELHOS_LIB
    if _CONCELHOS_LIB is not None:
        return _CONCELHOS_LIB
    _CONCELHOS_LIB = {}
    shp_2025 = find_year_shapefile(MAPAS_DIR / "continente freguesias", 2025)
    if shp_2025:
        try:
            gdf, _ = read_shapefile(shp_2025)
            key = find_col(gdf, KEY_CANDIDATES)
            conc = find_col(gdf, CONCELHO_CANDIDATES)
            if key and conc:
                for old, cname in zip(gdf[key], gdf[conc]):
                    code = norm_dicofre(old)
                    if code and len(code) >= 4:
                        dico = code[:4]
                        cname_clean = smart_title(str(cname).strip())
                        if cname_clean and not has_mojibake(cname_clean):
                            _CONCELHOS_LIB[dico] = cname_clean
        except Exception as e:
            print(f"  AVISO: não foi possível gerar biblioteca de concelhos ({e})")
    static_fallback = {
        "1413": "Mação", "0508": "Proença-a-Nova", "1417": "Sardoal",
        "0101": "Águeda", "0602": "Arganil", "1312": "Santo Tirso"
    }
    for k, v in static_fallback.items():
        if k not in _CONCELHOS_LIB:
            _CONCELHOS_LIB[k] = v
    return _CONCELHOS_LIB


def coverage_simplify_part(gdf, tol):
    """Simplifica um conjunto de polígonos COMO COBERTURA: as arestas partilhadas
    entre vizinhos ficam com vértices idênticos, evitando o desalinhamento (linhas
    brancas grossas) que a simplificação por-polígono produz. Fallback para
    .simplify() por-polígono se a coverage_simplify falhar."""
    if len(gdf) == 0:
        return gdf
    gdf = gdf.copy()
    geoms = gdf.geometry.values
    # A fonte CAOP não é perfeitamente topológica entre a parte Principal e os
    # exclaves (Área Secundária): pode ter micro-overlaps que tornam a cobertura
    # inválida e fazem o coverage_simplify abrir slivers (linhas pretas). Um snap de
    # 1 cm (set_precision) reconcilia as arestas partilhadas -> cobertura válida.
    if not shapely.coverage_is_valid(geoms, gap_width=0.0):
        snapped = shapely.make_valid(shapely.set_precision(geoms, 0.01))
        if shapely.coverage_is_valid(snapped, gap_width=0.0):
            geoms = snapped
    try:
        simp = shapely.coverage_simplify(geoms, tolerance=tol, simplify_boundary=True)
        gdf["geometry"] = gpd.GeoSeries(simp, index=gdf.index, crs=gdf.crs).make_valid()
    except Exception as e:
        print(f"  AVISO: coverage_simplify falhou ({e}); fallback .simplify")
        gdf["geometry"] = gpd.GeoSeries(geoms, index=gdf.index, crs=gdf.crs).simplify(
            tol, preserve_topology=True).make_valid()
    return gdf


def round_geom(geom, decimals=5):
    return shapely.transform(geom, lambda a: np.round(a, decimals))


def write_geojson(gdf, path, prop_cols):
    features = []
    for row in gdf.itertuples(index=False):
        props = {c: getattr(row, c) for c in prop_cols}
        props = {k: (v if v == v and v is not None else None) for k, v in props.items()}
        features.append({"type": "Feature", "properties": props,
                         "geometry": mapping(round_geom(row.geometry))})
    fc = {"type": "FeatureCollection", "features": features}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False, separators=(",", ":"))
    size_mb = path.stat().st_size / 1e6
    print(f"  -> {path.name}: {len(features)} features, {size_mb:.1f} MB")
    return size_mb


def bbox_ok(gdf):
    """Todas as geometrias dentro de um dos bbox de Portugal?"""
    bad = []
    for row in gdf.itertuples(index=False):
        x, y = row.geometry.representative_point().coords[0]
        inside = any(bx[0] <= x <= bx[2] and bx[1] <= y <= bx[3]
                     for bx in (BBOX_CONTINENTE, BBOX_MADEIRA, BBOX_ACORES))
        if not inside:
            bad.append((row.dicofre, round(x, 3), round(y, 3)))
    return bad


def build_year(year, simplify_freg=18, simplify_conc=35, simplify_dist=90):
    print(f"=== {year} ===")
    parts = []
    if year == 2026:
        gpkg_path = MAPAS_DIR / "freguesias2026.gpkg"
        if not gpkg_path.exists():
            print(f"  ERRO: {gpkg_path} não existe")
            return False
        gdf, _ = read_shapefile(gpkg_path)
        import shapely
        gdf.geometry = shapely.force_2d(gdf.geometry)
        print(f"  GPKG 2026: {gpkg_path.name} ({len(gdf)} rows, crs={gdf.crs.name if gdf.crs else 'NONE'})")
        norm = normalize_layer(gdf, gpkg_path.name)
        parts.append(norm.to_crs(3763))
    else:
        cont_path = find_year_shapefile(MAPAS_DIR / "continente freguesias", year)
        ilhas_path = find_year_shapefile(MAPAS_DIR / "madeira e açores freguesias", year)
        if cont_path:
            gdf, enc = read_shapefile(cont_path)
            print(f"  continente: {cont_path.name} ({len(gdf)} rows, crs={gdf.crs.name if gdf.crs else 'NONE'}"
                  + (f", enc={enc}" if enc else "") + ")")
            norm = normalize_layer(gdf, cont_path.name)
            parts.append(norm[norm["circulo"] <= "18"].to_crs(3763))
        if ilhas_path:
            gdf, enc = read_shapefile(ilhas_path)
            print(f"  ilhas: {ilhas_path.name} ({len(gdf)} rows, crs={gdf.crs.name if gdf.crs else 'NONE'}"
                  + (f", enc={enc}" if enc else "") + ")")
            norm = normalize_layer(gdf, ilhas_path.name)
            ilhas = norm[norm["circulo"] >= "30"].to_crs(3763)
            # Alguns anos (ex.: 2005) não trazem polígonos de ilha no shapefile próprio.
            # Fallback: usar a geometria de ilhas de 2002 (já em posição real).
            if len(ilhas) == 0:
                fb = find_year_shapefile(MAPAS_DIR / "madeira e açores freguesias", 2002)
                if fb is not None:
                    gfb, _ = read_shapefile(fb)
                    ilhas = normalize_layer(gfb, fb.name)
                    ilhas = ilhas[ilhas["circulo"] >= "30"].to_crs(3763)
                    print(f"  ilhas VAZIAS em {year}; geometria de 2002: {len(ilhas)} freguesias")

            ilhas["geometry"] = ilhas.geometry.make_valid()
            if year >= 2015:
                # Pós-2013: as freguesias de ilha têm a MESMA subdivisão do 2025-continente
                # (códigos idênticos). Usar diretamente a geometria de referência em posição
                # real (limpa, sem buracos, sem quirks de escala como o inset de 2024).
                ilhas["geometry"] = ilhas["dicofre"].map(lambda d: true_island_geom(d, year))
                miss = int(ilhas["geometry"].isna().sum())
                if miss:
                    print(f"  AVISO: {miss} ilhas sem geometria de referência (descartadas)")
                    ilhas = ilhas[ilhas["geometry"].notna()]
                ilhas = gpd.GeoDataFrame(ilhas, geometry="geometry", crs=3763)
            else:
                # Até 2011: subdivisão própria do ano (não coincide com a referência) —
                # manter a geometria própria (que encaixa) e deslocá-la por ilha.
                ilhas = reposition_islands(ilhas, year)
            parts.append(ilhas)
    if not parts:
        print(f"  ERRO: sem shapefiles para {year}")
        return False

    freg = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=3763)

    # dissolve por dicofre (funde partes TAA / multipolígonos duplicados)
    freg["geometry"] = freg.geometry.make_valid()
    n_rows = len(freg)
    freg = freg.dissolve(by="dicofre", as_index=False, aggfunc="first")
    print(f"  {n_rows} rows -> {len(freg)} freguesias únicas")

    # Corrige nomes de concelhos e freguesias usando fontes oficiais limpas para eliminar mojibakes do shapefile
    try:
        conc_lib = load_concelhos_library()
        freg["_dico_temp"] = freg["dicofre"].str[:4]
        for idx, row in freg.iterrows():
            dico = row["_dico_temp"]
            if dico in conc_lib:
                freg.at[idx, "concelho"] = conc_lib[dico]
        freg = freg.drop(columns=["_dico_temp"])
    except Exception as e:
        print(f"  AVISO: falha a corrigir nomes de concelhos ({e})")

    try:
        from build_results import load_certo
        _, res_names, _, _ = load_certo(year)
        if res_names:
            corrected = 0
            for idx, row in freg.iterrows():
                code = row["dicofre"]
                if code in res_names and res_names[code]:
                    freg.at[idx, "nome"] = res_names[code]
                    corrected += 1
            print(f"  Nomes de freguesias corrigidos com resultados de {year}: {corrected}")
    except Exception as e:
        print(f"  AVISO: falha a corrigir nomes de freguesias ({e})")

    # Simplificação por cobertura, por parte disjunta (continente vs ilhas): as
    # arestas partilhadas entre freguesias vizinhas ficam idênticas -> sem linhas
    # brancas grossas ao ampliar.
    # Nos anos com malha MUITO densa (ex.: 2009/2011 e anos antigos, >3500 freguesias
    # no continente), o coverage_simplify a tolerância 18 abre micro-slivers pretos.
    # Baixamos a tolerância nesses anos (8 m) para eliminar os slivers.
    n_cont = int((freg["circulo"] <= "18").sum())
    tol_freg = 10 if n_cont > 3500 else simplify_freg
    cont_part = coverage_simplify_part(freg[freg["circulo"] <= "18"], tol_freg)
    ilha_part = coverage_simplify_part(freg[freg["circulo"] >= "30"], tol_freg)
    freg = gpd.GeoDataFrame(pd.concat([cont_part, ilha_part], ignore_index=True), crs=3763)

    # camadas dissolvidas (linhas de sobreposição): dissolvidas a partir das
    # freguesias já simplificadas por cobertura e depois simplificadas por cobertura
    # com tolerância maior — as fronteiras entre concelhos/distritos vizinhos ficam
    # idênticas (sem linhas grossas) e os ficheiros ficam leves.
    freg["dico"] = freg["dicofre"].str[:4]
    conc = freg.dissolve(by="dico", as_index=False, aggfunc="first")[
        ["dico", "concelho", "circulo", "geometry"]]
    conc["geometry"] = conc.geometry.make_valid()
    conc = coverage_simplify_part(conc, simplify_conc)
    dist = freg.dissolve(by="circulo", as_index=False, aggfunc="first")[["circulo", "geometry"]]
    dist["geometry"] = dist.geometry.make_valid()
    dist = coverage_simplify_part(dist, simplify_dist)

    # para WGS84
    freg = freg.to_crs(4326)
    conc = conc.to_crs(4326)
    dist = dist.to_crs(4326)

    # QA
    dups = freg["dicofre"].duplicated().sum()
    bad = bbox_ok(freg)
    moji = sum(has_mojibake(str(v)) for v in freg["nome"].tolist())
    if dups or bad or moji:
        print(f"  QA: duplicados={dups}, fora de bbox={len(bad)}, mojibake={moji}")
        if bad:
            print(f"  fora de bbox (primeiros 5): {bad[:5]}")
            raise SystemExit(f"{year}: {len(bad)} features fora de Portugal — verificar CRS")
    circ_counts = freg.groupby("circulo").size().to_dict()
    print(f"  círculos: { {k: circ_counts[k] for k in sorted(circ_counts)} }")

    out = OUT_DIR / "mapas"
    size = write_geojson(freg, out / f"freguesias_{year}.geojson",
                         ["dicofre", "nome", "concelho", "circulo"])
    if size > 35:
        print(f"  AVISO: {size:.1f} MB > 35 MB — repetir com tolerância maior (coverage)")
        freg = freg.to_crs(3763)
        cont2 = coverage_simplify_part(freg[freg["circulo"] <= "18"], 8)
        ilha2 = coverage_simplify_part(freg[freg["circulo"] >= "30"], 8)
        freg = gpd.GeoDataFrame(pd.concat([cont2, ilha2], ignore_index=True), crs=3763).to_crs(4326)
        write_geojson(freg, out / f"freguesias_{year}.geojson",
                      ["dicofre", "nome", "concelho", "circulo"])
    write_geojson(conc, out / f"concelhos_{year}.geojson", ["dico", "concelho", "circulo"])
    write_geojson(dist, out / f"distritos_{year}.geojson", ["circulo"])
    return True


def build_static_distritos():
    """Converte mapas/distritos-shapefile/distritos.shp (GADM, 20 círculos, chave
    CCA_1 = '01'..'18'/'30'/'40', ilhas em posição real) para o ficheiro ESTÁTICO
    dados/mapas/distritos.geojson usado pelo visualizador em todos os anos
    (as fronteiras de distrito são estáveis)."""
    shp = MAPAS_DIR / "distritos-shapefile" / "distritos.shp"
    gdf, enc = read_shapefile(shp)
    print(f"distritos-shapefile: {len(gdf)} features" + (f" (enc={enc})" if enc else ""))

    out = gpd.GeoDataFrame({
        "circulo": gdf["CCA_1"].astype(str).str.strip().str.zfill(2),
        "nome": gdf["NAME_1"].map(smart_title),
    }, geometry=gdf.geometry, crs=gdf.crs).to_crs(3763)
    out["geometry"] = out.geometry.make_valid()

    expected = {k for k in CIRCULOS_KEYS if k not in ("E1", "E2")}
    got = set(out["circulo"])
    if got != expected:
        raise SystemExit(f"distritos estático: círculos inesperados; falta {expected-got}, extra {got-expected}")

    for tol in (120, 150, 200):
        parts = []
        for mask in (out["circulo"] <= "18", out["circulo"] == "30", out["circulo"] == "40"):
            parts.append(coverage_simplify_part(out[mask], tol))
        simp = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=3763).to_crs(4326)
        bad = bbox_ok(gpd.GeoDataFrame({"dicofre": simp["circulo"]},
                                       geometry=simp.geometry, crs=4326))
        if bad:
            raise SystemExit(f"distritos estático: {len(bad)} features fora de Portugal")
        size = write_geojson(simp, OUT_DIR / "mapas" / "distritos.geojson", ["circulo", "nome"])
        if size <= 0.8:
            break
        print(f"  {size:.2f} MB > 0.8 MB — a repetir com tolerância maior")
    return True


# círculos esperados (sem E1/E2, que não têm geometria)
CIRCULOS_KEYS = [f"{i:02d}" for i in range(1, 19)] + ["30", "40", "E1", "E2"]


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--distritos-static" in args:
        build_static_distritos()
        sys.exit(0)
    years = YEARS if "--all" in args else [int(a) for a in args if a.isdigit()]
    if not years:
        print(__doc__)
        sys.exit(1)
    for y in years:
        build_year(y)
