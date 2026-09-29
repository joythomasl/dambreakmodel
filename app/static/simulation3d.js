/* An honest 3-D view of the executed 2-D model: every blue cell is a saved
   water depth. Terrain smoothing, lighting and contours aid reading, but add
   no hydraulic resolution. No remote rendering dependency is used. */
(() => {
  const canvas = document.getElementById('simulationCanvas');
  const branchSelect = document.getElementById('simulationBranch');
  const slider = document.getElementById('simulationTime');
  const playButton = document.getElementById('simulationPlay');
  const peakButton = document.getElementById('simulationPeak');
  const clock = document.getElementById('simulationClock');
  const overlay = document.getElementById('simulationOverlay');
  const stats = document.getElementById('simulationStats');
  const attribution = document.getElementById('simulationAttribution');
  const scaleLabel = document.getElementById('simulationScale');
  const probe = document.getElementById('simulationProbe');
  const compass = document.getElementById('simulationCompass');
  const exaggeration = document.getElementById('simulationExaggeration');
  const exaggerationValue = document.getElementById('simulationExaggerationValue');
  const showStructures = document.getElementById('simulationStructures');
  const showWireframe = document.getElementById('simulationWireframe');
  const showMaximum = document.getElementById('simulationMaxExtent');
  const domainSelect = document.getElementById('simulationDomain');
  const showSatellite = document.getElementById('simulationSatellite');
  const showRoads = document.getElementById('simulationRoads');
  const showLabels = document.getElementById('simulationLabelsToggle');
  const labelLayer = document.getElementById('simulationLabels');
  const gl = canvas.getContext('webgl', {antialias: true, alpha: false});

  let result = null;
  let frameIndex = 0;
  let timer = null;
  let yaw = -0.55;
  let pitch = 0.72;
  let zoom = 22;
  let drag = null;
  let program = null;
  let buffer = null;
  let uniform = null;
  let geometry = null;
  let satelliteTexture = null;
  let satelliteTextureUrl = '';
  let labelEntries = [];
  const stride = 9 * 4;

  function compile(type, source) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader));
    return shader;
  }

  if (gl) {
    try {
      program = gl.createProgram();
      gl.attachShader(program, compile(gl.VERTEX_SHADER, `
         attribute vec3 aPosition;
         attribute vec4 aColor;
         attribute vec2 aTexCoord;
        uniform float uYaw;
        uniform float uPitch;
        uniform float uZoom;
        uniform float uHeightCenter;
         varying vec4 vColor;
         varying vec2 vTexCoord;
        void main() {
          float cy=cos(uYaw), sy=sin(uYaw), cp=cos(uPitch), sp=sin(uPitch);
          float z=aPosition.z-uHeightCenter;
          float x=cy*aPosition.x-sy*aPosition.y;
          float y=sy*aPosition.x+cy*aPosition.y;
          float screenY=y*cp-z*sp;
          float depth=y*sp+z*cp;
          gl_Position=vec4(x/uZoom,-screenY/uZoom,-depth/100.0,1.0);
           vColor=aColor;
           vTexCoord=aTexCoord;
         }`));
      gl.attachShader(program, compile(gl.FRAGMENT_SHADER, `
         precision mediump float;
         varying vec4 vColor;
         varying vec2 vTexCoord;
         uniform sampler2D uTexture;
         uniform float uUseTexture;
         void main() {
           vec4 imagery=texture2D(uTexture,vTexCoord);
           vec4 textured=vec4(mix(vColor.rgb,imagery.rgb,0.86),vColor.a);
           gl_FragColor=mix(vColor,textured,uUseTexture);
         }`));
      gl.linkProgram(program);
      if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program));
      buffer = gl.createBuffer();
      gl.useProgram(program);
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      const position = gl.getAttribLocation(program, 'aPosition');
       const color = gl.getAttribLocation(program, 'aColor');
       const texCoord = gl.getAttribLocation(program, 'aTexCoord');
      gl.enableVertexAttribArray(position);
       gl.enableVertexAttribArray(color);
       gl.enableVertexAttribArray(texCoord);
      gl.vertexAttribPointer(position, 3, gl.FLOAT, false, stride, 0);
       gl.vertexAttribPointer(color, 4, gl.FLOAT, false, stride, 12);
       gl.vertexAttribPointer(texCoord, 2, gl.FLOAT, false, stride, 28);
      uniform = {
        yaw: gl.getUniformLocation(program, 'uYaw'),
        pitch: gl.getUniformLocation(program, 'uPitch'),
        zoom: gl.getUniformLocation(program, 'uZoom'),
         heightCenter: gl.getUniformLocation(program, 'uHeightCenter'),
         useTexture: gl.getUniformLocation(program, 'uUseTexture'),
         texture: gl.getUniformLocation(program, 'uTexture'),
      };
      gl.uniform1i(uniform.texture, 0);
      // Keep the sampler complete before the optional image has loaded. This
      // also guarantees the colour-only terrain remains visible on failure.
      satelliteTexture = gl.createTexture();
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, satelliteTexture);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 1, 1, 0, gl.RGBA,
        gl.UNSIGNED_BYTE, new Uint8Array([112, 139, 105, 255]));
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      gl.enable(gl.DEPTH_TEST);
      gl.depthFunc(gl.LEQUAL);
      gl.clearColor(0.83, 0.91, 0.92, 1);
    } catch (error) {
      overlay.textContent = `3-D renderer could not start: ${error.message}`;
      program = null;
    }
  } else {
    overlay.textContent = 'WebGL is unavailable. Enable graphics acceleration for 3-D playback; the server-side simulation still runs.';
  }

  function regionalSimulation() {
    const terrain=result?.spatial_context?.regional_terrain;
    const map=result?.spatial_context?.regional_map;
    const branch=result?.cascade?.branches?.[branchSelect.value];
    if (!terrain?.elevation_m?.length || !map?.cascade_nodes?.length || !branch) return null;
    const firstTime=new Date(branch.timeline[0]?.time||0);
    const nodeTimes=map.cascade_nodes.map(node=>{
      const match=branch.timeline.find(item=>String(item.node).toLowerCase().startsWith(node.name.split(' ')[0].toLowerCase()));
      return Math.max(0,Math.round((new Date(match?.time||firstTime)-firstTime)/1000));
    });
    const empty=new Array(terrain.width*terrain.height).fill(0);
    return {
      id:terrain.id,is_regional_context:true,width:terrain.width,height:terrain.height,
      cell_size_m:terrain.cell_size_m,elevation_m:terrain.elevation_m,
      maximum_depth_m:empty,peak_depth_m:0,wet_cell_count:0,time_steps:0,
      frames:nodeTimes.map((time_s,index)=>({time_s,depth_m:empty,route_progress:index})),
      volume:{mass_balance_error_m3:0},terrain:{
        west:terrain.west,north:terrain.north,lon_step:terrain.lon_step,lat_step:terrain.lat_step,
        source:terrain.source,id:terrain.id,
      },satellite:terrain.satellite,
    };
  }
  function active() { return domainSelect.value==='regional'?regionalSimulation():result?.spatial_simulation?.[branchSelect.value]; }
  function activeContext() { return domainSelect.value==='regional'?result?.spatial_context?.regional_map:result?.spatial_context?.local_map; }
  function activeSatellite(sim) {
    return sim?.is_regional_context ? sim.satellite : result?.spatial_context?.local_map?.satellite;
  }
  function heightScale(sim) { return Number(exaggeration.value) / sim.cell_size_m; }
  function point(col, row, z, sim) { return [col - sim.width / 2, row - sim.height / 2, z]; }

  function loadSatellite(sim) {
    const metadata = activeSatellite(sim);
    if (!gl || !metadata?.url || satelliteTextureUrl === metadata.url) return;
    const requestedUrl = metadata.url;
    const image = new Image();
    image.onload = () => {
      if (activeSatellite(active())?.url !== requestedUrl) return;
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, satelliteTexture);
      // Row zero in both model grids is the northern edge; the WMS image's
      // first row is also north, so keep upload row order unchanged.
      gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, image);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      satelliteTextureUrl = requestedUrl;
      draw();
    };
    image.onerror = () => {
      if (activeSatellite(active())?.url === requestedUrl) {
        overlay.textContent = 'Satellite texture unavailable; showing shaded elevation terrain.';
      }
    };
    image.src = requestedUrl;
  }

  function triangle(out, a, b, c, ca, cb=ca, cc=ca, ua=[0,0], ub=ua, uc=ua) {
    out.push(...a, ...ca, ...ua, ...b, ...cb, ...ub, ...c, ...cc, ...uc);
  }
  function quad(out, a, b, c, d, colours, uvs=[[0,0],[0,0],[0,0],[0,0]]) {
    const colors = Array.isArray(colours[0]) ? colours : [colours, colours, colours, colours];
    triangle(out, a, b, c, colors[0], colors[1], colors[2], uvs[0], uvs[1], uvs[2]);
    triangle(out, a, c, d, colors[0], colors[2], colors[3], uvs[0], uvs[2], uvs[3]);
  }
  function line(out, a, b, color) { out.push(...a, ...color, 0, 0, ...b, ...color, 0, 0); }
  function mix(a, b, t) { return a.map((value, i) => value * (1 - t) + b[i] * t); }

  function cornerGrid(sim) {
    const corners = [];
    for (let row = 0; row <= sim.height; row++) {
      const values = [];
      for (let col = 0; col <= sim.width; col++) {
        let sum = 0, count = 0;
        for (let r = Math.max(0, row - 1); r <= Math.min(sim.height - 1, row); r++) {
          for (let c = Math.max(0, col - 1); c <= Math.min(sim.width - 1, col); c++) {
            sum += sim.elevation_m[r * sim.width + c];
            count++;
          }
        }
        values.push(sum / count);
      }
      corners.push(values);
    }
    return corners;
  }

  function terrainColour(sim, corners, row, col, minimum, maximum) {
    const elevation = corners[row][col];
    const t = Math.max(0, Math.min(1, (elevation - minimum) / Math.max(maximum - minimum, 1)));
    const low = [0.22, 0.49, 0.44];
    const mid = [0.48, 0.59, 0.39];
    const high = [0.74, 0.62, 0.45];
    const base = t < 0.55 ? mix(low, mid, t / 0.55) : mix(mid, high, (t - 0.55) / 0.45);
    const x0 = Math.max(0, col - 1), x1 = Math.min(sim.width, col + 1);
    const y0 = Math.max(0, row - 1), y1 = Math.min(sim.height, row + 1);
    const factor = heightScale(sim);
    const dzdx = (corners[row][x1] - corners[row][x0]) * factor / Math.max(x1 - x0, 1);
    const dzdy = (corners[y1][col] - corners[y0][col]) * factor / Math.max(y1 - y0, 1);
    const nx = -dzdx, ny = -dzdy, nz = 1;
    const length = Math.hypot(nx, ny, nz);
    const sun = Math.max(0, (nx * -0.43 + ny * -0.46 + nz * 0.78) / length);
    const light = 0.68 + 0.42 * sun;
    return [...base.map(value => Math.min(1, value * light)), 1];
  }

  function buildGeometry(sim) {
    const bed = sim.elevation_m;
    const minimum = Math.min(...bed), maximum = Math.max(...bed);
    const scale = heightScale(sim);
    const corners = cornerGrid(sim);
    const terrain = [], skirt = [], contours = [], grid = [], maximumExtent = [];
    const z = (elevation) => (elevation - minimum) * scale;
    for (let row = 0; row < sim.height; row++) {
      for (let col = 0; col < sim.width; col++) {
        const a = point(col, row, z(corners[row][col]), sim);
        const b = point(col + 1, row, z(corners[row][col + 1]), sim);
        const c = point(col + 1, row + 1, z(corners[row + 1][col + 1]), sim);
        const d = point(col, row + 1, z(corners[row + 1][col]), sim);
        quad(terrain, a, b, c, d, [
          terrainColour(sim, corners, row, col, minimum, maximum),
          terrainColour(sim, corners, row, col + 1, minimum, maximum),
          terrainColour(sim, corners, row + 1, col + 1, minimum, maximum),
          terrainColour(sim, corners, row + 1, col, minimum, maximum),
        ], [[col/sim.width,row/sim.height],[(col+1)/sim.width,row/sim.height],[(col+1)/sim.width,(row+1)/sim.height],[col/sim.width,(row+1)/sim.height]]);
        // Ten-metre contours are interpolated across the same displayed mesh.
        for (let level = Math.ceil(Math.min(corners[row][col], corners[row][col + 1], corners[row + 1][col + 1], corners[row + 1][col]) / 10) * 10;
             level <= Math.max(corners[row][col], corners[row][col + 1], corners[row + 1][col + 1], corners[row + 1][col]); level += 10) {
          const corners2d = [[col,row,corners[row][col]],[col+1,row,corners[row][col+1]],
            [col+1,row+1,corners[row+1][col+1]],[col,row+1,corners[row+1][col]]];
          const crossings = [];
          for (let edge = 0; edge < 4; edge++) {
            const p = corners2d[edge], q = corners2d[(edge + 1) % 4];
            if ((p[2] < level && q[2] >= level) || (q[2] < level && p[2] >= level)) {
              const ratio = (level - p[2]) / (q[2] - p[2]);
              crossings.push(point(p[0] + (q[0]-p[0])*ratio, p[1] + (q[1]-p[1])*ratio,
                z(level) + 0.018, sim));
            }
          }
          for (let i = 0; i + 1 < crossings.length; i += 2)
            line(contours, crossings[i], crossings[i + 1], [0.11, 0.24, 0.25, 0.33]);
        }
        if (sim.maximum_depth_m[row * sim.width + col] >= 0.1) {
          const wet = (r,c) => r >= 0 && r < sim.height && c >= 0 && c < sim.width &&
            sim.maximum_depth_m[r * sim.width + c] >= 0.1;
          const gold = [0.98, 0.73, 0.26, 0.95];
          const lift = vertex => [vertex[0], vertex[1], vertex[2] + 0.05];
          if (!wet(row-1,col)) line(maximumExtent, lift(a), lift(b), gold);
          if (!wet(row,col+1)) line(maximumExtent, lift(b), lift(c), gold);
          if (!wet(row+1,col)) line(maximumExtent, lift(c), lift(d), gold);
          if (!wet(row,col-1)) line(maximumExtent, lift(d), lift(a), gold);
        }
      }
    }
    const gridColor = [0.94, 0.98, 0.93, 0.22];
    for (let row = 0; row <= sim.height; row += 2) {
      for (let col = 0; col < sim.width; col++) {
        line(grid, point(col,row,z(corners[row][col])+0.025,sim),
          point(col+1,row,z(corners[row][col+1])+0.025,sim), gridColor);
      }
    }
    for (let col = 0; col <= sim.width; col += 2) {
      for (let row = 0; row < sim.height; row++) {
        line(grid, point(col,row,z(corners[row][col])+0.025,sim),
          point(col,row+1,z(corners[row+1][col])+0.025,sim), gridColor);
      }
    }
    const bottom = -0.85;
    const side = [0.19, 0.29, 0.25, 1];
    for (let col = 0; col < sim.width; col++) {
      const topN0 = point(col, 0, z(corners[0][col]), sim);
      const topN1 = point(col + 1, 0, z(corners[0][col + 1]), sim);
      const topS0 = point(col, sim.height, z(corners[sim.height][col]), sim);
      const topS1 = point(col + 1, sim.height, z(corners[sim.height][col + 1]), sim);
      quad(skirt, topN0, topN1, point(col+1,0,bottom,sim), point(col,0,bottom,sim), side);
      quad(skirt, topS1, topS0, point(col,sim.height,bottom,sim), point(col+1,sim.height,bottom,sim), side);
    }
    for (let row = 0; row < sim.height; row++) {
      const west0 = point(0,row,z(corners[row][0]),sim);
      const west1 = point(0,row+1,z(corners[row+1][0]),sim);
      const east0 = point(sim.width,row,z(corners[row][sim.width]),sim);
      const east1 = point(sim.width,row+1,z(corners[row+1][sim.width]),sim);
      quad(skirt, west1, west0, point(0,row,bottom,sim), point(0,row+1,bottom,sim), side);
      quad(skirt, east0, east1, point(sim.width,row+1,bottom,sim), point(sim.width,row,bottom,sim), side);
    }
    return {
      terrain: new Float32Array(terrain), skirt: new Float32Array(skirt),
      contours: new Float32Array(contours), grid: new Float32Array(grid),
      maximumExtent: new Float32Array(maximumExtent),
      minimum, maximum, corners, scale,
    };
  }

  function terrainElevationAt(sim, lon, lat) {
    const col = Math.max(0, Math.min(sim.width - 1, Math.floor((lon - sim.terrain.west) / sim.terrain.lon_step)));
    const row = Math.max(0, Math.min(sim.height - 1, Math.floor((sim.terrain.north - lat) / sim.terrain.lat_step)));
    return sim.elevation_m[row * sim.width + col];
  }

  function surfaceVertex(sim, lon, lat, lift=0.08) {
    const col = (lon - sim.terrain.west) / sim.terrain.lon_step;
    const row = (sim.terrain.north - lat) / sim.terrain.lat_step;
    if (col < 0 || row < 0 || col > sim.width || row > sim.height) return null;
    const elevation = terrainElevationAt(sim, lon, lat);
    const z = (elevation - geometry.minimum) * geometry.scale + lift;
    return point(col, row, z, sim);
  }

  function appendMappedLine(out, sim, coordinates, color, lift=0.08) {
    if (!Array.isArray(coordinates)) return;
    for (let index = 0; index + 1 < coordinates.length; index++) {
      const a = surfaceVertex(sim, coordinates[index][0], coordinates[index][1], lift);
      const b = surfaceVertex(sim, coordinates[index + 1][0], coordinates[index + 1][1], lift);
      if (a && b) line(out, a, b, color);
    }
  }

  function buildMapContext(sim) {
    const context = activeContext();
    const roads = [], waterways = [], routeBase = [], routeSegments = [];
    for (const road of context?.roads || []) {
      const major = ['primary','secondary','trunk','motorway'].includes(road.kind);
      appendMappedLine(roads, sim, road.coordinates,
        major ? [1.0,0.79,0.31,0.94] : [0.96,0.97,0.89,0.70], major ? 0.14 : 0.10);
    }
    for (const waterway of context?.waterways || []) {
      appendMappedLine(waterways, sim, waterway.coordinates, [0.18,0.76,0.98,0.94], 0.16);
    }
    const nodes = [...(context?.cascade_nodes || [])].sort((a,b)=>(a.order||0)-(b.order||0));
    for (let index = 0; index + 1 < nodes.length; index++) {
      const coordinates = [[nodes[index].lon,nodes[index].lat],[nodes[index+1].lon,nodes[index+1].lat]];
      appendMappedLine(routeBase, sim, coordinates, [0.10,0.17,0.18,0.55], 0.30);
      const segment = [];
      appendMappedLine(segment, sim, coordinates, [1.0,0.42,0.13,1.0], 0.34);
      routeSegments.push(new Float32Array(segment));
    }
    geometry.roads = new Float32Array(roads);
    geometry.waterways = new Float32Array(waterways);
    geometry.routeBase = new Float32Array(routeBase);
    geometry.routeSegments = routeSegments;
  }

  function buildStructures(sim) {
    const out = [];
    if (sim.is_regional_context) return new Float32Array(out);
    const collection = result?.spatial_context?.structures;
    if (!collection?.structures?.length) return new Float32Array(out);
    for (const structure of collection.structures) {
      const ring = structure.coordinates || [];
      if (ring.length < 3) continue;
      const base = ring.map(([lon,lat]) => {
        const x = (lon - sim.terrain.west) / sim.terrain.lon_step;
        const y = (sim.terrain.north - lat) / sim.terrain.lat_step;
        const ground = (terrainElevationAt(sim, lon, lat) - geometry.minimum) * geometry.scale + 0.04;
        return point(x, y, ground, sim);
      });
      const displayedHeight = Math.max(0.22, structure.height_m * geometry.scale);
      const top = base.map(vertex => [vertex[0], vertex[1], vertex[2] + displayedHeight]);
      const mapped = structure.height_basis !== 'estimated_from_type';
      const wall = mapped ? [0.69,0.54,0.36,0.96] : [0.55,0.52,0.46,0.90];
      const roof = mapped ? [0.94,0.80,0.57,0.98] : [0.77,0.72,0.63,0.94];
      for (let i = 1; i < top.length - 1; i++) triangle(out, top[0], top[i], top[i+1], roof);
      for (let i = 0; i < base.length; i++) {
        const next = (i + 1) % base.length;
        quad(out, base[i], base[next], top[next], top[i], wall);
      }
    }
    return new Float32Array(out);
  }

  function waterColour(depth) {
    const shallow = [0.46, 0.83, 0.88, 0.86];
    const middle = [0.10, 0.58, 0.80, 0.88];
    const deep = [0.03, 0.31, 0.67, 0.91];
    if (depth < 0.5) return mix(shallow, middle, Math.min(1, depth / 0.5));
    return mix(middle, deep, Math.min(1, (depth - 0.5) / 3.5));
  }

  function buildWater(sim, frame) {
    const out = [];
    if (sim.is_regional_context) return new Float32Array(out);
    const depthGrid = frame.depth_m;
    const scale = geometry.scale;
    const min = geometry.minimum;
    const dry = (r,c) => r < 0 || r >= sim.height || c < 0 || c >= sim.width ||
      depthGrid[r * sim.width + c] < 0.1;
    const cornerDepth = (row,col) => {
      let total=0, count=0;
      for (let rr=Math.max(0,row-1); rr<=Math.min(sim.height-1,row); rr++) {
        for (let cc=Math.max(0,col-1); cc<=Math.min(sim.width-1,col); cc++) {
          const value=depthGrid[rr*sim.width+cc];
          if (value>=0.03) { total+=value; count++; }
        }
      }
      return count ? total/count : 0;
    };
    for (let row = 0; row < sim.height; row++) {
      for (let col = 0; col < sim.width; col++) {
        const index = row * sim.width + col;
        const depth = depthGrid[index];
        if (depth < 0.1) continue;
        const color = waterColour(depth);
        const a = point(col,row,(geometry.corners[row][col]+cornerDepth(row,col)-min)*scale+0.035,sim);
        const b = point(col+1,row,(geometry.corners[row][col+1]+cornerDepth(row,col+1)-min)*scale+0.035,sim);
        const c = point(col+1,row+1,(geometry.corners[row+1][col+1]+cornerDepth(row+1,col+1)-min)*scale+0.035,sim);
        const d = point(col,row+1,(geometry.corners[row+1][col]+cornerDepth(row+1,col)-min)*scale+0.035,sim);
        quad(out,a,b,c,d,color);
        const edge = [color[0]*0.67,color[1]*0.72,color[2]*0.85,0.89];
        if (dry(row-1,col)) quad(out,b,a,point(col,row,(geometry.corners[row][col]-min)*scale,sim),
          point(col+1,row,(geometry.corners[row][col+1]-min)*scale,sim),edge);
        if (dry(row,col+1)) quad(out,c,b,point(col+1,row,(geometry.corners[row][col+1]-min)*scale,sim),
          point(col+1,row+1,(geometry.corners[row+1][col+1]-min)*scale,sim),edge);
        if (dry(row+1,col)) quad(out,d,c,point(col+1,row+1,(geometry.corners[row+1][col+1]-min)*scale,sim),
          point(col,row+1,(geometry.corners[row+1][col]-min)*scale,sim),edge);
        if (dry(row,col-1)) quad(out,a,d,point(col,row+1,(geometry.corners[row+1][col]-min)*scale,sim),
          point(col,row,(geometry.corners[row][col]-min)*scale,sim),edge);
      }
    }
    return new Float32Array(out);
  }

  function drawLayer(vertices, primitive, transparent=false, textured=false) {
    if (!vertices.length) return;
    const useTexture = textured && showSatellite.checked && satelliteTextureUrl === activeSatellite(active())?.url;
    gl.uniform1f(uniform.useTexture, useTexture ? 1 : 0);
    if (useTexture) {
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, satelliteTexture);
    }
    if (transparent) {
      gl.enable(gl.BLEND);
      gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
      gl.depthMask(false);
    }
    gl.bufferData(gl.ARRAY_BUFFER, vertices, gl.DYNAMIC_DRAW);
    gl.drawArrays(primitive, 0, vertices.length / 9);
    if (transparent) { gl.depthMask(true); gl.disable(gl.BLEND); }
    gl.uniform1f(uniform.useTexture, 0);
  }

  function updateStats(sim, frame) {
    if (sim.is_regional_context) {
      const context = activeContext();
      const nodes = [...(context?.cascade_nodes || [])].sort((a,b)=>(a.order||0)-(b.order||0));
      const currentNode = nodes[Math.min(frame.route_progress || 0, Math.max(0,nodes.length-1))];
      clock.textContent = `t = ${(frame.time_s / 3600).toFixed(1)} h`;
      slider.value = String(frameIndex);
      stats.innerHTML = `<div><span>Current cascade stop</span><strong>${currentNode?.name || 'Tehri Dam'}</strong></div>` +
        `<div><span>Elevation · m AMSL</span><strong>${geometry.minimum.toFixed(0)}–${geometry.maximum.toFixed(0)} m</strong></div>` +
        `<div><span>Context grid · cells</span><strong>${sim.width} × ${sim.height}</strong></div>` +
        `<div><span>Cell size · m</span><strong>${sim.cell_size_m.toFixed(0)} m × ${sim.cell_size_m.toFixed(0)} m</strong></div>`;
      exaggerationValue.textContent = `${exaggeration.value}×`;
      return;
    }
    const wet = frame.depth_m.filter(value => value >= 0.1).length;
    const peak = Math.max(...frame.depth_m);
    let frontRow=-1;
    frame.depth_m.forEach((value,index)=>{if(value>=0.1)frontRow=Math.max(frontRow,Math.floor(index/sim.width));});
    const reach=frontRow<0?0:Math.round(frontRow/Math.max(1,sim.height-1)*100);
    clock.textContent = `t = ${(frame.time_s/60).toFixed(frame.time_s%60?1:0)} min`;
    slider.value = String(frameIndex);
    stats.innerHTML = `<div><span>Wet cells now</span><strong>${wet} / ${sim.width * sim.height}</strong></div>` +
      `<div><span>Peak depth · m</span><strong>${peak.toFixed(2)} m</strong></div>` +
      `<div><span>Downstream progress · %</span><strong>${reach}%${reach===100?' · outlet':''}</strong></div>` +
      `<div><span>Volume-balance error · m³</span><strong>${sim.volume.mass_balance_error_m3.toFixed(2)} m³</strong></div>`;
    exaggerationValue.textContent = `${exaggeration.value}×`;
  }

  function rebuildLabels(sim) {
    labelLayer.textContent = '';
    labelEntries = [];
    const context = activeContext();
    let candidates = [];
    if (sim.is_regional_context) {
      const cascade = (context?.cascade_nodes || []).map(item=>({...item,labelType:'cascade'}));
      const cascadeNames = new Set(cascade.map(item=>item.name.toLowerCase().split(' ')[0]));
      const towns = (context?.places || []).filter(item=>item.kind==='town' && !cascadeNames.has(item.name.toLowerCase().split(' ')[0]));
      const villages = (context?.places || []).filter(item=>item.kind==='village').filter((_,index)=>index%10===0).slice(0,9);
      candidates = [...cascade,...towns,...villages];
    } else {
      candidates = (context?.labels || []).slice(0,24);
    }
    for (const item of candidates) {
      if (!Number.isFinite(item.lon) || !Number.isFinite(item.lat) || !item.name) continue;
      const element = document.createElement('span');
      const type = item.labelType === 'cascade' ? 'cascade' : (item.kind || 'place');
      element.className = `terrain-label terrain-label-${String(type).replace(/[^a-z0-9_-]/gi,'').toLowerCase()}`;
      element.textContent = item.name;
      labelLayer.appendChild(element);
      labelEntries.push({item,element});
    }
  }

  function updateLabels(sim, frame) {
    if (!showLabels.checked) { labelLayer.classList.add('hidden'); return; }
    labelLayer.classList.remove('hidden');
    const rect = canvas.getBoundingClientRect();
    const cp=Math.cos(pitch), sp=Math.sin(pitch), cy=Math.cos(yaw), sy=Math.sin(yaw);
    const centerZ=(geometry.maximum-geometry.minimum)*geometry.scale/2;
    for (const entry of labelEntries) {
      const vertex=surfaceVertex(sim,entry.item.lon,entry.item.lat,0.42);
      if (!vertex) { entry.element.style.display='none'; continue; }
      const rx=cy*vertex[0]-sy*vertex[1];
      const ry=sy*vertex[0]+cy*vertex[1];
      const pz=vertex[2]-centerZ;
      const x=(rx/zoom+1)*rect.width/2;
      const y=(1+(ry*cp-pz*sp)/zoom)*rect.height/2;
      const visible=x>18 && x<rect.width-18 && y>18 && y<rect.height-12;
      entry.element.style.display=visible?'block':'none';
      entry.element.style.left=`${x}px`;
      entry.element.style.top=`${y}px`;
      entry.element.classList.toggle('reached',entry.item.labelType==='cascade' && (entry.item.order||0)<=(frame.route_progress||0));
    }
  }

  function draw() {
    const sim = active();
    if (!sim || !program || !geometry) return;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    const w = Math.max(1, Math.round(canvas.clientWidth * ratio));
    const h = Math.max(1, Math.round(canvas.clientHeight * ratio));
    if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
    gl.viewport(0, 0, w, h);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.useProgram(program);
    gl.uniform1f(uniform.yaw, yaw);
    gl.uniform1f(uniform.pitch, pitch);
    gl.uniform1f(uniform.zoom, zoom);
    gl.uniform1f(uniform.heightCenter, (geometry.maximum - geometry.minimum) * geometry.scale / 2);
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    drawLayer(geometry.skirt, gl.TRIANGLES);
    drawLayer(geometry.terrain, gl.TRIANGLES, false, true);
    drawLayer(geometry.contours, gl.LINES, true);
    if (showWireframe.checked) drawLayer(geometry.grid, gl.LINES, true);
    if (showRoads.checked) {
      drawLayer(geometry.waterways || new Float32Array(), gl.LINES, true);
      drawLayer(geometry.roads || new Float32Array(), gl.LINES, true);
    }
    if (sim.is_regional_context) {
      drawLayer(geometry.routeBase || new Float32Array(), gl.LINES, true);
      const progress=sim.frames[frameIndex].route_progress || 0;
      for (let index=0; index<progress; index++) drawLayer(geometry.routeSegments?.[index] || new Float32Array(),gl.LINES,true);
    }
    if (showStructures.checked) drawLayer(geometry.structures || new Float32Array(), gl.TRIANGLES);
    if (showMaximum.checked) drawLayer(geometry.maximumExtent, gl.LINES, true);
    const frame = sim.frames[frameIndex];
    drawLayer(buildWater(sim, frame), gl.TRIANGLES, true);
    updateStats(sim, frame);
    updateLabels(sim,frame);
    const northAngle = Math.atan2(Math.sin(yaw), Math.cos(yaw) * Math.cos(pitch)) * 180 / Math.PI;
    compass.querySelector('i').style.transform = `rotate(${northAngle}deg)`;
  }

  function updateProbe(event) {
    const sim = active();
    if (!sim || !geometry || drag) { probe.classList.add('hidden'); return; }
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left, y = event.clientY - rect.top;
    const cp = Math.cos(pitch), sp = Math.sin(pitch), cy = Math.cos(yaw), sy = Math.sin(yaw);
    const centerZ = (geometry.maximum - geometry.minimum) * geometry.scale / 2;
    let nearest = null, best = 22 * 22;
    for (let row = 0; row < sim.height; row++) {
      for (let col = 0; col < sim.width; col++) {
        const index = row * sim.width + col;
        const px = col + 0.5 - sim.width / 2;
        const py = row + 0.5 - sim.height / 2;
        const pz = (sim.elevation_m[index] - geometry.minimum + sim.frames[frameIndex].depth_m[index]) * geometry.scale - centerZ;
        const rx = cy * px - sy * py;
        const ry = sy * px + cy * py;
        const sx = (rx / zoom + 1) * rect.width / 2;
        const screenY = ry * cp - pz * sp;
        const syPixels = (1 + screenY / zoom) * rect.height / 2;
        const distance = (sx - x) ** 2 + (syPixels - y) ** 2;
        if (distance < best) { best = distance; nearest = {row,col,index}; }
      }
    }
    if (!nearest) { probe.classList.add('hidden'); return; }
    const {row,col,index} = nearest;
    const lon = sim.terrain.west + (col + 0.5) * sim.terrain.lon_step;
    const lat = sim.terrain.north - (row + 0.5) * sim.terrain.lat_step;
    probe.textContent = `Cell ${row}, ${col} · Ground ${sim.elevation_m[index].toFixed(1)} m AMSL · Water depth ${sim.frames[frameIndex].depth_m[index].toFixed(2)} m · ${lat.toFixed(4)}°N, ${lon.toFixed(4)}°E`;
    probe.style.left = `${Math.max(8, Math.min(x + 14, rect.width - 230))}px`;
    probe.style.top = `${Math.max(8, Math.min(y + 14, rect.height - 70))}px`;
    probe.classList.remove('hidden');
  }

  function stop() { if (timer) clearInterval(timer); timer = null; playButton.textContent = 'Play'; }
  function peakFrame() {
    stop();
    const sim = active();
    if (!sim) return;
    if (sim.is_regional_context) {
      frameIndex=sim.frames.length-1;
      draw();
      return;
    }
    frameIndex = sim.frames.reduce((best, frame, index) => {
      const wet = frame.depth_m.filter(value => value >= 0.1).length;
      const peak = Math.max(...frame.depth_m);
      const bestFrame = sim.frames[best];
      const bestWet = bestFrame.depth_m.filter(value => value >= 0.1).length;
      const bestPeak = Math.max(...bestFrame.depth_m);
      return wet > bestWet || (wet === bestWet && peak > bestPeak) ? index : best;
    }, 0);
    draw();
  }
  function selectBranch() {
    stop();
    const sim = active();
    if (!sim) return;
    frameIndex = 0;
    slider.max = String(sim.frames.length - 1);
    slider.value = '0';
    slider.disabled = false;
    playButton.disabled = false;
    peakButton.disabled = false;
    peakButton.textContent = sim.is_regional_context ? 'Final stop' : 'Peak frame';
    yaw = sim.is_regional_context ? -0.30 : -0.55;
    pitch = sim.is_regional_context ? 0.62 : 0.72;
    zoom = sim.is_regional_context ? 61 : 22;
    geometry = buildGeometry(sim);
    geometry.structures = buildStructures(sim);
    buildMapContext(sim);
    rebuildLabels(sim);
    loadSatellite(sim);
    showStructures.disabled = sim.is_regional_context;
    showMaximum.disabled = sim.is_regional_context;
    scaleLabel.textContent = `Grid ≈ ${sim.cell_size_m.toFixed(0)} m × ${sim.cell_size_m.toFixed(0)} m per cell`;
    const structures = result?.spatial_context?.structures;
    const structureNote = structures?.structures?.length ? `${structures.structures.length} mapped OSM footprints; heights may be estimated.` : 'No mapped structures cached.';
    if (sim.is_regional_context) {
      overlay.textContent = `REGIONAL RESERVOIR CORRIDOR · Tehri Reservoir → Koteshwar → Devprayag → Rishikesh · ${exaggeration.value}× vertical display.`;
      const satellite=activeSatellite(sim);
      const context=activeContext();
      attribution.textContent = `Terrain: ${sim.terrain.source}. Imagery: ${satellite.attribution} (${satellite.license}). Roads, rivers and place names: ${context.source} (${context.license}). The orange cascade link is schematic between verified nodes; this regional view is context, not a continuous hydraulic solve.`;
    } else if (structures?.structures?.length) {
      const outletNote=sim.downstream_reached?` Downstream outlet reached after ${(sim.downstream_arrival_s/60).toFixed(1)} min.`:' Downstream outlet not reached in this run.';
      overlay.textContent = `${result.mode === 'offline_demo' ? 'SYNTHETIC WATER INPUT · ' : ''}Mapped Ganges corridor on sampled terrain; ${structureNote} ${sim.time_steps} numerical steps.${outletNote} ${exaggeration.value}× vertical display.`;
      const mappedHeights = structures.structures.filter(item => item.height_basis !== 'estimated_from_type').length;
      const failed = structures.tile_grid?.failed_tiles?.length || 0;
      const satellite=activeSatellite(sim);
      const context=activeContext();
      attribution.textContent = `Terrain: ${sim.terrain.source}. Imagery: ${satellite?.attribution || 'not loaded'} (${satellite?.license || 'source metadata unavailable'}). Roads: ${context?.roads_source || 'OpenStreetMap contributors'} (${context?.roads_license || 'ODbL'}). Structures: ${structures.source} (${structures.license}). ${structures.structures.length} retained footprints; ${mappedHeights} use mapped height/levels and the rest use display-only estimates.${failed ? ` ${failed} source tile(s) failed and are recorded in the cache metadata.` : ''}`;
    } else {
      overlay.textContent = `${result.mode === 'offline_demo' ? 'SYNTHETIC WATER INPUT · ' : ''}Real sampled terrain; ${structureNote} ${sim.time_steps} numerical steps. ${exaggeration.value}× vertical display.`;
      attribution.textContent = `Terrain: ${sim.terrain.source}. No mapped structure cache is loaded.`;
    }
    draw();
  }
  function play() {
    if (timer) { stop(); return; }
    if (!active()) return;
    if (frameIndex >= active().frames.length - 1) frameIndex = 0;
    playButton.textContent = 'Pause';
    timer = setInterval(() => {
      frameIndex++;
      if (frameIndex >= active().frames.length) { frameIndex=active().frames.length-1; stop(); draw(); return; }
      draw();
    }, 550);
  }

  branchSelect.addEventListener('change', selectBranch);
  domainSelect.addEventListener('change', () => { selectBranch(); play(); });
  slider.addEventListener('input', () => { stop(); frameIndex = Number(slider.value); draw(); });
  playButton.addEventListener('click', play);
  peakButton.addEventListener('click', peakFrame);
  document.getElementById('simulationOblique').addEventListener('click', () => { const regional=active()?.is_regional_context; yaw=regional?-0.30:-0.55; pitch=regional?0.62:0.72; zoom=regional?61:22; draw(); });
  document.getElementById('simulationTop').addEventListener('click', () => { const regional=active()?.is_regional_context; yaw=0; pitch=0; zoom=regional?55:22; draw(); });
  exaggeration.addEventListener('input', () => {
    exaggerationValue.textContent = `${exaggeration.value}×`;
    if (active()) { geometry = buildGeometry(active()); geometry.structures = buildStructures(active()); buildMapContext(active()); draw(); }
  });
  showSatellite.addEventListener('change', draw);
  showRoads.addEventListener('change', draw);
  showLabels.addEventListener('change', draw);
  showMaximum.addEventListener('change', draw);
  showStructures.addEventListener('change', draw);
  showWireframe.addEventListener('change', draw);
  canvas.addEventListener('pointerdown', event => { drag={x:event.clientX,y:event.clientY}; canvas.setPointerCapture(event.pointerId); probe.classList.add('hidden'); });
  canvas.addEventListener('pointermove', event => {
    if (!drag) { updateProbe(event); return; }
    yaw += (event.clientX - drag.x) * 0.008;
    pitch = Math.max(0, Math.min(1.42, pitch + (event.clientY - drag.y) * 0.006));
    drag = {x:event.clientX,y:event.clientY};
    draw();
  });
  canvas.addEventListener('pointerup', () => { drag = null; });
  canvas.addEventListener('pointercancel', () => { drag = null; });
  canvas.addEventListener('pointerleave', () => probe.classList.add('hidden'));
  canvas.addEventListener('wheel', event => { event.preventDefault(); const regional=active()?.is_regional_context; zoom=Math.max(regional?34:16,Math.min(regional?105:55,zoom*(event.deltaY>0?1.08:0.92))); draw(); }, {passive:false});
  canvas.addEventListener('keydown', event => {
    if (!active()) return;
    if (event.key === ' ' || event.key === 'Enter') { event.preventDefault(); play(); }
    if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
      event.preventDefault(); stop();
      frameIndex = Math.max(0, Math.min(active().frames.length - 1, frameIndex + (event.key === 'ArrowRight' ? 1 : -1)));
      draw();
    }
  });
  window.addEventListener('resize', draw);

  window.Simulation3D = {
    load(scenario) { result=scenario; selectBranch(); play(); },
    clear() { stop(); result=null; geometry=null; labelEntries=[]; labelLayer.textContent=''; slider.disabled=true; playButton.disabled=true; peakButton.disabled=true; stats.textContent=''; probe.classList.add('hidden'); overlay.textContent='Run a scenario to generate depth frames.'; },
  };
})();
