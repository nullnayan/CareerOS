// Keep release verification separate from a running local development server.
export default {
  distDir: process.env.CAREEROS_NEXT_DIST_DIR || ".next",
};
