import exec from "k6/execution";
import http from "k6/http";
import { check, sleep } from "k6";
import { Counter } from "k6/metrics";

const failedRequests = new Counter("lv3_failed_requests");
const successfulRequests = new Counter("lv3_successful_requests");

function loadConfig() {
  const configPath = __ENV.LV3_K6_CONFIG_PATH;
  if (!configPath) {
    throw new Error("LV3_K6_CONFIG_PATH is required");
  }
  return JSON.parse(open(configPath));
}

const config = loadConfig();

function buildThresholds() {
  const thresholds = {};
  for (const service of config.services) {
    const selector = `{service_id:${service.service_id}}`;
    thresholds[`checks${selector}`] = ["rate>0.99"];
    thresholds[`http_req_failed${selector}`] = [`rate<=${service.max_error_rate}`];
    if (service.latency_threshold_ms !== null) {
      thresholds[`http_req_duration${selector}`] = [`p(95)<=${service.latency_threshold_ms}`];
    }
  }
  return thresholds;
}

function buildScenario(service) {
  if (service.scenario_type === "load") {
    return {
      executor: "ramping-vus",
      exec: "probe",
      startVUs: 1,
      gracefulRampDown: "15s",
      stages: [
        { duration: service.ramp_up_duration, target: service.vus },
        { duration: service.hold_duration, target: service.vus },
        { duration: "30s", target: 0 },
      ],
      env: {
        LV3_K6_SERVICE_ID: service.service_id,
      },
      tags: {
        service_id: service.service_id,
        scenario_type: service.scenario_type,
      },
    };
  }
  return {
    executor: "constant-vus",
    exec: "probe",
    vus: service.vus,
    duration: service.duration,
    env: {
      LV3_K6_SERVICE_ID: service.service_id,
    },
    tags: {
      service_id: service.service_id,
      scenario_type: service.scenario_type,
    },
  };
}

export const options = {
  thresholds: buildThresholds(),
  scenarios: Object.fromEntries(
    config.services.map((service) => [`${service.scenario_type}_${service.service_id}`, buildScenario(service)])
  ),
  noConnectionReuse: false,
  userAgent: "lv3-k6-slo-probe/1.0",
};

function currentService() {
  const serviceId = __ENV.LV3_K6_SERVICE_ID || exec.vu.tags.service_id;
  const service = config.services.find((item) => item.service_id === serviceId);
  if (!service) {
    throw new Error(`Unknown service_id ${serviceId}`);
  }
  return service;
}

export function probe() {
  const service = currentService();
  const tags = {
    service_id: service.service_id,
    scenario_type: service.scenario_type,
  };
  const params = {
    headers: service.headers || {},
    redirects: service.follow_redirects ? 10 : 0,
    tags,
    timeout: `${service.request_timeout_seconds}s`,
  };
  const response = http.request(service.method, service.target_url, service.body || null, params);
  const passed = check(response, {
    [`${service.service_id} expected status`]: (value) => service.expected_status.includes(value.status),
  });
  if (passed) {
    successfulRequests.add(1, tags);
  } else {
    failedRequests.add(1, tags);
  }
  sleep(service.think_time_seconds);
}
