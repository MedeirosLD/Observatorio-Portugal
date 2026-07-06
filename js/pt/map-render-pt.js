// ============================================================================
// map-render-pt.js — choropleth de freguesias (MapLibre via MLCompat.GeoLayer)
// ============================================================================

// ---------- ESTILO ----------

const MAP_LEVELS = {
  distrito: {
    idProp: 'circulo',
    getVotes: (id) => {
      if (STATE.currentCirculo === 'E1' || STATE.currentCirculo === 'E2') {
        return STATE.data?.COUNTRIES?.[STATE.currentCirculo]?.[id]?.votes;
      }
      return STATE.data?.AGG?.distrito?.[id]?.votes;
    },
    getName: (id) => CIRCULOS.get(id) || id,
    getOfficial: (id) => {
      if (STATE.currentCirculo === 'E1' || STATE.currentCirculo === 'E2') {
        return STATE.data?.COUNTRIES?.[STATE.currentCirculo]?.[id];
      }
      return STATE.data?.AGG?.distrito?.[id];
    }
  },
  concelho: {
    idProp: 'dico',
    getVotes: (id) => STATE.data?.AGG?.concelho?.[id]?.votes,
    getName: (id) => getConcelhoNome(id),
    getOfficial: (id) => STATE.data?.AGG?.concelho?.[id]
  },
  freguesia: {
    idProp: 'dicofre',
    getVotes: (id) => STATE.data?.RESULTS?.[id],
    getName: (id) => STATE.data?.NAMES?.[id] || id,
    getOfficial: (id) => {
      const offVal = STATE.data?.OFFICIAL_F?.[id];
      return offVal ? {
        inscritos: offVal[0],
        votantes: offVal[1],
        brancos: offVal[2],
        nulos: offVal[3]
      } : null;
    }
  }
};

const EXTRUSION_SCALE = {
  freguesia: 260,
  concelho: 110,
  distrito: 45
};

function registerStripePattern(color1, color2) {
  if (typeof window === 'undefined' || !window.map) return null;
  const m = window.map;
  
  const c1 = color1.replace('#', '').toLowerCase();
  const c2 = color2.replace('#', '').toLowerCase();
  const patternId = `tie-${c1}-${c2}`;
  
  if (m.hasImage(patternId)) return patternId;
  
  const canvas = document.createElement('canvas');
  canvas.width = 32;
  canvas.height = 32;
  const ctx = canvas.getContext('2d');
  
  ctx.fillStyle = color1;
  ctx.fillRect(0, 0, 32, 32);
  
  ctx.fillStyle = color2;
  ctx.beginPath();
  ctx.moveTo(0, 32);
  ctx.lineTo(32, 0);
  ctx.lineTo(32, 16);
  ctx.lineTo(16, 32);
  ctx.closePath();
  ctx.fill();
  
  ctx.beginPath();
  ctx.moveTo(0, 16);
  ctx.lineTo(16, 0);
  ctx.lineTo(0, 0);
  ctx.closePath();
  ctx.fill();
  
  try {
    const imgData = ctx.getImageData(0, 0, 32, 32);
    m.addImage(patternId, imgData);
  } catch (err) {
    console.error("Erro ao registrar padrão de empate:", err);
  }
  
  return patternId;
}

