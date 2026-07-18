# -*- coding: utf-8 -*-
"""
Alinha as ilhas (Madeira, Porto Santo, Desertas, Selvagens e as 9 dos Açores)
das cartografias antigas com a cartografia de referência (2025).

As fontes por ano têm datums/CRS distintos: 2009-2011 têm a Madeira inflada
(~31% mais larga), 1975-1999 usam o datum antigo (~1,5 km de desvio). O ajuste
é afim por eixo, por ilha: bbox do ano -> bbox de referência.

Uso:
  python etl/fix_islands_alignment.py           # aplica in-place em dados/mapas
  python etl/fix_islands_alignment.py --dry-run # só relata
"""

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAPAS = ROOT / "dados" / "mapas"
REF_ANO = "2025"
LON_ILHAS = -11.0       # tudo a oeste disto é ilha (continente: lon > -10)
TOL_CLUSTER = 0.08      # graus: distância máx. entre bboxes para unir num cluster
IDENT_S = 0.002         # |s-1| abaixo disto e |t| abaixo de IDENT_T => identidade
IDENT_T = 0.0005


def feature_bbox(geom):
    bb = [999.0, 999.0, -999.0, -999.0]

    def walk(c):
        if isinstance(c[0], (int, float)):
            bb[0] = min(bb[0], c[0]); bb[1] = min(bb[1], c[1])
            bb[2] = max(bb[2], c[0]); bb[3] = max(bb[3], c[1])
        else:
            for x in c:
                walk(x)

    walk(geom["coordinates"])
    return bb


def bb_union(a, b):
    return [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]


def bb_gap(a, b):
    """Distância entre bboxes (0 se sobrepõem)."""
    dx = max(a[0] - b[2], b[0] - a[2], 0.0)
    dy = max(a[1] - b[3], b[1] - a[3], 0.0)
    return math.hypot(dx, dy)


def iter_polygons(geom):
    """Itera polígonos individuais: devolve lista de anéis (cada polígono =
    lista de anéis). Nota: concelhos como o Funchal incluem as Selvagens no
    mesmo MultiPolygon — o alinhamento tem de ser por polígono, não por feature."""
    t = geom.get("type")
    if t == "Polygon":
        return [geom["coordinates"]]
    if t == "MultiPolygon":
        return geom["coordinates"]
    return []


def poly_bbox(poly):
    bb = [999.0, 999.0, -999.0, -999.0]
    for ring in poly:
        for pt in ring:
            x, y = pt[0], pt[1]
            bb[0] = min(bb[0], x); bb[1] = min(bb[1], y)
            bb[2] = max(bb[2], x); bb[3] = max(bb[3], y)
    return bb


def cluster_island_features(features):
    """Agrupa POLÍGONOS insulares por proximidade de bbox. Devolve lista de
    [bbox, [(feature_idx, poly_idx)...]]."""
    items = []
    for i, f in enumerate(features):
        geom = f.get("geometry")
        if not geom or not geom.get("coordinates"):
            continue
        for j, poly in enumerate(iter_polygons(geom)):
            bb = poly_bbox(poly)
            cx = (bb[0] + bb[2]) / 2
            if cx >= LON_ILHAS:
                continue
            items.append((bb, (i, j)))

    clusters = []  # [bbox, [idx...]]
    for bb, i in items:
        merged = None
        for cl in clusters:
            if bb_gap(cl[0], bb) <= TOL_CLUSTER:
                cl[0] = bb_union(cl[0], bb)
                cl[1].append(i)
                merged = cl
                break
        if merged is None:
            clusters.append([bb, [i]])

    # passadas extra para fundir clusters que se tocaram após uniões
    changed = True
    while changed:
        changed = False
        out = []
        for cl in clusters:
            hit = None
            for o in out:
                if bb_gap(o[0], cl[0]) <= TOL_CLUSTER:
                    hit = o
                    break
            if hit:
                hit[0] = bb_union(hit[0], cl[0])
                hit[1].extend(cl[1])
                changed = True
            else:
                out.append(cl)
        clusters = out
    return clusters


