const routes = ['/', '/src/main.ts', '/src/project.ts', '/public/motion_input.json'];

/** Fetch Vite's document and Motion Canvas entry modules for diagnostics. */
export const probePreviewResources = async (baseUrl, fetchImpl = fetch) => Promise.all(
  routes.map(async route => {
    const url = `${baseUrl}${route}`;
    try {
      const response = await fetchImpl(url, {signal: AbortSignal.timeout(1000)});
      return {
        url,
        status: response.status,
        content_type: response.headers.get('content-type'),
        body: (await response.text()).slice(0, 200),
      };
    } catch (error) {
      return {
        url,
        error: error instanceof Error ? error.message : String(error),
      };
    }
  }),
);