function getFeatureFill(level, feature) {
  const cfg = MAP_LEVELS[level];
  const idProp = (level === 'distrito' && (STATE.currentCirculo === 'E1' || STATE.currentCirculo === 'E2')) ? 'nome' : cfg.idProp;
  const id = feature.properties?.[idProp];
  const votes = cfg.getVotes(id);
  
  if (STATE.currentElectionType === 'au' && !votes && level !== 'freguesia') return { fillColor: DEFAULT_SWATCH, pattern: null };
  if (STATE.currentElectionType !== 'au' && (!votes || !Object.keys(votes).length)) return { fillColor: DEFAULT_SWATCH, pattern: null };

  if (currentVizMode === 'desempenho' && STATE.vizParty) {
    const pct = getPartyPct(votes, STATE.vizParty);
    if (pct === null) return { fillColor: DEFAULT_SWATCH, pattern: null };
    const base = getResolvedPartyColor(STATE.vizParty);
    const stats = STATE.performanceStats;
    let color = DEFAULT_SWATCH;
    if (stats && stats.party === STATE.vizParty) {
      color = getRelativeGradientColor(base, pct, stats.minPct, stats.maxPct);
    } else {
      color = getUniversalGradientColor(base, pct);
    }
    return { fillColor: color, pattern: null };
  }

  if (STATE.currentElectionType === 'au') {
    const subType = STATE.auSubtype || 'cm';
    let presidents = null;
    let maiorias = null;
    let mandatos_p = null;
    
    if (level === 'distrito') {
      const entry = STATE.data?.AGG?.distrito?.[id];
      presidents = entry?.presidents || {};
      maiorias = entry?.maiorias || {};
      mandatos_p = entry?.mandatos_p || {};
    } else if (level === 'concelho') {
      const entry = STATE.data?.AGG?.concelho?.[id];
      presidents = entry?.presidents || {};
      maiorias = entry?.maiorias || {};
      mandatos_p = entry?.mandatos_p || {};
    }
    
    const grouped = groupAutarquicasVotes(votes || {}, presidents, maiorias, mandatos_p, level, subType);
    if (!grouped || !grouped.length) return { fillColor: DEFAULT_SWATCH, pattern: null };
    
    const isCM_AF_Agg = (subType === 'cm' && (level === 'national' || level === 'distrito')) ||
                        (subType === 'af' && (level === 'national' || level === 'distrito' || level === 'concelho'));
    
    const metricKey = isCM_AF_Agg ? 'presidents' : (subType === 'am' && (level === 'national' || level === 'distrito') ? 'mandatos' : 'votes');
    
    const winVal = grouped[0]?.[metricKey] || 0;
    const secondVal = grouped[1]?.[metricKey] || 0;
    
    const color1 = getResolvedPartyColor(grouped[0]?.mainParty || grouped[0]?.party);
    
    if (winVal === secondVal && winVal > 0) {
      const color2 = getResolvedPartyColor(grouped[1]?.mainParty || grouped[1]?.party);
      const patternId = registerStripePattern(color1, color2);
      return { fillColor: color1, pattern: patternId };
    }
    
    const totalMetric = grouped.reduce((sum, item) => sum + (item[metricKey] || 0), 0);
    const pct = totalMetric > 0 ? (winVal / totalMetric) * 100 : 0;
    const marginPct = totalMetric > 0 ? ((winVal - secondVal) / totalMetric) * 100 : 0;
    
    const color = getGradientColorForMode(color1, marginPct, pct);
    return { fillColor: color, pattern: null };
  }

  const w = getWinner(votes);
  if (!w) return { fillColor: DEFAULT_SWATCH, pattern: null };
  const base = getResolvedPartyColor(w.party);
  const color = getGradientColorForMode(base, w.marginPct, w.pct);
  return { fillColor: color, pattern: null };
}

function getFeatureStyle(level, feature) {
  const cfg = MAP_LEVELS[level];
  const idProp = (level === 'distrito' && (STATE.currentCirculo === 'E1' || STATE.currentCirculo === 'E2')) ? 'nome' : cfg.idProp;
  const id = feature.properties?.[idProp];
  
  let isSelected = false;
  if (level === 'freguesia') {
    isSelected = selectedLocationIDs.has(id);
  } else if (level === 'distrito' && (STATE.currentCirculo === 'E1' || STATE.currentCirculo === 'E2')) {
    isSelected = (id === STATE.selectedCountry);
  } else if (level === STATE.scope.level && id === STATE.scope.key) {
    isSelected = true;
  }

  let inFocus = true;
  if (STATE.currentCirculo) {
    if (STATE.currentCirculo === 'E1' || STATE.currentCirculo === 'E2') {
      if (level === 'distrito') {
        const featCirc = feature.properties?.circulo;
        inFocus = (featCirc === STATE.currentCirculo);
      }
    } else if (!CIRCULOS_SEM_GEOMETRIA.has(STATE.currentCirculo)) {
      if (level === 'distrito') {
        inFocus = (id === STATE.currentCirculo);
      } else if (level === 'concelho') {
        const circ = feature.properties?.circulo || circuloFromDicofre(id + '00');
        inFocus = (circ === STATE.currentCirculo);
      } else if (level === 'freguesia') {
        if (STATE.scope.level === 'concelho' || STATE.scope.level === 'freguesia') {
          const activeDico = STATE.scope.level === 'concelho' ? STATE.scope.key : STATE.scope.key.slice(0, 4);
          const featDico = id.slice(0, 4);
          inFocus = (featDico === activeDico);
        } else {
          const circ = feature.properties?.circulo || circuloFromDicofre(id);
          inFocus = (circ === STATE.currentCirculo);
        }
      }
    }
  }

  const fillInfo = getFeatureFill(level, feature);
  const style = {
    fillColor: typeof fillInfo === 'string' ? fillInfo : fillInfo.fillColor,
    fillOpacity: inFocus ? 0.82 : 0.18,
    color: isSelected ? 'var(--accent)' : 'rgba(255,255,255,0.22)',
    weight: isSelected ? 2.5 : 0.4,
    opacity: isSelected ? 1 : (inFocus ? 0.85 : 0.25)
  };

  if (fillInfo && fillInfo.pattern) {
    style.pattern = fillInfo.pattern;
  }

  if (STATE.extrusionEnabled && level === STATE.mapLevel) {
    const votes = cfg.getVotes(id);
    let total = 0;
    if (votes) {
      for (const v of Object.values(votes)) total += v;
    }
    const scale = EXTRUSION_SCALE[level] || 100;
    style.height = Math.sqrt(total) * scale;
  } else {
    style.height = 0;
  }
  return style;
}

