// Regenerates land.b64: a Fibonacci lattice over the sphere, keeping only points that
// fall on land (Natural Earth 110m via world-atlas). Output is int16 pairs of
// (lon × 100, lat × 100), base64-encoded, so the preview page carries its own geometry.
//
//   npm i --no-save world-atlas@2 topojson-client@3 && node make_land.mjs
import { writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { feature } from "topojson-client";

const require = createRequire(import.meta.url);
const topo = require("world-atlas/land-110m.json");
const land = feature(topo, topo.objects.land);

const rings = [];
for (const f of land.features) {
  const g = f.geometry;
  const polys = g.type === "Polygon" ? [g.coordinates] : g.coordinates;
  for (const p of polys) for (const r of p) rings.push(r);
}

// Even-odd ray cast in lon/lat. Good enough at 110m resolution away from the poles.
function onLand(lon, lat) {
  let inside = false;
  for (const r of rings) {
    for (let i = 0, j = r.length - 1; i < r.length; j = i++) {
      const [xi, yi] = r[i], [xj, yj] = r[j];
      if ((yi > lat) !== (yj > lat) && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside;
    }
  }
  return inside;
}

const N = 42000, golden = Math.PI * (3 - Math.sqrt(5));
const out = [];
for (let i = 0; i < N; i++) {
  const y = 1 - (2 * (i + 0.5)) / N, r = Math.sqrt(1 - y * y), t = i * golden;
  const lat = (Math.asin(y) * 180) / Math.PI, lon = (Math.atan2(r * Math.sin(t), r * Math.cos(t)) * 180) / Math.PI;
  if (lat < -84) continue; // Antarctica's interior would just be a white disc
  if (onLand(lon, lat)) out.push(Math.round(lon * 100), Math.round(lat * 100));
}
writeFileSync(new URL("./land.b64", import.meta.url), Buffer.from(new Int16Array(out).buffer).toString("base64"));
console.log(`${out.length / 2} land points`);
