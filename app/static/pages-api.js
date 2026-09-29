(function () {
  if (!window.HYDRA_STATIC_SITE) return;

  const nativeFetch = window.fetch.bind(window);
  const dataRoot = new URL('./pages-data/', document.baseURI);
  const cache = new Map();
  const presets = {
    tehri_breach: {event_type:'dam_breach', breach_width_m:60, breach_depth_m:30, formation_hours:1.5, rainfall_multiplier:1.0},
    extreme_monsoon: {event_type:'dam_breach', breach_width_m:80, breach_depth_m:35, formation_hours:0.75, rainfall_multiplier:1.3},
    lake_outburst: {event_type:'lake_burst', breach_width_m:42, breach_depth_m:24, formation_hours:0.6, rainfall_multiplier:1.15},
    blockage_failure: {event_type:'blockage_failure', breach_width_m:55, breach_depth_m:22, formation_hours:1.0, rainfall_multiplier:1.2},
    sudden_release: {event_type:'sudden_release', breach_width_m:28, breach_depth_m:14, formation_hours:4.0, rainfall_multiplier:0.9},
  };

  async function loadJson(relativePath) {
    if (cache.has(relativePath)) return structuredClone(cache.get(relativePath));
    const response = await nativeFetch(new URL(relativePath, dataRoot));
    if (!response.ok) throw new Error(`Static deployment data is unavailable (${response.status}).`);
    const payload = await response.json();
    cache.set(relativePath, payload);
    return structuredClone(payload);
  }

  function sameScenario(left, right) {
    const numeric = ['breach_width_m', 'breach_depth_m', 'formation_hours', 'rainfall_multiplier'];
    return left.event_type === right.event_type && numeric.every(key => Math.abs(Number(left[key]) - Number(right[key])) < 1e-9);
  }

  function fail(message) {
    const error = new Error(message);
    error.payload = {error: message};
    throw error;
  }

  window.HYDRA_STATIC_API = async function (path, options={}) {
    const route = String(path).split('?')[0];
    if (route === '/api/catalog') return loadJson('catalog.json');
    if (route === '/api/state') return loadJson('state.json');
    if (route === '/api/sources') return loadJson('sources.json');
    if (route === '/api/demo') return loadJson('demo.json');
    if (route === '/api/demo/scenarios' && String(options.method || 'GET').toUpperCase() === 'POST') {
      const request = JSON.parse(options.body || '{}');
      const match = Object.entries(presets).find(([, preset]) => sameScenario(request, preset));
      if (!match) fail('The GitHub Pages deployment runs the five packaged presets. Select a Demo story preset before running; custom simulations require the local Python application.');
      return loadJson(`scenarios/${match[0]}.json`);
    }
    if (route.startsWith('/api/import/')) fail('File ingestion requires the local Python application; GitHub Pages is the packaged demonstration.');
    if (route === '/api/scenarios') fail('Live-input scenarios require the local Python application; GitHub Pages is the packaged demonstration.');
    fail(`Route ${route} is not available in the GitHub Pages deployment.`);
  };
}());