// ---------- TOOLTIP ----------

function buildFeatureTooltip(level, feature) {
  const cfg = MAP_LEVELS[level];
  const p = feature.properties || {};
  const idProp = (level === 'distrito' && (STATE.currentCirculo === 'E1' || STATE.currentCirculo === 'E2')) ? 'nome' : cfg.idProp;
  const id = p[idProp];
  const votes = cfg.getVotes(id);
  const nome = (level === 'distrito' && (STATE.currentCirculo === 'E1' || STATE.currentCirculo === 'E2')) ? id : cfg.getName(id);

  let rowsHtml = '';
  let totalLabel = '';
  
  if (STATE.currentElectionType === 'au') {
    const subType = STATE.auSubtype || 'cm';
    let presidents = null;
    let maiorias = null;
    let mandatos_p = null;
    
    if (level === 'distrito') {
      const entry = STATE.data?.AGG?.distrito?.[id];
      presidents = entry?.presidents || {};
      maiorias = entry?.maiorias || {};
      mandatos_p = entry?.mandatos_p || {};
    } else if (level === 'concelho') {
      const entry = STATE.data?.AGG?.concelho?.[id];
      presidents = entry?.presidents || {};
      maiorias = entry?.maiorias || {};
      mandatos_p = entry?.mandatos_p || {};
    }
    
    const yearNum = parseInt(STATE.currentYear || '0', 10);
    const isPlenario = (level === 'freguesia' && subType === 'af' && yearNum <= 2009 && (!votes || !Object.keys(votes).length));

    if (isPlenario) {
      const limit = yearNum <= 1999 ? '300' : '150';
      rowsHtml = `
        <div style="color:var(--accent); font-size:0.8rem; font-weight:700; margin-top:6px; line-height:1.45;">
          Plenário de Cidadãos
        </div>
        <div style="color:var(--text-sec); font-size:0.72rem; margin-top:2px; line-height:1.35; font-weight:500;">
          Dispensa de eleição direta por ter menos de ${limit} eleitores inscritos.
        </div>
      `;
      totalLabel = '';
    } else {
      const grouped = groupAutarquicasVotes(votes || {}, presidents, maiorias, mandatos_p, level, subType);
      if (grouped && grouped.length) {
        const isCM_AF_Agg = (subType === 'cm' && (level === 'national' || level === 'distrito')) ||
                            (subType === 'af' && (level === 'national' || level === 'distrito' || level === 'concelho'));
        const metricKey = isCM_AF_Agg ? 'presidents' : (subType === 'am' && (level === 'national' || level === 'distrito') ? 'mandatos' : 'votes');
        
        const total = grouped.reduce((sum, item) => sum + (item[metricKey] || 0), 0);
        
        rowsHtml = grouped.slice(0, 3).map(item => {
          const v = item[metricKey] || 0;
          const color = getResolvedPartyColor(item.isGroup ? item.mainParty : item.party);
          const pct = total > 0 ? (v / total) : 0;
          
          let label = '';
          if (metricKey === 'presidents') {
            const typeLabel = subType === 'cm' ? (v === 1 ? 'Câmara' : 'Câmaras') : (v === 1 ? 'Junta' : 'Juntas');
            label = `${v} ${typeLabel}`;
          } else if (metricKey === 'mandatos') {
            label = `${v} ${v === 1 ? 'Mandato' : 'Mandatos'}`;
          } else {
            label = `${fmtPct(pct)} <span style="color:var(--muted); font-size:0.7rem; font-weight:400; font-variant-numeric:tabular-nums; margin-left:4px;">(${fmtInt(v)})</span>`;
          }
          
          const pctHtml = (metricKey === 'presidents' || metricKey === 'mandatos') ? ` <span style="color:var(--muted); font-variant-numeric: tabular-nums;">(${fmtPct(pct)})</span>` : '';
          
          return `<div style="display:flex; align-items:center; gap:6px; margin-top:3px;">
            <span style="width:9px; height:9px; border-radius:2px; background:${color}; flex-shrink:0;"></span>
            <span style="flex:1; min-width: 80px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${escapeHtml(item.party)}">${escapeHtml(item.party)}</span>
            <strong style="font-variant-numeric: tabular-nums;">${label}</strong>
            ${pctHtml}
          </div>`;
        }).join('');
        
        if (metricKey === 'presidents') {
          const typeLabel = subType === 'cm' ? 'Municípios' : 'Freguesias';
          totalLabel = `<div style="margin-top:6px; color:var(--muted); font-size:0.72rem; border-top:1px solid rgba(255,255,255,0.06); padding-top:4px;">Total: ${total} ${typeLabel}</div>`;
        } else if (metricKey === 'mandatos') {
          totalLabel = `<div style="margin-top:6px; color:var(--muted); font-size:0.72rem; border-top:1px solid rgba(255,255,255,0.06); padding-top:4px;">Total: ${total} Mandatos</div>`;
        } else {
          totalLabel = `<div style="margin-top:6px; color:var(--muted); font-size:0.72rem; border-top:1px solid rgba(255,255,255,0.06); padding-top:4px;">Total: ${fmtInt(total)} Votos Válidos</div>`;
        }
      } else {
        rowsHtml = `<div style="color:var(--muted); margin-top:3px;">Sem dados</div>`;
      }
    }
  } else if (votes && Object.keys(votes).length) {
    const entries = Object.entries(votes).sort((a, b) => b[1] - a[1]);
    let total = 0;
    entries.forEach(([, v]) => { total += v; });
    rowsHtml = entries.slice(0, 3).map(([party, v]) => {
      const color = getResolvedPartyColor(party);
      const pct = total > 0 ? (v / total) : 0;
      return `<div style="display:flex; align-items:center; gap:6px; margin-top:3px;">
        <span style="width:9px; height:9px; border-radius:2px; background:${color}; flex-shrink:0;"></span>
        <span style="flex:1; min-width: 80px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${escapeHtml(party)}">${escapeHtml(party)}</span>
        <strong style="font-variant-numeric: tabular-nums;">${fmtPct(pct)}</strong>
        <span style="color:var(--muted); font-variant-numeric: tabular-nums;">${fmtInt(v)}</span>
      </div>`;
    }).join('');
    totalLabel = `<div style="margin-top:6px; color:var(--muted); font-size:0.72rem; border-top:1px solid rgba(255,255,255,0.06); padding-top:4px;">Total: ${fmtInt(total)} Votos Válidos</div>`;
  } else {
    const noElection = (typeof territoryHasNoElection === 'function') && territoryHasNoElection(id);
    rowsHtml = `<div style="color:var(--muted); margin-top:3px;">${noElection ? 'Votação não realizada' : 'Sem dados'}</div>`;
  }

  const parentName = (level === 'distrito' && (STATE.currentCirculo === 'E1' || STATE.currentCirculo === 'E2'))
    ? CIRCULOS.get(STATE.currentCirculo)
    : (level === 'freguesia'
       ? `${escapeHtml(p.concelho || '')}${p.concelho ? ' · ' : ''}${escapeHtml(CIRCULOS.get(p.circulo) || '')}`
       : (level === 'concelho' ? escapeHtml(CIRCULOS.get(p.circulo) || '') : 'Portugal'));

  return `<div style="min-width: 170px;">
    <div style="font-weight:700;">${escapeHtml(nome)}</div>
    <div style="color:var(--muted); font-size:0.75rem;">${parentName}</div>
    ${rowsHtml}
    ${totalLabel}
  </div>`;
}

