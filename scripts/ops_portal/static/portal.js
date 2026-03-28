(() => {
  const instances = new Map();

  function initCharts(root = document) {
    if (typeof window.echarts === "undefined") {
      return;
    }

    root.querySelectorAll("[data-echart-target]").forEach((element) => {
      const sourceId = element.dataset.echartTarget;
      if (!sourceId) {
        return;
      }
      const source = document.getElementById(sourceId);
      if (!source) {
        return;
      }

      try {
        const option = JSON.parse(source.textContent || "{}");
        const existing = window.echarts.getInstanceByDom(element);
        if (existing) {
          existing.dispose();
        }
        const chart = window.echarts.init(element, null, { renderer: "canvas" });
        chart.setOption(option, true);
        instances.set(sourceId, chart);
      } catch (error) {
        console.error(`Failed to initialize chart ${sourceId}`, error);
      }
    });
  }

  function resizeCharts() {
    instances.forEach((chart) => chart.resize());
  }

  function connectDeploymentStream() {
    const consoleLog = document.getElementById("deployment-console-log");
    if (!consoleLog || consoleLog.dataset.streamAttached === "true") {
      return;
    }
    consoleLog.dataset.streamAttached = "true";

    const stream = new EventSource("/events/deployments");

    function appendConsoleLine(payload) {
      const timestamp = payload.ts || new Date().toISOString();
      const message = payload.message || JSON.stringify(payload);
      if (consoleLog.textContent.includes("Connecting to deployment stream")) {
        consoleLog.textContent = "";
      }
      consoleLog.textContent += `[${timestamp}] ${message}\n`;
      consoleLog.scrollTop = consoleLog.scrollHeight;
    }

    stream.addEventListener("heartbeat", () => {});
    stream.addEventListener("log", (event) => appendConsoleLine(JSON.parse(event.data)));
    stream.addEventListener("deploy", (event) => appendConsoleLine(JSON.parse(event.data)));
    stream.addEventListener("secret", (event) => appendConsoleLine(JSON.parse(event.data)));
    stream.addEventListener("runbook", (event) => appendConsoleLine(JSON.parse(event.data)));
  }

  document.addEventListener("DOMContentLoaded", () => {
    initCharts(document);
    connectDeploymentStream();
  });

  document.body.addEventListener("htmx:afterSwap", (event) => {
    if (event.target instanceof HTMLElement) {
      initCharts(event.target);
    } else {
      initCharts(document);
    }
    resizeCharts();
  });

  window.addEventListener("resize", resizeCharts);
})();
