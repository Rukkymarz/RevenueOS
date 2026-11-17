import "./tracing.js";
import "reflect-metadata";
import { NestFactory } from "@nestjs/core";
import { AppModule } from "./app.module.js";

export async function bootstrap(port = Number(process.env.PORT ?? 3000)) {
  const app = await NestFactory.create(AppModule, { logger: ["error", "warn", "log"] });
  app.enableShutdownHooks();
  await app.listen(port, "0.0.0.0");
  return app;
}

if (require.main === module) {
  void bootstrap();
}
