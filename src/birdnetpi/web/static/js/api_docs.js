/**
 * API Documentation JavaScript - Swagger UI initialization
 */

// Initialize Swagger UI on page load
window.onload = function () {
  const swaggerContainer = document.getElementById("swagger-ui");
  if (!swaggerContainer) return;

  // Get OpenAPI URL from data attribute
  const openApiUrl = swaggerContainer.dataset.openapiUrl;
  if (!openApiUrl) {
    console.error("OpenAPI URL not found in data attribute");
    return;
  }

  const ui = SwaggerUIBundle({
    url: openApiUrl,
    dom_id: "#swagger-ui",
    deepLinking: true,
    presets: [SwaggerUIBundle.presets.apis, SwaggerUIStandalonePreset],
    plugins: [SwaggerUIBundle.plugins.DownloadUrl],
    layout: "BaseLayout",
    // Disable the "Try it out" functionality if needed
    // tryItOutEnabled: false,
    // Show operation IDs
    displayOperationId: false,
    // Show request duration
    displayRequestDuration: true,
    // Default models expansion
    docExpansion: "list",
    // Default model expansion
    defaultModelsExpandDepth: 1,
    // Default model rendering
    defaultModelRendering: "example",
    // Show common extensions
    showCommonExtensions: true,
    // Show extensions
    showExtensions: true,
    // Filter
    filter: true,
    // Validation
    validatorUrl: null,
  });

  window.ui = ui;
};