// ---------- CLIQUE / NAVEGAÇÃO ----------

function onFeatureClick(level, feature, e) {
  const cfg = MAP_LEVELS[level];
  const idProp = (level === 'distrito' && (STATE.currentCirculo === 'E1' || STATE.currentCirculo === 'E2')) ? 'nome' : cfg.idProp;
  const id = feature.properties?.[idProp];
  if (!id) return;

  if (typeof window.isFeatureDisabled === 'function' && window.isFeatureDisabled(level === 'freguesia' ? 'freguesias' : (level === 'concelho' ? 'concelhos' : 'distritos'), feature)) {
    return;
  }

  if (level === 'distrito') {
    if (STATE.currentCirculo === 'E1' || STATE.currentCirculo === 'E2') {
      STATE.selectedCountry = id;
      renderResultsPanel();
      applyFiltersAndRedraw();
      return;
    }
    navigateToDistrito(id, { focus: true });
  } else if (level === 'concelho') {
    navigateToConcelho(id, feature);
  } else if (level === 'freguesia') {
    const shiftKey = !!(e?.originalEvent?.shiftKey);
    if (shiftKey) {
      if (selectedLocationIDs.has(id)) selectedLocationIDs.delete(id);
      else selectedLocationIDs.add(id);
      isDragSelection = false;
      applyFiltersAndRedraw();
      return;
    }
    selectedLocationIDs.clear();
    STATE.scope = {
      level: 'freguesia',
      key: id,
      concelho: id.slice(0, 4),
      circulo: circuloFromDicofre(id)
    };
    applyFiltersAndRedraw();
  }
}

