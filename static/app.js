const els = {
  cpu: document.getElementById('cpu'),
  memory: document.getElementById('memory'),
  temp: document.getElementById('temp'),
  network: document.getElementById('network'),
  uptime: document.getElementById('uptime'),
  networkHistory: document.getElementById('network-history'),
  serviceStatus: document.getElementById('service-status'),
  nasCards: document.getElementById('nas-cards'),
  iotCards: document.getElementById('iot-cards')
};

function levelClass(percent) {
  if (percent >= 85) return 'level-danger';
  if (percent >= 60) return 'level-warn';
  return 'level-ok';
}

function renderServices(services) {
  els.serviceStatus.innerHTML = '';
  services.forEach((service) => {
    const item = document.createElement('span');
    item.className = `service-pill ${service.online ? 'level-ok' : 'level-danger'}`;
    const latency = service.latency_ms ? `${service.latency_ms} ms` : 'offline';
    item.textContent = `${service.name}: ${latency}`;
    els.serviceStatus.appendChild(item);
  });
}

function renderNas(disks) {
  els.nasCards.innerHTML = '';
  if (!disks.length) {
    els.nasCards.innerHTML = '<article class="card"><h3>Sem volumes NAS detectados</h3></article>';
    return;
  }

  disks.forEach((disk) => {
    const card = document.createElement('article');
    card.className = `card ${levelClass(disk.percent)}`;
    card.innerHTML = `
      <h3>${disk.device} (${disk.mountpoint})</h3>
      <p>Usado: ${disk.used_h} / ${disk.total_h}</p>
      <p>Livre: ${disk.free_h} (${(100 - disk.percent).toFixed(1)}%)</p>
    `;
    els.nasCards.appendChild(card);
  });
}

function renderIot(devices) {
  els.iotCards.innerHTML = '';
  if (!devices.length) {
    els.iotCards.innerHTML = '<article class="card"><h3>Nenhuma ESP online ainda</h3><p>Aguardando mensagens MQTT...</p></article>';
    return;
  }

  devices.forEach((dev) => {
    const card = document.createElement('article');
    card.className = `card ${dev.status === 'online' ? 'level-ok' : 'level-warn'}`;
    card.innerHTML = `
      <h3>${dev.hostname || dev.device_id}</h3>
      <p>ID: ${dev.device_id}</p>
      <p>IP: ${dev.ip_address || 'N/D'}</p>
      <p>Último sinal: ${new Date(dev.last_seen).toLocaleString('pt-BR')}</p>
    `;
    els.iotCards.appendChild(card);
  });
}

async function loadMetrics() {
  const metricsRes = await fetch('/api/metrics');
  const metrics = await metricsRes.json();

  els.cpu.textContent = `${metrics.system.cpu_percent.toFixed(1)}%`;
  els.memory.textContent = `${metrics.system.memory_percent.toFixed(1)}% (${metrics.system.memory_used}/${metrics.system.memory_total})`;
  els.temp.textContent = `CPU: ${metrics.system.temperature_cpu ?? 'N/D'}°C | GPU: ${metrics.system.temperature_gpu ?? 'N/D'}°C`;
  els.network.textContent = `Mês ${metrics.system.network_current_month}: ↓ ${metrics.system.network_download} | ↑ ${metrics.system.network_upload}`;
  els.uptime.textContent = metrics.system.uptime_human;

  document.getElementById('cpu').closest('.card').className = `card ${levelClass(metrics.system.cpu_percent)}`;
  document.getElementById('memory').closest('.card').className = `card ${levelClass(metrics.system.memory_percent)}`;

  els.networkHistory.innerHTML = '';
  metrics.system.network_history.forEach((month) => {
    const li = document.createElement('li');
    li.textContent = `${month.month} → ↓ ${month.download} | ↑ ${month.upload}`;
    els.networkHistory.appendChild(li);
  });

  renderServices(metrics.services);
  renderNas(metrics.nas);

  const iotRes = await fetch('/api/iot-devices');
  const devices = await iotRes.json();
  renderIot(devices);
}

loadMetrics();
setInterval(loadMetrics, 5000);
