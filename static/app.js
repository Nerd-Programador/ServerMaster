const els = {
  cpu: document.getElementById('cpu'),
  memory: document.getElementById('memory'),
  temp: document.getElementById('temp'),
  network: document.getElementById('network'),
  uptime: document.getElementById('uptime'),
  networkHistory: document.getElementById('network-history'),
  serviceStatus: document.getElementById('service-status'),
  nasCards: document.getElementById('nas-cards'),
  iotCards: document.getElementById('iot-cards'),
  errorBanner: document.getElementById('error-banner'),
  source: document.getElementById('data-source'),
  updated: document.getElementById('last-updated')
};

function levelClass(percent) {
  if (percent >= 85) return 'level-danger';
  if (percent >= 60) return 'level-warn';
  return 'level-ok';
}

function showError(message) {
  els.errorBanner.textContent = message;
  els.errorBanner.classList.remove('hidden');
}

function clearError() {
  els.errorBanner.classList.add('hidden');
  els.errorBanner.textContent = '';
}

function renderServices(services) {
  els.serviceStatus.innerHTML = '';
  services.forEach((service) => {
    const item = document.createElement('span');
    item.className = `service-pill ${service.online ? 'level-ok' : 'level-danger'}`;
    const latency = service.latency_ms !== null && service.latency_ms !== undefined ? `${service.latency_ms} ms` : 'offline';
    item.textContent = `${service.name}: ${latency}`;
    els.serviceStatus.appendChild(item);
  });
}

function renderNas(disks) {
  els.nasCards.innerHTML = '';
  if (!disks.length) {
    els.nasCards.innerHTML = '<article class="card"><h3>Sem volumes NAS detectados</h3><p>Conecte um disco e atualize.</p></article>';
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

function formatDate(iso) {
  if (!iso) return 'N/D';
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleString('pt-BR');
}

function renderIot(devices) {
  els.iotCards.innerHTML = '';
  if (!devices.length) {
    els.iotCards.innerHTML = '<article class="card"><h3>Nenhuma ESP online ainda</h3><p>Use o script de simulação ou publique no MQTT.</p></article>';
    return;
  }

  devices.forEach((dev) => {
    const card = document.createElement('article');
    card.className = `card ${dev.status === 'online' ? 'level-ok' : 'level-warn'}`;
    card.innerHTML = `
      <h3>${dev.hostname || dev.device_id}</h3>
      <p>ID: ${dev.device_id}</p>
      <p>IP: ${dev.ip_address || 'N/D'}</p>
      <p>Status: ${dev.status || 'desconhecido'}</p>
      <p>Último sinal: ${formatDate(dev.last_seen)}</p>
    `;
    els.iotCards.appendChild(card);
  });
}

async function loadMetrics() {
  try {
    const metricsRes = await fetch('/api/metrics');
    const metrics = await metricsRes.json();

    if (!metricsRes.ok) {
      throw new Error(metrics.hint || metrics.error || 'Falha ao carregar /api/metrics');
    }

    clearError();

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

    els.source.textContent = `Fonte: ${metrics.data_source === 'simulated' ? 'simulada' : 'real'}`;
    els.updated.textContent = `Atualizado: ${new Date().toLocaleTimeString('pt-BR')}`;

    renderServices(metrics.services || []);
    renderNas(metrics.nas || []);

    const iotRes = await fetch('/api/iot-devices');
    const devices = await iotRes.json();
    renderIot(Array.isArray(devices) ? devices : []);
  } catch (error) {
    showError(`Não foi possível carregar os dados. ${error.message}`);
  }
}

loadMetrics();
setInterval(loadMetrics, 5000);
