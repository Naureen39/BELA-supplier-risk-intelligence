// Converts the US Census cartographic boundary states (distributed as us-atlas TopoJSON) to GeoJSON
// bundled with the site, so maps need no tiles and no network access at run time.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { feature } from "topojson-client";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const topo = JSON.parse(readFileSync(join(root, "node_modules/us-atlas/states-10m.json"), "utf8"));
const fc = feature(topo, topo.objects.states);
// The map shows the contiguous states and DC. Alaska, Hawaii, and territories stretch a longitude and
// latitude layout across the whole globe, so events there appear in the table view only.
const skip = new Set([
  "Alaska",
  "Hawaii",
  "Puerto Rico",
  "Guam",
  "American Samoa",
  "Northern Mariana Islands",
  "United States Virgin Islands",
]);
fc.features = fc.features
  .filter((f) => !skip.has(f.properties.name))
  .map((f) => ({ type: "Feature", properties: { name: f.properties.name }, geometry: f.geometry }));
mkdirSync(join(root, "public/geo"), { recursive: true });
writeFileSync(join(root, "public/geo/us-states.json"), JSON.stringify(fc));
console.log(`${fc.features.length} states written`);
