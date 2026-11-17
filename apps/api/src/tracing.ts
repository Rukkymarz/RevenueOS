/**
 * OpenTelemetry for the API. Imported first in main.ts so inbound HTTP is
 * instrumented; outbound calls inject trace context explicitly (see app.module.ts).
 */
import { NodeSDK } from "@opentelemetry/sdk-node";
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-http";
import { HttpInstrumentation } from "@opentelemetry/instrumentation-http";
import { resourceFromAttributes } from "@opentelemetry/resources";

const endpoint = process.env.OTEL_EXPORTER_OTLP_ENDPOINT;
export const sdk = endpoint
  ? new NodeSDK({
      resource: resourceFromAttributes({ "service.name": "api" }),
      traceExporter: new OTLPTraceExporter({ url: `${endpoint.replace(/\/$/, "")}/v1/traces` }),
      instrumentations: [new HttpInstrumentation()],
    })
  : undefined;
sdk?.start();