async function navigateToNational({ focus = false } = {}) {
  selectedLocationIDs.clear();
  STATE.selectedCountry = null;
  STATE.scope = { level: 'national', key: null };
  STATE.mapLevel = STATE.granularity;
  if (dom.selectCirculo) dom.selectCirculo.value = '';
  STATE.currentCirculo = '';
  
  if (STATE.mapLevel === 'freguesia') {
    const bundle = PT_YEAR_CACHE.get(STATE.currentElectionType === 'au' ? `${STATE.currentElectionType}:${STATE.auSubtype}:${STATE.currentYear}` : `${STATE.currentElectionType}:${STATE.currentYear}`);
    if (bundle && !bundle.freguesiasLoaded) {
      showMapLoading("A carregar freguesias em fundo...", 50);
      await bundle.freguesiasReady;
      hideMapLoading();
    }
  }
  
  syncMapLevel();
  if (focus) {
    focusCountryOnMap(true);
  }
  applyFiltersAndRedraw();
}

async function navigateToDistrito(circulo, { focus = false } = {}) {
  selectedLocationIDs.clear();
  STATE.selectedCountry = null;
  STATE.currentCirculo = circulo;

  if (CIRCULOS_SEM_GEOMETRIA.has(circulo)) {
    STATE.scope = { level: 'distrito', key: circulo };
    STATE.mapLevel = 'distrito';
    syncMapLevel();
    if (dom.selectCirculo) dom.selectCirculo.value = circulo;
    if (focus) {
      focusCirculoOnMap(circulo, true);
    }
    applyFiltersAndRedraw();
    return;
  }
  
  STATE.scope = { level: 'distrito', key: circulo };
  if (dom.selectCirculo) dom.selectCirculo.value = circulo;
  
  // Sempre entra em concelhos quando clica/seleciona distrito
  STATE.mapLevel = 'concelho';
  
  syncMapLevel();
  if (focus) {
    focusCirculoOnMap(circulo, true);
  }
  applyFiltersAndRedraw();
}

async function navigateToConcelho(dico, feature = null) {
  selectedLocationIDs.clear();
  STATE.selectedCountry = null;
  const circulo = circuloFromDicofre(dico + '00');
  
  STATE.scope = {
    level: 'concelho',
    key: dico,
    nome: feature?.properties?.concelho || getConcelhoNome(dico),
    circulo: circulo
  };
  
  // Sempre entra em freguesias quando clica/seleciona concelho
  STATE.mapLevel = 'freguesia';
  
  if (dom.selectCirculo) dom.selectCirculo.value = circulo;
  STATE.currentCirculo = circulo;
  
  if (STATE.mapLevel === 'freguesia') {
    const bundle = PT_YEAR_CACHE.get(STATE.currentElectionType === 'au' ? `${STATE.currentElectionType}:${STATE.auSubtype}:${STATE.currentYear}` : `${STATE.currentElectionType}:${STATE.currentYear}`);
    if (bundle && !bundle.freguesiasLoaded) {
      showMapLoading("A carregar freguesias em fundo...", 50);
      await bundle.freguesiasReady;
      hideMapLoading();
    }
  }

  syncMapLevel();
  
  let targetFeature = feature;
  if (!targetFeature && STATE.geo?.concelhos) {
    targetFeature = STATE.geo.concelhos.features.find(f => f.properties?.dico === dico);
  }
  if (targetFeature) {
    const bounds = MLCompat.featureBounds(targetFeature);
    if (bounds) MLCompat.fitMapToBounds(map, bounds, { padding: [40, 40], animate: true });
  }
  applyFiltersAndRedraw();
}

function clearSelection(redraw = true) {
  selectedLocationIDs.clear();
  STATE.selectedCountry = null;
  isDragSelection = false;
  if (STATE.currentCirculo) {
    navigateToDistrito(STATE.currentCirculo, { focus: false });
  } else {
    navigateToNational({ focus: false });
  }
}