def centroid(bb):
    return ((bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2)


def load(fn):
    with open(fn, encoding="utf-8") as f:
        return json.load(f)


def save(fn, obj):
    import time
    for tent in range(4):
        try:
            with open(fn, "w", encoding="utf-8") as f:
                json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
            return
        except OSError:
            if tent == 3:
                raise
            time.sleep(2)  # lock transitório (antivírus/indexador)


def transform_for(bb_src, bb_ref):
    """Afim por eixo que leva bb_src a bb_ref. Devolve (sx, sy, tx, ty)."""
    w_s, h_s = bb_src[2] - bb_src[0], bb_src[3] - bb_src[1]
    w_r, h_r = bb_ref[2] - bb_ref[0], bb_ref[3] - bb_ref[1]
    sx = w_r / w_s if w_s else 1.0
    sy = h_r / h_s if h_s else 1.0
    tx = bb_ref[0] - bb_src[0] * sx
    ty = bb_ref[1] - bb_src[1] * sy
    return sx, sy, tx, ty


def is_identity(sx, sy, tx, ty, bb):
    # avaliar o deslocamento efetivo nos cantos do bbox
    for x, y in ((bb[0], bb[1]), (bb[2], bb[3])):
        if abs(x * sx + tx - x) > IDENT_T or abs(y * sy + ty - y) > IDENT_T:
            if abs(sx - 1) > IDENT_S or abs(sy - 1) > IDENT_S \
               or abs(tx) > IDENT_T or abs(ty) > IDENT_T:
                return False
    return abs(sx - 1) <= IDENT_S and abs(sy - 1) <= IDENT_S


def transform_poly(poly, sx, sy, tx, ty):
    return [[[pt[0] * sx + tx, pt[1] * sy + ty] for pt in ring] for ring in poly]


# ---------------------------------------------------------------- ICP (fase 2)

def coastline_points(poly_items):
    """poly_items: lista de (feature_idx, poly). Vértices da linha de costa =
    pontos que aparecem numa só feature (fronteiras internas são partilhadas
    por >=2 features)."""
    from collections import defaultdict
    seen = defaultdict(set)  # ponto arredondado -> set(feature_idx)
    pts = {}
    for fi, poly in poly_items:
        for ring in poly:
            for pt in ring:
                key = (round(pt[0], 5), round(pt[1], 5))
                seen[key].add(fi)
                pts[key] = (pt[0], pt[1])
    coast = [pts[k] for k, owners in seen.items() if len(owners) == 1]
    if len(coast) < 100:  # topologia não-snapped ou ilha de 1 concelho: usa tudo
        coast = list(pts.values())
    return coast


def cluster_polys(features, cluster_idx_list):
    """[(fi, pj)] -> [(fi, poly)]"""
    out = []
    for fi, pj in cluster_idx_list:
        polys = iter_polygons(features[fi]["geometry"])
        out.append((fi, polys[pj]))
    return out


class Grid:
    """Índice espacial simples para vizinho mais próximo."""

    def __init__(self, points, cell=0.005):
        from collections import defaultdict
        self.cell = cell
        self.map = defaultdict(list)
        for p in points:
            self.map[(int(p[0] / cell), int(p[1] / cell))].append(p)

    def nearest(self, x, y):
        cx, cy = int(x / self.cell), int(y / self.cell)
        best, best_d2 = None, 1e18
        for r in (0, 1, 2):
            for gx in range(cx - r, cx + r + 1):
                for gy in range(cy - r, cy + r + 1):
                    if r > 0 and abs(gx - cx) != r and abs(gy - cy) != r:
                        continue
                    for p in self.map.get((gx, gy), ()):
                        d2 = (p[0] - x) ** 2 + (p[1] - y) ** 2
                        if d2 < best_d2:
                            best, best_d2 = p, d2
            if best is not None and r >= 1:
                break
        return best, math.sqrt(best_d2) if best else 1e9


def solve_affine(pairs):
    """Mínimos quadrados para afim 6-param: (x,y)->(a x + b y + c, d x + e y + f).
    Resolve dois sistemas 3x3 independentes."""
    n = len(pairs)
    sx = sy = sxx = sxy = syy = 0.0
    tx1 = ty1 = txx1 = txy1 = 0.0
    tx2 = ty2 = txx2 = txy2 = 0.0
    for (x, y), (u, v) in pairs:
        sx += x; sy += y; sxx += x * x; sxy += x * y; syy += y * y
        tx1 += u; txx1 += x * u; txy1 += y * u
        ty2 += v; txx2 += x * v; txy2 += y * v
    # matriz normal comum: [[sxx,sxy,sx],[sxy,syy,sy],[sx,sy,n]]
    M = [[sxx, sxy, sx], [sxy, syy, sy], [sx, sy, float(n)]]
    def solve3(M, b):
        import copy
        A = [row[:] + [bv] for row, bv in zip(copy.deepcopy(M), b)]
        for i in range(3):
            piv = max(range(i, 3), key=lambda r: abs(A[r][i]))
            A[i], A[piv] = A[piv], A[i]
            for r in range(i + 1, 3):
                f = A[r][i] / A[i][i]
                for c in range(i, 4):
                    A[r][c] -= f * A[i][c]
        out = [0.0] * 3
        for i in (2, 1, 0):
            out[i] = (A[i][3] - sum(A[i][c] * out[c] for c in range(i + 1, 3))) / A[i][i]
        return out
    a, b, c = solve3(M, [txx1, txy1, tx1])
    d, e, f = solve3(M, [txx2, txy2, ty2])
    return (a, b, c, d, e, f)


def apply_affine6_pt(t, x, y):
    a, b, c, d, e, f = t
    return a * x + b * y + c, d * x + e * y + f


def icp_fit(src_pts, ref_pts, iters=30):
    """Ajusta afim 6-param de src->ref por ICP. Devolve (transform, resíduo_médio)."""
    import random
    rnd = random.Random(42)
    if len(src_pts) > 1500:
        src_pts = rnd.sample(src_pts, 1500)
    grid = Grid(ref_pts)
    t = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
    prev_res = None
    for _ in range(iters):
        pairs = []
        dists = []
        for p in src_pts:
            x, y = apply_affine6_pt(t, p[0], p[1])
            q, d = grid.nearest(x, y)
            if q is not None:
                pairs.append(((p[0], p[1]), q, d))
                dists.append(d)
        if len(pairs) < 20:
            return t, 1e9
        dists.sort()
        med = dists[len(dists) // 2]
        lim = max(med * 3, 1e-4)
        use = [((x, y), q) for (x, y), q, d in pairs if d <= lim]
        if len(use) < 20:
            return t, med
        t = solve_affine(use)
        res = sum(d for _, _, d in pairs) / len(pairs)
        if prev_res is not None and abs(prev_res - res) < 1e-9:
            break
        prev_res = res
    return t, prev_res if prev_res is not None else 1e9


def affine6_is_identity(t):
    a, b, c, d, e, f = t
    return (abs(a - 1) < 5e-4 and abs(e - 1) < 5e-4 and abs(b) < 5e-4
            and abs(d) < 5e-4 and abs(c) < 2e-2 and abs(f) < 2e-2
            and residual_shift(t) < 2e-4)


def residual_shift(t):
    """Deslocamento máximo que a afim induz na região das ilhas."""
    m = 0.0
    for x, y in ((-31.3, 39.8), (-16.0, 30.0), (-17.4, 33.2), (-25.0, 36.9)):
        u, v = apply_affine6_pt(t, x, y)
        m = max(m, abs(u - x), abs(v - y))
    return m


def transform_poly6(poly, t):
    return [[list(apply_affine6_pt(t, pt[0], pt[1])) for pt in ring] for ring in poly]


def build_reference():
    """Clusters de referência a partir de concelhos+freguesias 2025."""
    ref_clusters = []
    for camada in ("concelhos", "freguesias"):
        fn = MAPAS / f"{camada}_{REF_ANO}.geojson"
        g = load(fn)
        for bb, _idx in cluster_island_features(g["features"]):
            hit = None
            for cl in ref_clusters:
                if bb_gap(cl, bb) <= TOL_CLUSTER:
                    hit = cl
                    break
            if hit:
                hit[:] = bb_union(hit, bb)
            else:
                ref_clusters.append(list(bb))
    return ref_clusters


def match_ref(bb, ref_clusters):
    cx, cy = centroid(bb)
    best, best_d = None, 1e9
    for rb in ref_clusters:
        rx, ry = centroid(rb)
        d = math.hypot(cx - rx, cy - ry)
        if d < best_d:
            best, best_d = rb, d
    # segurança: um desvio de datum é <0.2°; nunca casar ilhas diferentes
    return best if best is not None and best_d < 0.6 else None


def icp_pass(dry=False):
    """Fase 2: ajuste fino por ICP da linha de costa contra a referência."""
    print("\n=== Fase 2: ICP de linha de costa ===")
    ref = load(MAPAS / f"concelhos_{REF_ANO}.geojson")
    ref_clusters = cluster_island_features(ref["features"])
    ref_data = []  # (bbox, coastline)
    for bb, idx in ref_clusters:
        ref_data.append((bb, coastline_points(cluster_polys(ref["features"], idx))))

    anos = sorted({fn.stem.split("_")[1] for fn in MAPAS.glob("concelhos_*.geojson")})
    for ano in anos:
        if ano == REF_ANO:
            continue
        g_base = load(MAPAS / f"concelhos_{ano}.geojson")
        clusters = cluster_island_features(g_base["features"])
        transforms = []  # (bbox, t6)
        for bb, idx in clusters:
            cx, cy = centroid(bb)
            best, best_d = None, 1e9
            for rb, coast in ref_data:
                rx, ry = centroid(rb)
                d = math.hypot(cx - rx, cy - ry)
                if d < best_d:
                    best, best_d = coast, d
            if best is None or best_d > 0.3:
                continue
            src = coastline_points(cluster_polys(g_base["features"], idx))
            if len(src) < 120:
                continue  # ilhéu minúsculo: fase 1 chega
            t, res = icp_fit(src, best)
            if affine6_is_identity(t):
                continue
            # salvaguarda: o ICP só refina (rotação/escala pequenas);
            # transformações drásticas em ilhéus são ruído — ignorar
            if (abs(t[0] - 1) > 0.15 or abs(t[4] - 1) > 0.15
                    or abs(t[1]) > 0.15 or abs(t[3]) > 0.15):
                print(f"  {ano}: ilha c=({cx:.2f},{cy:.2f}) transformação drástica ignorada")
                continue
            transforms.append((bb, t))
            print(f"  {ano}: ilha c=({cx:.2f},{cy:.2f}) resíduo={res:.5f}° "
                  f"a={t[0]:.4f} b={t[1]:+.4f} d={t[3]:+.4f} e={t[4]:.4f}")
        if not transforms:
            print(f"{ano}: ICP identidade")
            continue
        if dry:
            print(f"{ano}: {len(transforms)} ilhas a refinar (dry-run)")
            continue
        for camada in ("concelhos", "freguesias", "distritos"):
            fn = MAPAS / f"{camada}_{ano}.geojson"
            if not fn.exists():
                continue
            g = load(fn)
            n_mod = 0
            for f in g["features"]:
                geom = f.get("geometry")
                if not geom or not geom.get("coordinates"):
                    continue
                polys = iter_polygons(geom)
                new_polys = []
                changed = False
                for poly in polys:
                    bb = poly_bbox(poly)
                    if (bb[0] + bb[2]) / 2 >= LON_ILHAS:
                        new_polys.append(poly)
                        continue
                    best, best_d = None, 1e9
                    for tbb, t in transforms:
                        d = bb_gap(tbb, bb)
                        if d < best_d:
                            best, best_d = t, d
                    if best is None or best_d > TOL_CLUSTER:
                        new_polys.append(poly)
                        continue
                    new_polys.append(transform_poly6(poly, best))
                    changed = True
                if changed:
                    n_mod += 1
                    if geom["type"] == "Polygon":
                        geom["coordinates"] = new_polys[0]
                    else:
                        geom["coordinates"] = new_polys
            save(fn, g)
            print(f"    {camada}_{ano}: {n_mod} features refinadas")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-bbox", action="store_true", help="só a fase ICP")
    args = ap.parse_args()

    ref_clusters = build_reference()
    print(f"Referência {REF_ANO}: {len(ref_clusters)} ilhas/grupos")

    anos = sorted({fn.stem.split("_")[1] for fn in MAPAS.glob("concelhos_*.geojson")})
    for ano in anos:
        if args.skip_bbox:
            break
        if ano == REF_ANO:
            continue
        base = MAPAS / f"concelhos_{ano}.geojson"
        g_base = load(base)
        clusters = cluster_island_features(g_base["features"])
        # matching injetivo (guloso por distância): cada ilha de referência
        # é usada no máximo uma vez — evita dois ilhéus a disputar o mesmo par
        pares = []
        for ci, (bb, _idx) in enumerate(clusters):
            cx, cy = centroid(bb)
            for ri, rb in enumerate(ref_clusters):
                rx, ry = centroid(rb)
                d = math.hypot(cx - rx, cy - ry)
                if d < 0.6:
                    pares.append((d, ci, ri))
        pares.sort()
        atrib = {}
        usados = set()
        for d, ci, ri in pares:
            if ci in atrib or ri in usados:
                continue
            atrib[ci] = ri
            usados.add(ri)
        transforms = []  # (bbox_origem_expandida, sx, sy, tx, ty)
        for ci, (bb, _idx) in enumerate(clusters):
            ri = atrib.get(ci)
            if ri is None:
                print(f"  {ano}: cluster {bb} sem par na referência — intacto")
                continue
            rb = ref_clusters[ri]
            sx, sy, tx, ty = transform_for(bb, rb)
            if is_identity(sx, sy, tx, ty, bb):
                continue
            transforms.append((bb, sx, sy, tx, ty))
            print(f"  {ano}: ilha c=({centroid(bb)[0]:.2f},{centroid(bb)[1]:.2f}) "
                  f"sx={sx:.4f} sy={sy:.4f} dx={tx + bb[0]*(sx-1):+.4f} dy={ty + bb[1]*(sy-1):+.4f}")

        if not transforms:
            print(f"{ano}: alinhado (identidade)")
            continue
        if args.dry_run:
            print(f"{ano}: {len(transforms)} ilhas a corrigir (dry-run)")
            continue

        # aplica as mesmas transformações (por polígono) a todas as camadas do ano
        for camada in ("concelhos", "freguesias", "distritos"):
            fn = MAPAS / f"{camada}_{ano}.geojson"
            if not fn.exists():
                continue
            g = load(fn)
            n_mod = 0
            for f in g["features"]:
                geom = f.get("geometry")
                if not geom or not geom.get("coordinates"):
                    continue
                polys = iter_polygons(geom)
                new_polys = []
                changed = False
                for poly in polys:
                    bb = poly_bbox(poly)
                    if (bb[0] + bb[2]) / 2 >= LON_ILHAS:
                        new_polys.append(poly)
                        continue
                    best, best_d = None, 1e9
                    for tbb, sx, sy, tx, ty in transforms:
                        d = bb_gap(tbb, bb)
                        if d < best_d:
                            best, best_d = (sx, sy, tx, ty), d
                    if best is None or best_d > TOL_CLUSTER:
                        new_polys.append(poly)
                        continue
                    new_polys.append(transform_poly(poly, *best))
                    changed = True
                if changed:
                    n_mod += 1
                    if geom["type"] == "Polygon":
                        geom["coordinates"] = new_polys[0]
                    else:
                        geom["coordinates"] = new_polys
            save(fn, g)
            print(f"    {camada}_{ano}: {n_mod} features corrigidas")

    icp_pass(dry=args.dry_run)
    print("OK")


if __name__ == "__main__":
    sys.exit(main())
