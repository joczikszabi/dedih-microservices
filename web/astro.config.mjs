// Static build: `astro build` writes plain HTML, CSS and JS into dist/.
// No server side rendering, so the result can be served by a plain Nginx.
import { defineConfig } from "astro/config";

export default defineConfig({
  output: "static",
});