function updateClearSelectionButtonVisibility() {
  const btn = dom.btnClearSelection || document.getElementById('btnClearSelection');
  if (btn) {
    const show = selectedLocationIDs.size > 0 || !!STATE.selectedCountry;
    btn.style.display = show ? 'inline-flex' : 'none';
  }
}

// ---------- CAMADAS ----------

function buildMapLayers() {
  const geo = STATE.geo;
  if (!geo) return;

  if (STATE.freguesiasLayer) { STATE.freguesiasLayer.remove(); STATE.freguesiasLayer = null; }
  if (STATE.concelhosLayer) { STATE.concelhosLayer.remove(); STATE.concelhosLayer = null; }
  if (STATE.distritosLayer) { STATE.distritosLayer.remove(); STATE.distritosLayer = null; }
  if (STATE.concelhosOutlineLayer) { STATE.concelhosOutlineLayer.remove(); STATE.concelhosOutlineLayer = null; }
  if (STATE.distritosOutlineLayer) { STATE.distritosOutlineLayer.remove(); STATE.distritosOutlineLayer = null; }

  // 1. Freguesias Fill
  STATE.freguesiasLayer = new MLCompat.GeoLayer(map, {
    id: 'freguesias',
    type: 'polygon',
    styleFn: (feat) => getFeatureStyle('freguesia', feat),
    tooltipFn: (feat) => buildFeatureTooltip('freguesia', feat),
    onClick: (feat, e) => onFeatureClick('freguesia', feat, e),
    hover: true
  }).setFeatures([]).addTo(map);

  // 2. Concelhos Fill
  STATE.concelhosLayer = new MLCompat.GeoLayer(map, {
    id: 'concelhos',
    type: 'polygon',
    styleFn: (feat) => getFeatureStyle('concelho', feat),
    tooltipFn: (feat) => buildFeatureTooltip('concelho', feat),
    onClick: (feat, e) => onFeatureClick('concelho', feat, e),
    hover: true
  }).setFeatures([]).addTo(map);

  // 3. Distritos Fill
  STATE.distritosLayer = new MLCompat.GeoLayer(map, {
    id: 'distritos',
    type: 'polygon',
    styleFn: (feat) => getFeatureStyle('distrito', feat),
    tooltipFn: (feat) => buildFeatureTooltip('distrito', feat),
    onClick: (feat, e) => onFeatureClick('distrito', feat, e),
    hover: true
  }).setFeatures(geo.distritos.features).addTo(map);

  // 4. Concelhos Outline
  STATE.concelhosOutlineLayer = new MLCompat.GeoLayer(map, {
    id: 'concelhos-outline',
    type: 'polygon',
    styleFn: () => ({
      fillColor: '#000000', fillOpacity: 0,
      color: 'rgba(255,255,255,0.55)', weight: 0.9, opacity: 0.7
    })
  }).setFeatures([]).addTo(map);

  // 5. Distritos Outline
  STATE.distritosOutlineLayer = new MLCompat.GeoLayer(map, {
    id: 'distritos-outline',
    type: 'polygon',
    styleFn: () => ({
      fillColor: '#000000', fillOpacity: 0,
      color: 'rgba(255,255,255,0.85)', weight: 1.4, opacity: 0.8
    })
  }).setFeatures([]).addTo(map);

  syncMapLevel();
}

