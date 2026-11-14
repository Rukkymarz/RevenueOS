/** Typed client for the RevenueOS API. Every response is validated against packages/contracts. */
import { HealthResponse, ProbeRequest, ProbeResponse, type HealthResponse as Health, type ProbeResponse as Probe } from "@revenueos/contracts";

export class RevenueOSClient {
  constructor(private readonly baseUrl: string, private readonly fetchImpl: typeof fetch = fetch) {}

  private async json(path: string, init?: RequestInit): Promise<unknown> {
    const res = await this.fetchImpl(new URL(path, this.baseUrl), init);
    const body = await res.json();
    if (!res.ok && res.status !== 503) throw new Error(`${init?.method ?? "GET"} ${path} -> ${res.status}`);
    return body;
  }

  async health(): Promise<Health> {
    return HealthResponse.parse(await this.json("/health"));
  }

  async probe(req: { task_id: string; agent_id: string; message: string }): Promise<Probe> {
    const body = ProbeRequest.parse(req);
    return ProbeResponse.parse(await this.json("/v1/probe", {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
    }));
  }
}
