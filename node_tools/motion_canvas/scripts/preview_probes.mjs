const routes = ['/', '/src/main.ts', '/src/project.ts'];

/** Fetch Vite's document and Motion Canvas entry modules for diagnostics. */
export const probePreviewResources = async (baseUrl, fetchImpl = fetch) => Promise.all(
  routes.map(async route => {
    const url = `${baseUrl}${route}`;
    try {
      const response = await fetchImpl(url, {signal: AbortSignal.timeout(1000)});
      return {
        path: route,
        status: response.status,
        response_text: (await response.text()).slice(0, 500),
      };
    } catch (error) {
      return {
        path: route,
        error: error instanceof Error ? error.message : String(error),
      };
    }
  }),
);