function syncMapLevel() {
  const geo = STATE.geo;
  if (!geo) return;

  const level = STATE.mapLevel;

  if (map) {
    try {
      map.setFeatureState({ source: 'distritos-source', id: 0 }, { hover: false });
      map.setFeatureState({ source: 'concelhos-source', id: 0 }, { hover: false });
      map.setFeatureState({ source: 'freguesias-source', id: 0 }, { hover: false });
    } catch (_) {}

    if (STATE.currentCirculo === 'E1' || STATE.currentCirculo === 'E2') {
      map.setMinZoom(1);
    } else {
      map.setMinZoom(4.5);
    }
  }

  if (level === 'distrito') {
    if (STATE.currentCirculo === 'E1') {
      STATE.distritosLayer?.setData(geo.estrangeiroEuropa?.features || []);
    } else if (STATE.currentCirculo === 'E2') {
      STATE.distritosLayer?.setData(geo.estrangeiroMundo?.features || []);
    } else {
      STATE.distritosLayer?.setData(geo.distritos.features);
    }
    STATE.concelhosLayer?.setData([]);
    STATE.freguesiasLayer?.setData([]);

    STATE.distritosOutlineLayer?.setData([]);
    STATE.concelhosOutlineLayer?.setData([]);
  }
  else if (level === 'concelho') {
    // Mostra TODOS os concelhos de Portugal no mapa (os adjacentes continuam visíveis)
    STATE.concelhosLayer?.setData(geo.concelhos.features);
    STATE.distritosLayer?.setData([]);
    STATE.freguesiasLayer?.setData([]);

    // Contorno do distrito selecionado para destaque
    let distFeats = geo.distritos.features;
    if (STATE.currentCirculo && !CIRCULOS_SEM_GEOMETRIA.has(STATE.currentCirculo)) {
      distFeats = distFeats.filter(f => f.properties?.circulo === STATE.currentCirculo);
    }
    STATE.distritosOutlineLayer?.setData(distFeats);
    STATE.concelhosOutlineLayer?.setData([]);
  }
  else if (level === 'freguesia') {
    // Mostra TODAS as freguesias de Portugal no mapa (as adjacentes continuam visíveis)
    STATE.freguesiasLayer?.setData(geo.freguesias?.features || []);
    STATE.distritosLayer?.setData([]);
    STATE.concelhosLayer?.setData([]);

    // Contorno do concelho/distrito selecionado para destaque
    let concFeats = geo.concelhos.features;
    if (STATE.scope.level === 'concelho' || STATE.scope.level === 'freguesia') {
      const dico = STATE.scope.level === 'concelho' ? STATE.scope.key : STATE.scope.key.slice(0, 4);
      concFeats = concFeats.filter(f => f.properties?.dico === dico);
    } else if (STATE.currentCirculo && !CIRCULOS_SEM_GEOMETRIA.has(STATE.currentCirculo)) {
      concFeats = concFeats.filter(f => f.properties?.circulo === STATE.currentCirculo);
    }
    STATE.concelhosOutlineLayer?.setData(concFeats);
    STATE.distritosOutlineLayer?.setData([]);
  }
}

function applyFiltersAndRedraw() {
  const level = STATE.mapLevel;
  if (level === 'distrito' && STATE.distritosLayer) {
    STATE.distritosLayer.setExtrusionEnabled(STATE.extrusionEnabled);
    STATE.distritosLayer.refresh();
  } else if (level === 'concelho' && STATE.concelhosLayer) {
    STATE.concelhosLayer.setExtrusionEnabled(STATE.extrusionEnabled);
    STATE.concelhosLayer.refresh();
  } else if (level === 'freguesia' && STATE.freguesiasLayer) {
    STATE.freguesiasLayer.setExtrusionEnabled(STATE.extrusionEnabled);
    STATE.freguesiasLayer.refresh();
  }
  if (typeof renderResultsPanel === 'function') renderResultsPanel();
  updateClearSelectionButtonVisibility();
  if (typeof window.syncShortcutButtons === 'function') {
    window.syncShortcutButtons();
  }
}

function refreshMapStylesAndTooltips() {
  applyFiltersAndRedraw();
}

// ---------- FOCO / ZOOM ----------

function focusCirculoOnMap(circulo, animate = true) {
  if (!STATE.geo || !circulo) return;
  if (circulo === 'E1') {
    const bounds = MLCompat.featureCollectionBounds(STATE.geo.estrangeiroEuropa?.features || []);
    if (bounds) MLCompat.fitMapToBounds(map, bounds, { padding: [40, 40], animate });
    return;
  }
  if (circulo === 'E2') {
    const bounds = MLCompat.featureCollectionBounds(STATE.geo.estrangeiroMundo?.features || []);
    if (bounds) MLCompat.fitMapToBounds(map, bounds, { padding: [40, 40], animate });
    return;
  }
  if (CIRCULOS_SEM_GEOMETRIA.has(circulo)) return;
  const feature = STATE.geo.distritos.features.find(f => f.properties?.circulo === circulo);
  if (!feature) return;
  const bounds = MLCompat.featureBounds(feature);
  if (bounds) MLCompat.fitMapToBounds(map, bounds, { padding: [40, 40], animate });
}

function focusCountryOnMap(animate = false) {
  if (!STATE.geo) return;
  const level = STATE.mapLevel;
  const list = (level === 'freguesia') ? (STATE.geo.freguesias?.features || [])
             : (level === 'concelho' ? STATE.geo.concelhos.features
             : STATE.geo.distritos.features);
             
  const cont = list.filter(f => {
    const circ = f.properties?.circulo || (level === 'distrito' ? f.properties?.circulo : circuloFromDicofre(f.properties?.dico + '00'));
    return circ && circ <= '18';
  });
  
  const bounds = cont.length
    ? MLCompat.featureCollectionBounds(cont)
    : (level === 'freguesia' && STATE.freguesiasLayer ? STATE.freguesiasLayer.getBounds()
       : (level === 'concelho' && STATE.concelhosLayer ? STATE.concelhosLayer.getBounds()
       : STATE.distritosLayer?.getBounds()));
       
  if (bounds) MLCompat.fitMapToBounds(map, bounds, { padding: [24, 24], animate });
}

// ---------- SELEÇÃO POR ARRASTO (Shift+drag) ----------

function setupBoxSelection() {
  const mapContainer = map.getContainer();
  if (map.boxZoom) map.boxZoom.disable();

  selectionBoxElement = document.createElement('div');
  selectionBoxElement.classList.add('selection-box');
  mapContainer.appendChild(selectionBoxElement);

  mapContainer.addEventListener('mousedown', handleBoxSelectMouseDown);
  window.addEventListener('mousemove', handleBoxSelectMouseMove);
  window.addEventListener('mouseup', handleBoxSelectMouseUp);
}

function handleBoxSelectMouseDown(e) {
  if (!e.shiftKey || e.button !== 0) return;
  isSelectorsActive = true;
  if (map.dragPan) map.dragPan.disable();

  const rect = map.getContainer().getBoundingClientRect();
  startSelectionPoint = { x: e.clientX - rect.left, y: e.clientY - rect.top };
  updateSelectionBox(startSelectionPoint.x, startSelectionPoint.y, 0, 0);
  selectionBoxElement.style.display = 'block';
  e.preventDefault();
}

function handleBoxSelectMouseMove(e) {
  if (!isSelectorsActive) return;
  const rect = map.getContainer().getBoundingClientRect();
  const currentX = e.clientX - rect.left;
  const currentY = e.clientY - rect.top;
  updateSelectionBox(
    Math.min(startSelectionPoint.x, currentX),
    Math.min(startSelectionPoint.y, currentY),
    Math.abs(currentX - startSelectionPoint.x),
    Math.abs(currentY - startSelectionPoint.y)
  );
}

function handleBoxSelectMouseUp(e) {
  if (!isSelectorsActive) return;
  isSelectorsActive = false;
  selectionBoxElement.style.display = 'none';
  if (map.dragPan) map.dragPan.enable();

  const rect = map.getContainer().getBoundingClientRect();
  const endX = e.clientX - rect.left;
  const endY = e.clientY - rect.top;
  const dist = Math.hypot(endX - startSelectionPoint.x, endY - startSelectionPoint.y);
  if (dist < 5) return;

  const minX = Math.min(startSelectionPoint.x, endX);
  const maxX = Math.max(startSelectionPoint.x, endX);
  const minY = Math.min(startSelectionPoint.y, endY);
  const maxY = Math.max(startSelectionPoint.y, endY);
  selectFreguesiasInPixelBox([[minX, minY], [maxX, maxY]]);
}

function updateSelectionBox(x, y, w, h) {
  selectionBoxElement.style.left = x + 'px';
  selectionBoxElement.style.top = y + 'px';
  selectionBoxElement.style.width = w + 'px';
  selectionBoxElement.style.height = h + 'px';
}

function selectFreguesiasInPixelBox(pixelBox) {
  if (STATE.mapLevel !== 'freguesia') return;
  if (!map.getLayer('freguesias-fill')) return;
  let added = 0;
  const found = map.queryRenderedFeatures(pixelBox, { layers: ['freguesias-fill'] });
  found.forEach((feat) => {
    const dicofre = feat.properties?.dicofre;
    if (dicofre && !selectedLocationIDs.has(dicofre)) {
      selectedLocationIDs.add(dicofre);
      added++;
    }
  });
  if (added > 0) {
    isDragSelection = true;
    applyFiltersAndRedraw();
  }
}

// Exports globais
window.applyFiltersAndRedraw = applyFiltersAndRedraw;
window.refreshMapStylesAndTooltips = refreshMapStylesAndTooltips;
window.clearSelection = clearSelection;
window.updateClearSelectionButtonVisibility = updateClearSelectionButtonVisibility;

window.navigateToNational = navigateToNational;
window.navigateToDistrito = navigateToDistrito;
window.navigateToConcelho = navigateToConcelho;
window.focusCountryOnMap = focusCountryOnMap;
window.focusCirculoOnMap = focusCirculoOnMap;
window.syncMapLevel = syncMapLevel;
